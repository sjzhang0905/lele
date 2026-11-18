"""Cached VTK geometry for interactive fragment translation and rotation.

The normal scene is retained while a drag is active: charge-density surfaces,
cuts, cell, and the camera are never reconstructed for every pointer event.
Only temporary atom/bond/label actors are translated. Actual frame coordinates
and the single undo record remain owned by the main-window gesture handler.
"""
from copy import deepcopy
from dataclasses import replace

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer

from .atom_appearance import appearance
from .core import atom_label_texts, visible_bonds


class FragmentPanPreview:
    def __init__(self, renderer, source_frame, indices):
        from .renderer import MoleculeRenderer

        self.owner = renderer
        self.scene = renderer.renderer
        self.original = [(actor, actor.GetVisibility())
                         for actor in renderer.fragment_geometry_actors]
        self.builders = []
        self.actors = []
        self.moving_actors = []
        self.offset = np.zeros(3)
        self.closed = False
        display = renderer.boundary_display
        if display is None:
            frame = renderer.frame.clone()
            source_indices = np.arange(len(frame.symbols), dtype=int)
            bonds = visible_bonds(frame, renderer.options.bond_cutoff)
        else:
            frame = display.frame.clone()
            source_indices = np.asarray(display.source_indices, dtype=int)
            bonds = display.bonds
        selected = np.isin(source_indices, np.asarray(indices, dtype=int))

        # A duplicate boundary atom keeps the label of its source atom.
        label_names = {}
        for i, source_index in enumerate(source_indices):
            style = appearance(frame, i)
            mode = renderer.options.labels if style.label_mode == 'Global' else style.label_mode
            if mode in ('Custom', 'None'):
                continue
            if mode not in label_names:
                label_names[mode] = atom_label_texts(source_frame.symbols, mode,
                    source_frame.info.get('poscar_groups'))
            frame.atom_appearance[i] = replace(style, label_mode='Custom',
                label_text=label_names[mode][source_index])

        options = deepcopy(renderer.options)
        options.boundary_enabled = False  # frame already contains display replicas
        options.show_volume = False
        options.unit_cell = False
        options.axes_position = 'Off'
        options.lattice_planes = []
        try:
            for moving in (False, True):
                partial = frame.clone()
                for i in range(len(partial.symbols)):
                    if bool(selected[i]) != moving:
                        partial.atom_appearance[i] = replace(appearance(partial, i), visible=False)
                temporary_scene = vtkRenderer()
                temporary_scene.SetActiveCamera(self.scene.GetActiveCamera())
                builder = MoleculeRenderer(temporary_scene)
                builder.options = options
                builder.fixed_bonds = bonds
                builder.selected = np.flatnonzero(selected).tolist() if moving else []
                builder.set_scene(partial)
                # Keep mapper clips in world coordinates, as in the full scene.
                for actor in builder.fragment_geometry_actors:
                    mapper = actor.GetMapper() if hasattr(actor, 'GetMapper') else None
                    if mapper is not None and hasattr(mapper, 'AddClippingPlane'):
                        for plane in renderer._vtk_clip_planes:
                            mapper.AddClippingPlane(plane)
                    self.scene.AddViewProp(actor)
                    self.actors.append(actor)
                    if moving:
                        self.moving_actors.append((actor, np.asarray(actor.GetPosition(), dtype=float)))
                self.builders.append(builder)
            # Hide original geometry only after both preview groups succeeded.
            for actor, _visibility in self.original:
                actor.VisibilityOff()
            renderer._fragment_pan_preview = self
        except Exception:
            self.close()
            raise

    def translate(self, offset):
        if self.closed:
            return
        self.offset += np.asarray(offset, dtype=float)
        for actor, origin in self.moving_actors:
            actor.SetPosition(*(origin + self.offset))

    def close(self):
        if self.closed:
            return
        for actor in self.actors:
            self.scene.RemoveViewProp(actor)
        for actor, visibility in self.original:
            actor.SetVisibility(visibility)
        for builder in self.builders:
            builder.renderer.RemoveObservers('StartEvent')
            builder.clear()
        self.builders.clear()
        self.actors.clear()
        self.moving_actors.clear()
        if getattr(self.owner, '_fragment_pan_preview', None) is self:
            self.owner._fragment_pan_preview = None
        self.closed = True


