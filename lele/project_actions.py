"""Project save/open actions with complete in-memory scientific snapshots."""
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QFileDialog, QMessageBox
from .operations import run_data_task,gui_operation
from .output_text import LoadCancelled


def camera_data(camera):
    if camera is None:return None
    return dict(position=camera.GetPosition(), focal_point=camera.GetFocalPoint(),
        view_up=camera.GetViewUp(), parallel_projection=bool(camera.GetParallelProjection()),
        parallel_scale=camera.GetParallelScale(), view_angle=camera.GetViewAngle(),
        clipping_range=camera.GetClippingRange(), window_center=camera.GetWindowCenter())


def camera_from_data(data):
    if data is None:return None
    from vtkmodules.vtkRenderingCore import vtkCamera
    camera = vtkCamera()
    camera.SetPosition(*data['position']);camera.SetFocalPoint(*data['focal_point']);camera.SetViewUp(*data['view_up'])
    camera.SetParallelProjection(data['parallel_projection']);camera.SetParallelScale(data['parallel_scale'])
    camera.SetViewAngle(data['view_angle']);camera.SetClippingRange(*data['clipping_range'])
    camera.SetWindowCenter(*data.get('window_center', (0., 0.)))
    return camera


class ProjectActions:
    def _install_project_actions(self):
        self._project_path = None
        self.open_project_action = self._action(self.file_menu, 'Open project…', self.open_project_dialog, 'Ctrl+Alt+O')
        self.save_project_action = self._action(self.file_menu, 'Save project…', self.save_project_dialog, 'Ctrl+Alt+S')
        self.save_project_as_action = self._action(self.file_menu, 'Save project as…', lambda:self.save_project_dialog(force_dialog=True))
        self.save_project_action.setEnabled(False);self.save_project_as_action.setEnabled(False)

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Open LELE project', '', 'LELE project (*.lele)')
        if path:self.open_path(path)

    def save_project_dialog(self, *, force_dialog=False):
        if not self.documents:return False
        path = self._project_path
        if path is None or force_dialog:
            default = str(path) if path is not None else str(self.doc.path.with_suffix('.lele'))
            name, _ = QFileDialog.getSaveFileName(self, 'Save LELE project', default, 'LELE project (*.lele)')
            if not name:return False
            path = Path(name)
            if path.suffix.lower() != '.lele':path = Path(str(path)+'.lele')
        return self.save_project_to(path)

    def _project_state(self):
        from .style_presets import CUSTOM_KEY, snapshot
        self._remember_document_view()
        entries = []
        for index, document in enumerate(self.documents):
            if document.source_preview is None:
                self._update_source_view(index)
                if document.source_preview is None:
                    document.source_preview = '[Source text unavailable. Loaded structures and calculation results are retained in this project.]'
            if document.project_original_path is None:document.project_original_path = str(document.path)
            view = self._document_views.get(id(document))
            options = self.render_options if view is None else view.options
            entries.append(dict(document=document, options=options,
                custom_style=snapshot(options) if view is None else view.custom_style,
                preset=CUSTOM_KEY if view is None else view.preset,
                camera=camera_data(None if view is None else view.camera),
                frame_index=(self.frame_index if document is self.doc else getattr(view, 'frame_index', 0)),
                alignment=self._trajectory_alignments.get(id(document)),
                alignment_enabled=id(document) in self._aligned_documents,
                geometry_parameters=self._geometry_parameters.get(id(document), []),
                vibration_references={ai:frame for (di, ai), frame in self._vibration_references.items() if di == index}))
        self._update_source_view()
        controls = self.vibration_controls
        return dict(documents=entries, current_document=self.current_doc, selection=list(self.selection),
            active_vibration=self._active_vibration, energy_only_context=self._energy_only_context,
            result_sequence=getattr(self, '_result_sequence', None), vibration_controls=dict(
                amplitude=controls.amplitude.value(), speed=controls.speed.value(),
                arrow_length=controls.arrow_length.value(), arrows=controls.arrows_check.isChecked(),
                selected_arrows=controls.selected_arrows_check.isChecked()))

    def save_project_to(self, path):
        if not self.documents:return False
        from .project_file import save_project
        state=self._project_state()
        try:run_data_task(self,'Saving project',lambda:save_project(path,state))
        except (ValueError, TypeError, OSError) as exc:
            QMessageBox.warning(self, 'Could not save project', str(exc));return False
        self._project_path = Path(path)
        self.statusBar().showMessage(f'Saved project with {len(self.documents)} document(s): {Path(path).name}', 7000)
        return True

    def _load_project_path(self, path):
        from .project_file import load_project
        try:state = run_data_task(self,'Opening project',lambda:load_project(path),cancellable=True)
        except LoadCancelled:return False
        except (ValueError, TypeError, OSError) as exc:
            QMessageBox.warning(self, 'Could not open project', str(exc));return False
        from .document_view import DocumentView
        from .style_presets import CUSTOM_KEY
        offset = len(self.documents)
        for i, entry in enumerate(state['documents']):
            document = entry['document'];original = str(document.path)
            if not document.path.exists():
                name = original.replace('\\', '/').rsplit('/', 1)[-1]
                document.path = Path(path).resolve().parent/name
            document.project_original_path = document.project_original_path or original
            preset = entry.get('preset', CUSTOM_KEY)
            if self.preset_combo.findData(preset) < 0:preset = CUSTOM_KEY
            view = DocumentView(document, entry['options'], entry.get('custom_style', {}), preset,
                camera_from_data(entry.get('camera')), entry.get('frame_index', 0))
            self._document_views[id(document)] = view
            self.documents.append(document);self._add_document_tree(offset+i, document)
            alignment = entry.get('alignment')
            if alignment is not None:self._trajectory_alignments[id(document)] = alignment
            if entry.get('alignment_enabled'):self._aligned_documents.add(id(document))
            self._geometry_parameters[id(document)] = entry.get('geometry_parameters', [])
            for ai, frame in entry.get('vibration_references', {}).items():self._vibration_references[offset+i, ai] = frame
        active = offset+state.get('current_document', 0)
        self._result_sequence = state.get('result_sequence')
        controls = self.vibration_controls
        for key, widget, method in (
                ('amplitude', controls.amplitude, 'setValue'), ('speed', controls.speed, 'setValue'),
                ('arrow_length', controls.arrow_length, 'setValue'),
                ('arrows', controls.arrows_check, 'setChecked'),
                ('selected_arrows', controls.selected_arrows_check, 'setChecked')):
            if key in state.get('vibration_controls', {}):
                with QSignalBlocker(widget):getattr(widget, method)(state['vibration_controls'][key])
        self.change_frame(state['documents'][active-offset].get('frame_index', 0), switch_doc=active)
        vibration = state.get('active_vibration')
        if vibration is not None:self.select_vibration(offset+vibration[0], vibration[1], vibration[2], autoplay=False)
        energy = state.get('energy_only_context')
        if energy is not None:
            self._activate_document(offset+energy[0]);self._leave_vibration()
            self._energy_only_context = (offset+energy[0], energy[1]);self._show_results_only()
        if self.frame is not None:
            self.selection = [int(i) for i in state.get('selection', []) if 0 <= int(i) < len(self.frame.symbols)]
            # Entering a frequency reference may fit the camera. Restore the
            # saved view after the final source/mode and selection are active.
            self._pending_view_camera = camera_from_data(state['documents'][self.current_doc-offset].get('camera'))
            self._sync_selection_to_table();self.refresh_scene()
        self._update_source_view();self._refresh_info()
        self._project_path = Path(path) if offset == 0 else None
        self.statusBar().showMessage(f'Opened project: {len(state["documents"])} document(s) added; stored structures, results and views restored.', 8000)
        return True
