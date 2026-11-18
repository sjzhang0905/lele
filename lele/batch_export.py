"""Export the remembered frame and view of every open document safely."""
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
import os
import tempfile

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QApplication
from .dialog_policy import QFileDialog, QMessageBox, QDialog


@dataclass
class BatchResult:
    exported: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    failures: list = field(default_factory=list)
    cancelled: bool = False

    def summary(self):
        text = (f'{len(self.exported)} exported · {len(self.skipped)} skipped · '
                f'{len(self.failures)} failed' + (' · cancelled' if self.cancelled else ''))
        if self.skipped:text += '\n\nSkipped:\n' + '\n'.join(self.skipped)
        if self.failures:text += '\n\nFailed:\n' + '\n'.join(self.failures)
        return text


def _path_key(path):
    return str(Path(path).resolve()).casefold()


def allocate_paths(documents, directory, suffixes):
    """Deterministic names without replacing existing files or any source file."""
    directory = Path(directory)
    reserved = {_path_key(doc.path) for doc in documents}
    if directory.exists():reserved.update(_path_key(p) for p in directory.iterdir())
    paths = []
    for document, suffix in zip(documents, suffixes, strict=True):
        stem = Path(document.path).stem or 'structure'
        suffix = suffix if suffix.startswith('.') else '.' + suffix
        number = 1
        candidate = directory / (stem + suffix)
        while _path_key(candidate) in reserved:
            number += 1
            candidate = directory / f'{stem}_{number}{suffix}'
        reserved.add(_path_key(candidate));paths.append(candidate)
    return paths


def _reserve(path):
    """Claim a new output without clobbering a file created after planning."""
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    os.close(descriptor)


def _write_structure(frame, path, target, occupancy_policy):
    from .formats import export_frame
    from .core import valid_lattice
    from .output_text import check_load_cancelled
    if target == 'cif' and not valid_lattice(frame):
        raise ValueError('Periodic structure has no valid three-dimensional cell for CIF export.')
    descriptor, filename = tempfile.mkstemp(prefix='.lele-convert-', suffix='.'+target, dir=path.parent)
    os.close(descriptor);temporary = Path(filename);reserved = False
    try:
        notices = export_frame(frame, temporary, target, occupancy_policy=occupancy_policy)
        check_load_cancelled()
        _reserve(path);reserved = True
        os.replace(temporary, path);reserved = False
        return notices
    finally:
        temporary.unlink(missing_ok=True)
        if reserved:path.unlink(missing_ok=True)


def _camera_copy(camera):
    if camera is None:return None
    from vtkmodules.vtkRenderingCore import vtkCamera
    saved = vtkCamera();saved.DeepCopy(camera);saved.Modified()
    return saved


