"""VTK implementation of Miller cuts and coordination-polyhedron models."""
import numpy as np
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkPlane, vtkPolyData, vtkCellArray
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

from .core import Frame
from .atom_appearance import appearance
from .periodic_geometry import periodic_basis
from .crystal_planes import prepare_planes, plane_polygon, clip_polygon, inside_cuts
from .polyhedra import coordination_polyhedra
from .crystal_settings import POLYHEDRA_KEYS
from .element_rules import rule_signature


class CrystalRendering:
    def _init_crystal_rendering(self):
        self.crystal_cuts = [];self._vtk_clip_planes = [];self._clipping_suspended = False
        self.lattice_plane_data = [];self.lattice_plane_actors = []
        self.polyhedra = [];self.polyhedron_actors = [];self.polyhedra_extra_atoms = []
        self._polyhedra_cache = None;self._polyhedra_atoms_frame = None

    def _raw_display_atoms(self):
        if self.frame is None:return []
        if self.boundary_display is not None:
            return [(int(i), p) for i, p in zip(self.boundary_display.source_indices, self.boundary_display.frame.positions)]
        result = list(enumerate(self.frame.positions))
        if self.periodic_preview is not None:
            result += [(i, p @ self.display_rotation+self.display_translation)
                       for i, p in self.periodic_preview.image_positions.items()]
        return result

    def _prepare_crystal_geometry(self):
        self.crystal_cuts = [];self._vtk_clip_planes = [];self.lattice_plane_data = []
        self.lattice_plane_actors = [];self.polyhedra = [];self.polyhedron_actors = []
        self.polyhedra_extra_atoms = [];self._polyhedra_atoms_frame = None
        self._clipping_suspended = False
        if self.options.lattice_planes and periodic_basis(self.frame) is not None:
            self.lattice_plane_data, self.crystal_cuts = prepare_planes(
                self.frame.cell, self.options.lattice_planes, self.display_translation)
            for normal, origin in self.crystal_cuts:
                plane = vtkPlane();plane.SetNormal(*normal);plane.SetOrigin(*origin)
                self._vtk_clip_planes.append(plane)
        if self.options.style != 'Polyhedral':return
        source = self.source_frame
        key = (id(source), source.positions.tobytes(), source.cell.tobytes(), source.pbc,
            tuple(source.symbols), tuple(sorted(source.atom_appearance.items())), self.options.bond_cutoff,
            tuple(getattr(self.options, name) for name in POLYHEDRA_KEYS[:5]),
            rule_signature(self.options.element_pair_rules, self.options.pair_rules_only))
        if self._polyhedra_cache is None or self._polyhedra_cache[0] != key:
            self._polyhedra_cache = (key, coordination_polyhedra(source, self.options))
        by_center = {p.center:p for p in self._polyhedra_cache[1]}
        displayed = self._raw_display_atoms()
        known = {(i, tuple(np.round(p, 7))) for i, p in displayed}
        centers = set()
        for index, position in displayed:
            poly = by_center.get(index)
            center_key = (index, tuple(np.round(position, 7)))
            if poly is None or center_key in centers:continue
            centers.add(center_key)
            vertices = poly.vectors @ self.display_rotation + position
            self.polyhedra.append(dict(source=poly, center=index, origin=position, vertices=vertices))
            if self.options.polyhedra_show_atoms and self.options.polyhedra_show_vertices:
                for ligand, point in zip(poly.ligand_indices, vertices):
                    key = (int(ligand), tuple(np.round(point, 7)))
                    if key not in known:
                        self.polyhedra_extra_atoms.append((int(ligand), point));known.add(key)
        if self.polyhedra_extra_atoms:
            from .site_occupancy import subset_info
            self._polyhedra_atoms_frame = Frame(
                [source.symbols[i] for i, _ in self.polyhedra_extra_atoms],
                [p for _, p in self.polyhedra_extra_atoms], self.frame.cell, self.frame.pbc,
                info=subset_info(source.info,[i for i,_ in self.polyhedra_extra_atoms]),
                atom_appearance={j:appearance(source, i) for j, (i, _) in enumerate(self.polyhedra_extra_atoms)})

    def _attach_crystal_clips(self, actor):
        if self._clipping_suspended or not self._vtk_clip_planes:return
        mapper = actor.GetMapper() if hasattr(actor, 'GetMapper') else None
        if mapper is not None and hasattr(mapper, 'AddClippingPlane'):
            for plane in self._vtk_clip_planes:mapper.AddClippingPlane(plane)

    def _polygon_actor(self, vertices, faces, color, opacity):
        from .renderer import rgb
        points = vtkPoints()
        for point in vertices:points.InsertNextPoint(*point)
        polygons = vtkCellArray()
        for face in faces:
            polygons.InsertNextCell(len(face))
            for index in face:polygons.InsertCellPoint(int(index))
        data = vtkPolyData();data.SetPoints(points);data.SetPolys(polygons)
        mapper = vtkPolyDataMapper();mapper.SetInputData(data);mapper.ScalarVisibilityOff()
        actor = vtkActor();actor.SetMapper(mapper);actor.PickableOff()
        actor.GetProperty().SetColor(rgb(color));actor.GetProperty().SetOpacity(opacity)
        self._finish(actor.GetProperty());self._add_actor(actor)
        self._keepalive.append((points, polygons, data, mapper))
        return actor

    def _render_polyhedra(self):
        edges = []
        for item in self.polyhedra:
            poly, vertices, center = item['source'], item['vertices'], item['center']
            opacity = appearance(self.source_frame, center).opacity
            actor = self._polygon_actor(vertices, poly.faces, self.atom_color(self.source_frame, center),
                                        self.options.polyhedra_opacity*opacity)
            self.polyhedron_actors.append(actor)
            if self.options.polyhedra_edges:
                edges.extend((vertices[a], vertices[b], self.options.polyhedra_edge_color) for a, b in poly.edges)
        if edges:
            actor = self._tube_segments(edges, max(.009, self.options.bond_scale*.35))
            actor.PickableOff()

    def _render_lattice_planes(self):
        if not self.lattice_plane_data:return
        bounds = self.options.boundary_bounds if self.boundary_display is not None else ((0., 1.),)*3
        self._clipping_suspended = True
        try:
            for spec, plane, origin in self.lattice_plane_data:
                polygon = plane_polygon(self.frame.cell, plane.normal, origin, bounds, self.display_translation)
                polygon = clip_polygon(polygon, self.crystal_cuts)
                if len(polygon) < 3:continue
                actor = self._polygon_actor(polygon, [list(range(len(polygon)))], spec['color'], spec['opacity'])
                actor.GetProperty().LightingOff();self.lattice_plane_actors.append(actor)
                outline = self._tube_segments([(p, polygon[(i+1) % len(polygon)], spec['color']) for i, p in enumerate(polygon)], .012)
                outline.PickableOff()
        finally:self._clipping_suspended = False

    def _crystal_visible_atoms(self):
        if self.options.style == 'Polyhedral' and not self.options.polyhedra_show_atoms:return []
        result = self._raw_display_atoms()+self.polyhedra_extra_atoms
        if self.crystal_cuts and result:
            keep = inside_cuts([p for _, p in result], self.crystal_cuts)
            result = [item for item, show in zip(result, keep) if show]
        return result
