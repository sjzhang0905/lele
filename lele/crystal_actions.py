"""Crystal display actions. Scientific imports wait until a structure exists."""
from copy import deepcopy
from PySide6.QtWidgets import QMessageBox
from .crystal_settings import POLYHEDRA_KEYS


class CrystalActions:
    def _install_crystal_controls(self):
        from .crystal_panel import CrystalPanel
        self.crystal_panel = CrystalPanel()
        self.crystal_window=self._create_settings_window(self.crystal_panel,'Crystal tools',760,650)
        self.crystal_action=self._action(self.view_menu,'Crystal tools…',lambda:self._show_crystal_tools(0))
        planes = self.crystal_panel.planes
        planes.applyRequested.connect(self._apply_lattice_planes)
        planes.normalRequested.connect(self._view_lattice_normal)
        planes.centerRequested.connect(self._center_lattice_plane)
        planes.previewChanged.connect(self._update_lattice_plane_info)
        self.crystal_panel.polyhedra.applyRequested.connect(self._apply_polyhedra)
        self.crystal_panel.rules.applyRequested.connect(self._apply_element_pair_rules)
        self.crystal_panel.polyhedra.analyze.clicked.connect(self.show_polyhedron_analysis)
        self.polyhedron_analysis_action = self._action(self.analysis_menu, 'Coordination / polyhedron analysis…', self.show_polyhedron_analysis)
        self.polyhedron_analysis_action.setEnabled(False)
        self.lattice_planes_action = self._action(self.view_menu, 'Lattice planes / cuts…', lambda:self._show_crystal_tools(0))
        self.polyhedra_action = self._action(self.view_menu, 'Coordination polyhedra…', lambda:self._show_crystal_tools(1))
        self.lattice_planes_action.setEnabled(False);self.polyhedra_action.setEnabled(False)
        self.crystal_panel.set_values(self.render_options)

    def _show_crystal_tools(self, index):
        self.crystal_panel.tabs.setCurrentIndex(index)
        self._show_settings_window(self.crystal_window)

    def _apply_lattice_planes(self, values):
        if self.frame is None:return
        from .crystal_planes import validate_planes, prepare_planes
        try:
            records = validate_planes(values)
            prepare_planes(self.frame.cell, records)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Invalid Miller planes', str(exc));return False
        self.render_options.lattice_planes = records
        selected = self.crystal_panel.planes.table.currentRow()
        self.crystal_panel.planes.set_values(records)
        if records:self.crystal_panel.planes.table.selectRow(max(0, min(selected, len(records)-1)))
        self.refresh_scene();return True

    def _apply_polyhedra(self, values):
        if self.frame is None:return
        from .polyhedra import validate_polyhedra
        candidate = deepcopy(self.render_options)
        for key in POLYHEDRA_KEYS:setattr(candidate, key, values[key])
        try:validate_polyhedra(candidate)
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid polyhedra settings', str(exc));return False
        for key in POLYHEDRA_KEYS:setattr(self.render_options, key, getattr(candidate, key))
        self._set_option('style', 'Polyhedral');self._sync_style_widgets()
        self.crystal_panel.polyhedra.set_values(self.render_options);return True

    def _refresh_crystal_controls(self):
        frame = self.frame
        has_atoms = frame is not None and bool(frame.symbols)
        periodic = False
        if has_atoms:
            from .periodic_geometry import periodic_basis
            periodic = periodic_basis(frame) is not None
        self.crystal_panel.planes.setEnabled(periodic)
        self.crystal_panel.polyhedra.setEnabled(has_atoms)
        self.crystal_panel.rules.setEnabled(has_atoms)
        self.polyhedron_analysis_action.setEnabled(has_atoms)
        self.crystal_panel.rules.info.setText(f'{len(self.render_options.element_pair_rules)} applied rules · B ordinary bonds · P polyhedron coordination')
        self.lattice_planes_action.setEnabled(periodic);self.polyhedra_action.setEnabled(has_atoms)
        self._update_lattice_plane_info()
        if not has_atoms:self.crystal_panel.polyhedra.info.setText('Open a structure to display coordination polyhedra.');return
        if self.render_options.style == 'Polyhedral':
            counts = {}
            for item in self.renderer.polyhedra:
                n = len(item['source'].ligand_indices);counts[n] = counts.get(n, 0)+1
            summary = ', '.join(f'CN {n}: {count}' for n, count in sorted(counts.items()))
            text = f'{len(self.renderer.polyhedra)} polyhedra (before cuts)'+(' · '+summary if summary else '')
            if not counts:text += '\nNo non-collinear ligand shells match these settings. Adjust centers, ligands or distances.'
        else:text = 'Choose Polyhedral style or press Apply.'
        text += '\nElements: '+', '.join(dict.fromkeys(frame.symbols))
        self.crystal_panel.polyhedra.info.setText(text)

    def show_polyhedron_analysis(self):
        if self.doc is None or not self.doc.frames:return
        from .polyhedron_dialog import PolyhedronDialog
        return self._show_analysis_window(PolyhedronDialog(self.doc, self))

    def _update_lattice_plane_info(self):
        panel = self.crystal_panel.planes
        if self.frame is None:
            panel.info.setText('Open a periodic structure to define Miller planes.');return
        from .periodic_geometry import periodic_basis
        if periodic_basis(self.frame) is None:
            panel.info.setText('Miller planes require a periodic structure with a valid cell.');return
        p = panel.selected_plane()
        if p is None:
            panel.info.setText('Press New to add a Miller plane.');return
        from .crystal_planes import miller_plane
        try:
            plane = miller_plane(self.frame.cell, p['hkl'], p['offset'], p['unit'])
            text = f'd(hkl) = {plane.spacing:.6f} Å\nSigned distance = {plane.distance:.6f} Å'
            text += f'\nh·x + k·y + l·z = {plane.distance/plane.spacing:.6g} (fractional coordinates)'
        except ValueError as exc:text = str(exc)
        panel.info.setText(text)

    def _center_lattice_plane(self):
        if self.frame is None:return
        p = self.crystal_panel.planes.selected_plane()
        if p is None:return
        import numpy as np
        from .crystal_planes import miller_plane
        try:plane = miller_plane(self.frame.cell, p['hkl'])
        except ValueError:return
        bounds = self.render_options.boundary_bounds if self.render_options.boundary_enabled else ((0., 1.),)*3
        offset = float(np.asarray(p['hkl']) @ np.mean(np.asarray(bounds), axis=1))
        if p['unit'] == 'Å':offset *= plane.spacing
        self.crystal_panel.planes.offset.setValue(offset)

    def _view_lattice_normal(self, p):
        if self.frame is None or p is None:return
        import numpy as np
        from .crystal_planes import miller_plane
        try:plane = miller_plane(self.renderer.frame.cell, p['hkl'], p['offset'], p['unit'], self.renderer.display_translation)
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid Miller plane', str(exc));return
        camera = self.scene.GetActiveCamera();normal = plane.normal
        bounds = self.render_options.boundary_bounds if self.render_options.boundary_enabled else ((0., 1.),)*3
        center = np.mean(np.asarray(bounds), axis=1) @ self.renderer.frame.cell+self.renderer.display_translation
        target = center-normal*np.dot(center-plane.origin, normal)
        distance = max(1., np.linalg.norm(np.asarray(camera.GetPosition())-camera.GetFocalPoint()))
        up = np.asarray(camera.GetViewUp());up = up-normal*np.dot(up, normal)
        if np.linalg.norm(up) < 1.e-7:
            choices = self.renderer.frame.cell
            up = max((v-normal*np.dot(v, normal) for v in choices), key=np.linalg.norm)
        camera.SetFocalPoint(*target);camera.SetPosition(*(target+normal*distance))
        camera.SetViewUp(*(up/np.linalg.norm(up)));camera.OrthogonalizeViewUp()
        self.scene.ResetCameraClippingRange();self._sync_corner_axes();self.vtk.GetRenderWindow().Render()