def start_fragment_pan_preview(renderer, source_frame, indices):
    """Return a cached preview where it preserves the complete displayed model.

    Polyhedra and the temporary cross-boundary fragment display continue using
    the full redraw path; their geometry depends on more than rigid atom motion.
    """
    if (not hasattr(renderer, 'fragment_geometry_actors')
            or renderer.options.style == 'Polyhedral'
            or renderer.periodic_preview is not None
            or renderer.alignment is not None):
        return None
    display = renderer.boundary_display
    frame = renderer.frame if display is None else display.frame
    source_indices = (np.arange(len(frame.symbols), dtype=int) if display is None
                      else np.asarray(display.source_indices, dtype=int))
    moving = np.isin(source_indices, np.asarray(indices, dtype=int))
    bonds = (visible_bonds(frame, renderer.options.bond_cutoff)
             if display is None else display.bonds)
    # A link between moving and stationary atoms must stretch rather than
    # disappear. Keep the existing full update for such non-rigid geometry.
    if any(bool(moving[a]) != bool(moving[b]) for a, b in bonds):
        return None
    if renderer.options.hydrogen_bonds or frame.hbond_added:
        from .hydrogen_bonds import hydrogen_bond_links
        links = hydrogen_bond_links(frame, renderer.options.hydrogen_bonds)
        if any(bool(moving[link.first]) != bool(moving[link.second]) for link in links):
            return None
    previous = getattr(renderer, '_fragment_pan_preview', None)
    if previous is not None:
        previous.close()
    return FragmentPanPreview(renderer, source_frame, indices)


class FragmentRotationPreview:
    """Update existing VTK points from source displacements, including cell images."""
    def __init__(self, renderer, frame, indices):
        from vtkmodules.util.numpy_support import vtk_to_numpy

        self.owner = renderer
        self.frame = frame
        self.reference = frame.positions.copy()
        self.closed = False
        self.atoms = []
        self.bonds = []
        self.markers = []
        self.labels = []

        display = renderer.boundary_display
        sources = np.arange(len(frame.symbols)) if display is None else display.source_indices
        moving = np.zeros(len(frame.symbols), dtype=bool)
        moving[indices] = True
        renderer._select_fragment_highlights(indices)

        for points, display_ids in renderer.drag_atom_points:
            ids = sources[display_ids]
            rows = np.flatnonzero(moving[ids])
            if rows.size:
                xyz = vtk_to_numpy(points.GetData())
                self.atoms.append((points, xyz, rows, xyz[rows].copy(), ids[rows]))

        for points, pairs, fractions in renderer.drag_bond_points:
            ids = sources[pairs]
            rows = np.flatnonzero(moving[ids].any(axis=1))
            if rows.size:
                xyz = vtk_to_numpy(points.GetData()).reshape(-1, 2, 3)
                self.bonds.append((points, xyz, rows, xyz[rows].copy(), ids[rows], fractions[rows, :, None]))

        for index, sphere in renderer.drag_site_sectors:
            atom = sources[index]
            if moving[atom]:
                self.markers.append((sphere.SetCenter, np.array(sphere.GetCenter()), atom))
        for atom, ring in zip(renderer.highlight_indices, renderer.atom_highlights):
            if moving[atom]:
                self.markers.append((ring.SetPosition, np.array(ring.GetPosition()), atom))
        for index, position in zip(renderer.label_indices, renderer._label_positions):
            atom = sources[index]
            if moving[atom]:
                self.labels.append((position, position.copy(), atom))
        renderer._fragment_rotation_preview = self

    def update(self):
        # A translated cell replica gets the same *displacement* as its source.
        # Rotating all replicas around a single world-space pivot would rotate
        # the lattice translations and tear bonds at cell boundaries.
        delta = self.frame.positions - self.reference
        for points, xyz, rows, start, ids in self.atoms:
            xyz[rows] = start + delta[ids]
            points.Modified()
        for points, xyz, rows, start, ids, fractions in self.bonds:
            first = delta[ids[:, 0], None, :]
            second = delta[ids[:, 1], None, :]
            xyz[rows] = start + first + fractions * (second - first)
            points.Modified()
        for setter, start, atom in self.markers:
            setter(*(start + delta[atom]))
        for position, start, atom in self.labels:
            position[:] = start + delta[atom]

    def close(self):
        self.closed = True
        if self.owner._fragment_rotation_preview is self:
            self.owner._fragment_rotation_preview = None


def start_fragment_rotation_preview(renderer, frame, indices):
    if (getattr(renderer, 'source_frame', None) is not frame
            or renderer.options.style == 'Polyhedral'
            or renderer.periodic_preview is not None or renderer.alignment is not None
            or renderer.fitted_plane is not None or renderer.mode_vectors is not None
            or (renderer.dipole_vector is not None and renderer.options.dipole_mode != 'Off')
            or renderer.crystal_cuts):
        return None
    return FragmentRotationPreview(renderer, frame, indices)


def queue_fragment_rotation(window, gesture):
    """Paint the latest geometry once per event-loop turn, including fallback scenes."""
    from PySide6.QtCore import QObject, QTimer

    if gesture.get('paint_pending'):
        return
    gesture['paint_pending'] = True

    def paint():
        gesture['paint_pending'] = False
        if window._fragment_gesture is not gesture:
            return
        preview = gesture.get('preview')
        if preview is None or preview.closed:
            window.refresh_scene()
        else:
            preview.update()
            if gesture['kind'] == 'orbit':
                window.scene.ResetCameraClippingRange()
            window.vtk.GetRenderWindow().Render()

    if isinstance(window, QObject):
        QTimer.singleShot(0, window, paint)
    else:
        paint()
