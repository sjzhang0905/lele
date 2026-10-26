#!/usr/bin/env python3
"""Native VTK rendering of molecular structures and scalar volumetric fields.

Used by the PySide6 desktop application. It is not tied to ChemStructConverter.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import numpy as np

# vtkRenderingOpenGL2 must be imported to register OpenGL implementations.
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
import vtkmodules.vtkInteractionStyle  # noqa: F401
from vtkmodules.vtkCommonCore import vtkPoints, vtkUnsignedCharArray, vtkFloatArray
from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray, vtkStructuredGrid
from vtkmodules.vtkFiltersSources import vtkSphereSource, vtkArrowSource, vtkPlaneSource
from vtkmodules.vtkFiltersCore import vtkTubeFilter, vtkContourFilter
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkGlyph3DMapper, vtkRenderer, vtkBillboardTextActor3D, vtkAssembly
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkRenderingFreeType import vtkVectorText

from .core import Frame, Volume, visible_bonds, unit_cell_edges, colour, radius, atom_label_texts, axis_vectors
from .chemical_analysis import detect_hydrogen_bonds
from .periodic_geometry import periodic_basis, normalized_positions
from .style_presets import mix_color


def rgb(hex_color):
    c = hex_color.lstrip('#')
    return tuple(int(c[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def uchar_rgb(hex_color):
    return tuple(int(round(x * 255)) for x in rgb(hex_color))


@dataclass
class RenderOptions:
    style: str = 'Ball and stick'
    atom_palette: str = 'Element'
    bond_palette: str = 'Element'
    surface_finish: str = 'Balanced'
    element_colors: dict[str, str] = field(default_factory=dict)
    atom_scale: float = 0.60
    bond_scale: float = 0.11
    bond_cutoff: float = 1.18
    background: str = '#F7F8FA'
    bonds: bool = True
    hydrogen_bonds: bool = False
    unit_cell: bool = True
    labels: str = 'None'
    label_font: str = 'Arial'
    label_font_file: str = ''
    label_font_size: int = 15
    label_color: str = '#18212F'
    label_bold: bool = True
    axes_position: str = 'Corner'  # Off, Corner (overlay), Origin (0,0,0)
    axes_basis: str = 'XYZ'       # XYZ or abc (requires periodic lattice)
    axes_length: float = 2.5     # Cartesian axis length in Angstrom at origin
    volume_iso: float = 0.035
    volume_opacity: float = 0.65
    show_volume: bool = True


class MoleculeRenderer:
    def __init__(self, renderer: vtkRenderer):
        self.renderer = renderer
        self.options = RenderOptions()
        self.dynamic = []
        self.frame: Frame | None = None
        self.volume: Volume | None = None
        self.selected: list[int] = []
        self.periodic_preview = None
        self.fitted_plane = None
        self.atom_highlights = []
        self._keepalive = []
        self._label_actors = []
        self._label_positions = []
        self._label_radii = []
        # Project labels toward the camera before every draw: at ball centres in
        # screen space, but in front of the ball surface so they stay visible.
        self.renderer.AddObserver('StartEvent', self._place_labels)

    def clear(self):
        for actor in self.dynamic:
            self.renderer.RemoveActor(actor)
        self.dynamic.clear()
        self._keepalive.clear()
        self.atom_highlights.clear()
        self._label_actors.clear()
        self._label_positions.clear()
        self._label_radii.clear()

    def _add_actor(self, actor):
        self.renderer.AddActor(actor)
        self.dynamic.append(actor)
        return actor

    def set_scene(self, frame: Frame, volume: Volume | None = None, reset_camera: bool = False):
        self.frame, self.volume = frame, volume
        self.clear()
        self.renderer.SetBackground(rgb(self.options.background))
        if self.options.style != 'Wireframe':
            self._atoms(frame)
            if self.periodic_preview is not None:
                self._periodic_copy_atoms(frame)
        if self.options.bonds:
            self._bonds(frame)
            if self.periodic_preview is not None:
                self._periodic_fragment_bonds(frame)
        if self.options.hydrogen_bonds:
            self._hydrogen_bonds(frame)
        if self.options.unit_cell:
            if self.periodic_preview is not None and self.periodic_preview.extra_tiles:
                self._periodic_supercell_outline(frame)
            else:
                self._cell(frame)
        if self.options.labels != 'None':
            self._labels(frame)
        if self.options.axes_position == 'Origin':
            self._world_axes(frame)
        if volume is not None and self.options.show_volume:
            self._volume(volume)
        self._highlights()
        if self.fitted_plane is not None:
            self._selection_plane()
        if reset_camera:
            self.renderer.ResetCamera()
            self.renderer.ResetCameraClippingRange()
        self._place_labels()

    def _selection_plane(self):
        """A translucent non-pickable best-fit plane with a thin outline."""
        corners = self.fitted_plane.corners
        source = vtkPlaneSource()
        source.SetOrigin(*corners[0])
        source.SetPoint1(*corners[1])
        source.SetPoint2(*corners[3])
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.PickableOff()
        actor.GetProperty().SetColor(.18, .67, .92)
        actor.GetProperty().SetOpacity(.22)
        actor.GetProperty().LightingOff()
        self._add_actor(actor)
        outline = self._tube_segments([
            (corners[i], corners[(i + 1) % 4], '#2EABEB') for i in range(4)], .012)
        outline.PickableOff()
        self._keepalive.append((source, mapper))

    def _display_color(self, symbol, *, for_bond=False):
        if for_bond and self.options.bond_palette == 'Neutral gray':
            return '#969CA8'
        scheme = self.options.atom_palette
        if scheme == 'Monochrome':
            return '#ABB6C6'
        base = self.options.element_colors.get(symbol, colour(symbol))
        return mix_color(base, .43) if scheme == 'Pastel' else base

    def _finish(self, prop):
        lighting = {
            'Balanced': (.22, .72, .36, 24),
            'Glossy': (.17, .70, .78, 60),
            'Matte': (.32, .67, .05, 9),
        }
        ambient, diffuse, specular, power = lighting.get(
            self.options.surface_finish, lighting['Balanced'])
        prop.SetAmbient(ambient)
        prop.SetDiffuse(diffuse)
        prop.SetSpecular(specular)
        prop.SetSpecularPower(power)

    def _atoms(self, frame):
        groups = defaultdict(list)
        for i, symbol in enumerate(frame.symbols):
            groups[symbol].append(i)
        source = vtkSphereSource()
        source.SetRadius(1.0)
        source.SetThetaResolution(20)
        source.SetPhiResolution(16)
        source.Update()
        self._keepalive.append(source)
        for sym, indices in groups.items():
            pts = vtkPoints()
            sizes = vtkFloatArray()
            sizes.SetName('atom_radius')
            mode = self.options.style
            if mode == 'Space filling':
                ball_size = self._atom_radius(sym)
            elif mode == 'Sticks':
                ball_size = max(0.085, self.options.bond_scale * 1.18)
            else:
                ball_size = max(0.09, radius(sym) * self.options.atom_scale)
            for i in indices:
                pts.InsertNextPoint(*[float(x) for x in frame.positions[i]])
                sizes.InsertNextValue(ball_size)
            pdata = vtkPolyData()
            pdata.SetPoints(pts)
            pdata.GetPointData().AddArray(sizes)
            mapper = vtkGlyph3DMapper()
            mapper.SetInputData(pdata)
            mapper.SetSourceConnection(source.GetOutputPort())
            mapper.SetScaleArray('atom_radius')
            mapper.SetScaleModeToScaleByMagnitude()
            mapper.SetScaleFactor(1.0)
            mapper.ScalingOn()
            mapper.ScalarVisibilityOff()
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(rgb(self._display_color(sym)))
            self._finish(actor.GetProperty())
            self._add_actor(actor)
            self._keepalive.append((pts, pdata, sizes, mapper))

    def _tube_segments(self, segments, tube_radius):
        if not segments:
            return None
        points = vtkPoints()
        lines = vtkCellArray()
        colors = vtkUnsignedCharArray()
        colors.SetName('segment_rgb')
        colors.SetNumberOfComponents(3)
        for p, q, col in segments:
            a = points.InsertNextPoint(*[float(x) for x in p])
            b = points.InsertNextPoint(*[float(x) for x in q])
            lines.InsertNextCell(2)
            lines.InsertCellPoint(a)
            lines.InsertCellPoint(b)
            colors.InsertNextTuple3(*uchar_rgb(col))
            colors.InsertNextTuple3(*uchar_rgb(col))
        geometry = vtkPolyData()
        geometry.SetPoints(points)
        geometry.SetLines(lines)
        geometry.GetPointData().SetScalars(colors)
        tube = vtkTubeFilter()
        tube.SetInputData(geometry)
        tube.SetRadius(max(.008, float(tube_radius)))
        tube.SetNumberOfSides(9)
        tube.CappingOn()
        tube.Update()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(tube.GetOutputPort())
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToDirectScalars()
        actor = vtkActor()
        actor.SetMapper(mapper)
        self._finish(actor.GetProperty())
        self._keepalive.append((points, lines, geometry, tube, mapper, colors))
        return self._add_actor(actor)

    def _bonds(self, frame):
        if self.options.style == 'Space filling':
            return
        segments = []
        for a, b in visible_bonds(frame, self.options.bond_cutoff):
            p, q = frame.positions[a], frame.positions[b]
            m = (p + q) * 0.5
            segments.extend(((p, m, self._display_color(frame.symbols[a], for_bond=True)),
                             (m, q, self._display_color(frame.symbols[b], for_bond=True))))
        width = self.options.bond_scale * (.50 if self.options.style == 'Wireframe' else 1.0)
        self._tube_segments(segments, width)

    def _periodic_copy_atoms(self, frame):
        """Render extra unit-cell replicas; do not change stored coordinates."""
        preview = self.periodic_preview
        cell = periodic_basis(frame)
        if preview is None or cell is None:
            return
        base, _ = normalized_positions(frame)
        for tile in preview.extra_tiles:
            offset = np.asarray(tile, dtype=float) @ cell
            phantom = Frame(list(frame.symbols), base + offset, frame.cell, frame.pbc)
            self._atoms(phantom)
            # Extra cells are visual context; their atoms are not new indices.

    def _periodic_supercell_outline(self, frame):
        """One outer supercell box, with no seam cutting the fragment."""
        preview = self.periodic_preview
        if preview is None:
            return
        minimum = np.asarray(preview.supercell_min, dtype=float)
        extent = np.asarray(preview.supercell_extent, dtype=float)
        origin = minimum @ frame.cell
        enlarged_cell = frame.cell * extent[:, None]
        edges = [(p + origin, q + origin, '#8199B5')
                 for p, q in unit_cell_edges(enlarged_cell)]
        self._tube_segments(edges, .035)

    def _periodic_fragment_bonds(self, frame):
        preview = self.periodic_preview
        if preview is None or self.options.style == 'Space filling':
            return
        segments = []
        for i, j in preview.edges:
            p, q = preview.image_positions[i], preview.image_positions[j]
            midpoint = (p + q) / 2
            segments.extend(((p, midpoint, self._display_color(frame.symbols[i], for_bond=True)),
                             (midpoint, q, self._display_color(frame.symbols[j], for_bond=True))))
        self._tube_segments(segments, self.options.bond_scale * 1.08)

    def _hydrogen_bonds(self, frame):
        """Dashed geometry-only D-H...A proposals; do not affect Ctrl+B."""
        segments = []
        for hb in detect_hydrogen_bonds(frame):
            start, end = hb.hydrogen_pos, hb.acceptor_pos
            # Keep a gap next to covalent donor bond and draw 6 short dashes.
            for k in range(6):
                f0 = 0.11 + k * .145
                f1 = min(f0 + .077, .97)
                segments.append((start + (end-start)*f0,
                                 start + (end-start)*f1, '#23A9C4'))
        self._tube_segments(segments, max(.018, self.options.bond_scale * .36))

    def _cell(self, frame):
        edges = unit_cell_edges(frame.cell)
        self._tube_segments([(p, q, '#7D8CA4') for p, q in edges], .025)

    def _atom_radius(self, symbol):
        mode = self.options.style
        if mode == 'Wireframe':
            return max(.008, self.options.bond_scale * .50)
        if mode == 'Space filling':
            vdw = {'H': 1.20, 'C': 1.70, 'N': 1.55, 'O': 1.52,
                   'F': 1.47, 'P': 1.80, 'S': 1.80, 'Cl': 1.75,
                   'Br': 1.85, 'I': 1.98, 'Li': 1.82, 'Na': 2.27,
                   'K': 2.75, 'Fe': 2.0, 'Cu': 1.40, 'Zn': 1.39}.get(
                       symbol, max(1.1, radius(symbol) * 1.70))
            return max(.12, vdw * self.options.atom_scale)
        if mode == 'Sticks':
            return max(0.085, self.options.bond_scale * 1.18)
        return max(0.09, radius(symbol) * self.options.atom_scale)

    def _labels(self, frame):
        names = atom_label_texts(frame.symbols, self.options.labels, frame.info.get("poscar_groups"))
        for symbol, pos, text in zip(frame.symbols, frame.positions, names):
            t = vtkBillboardTextActor3D()
            t.SetInput(text)
            t.PickableOff()
            prop = t.GetTextProperty()
            prop.SetFontSize(int(self.options.label_font_size))
            prop.SetBold(bool(self.options.label_bold))
            prop.SetColor(rgb(self.options.label_color))
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            if self.options.label_font_file:
                prop.SetFontFamilyAsString('File')
                prop.SetFontFile(self.options.label_font_file)
            else:
                prop.SetFontFamilyAsString(self.options.label_font)
            self._add_actor(t)
            self._label_actors.append(t)
            self._label_positions.append(np.asarray(pos, dtype=float).copy())
            self._label_radii.append(self._atom_radius(symbol))

    def _place_labels(self, *_args):
        if not self._label_actors:
            return
        cam = self.renderer.GetActiveCamera()
        cp = np.asarray(cam.GetPosition(), dtype=float)
        parallel = bool(cam.GetParallelProjection())
        towards_cam = -np.asarray(cam.GetDirectionOfProjection(), dtype=float)
        for actor, pos, rad in zip(self._label_actors, self._label_positions, self._label_radii):
            direction = towards_cam if parallel else cp - pos
            n = np.linalg.norm(direction)
            if n > 1.e-12:
                direction = direction / n
            else:
                direction = np.array([0., 0., 1.])
            actor.SetPosition(*(float(x) for x in pos + direction * rad * 1.025))

    @staticmethod
    def _arrow_actor(vector, color):
        """Arrow extending precisely from world zero along vector."""
        vec = np.asarray(vector, dtype=float)
        length = np.linalg.norm(vec)
        if length < 1.e-9:
            return None, None
        xdir = vec / length
        tmp = np.array([0., 0., 1.]) if abs(xdir[2]) < .92 else np.array([0., 1., 0.])
        ydir = np.cross(tmp, xdir)
        ydir /= np.linalg.norm(ydir)
        zdir = np.cross(xdir, ydir)
        # Local arrow runs from x=0 to x=1. The transform keeps the direction
        # exact while keeping the cross-section size proportional to its length.
        matrix = vtkMatrix4x4()
        for row in range(3):
            matrix.SetElement(row, 0, float(vec[row]))
            matrix.SetElement(row, 1, float(ydir[row] * length))
            matrix.SetElement(row, 2, float(zdir[row] * length))
        source = vtkArrowSource()
        source.SetShaftRadius(.022)
        source.SetTipRadius(.09)
        source.SetTipLength(.22)
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(source.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetUserMatrix(matrix)
        actor.GetProperty().SetColor(rgb(color))
        actor.PickableOff()
        return actor, (source, mapper, matrix)

    AXIS_COLORS = ('#E84B4B', '#32A466', '#3F7BE0')

    def _world_axes(self, frame):
        for (name, vec), c in zip(axis_vectors(frame, self.options.axes_basis,
                                               self.options.axes_length), self.AXIS_COLORS):
            actor, resources = self._arrow_actor(vec, c)
            if actor is None:
                continue
            self._add_actor(actor)
            self._keepalive.append(resources)
            label = vtkBillboardTextActor3D()
            label.SetInput(name)
            label.SetPosition(*(float(x) for x in vec * 1.08))
            label.GetTextProperty().SetFontSize(18)
            label.GetTextProperty().SetBold(True)
            label.GetTextProperty().SetJustificationToCentered()
            label.GetTextProperty().SetVerticalJustificationToCentered()
            label.GetTextProperty().SetColor(rgb(c))
            label.PickableOff()
            self._add_actor(label)

    def make_corner_marker(self, frame):
        """Camera-oriented overlay: XYZ or actual nonorthogonal abc directions."""
        assembly = vtkAssembly()
        for (name, vec), c in zip(axis_vectors(frame, self.options.axes_basis,
                                               self.options.axes_length, corner=True), self.AXIS_COLORS):
            actor, resources = self._arrow_actor(vec, c)
            if actor is None:
                continue
            assembly.AddPart(actor)
            self._keepalive.append(resources)
            letters = vtkVectorText()
            letters.SetText(name)
            mapping = vtkPolyDataMapper()
            mapping.SetInputConnection(letters.GetOutputPort())
            label = vtkActor()
            label.SetMapper(mapping)
            label.GetProperty().SetColor(rgb(c))
            label.SetScale(.19)
            label.SetPosition(*(float(x) for x in vec * 1.15))
            label.PickableOff()
            assembly.AddPart(label)
            self._keepalive.append((letters, mapping))
        assembly.PickableOff()
        return assembly

    def _volume(self, volume):
        counts = volume.data.shape
        if volume.data.size > 2_000_000:
            return
        # vtkStructuredGrid preserves skewed CUBE voxel basis.
        ii, jj, kk = np.indices(counts, dtype=np.float32)
        gridpoints = volume.origin + ii[..., None] * volume.voxel_vectors[0] + jj[..., None] * volume.voxel_vectors[1] + kk[..., None] * volume.voxel_vectors[2]
        points = vtkPoints()
        points.SetData(numpy_to_vtk(np.ascontiguousarray(np.column_stack([gridpoints[..., j].ravel(order='F') for j in range(3)])), deep=True))
        grid = vtkStructuredGrid()
        grid.SetDimensions(*counts)
        grid.SetPoints(points)
        values = numpy_to_vtk(np.ascontiguousarray(volume.data.ravel(order='F')), deep=True)
        values.SetName('volume_field')
        grid.GetPointData().SetScalars(values)
        self._keepalive.append((points, grid, values))
        iso = max(1e-7, abs(self.options.volume_iso))
        low, high = float(volume.data.min()), float(volume.data.max())
        surfaces = [(iso, '#EC6B46')] if low >= 0 else [(-iso, '#556EE6'), (iso, '#EC6B46')]
        for value, hex_color in surfaces:
            if not (low <= value <= high):
                continue
            contour = vtkContourFilter()
            contour.SetInputData(grid)
            contour.SetValue(0, value)
            contour.Update()
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(contour.GetOutputPort())
            mapper.ScalarVisibilityOff()
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(rgb(hex_color))
            actor.GetProperty().SetOpacity(self.options.volume_opacity)
            actor.GetProperty().SetSpecular(.25)
            self._add_actor(actor)
            self._keepalive.append((contour, mapper))

    def _highlights(self):
        if self.frame is None:
            return
        for i in self.selected:
            if not (0 <= i < len(self.frame.symbols)):
                continue
            sphere = vtkSphereSource()
            sphere.SetRadius(max(.18, self._atom_radius(self.frame.symbols[i]) * 1.17))
            sphere.SetThetaResolution(20)
            sphere.SetPhiResolution(14)
            location = (self.periodic_preview.image_positions.get(i, self.frame.positions[i])
                        if self.periodic_preview is not None else self.frame.positions[i])
            sphere.SetCenter(*[float(x) for x in location])
            mapper = vtkPolyDataMapper()
            mapper.SetInputConnection(sphere.GetOutputPort())
            actor = vtkActor()
            actor.SetMapper(mapper)
            actor.GetProperty().SetRepresentationToWireframe()
            actor.GetProperty().SetColor(.15, .88, .75)
            actor.GetProperty().SetLineWidth(2.5)
            actor.PickableOff()
            self._add_actor(actor)
            self.atom_highlights.append(actor)
            self._keepalive.append((sphere, mapper))

    def pick_index(self, display_x: int, display_y: int, width: int = 0, height: int = 0):
        """Pick visible atom sphere in VTK *bottom-left-origin* display pixels.

        Uses the true projected sphere radius rather than a hardcoded 18 px
        centre-only test. Prioritize frontmost atom for overlapping balls.
        """
        frame = self.frame
        if frame is None:
            return None
        camera = self.renderer.GetActiveCamera()
        d = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
        up = np.asarray(camera.GetViewUp(), dtype=float)
        right = np.cross(d, up)
        length = float(np.linalg.norm(right))
        right = right / length if length > 1.e-12 else np.array([1., 0., 0.])
        hits = []
        candidates = [(i, pos) for i, pos in enumerate(frame.positions)]
        if self.periodic_preview is not None:
            candidates.extend((i, pos) for i, pos in self.periodic_preview.image_positions.items())
        for i, pos in candidates:
            p = np.asarray(pos, dtype=float)
            self.renderer.SetWorldPoint(*[float(x) for x in p], 1.)
            self.renderer.WorldToDisplay()
            sx, sy, sz = self.renderer.GetDisplayPoint()
            rad = self._atom_radius(frame.symbols[i])
            self.renderer.SetWorldPoint(*[float(x) for x in p + right * rad], 1.)
            self.renderer.WorldToDisplay()
            xx, yy, _ = self.renderer.GetDisplayPoint()
            px_radius = max(6., float(np.hypot(xx - sx, yy - sy)))
            if self.options.style == 'Wireframe':
                px_radius = 9.
            dist = float(np.hypot(sx - display_x, sy - display_y))
            if dist <= px_radius * 1.10:
                # VTK display depth: nearer is smaller; subtract an estimate
                # of the sphere's front-facing depth for visual overlap.
                eye_depth = float(np.linalg.norm(np.asarray(camera.GetPosition()) - p) - rad)
                if camera.GetParallelProjection():
                    eye_depth = float(np.dot(p - np.asarray(camera.GetPosition()), d) - rad)
                hits.append((eye_depth, dist / px_radius, i))
        return min(hits)[-1] if hits else None


def set_isometric_view(renderer: vtkRenderer):
    """Apply true orthographic isometry without modifying atoms or cell.

    The camera looks along the Cartesian (1, 1, 1) diagonal.  The view-up
    is perpendicular to this direction, preserving 120-degree projected axes.
    """
    cam = renderer.GetActiveCamera()
    # Reset scene bounds first so the camera's focal point matches the actual
    # visible model, even after loading a file with an offset origin.
    renderer.ComputeVisiblePropBounds()
    renderer.ResetCamera()
    centre = np.asarray(cam.GetFocalPoint(), dtype=float)
    span = max(10., float(cam.GetDistance()))
    look = np.array([1., 1., 1.]) / np.sqrt(3.)
    up = np.array([-1., -1., 2.]) / np.sqrt(6.)
    cam.SetFocalPoint(*centre)
    cam.SetPosition(*(centre + span * look))
    cam.SetViewUp(*up)
    cam.SetParallelProjection(True)
    cam.OrthogonalizeViewUp()
    renderer.ResetCamera()
    renderer.ResetCameraClippingRange()