class BatchExportActions:
    def _batch_import_pending(self):
        return bool(getattr(self, '_file_batch_active', None) is not None
                    or getattr(self, '_file_load_active', None) is not None
                    or getattr(self, '_file_load_sync_active', False)
                    or getattr(self, '_file_load_drain_pending', False)
                    or getattr(self, '_file_load_queue', ())
                    or getattr(self, '_pending_open_paths', ()))

    def _batch_check(self):
        if getattr(self, '_closing', False):raise ValueError('The window is closing.')
        if getattr(self, '_batch_exporting', False) or getattr(self, '_png_exporting', False) or getattr(self, '_gif_exporting', False):
            raise ValueError('Another export is already running.')
        if self._batch_import_pending():raise ValueError('Wait for all file imports to finish before exporting all files.')
        if not self.documents:raise ValueError('Open one or more structure files first.')

    def _batch_enable_actions(self):
        enabled = bool(any(doc.frames for doc in self.documents) and not getattr(self, '_closing', False)
                       and not getattr(self, '_batch_exporting', False))
        for name in ('convert_all_action', 'export_png_all_action'):
            action = getattr(self, name, None)
            if action is not None:action.setEnabled(enabled)

    def _batch_frames(self, *, images=False):
        """Capture source frame choices before the GUI or worker starts iterating."""
        self._remember_document_view()
        entries = [];skipped = []
        for index, document in enumerate(list(self.documents)):
            state = self._document_views.get(id(document))
            number = self.frame_index if index == self.current_doc else getattr(state, 'frame_index', 0)
            number = max(0, min(int(number), max(0, len(document.frames)-1)))
            frame = self.frame if index == self.current_doc else (document.frames[number] if document.frames else None)
            valid = frame is not None and not frame.info.get('missing_geometry')
            if valid and not frame.symbols:valid = bool(images and document.volume is not None)
            if not valid:
                skipped.append(f'{document.path.name}: no current structure to export')
                continue
            entries.append((index, document, number, frame if images else frame.clone()))
        return entries, skipped

    def _batch_feedback(self, title, result):
        self._last_batch_result = result
        self.statusBar().showMessage(result.summary().split('\n',1)[0], 10000)
        QMessageBox.information(self, title, result.summary())

    def convert_all_dialog(self):
        try:self._batch_check()
        except ValueError as exc:
            QMessageBox.information(self, 'Convert all', str(exc));return
        directory = QFileDialog.getExistingDirectory(self, 'Convert all — output folder', str(self.doc.path.parent))
        if not directory:return
        entries, _ = self._batch_frames()
        from .site_occupancy import is_disordered
        policy = 'error'
        if any(not any(frame.pbc) and is_disordered(frame) for _, _, _, frame in entries):
            from .structure_edit_dialogs import confirm_maximum_occupancy_export
            if not confirm_maximum_occupancy_export(self):return
            policy = 'maximum'
        try:result = self._run_batch_convert(directory, occupancy_policy=policy)
        except Exception as exc:
            QMessageBox.warning(self, 'Convert all failed', str(exc));return
        self._batch_feedback('Convert all', result)

    def export_png_all_dialog(self):
        try:self._batch_check()
        except ValueError as exc:
            QMessageBox.information(self, 'Export PNG all', str(exc));return
        directory = QFileDialog.getExistingDirectory(self, 'Export PNG all — output folder', str(self.doc.path.parent))
        if not directory:return
        self._ensure_3d_view()
        from .png_dialog import PngExportDialog
        dialog = PngExportDialog(self, view_size=self.vtk.GetRenderWindow().GetSize(),
            title='Export PNG all — image quality',
            note='Save one PNG per open structure, using its remembered frame, camera, colors and labels. Existing files are kept.')
        if dialog.exec() != QDialog.DialogCode.Accepted:return
        try:result = self._run_batch_png(directory, dialog.settings())
        except Exception as exc:
            QMessageBox.warning(self, 'Export PNG all failed', str(exc));return
        self._batch_feedback('Export PNG all', result)

    def _run_batch_convert(self, directory, *, occupancy_policy='error', cancelled=None, progress=None):
        from .operations import run_data_task
        from .output_text import check_load_cancelled, load_progress, LoadCancelled
        self._batch_check()
        directory = Path(directory)
        if not directory.is_dir():raise ValueError('Choose an existing output folder.')
        entries, skipped = self._batch_frames()
        documents = [e[1] for e in entries]
        targets = ['cif' if any(e[3].pbc) else 'xyz' for e in entries]
        paths = allocate_paths(documents, directory, ['.'+t for t in targets])
        result = BatchResult(skipped=skipped)
        self._batch_exporting = True
        self._batch_enable_actions()
        def convert():
            report = load_progress('Converting all structures', len(entries))
            for i, ((_, document, _, frame), target, path) in enumerate(zip(entries, targets, paths)):
                if cancelled is not None and cancelled():result.cancelled=True;break
                check_load_cancelled()
                label = f'Converting {document.path.name} ({i+1}/{len(entries)})'
                report(i)
                if progress is not None:progress(label, i, len(entries))
                try:
                    _write_structure(frame, path, target, occupancy_policy)
                    result.exported.append(path)
                except LoadCancelled:raise
                except Exception as exc:result.failures.append(f'{document.path.name}: {exc}')
            if not result.cancelled:report(len(entries))
        try:
            try:run_data_task(self, 'Converting all structures', convert, cancellable=True)
            except LoadCancelled:result.cancelled=True
        finally:
            self._batch_exporting = False
            self._batch_enable_actions()
            self._last_batch_result = result
        return result

    def _batch_scene_snapshot(self):
        self._remember_document_view()
        camera = None if self.scene is None else _camera_copy(self.scene.GetActiveCamera())
        views = {}
        for key, view in self._document_views.items():
            views[key] = (view, view.frame_index, _camera_copy(view.camera), deepcopy(view.options),
                          deepcopy(view.custom_style), view.preset)
        return dict(document=self.current_doc, frame=self.frame_index, camera=camera,
            selection=list(self.selection), sequence=getattr(self,'_result_sequence',None),
            vibration=self._active_vibration, reference=self._vibration_reference,
            phase=self._vibration_phase, energy=self._energy_only_context,
            plane=self._plane_fit, plane_context=self._plane_context,
            preview=None if self.renderer is None else self.renderer.periodic_preview,
            views=views, playing=self.playback.isActive(), vibrating=self.vibration_timer.isActive(),
            tabs=[(widget,widget.currentIndex()) for widget in (self.tabs,self.sidebar_tabs,self.bottom_control_tabs)],
            tree_item=self.files_tree.currentItem(),
            tree_scroll=(self.files_tree.verticalScrollBar().value(),self.files_tree.horizontalScrollBar().value()),
            annotation=(getattr(self,'_annotation_document',None),getattr(self,'_selected_annotation',None),
                        getattr(self,'_pending_annotation',None),getattr(self,'_annotation_gesture',None)),
            pointer=(getattr(self,'_pending_paste',None),getattr(self,'_fragment_gesture',None),
                     self.box_select_action.isChecked(),self.surface_hide_check.isChecked()))

    def _restore_batch_scene(self, state):
        """Restore source/mode first, then selection, overlays and the exact camera."""
        if getattr(self, '_closing', False):return
        from dataclasses import fields
        # Refresh may normalize display options; restore the original objects
        # so external references and each document's saved settings survive.
        for view, number, camera, options, custom, preset in state['views'].values():
            for member in fields(options):setattr(view.options, member.name, deepcopy(getattr(options,member.name)))
            view.frame_index = number;view.camera = _camera_copy(camera)
            view.custom_style = deepcopy(custom);view.preset = preset
        self._result_sequence = state['sequence']
        self.change_frame(state['frame'], switch_doc=state['document'])
        if state['vibration'] is not None:
            self.select_vibration(*state['vibration'], autoplay=False)
            self._vibration_reference = state['reference']
            self._vibration_phase = state['phase']
        if state['energy'] is not None:
            self._energy_only_context = state['energy'];self._show_results_only()
        self.selection = list(state['selection'])
        self._plane_fit = state['plane'];self._plane_context = state['plane_context']
        if self.renderer is not None:self.renderer.periodic_preview = state['preview']
        self._annotation_document,self._selected_annotation,self._pending_annotation,self._annotation_gesture = state['annotation']
        self._pending_view_camera = _camera_copy(state['camera'])
        self._sync_selection_to_table();self.refresh_scene()
        if state['camera'] is not None and self.scene is not None:
            self.scene.GetActiveCamera().DeepCopy(state['camera'])
            self.scene.GetActiveCamera().Modified()
            self.vtk.GetRenderWindow().Render()
        # _activate_document remembered the last export view on departure.
        for view, number, camera, _, custom, preset in state['views'].values():
            view.frame_index=number;view.camera=_camera_copy(camera)
            view.custom_style=deepcopy(custom);view.preset=preset
        self.box_select_action.setChecked(state['pointer'][2])
        self.surface_hide_check.setChecked(state['pointer'][3])
        self._pending_paste,self._fragment_gesture = state['pointer'][:2]
        self._pending_annotation,self._annotation_gesture = state['annotation'][2:]
        for widget,index in state['tabs']:
            with QSignalBlocker(widget):widget.setCurrentIndex(index)
        with QSignalBlocker(self.files_tree):self.files_tree.setCurrentItem(state['tree_item'])
        self.files_tree.verticalScrollBar().setValue(state['tree_scroll'][0])
        self.files_tree.horizontalScrollBar().setValue(state['tree_scroll'][1])
        if state['playing']:
            self.playback.start(1000 // self.fps_spin.value());self.play_btn.setText('Pause')
        if state['vibrating'] and self._active_vibration == state['vibration']:
            self._vibration_clock.start();self.vibration_timer.start()
            self.vibration_controls.play_button.setText('Pause')

    def _run_batch_png(self, directory, settings, *, cancelled=None, progress=None):
        from .operations import ui_operation, ui_checkpoint
        from .png_export import export_png
        self._batch_check()
        directory=Path(directory)
        if not directory.is_dir():raise ValueError('Choose an existing output folder.')
        entries, skipped = self._batch_frames(images=True)
        paths = allocate_paths([e[1] for e in entries], directory, ['.png']*len(entries))
        jobs = list(zip(entries, paths))
        # Preserve the current vibration phase, selection and temporary plane.
        jobs.sort(key=lambda job:job[0][0] != self.current_doc)
        state=self._batch_scene_snapshot();result=BatchResult(skipped=skipped)
        self._batch_exporting=True
        self._batch_enable_actions()
        self.playback.stop();self.vibration_timer.stop()
        try:
            with ui_operation(self, 'Exporting all PNG images') as dialog:
                self._batch_progress=dialog
                if dialog is not None:
                    dialog.cancellable=True;dialog.setCancelButtonText('Cancel');dialog.show()
                for i, ((index, document, number, _), path) in enumerate(jobs):
                    QApplication.processEvents()
                    if (getattr(self,'_closing',False) or (cancelled is not None and cancelled())
                            or (dialog is not None and dialog.wasCanceled())):
                        result.cancelled=True;break
                    label=f'Exporting {document.path.name} ({i+1}/{len(jobs)})'
                    if progress is not None:progress(label,i,len(jobs))
                    ui_checkpoint(label,i,len(jobs))
                    reserved=False
                    try:
                        if index != state['document']:
                            self.change_frame(number,switch_doc=index,reset_camera=False)
                        _reserve(path);reserved=True
                        export_png(path, self.vtk.GetRenderWindow(), settings,
                            mesh_items=self.renderer._keepalive, progress=ui_checkpoint)
                        reserved=False;result.exported.append(path)
                    except Exception as exc:
                        result.failures.append(f'{document.path.name}: {exc}')
                    finally:
                        if reserved:path.unlink(missing_ok=True)
                if not result.cancelled:ui_checkpoint('PNG export finished',len(jobs),len(jobs))
        finally:
            try:self._restore_batch_scene(state)
            except Exception as exc:result.failures.append('Restoring original view: '+str(exc))
            self._batch_exporting=False;self._batch_progress=None;self._last_batch_result=result
            self._batch_enable_actions()
        return result
