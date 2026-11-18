"""File-tree actions operate on loaded documents, never on source-file bytes."""
from pathlib import Path

from PySide6.QtCore import Qt, QSignalBlocker, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMenu

from .dialog_policy import QFileDialog, QInputDialog, QMessageBox
from .operations import run_data_task, ui_busy
from .output_text import LoadCancelled


def remap_undo_after_unload(items, removed):
    """Retain other documents' edit histories after compacting document indices."""
    def shifted(value):
        return value - (value > removed)

    def vibration(value):
        return (shifted(value[0]), *value[1:]) if value is not None else None

    result = []
    for item in items:
        row = list(item)
        named = isinstance(row[0], str)
        index_slot = 1 if named else 0
        if row[index_slot] == removed:
            continue
        row[index_slot] = shifted(row[index_slot])
        if not named:
            row[6] = vibration(row[6])
        elif row[0] in ('selection', 'appearance'):
            row[4] = vibration(row[4])
            if row[0] == 'appearance':
                row[5] = [(kind, (shifted(key[0]), *key[1:]) if kind == 'preview' else key, styles)
                          for kind, key, styles in row[5]]
        elif row[0] == 'pair_rules':
            row[7] = vibration(row[7])
        result.append(tuple(row))
    return result


class LoadedDocumentActions:
    def _document_heading(self, document):
        name = self._document_labels.get(id(document), document.path.name)
        kind = document.format_name + (' · results only' if not document.frames else '')
        return f'{name}  ({kind})'

    def _document_index(self, document):
        return next((i for i, candidate in enumerate(self.documents) if candidate is document), None)

    def _loaded_file_menu(self, document):
        menu = QMenu(self.files_tree)
        from .trajectory_link import association_role
        if association_role(document):
            menu.addAction('Associate file…', lambda: self._associate_loaded_file(document))
            menu.addSeparator()
        menu.addAction('Rename…', lambda: self._rename_loaded_document(document))
        menu.addAction('Remove from loaded files', lambda: self._unload_document(document))
        menu.addSeparator()
        menu.addAction('Open containing folder', lambda: self._open_document_folder(document))
        return menu

    def _associate_loaded_file(self, document, filename=None):
        from .trajectory_link import association_role, link_trajectory
        role = association_role(document)
        if not role or self._document_index(document) is None or ui_busy():
            return False
        if filename is None:
            if role == 'output':
                title, types = ('Associate position trajectory',
                                'Position trajectories (*.xyz *.extxyz *.log *.trj);;All files (*)')
            else:
                title, types = ('Associate calculation output',
                                'Calculation outputs (*.out *.log *.output *.txt);;All files (*)')
            filename, _ = QFileDialog.getOpenFileName(self, title, str(document.path.parent), types)
        if not filename:
            return False
        other = Path(filename).expanduser().resolve()
        output, positions = (document.path, other) if role == 'output' else (other, document.path)
        try:
            linked = run_data_task(self, 'Matching trajectory to calculation steps',
                                   lambda: link_trajectory(output, positions), cancellable=True)
        except LoadCancelled:
            return False
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, 'Could not associate files', str(error))
            return False
        if self._closing or self._document_index(document) is None:
            return False
        # Keep independently edited copies, including document annotations.
        companion = next((d for d in self.documents if d is not document and d.path == other
                          and not d.modified and not d.annotations), None)
        primary = document if not document.modified and not document.annotations else companion
        if primary is None:
            self._attach_loaded_document(linked)
        else:
            self._unload_document(primary, replacement=linked)
        if companion is not None and companion is not primary:
            self._unload_document(companion)
        self.statusBar().showMessage(linked.calculation_results.note.split('. ')[0] +
            f' · {linked.trajectory_link["matched"]} matched steps', 8000)
        return True

    def _loaded_file_context_menu(self, position):
        if ui_busy() or self._png_exporting or self._gif_exporting or self._batch_exporting:
            return
        item = self.files_tree.itemAt(position)
        if item is None:
            return
        while item.parent() is not None:
            item = item.parent()
        index = self.files_tree.indexOfTopLevelItem(item)
        if 0 <= index < len(self.documents):
            menu = self._loaded_file_menu(self.documents[index])
            menu.exec(self.files_tree.viewport().mapToGlobal(position))
            menu.deleteLater()

    def _rename_loaded_document(self, document, name=None):
        index = self._document_index(document)
        if index is None:
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self, 'Rename loaded file', 'Display name:',
                text=self._document_labels.get(id(document), document.path.name))
            if not accepted:
                return False
        name = str(name).strip()
        index = self._document_index(document)
        if not name or index is None:
            return False
        self._document_labels[id(document)] = name
        self.files_tree.topLevelItem(index).setText(0, self._document_heading(document))
        return True

    def _open_document_folder(self, document):
        folder = Path(document.path).expanduser().resolve().parent
        if not folder.is_dir():
            QMessageBox.information(self, 'Folder unavailable', f'The source folder is unavailable:\n{folder}')
            return False
        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not opened:
            QMessageBox.warning(self, 'Could not open folder', str(folder))
        return opened

    def _loaded_tree_expansion_state(self):
        # Lazy item callbacks capture document indices, so rebuilding is safer
        # than changing the data role on only the currently materialized items.
        expanded = {}
        def collect(item, path, paths):
            if item.isExpanded():
                paths.add(path)
                for k in range(item.childCount()):
                    child = item.child(k)
                    collect(child, path + (child.text(0),), paths)
        for index, document in enumerate(self.documents):
            head = self.files_tree.topLevelItem(index)
            paths = set()
            if head is not None:
                collect(head, (), paths)
            expanded[id(document)] = paths
        return expanded

    def _replace_loaded_document_tree(self, expanded):
        from .workflow_ui import expand_tree_item
        def restore(item, path, paths):
            item.setExpanded(path in paths)
            if path in paths:
                expand_tree_item(item)
                for k in range(item.childCount()):
                    child = item.child(k)
                    restore(child, path + (child.text(0),), paths)
        with QSignalBlocker(self.files_tree):
            self.files_tree.clear()
            self._frame_tree_items = {}; self._vibration_tree_items = {}
            self._series_tree_items = {}; self._sequence_pages = {}; self._tree_sequences = {}
            for index, document in enumerate(self.documents):
                self._add_document_tree(index, document)
                restore(self.files_tree.topLevelItem(index), (), expanded.get(id(document), {()}))

    def _unload_document(self, document, *, replacement=None):
        index = self._document_index(document)
        if index is None or ui_busy() or self._png_exporting or self._gif_exporting or self._batch_exporting:
            return False
        for dialog in list(self._analysis_windows):
            if getattr(dialog, '_lele_document', None) is document:
                dialog.close()
        active = self.doc
        self._remember_document_view()
        expanded = self._loaded_tree_expansion_state()
        current = self.files_tree.currentItem()
        current_data = None if current is None else current.data(0, Qt.ItemDataRole.UserRole)
        if document is active:
            self.playback.stop(); self.play_btn.setText('Play')
            self._leave_vibration()
            self.selection.clear()
            self.cancel_pointer_action()
            self._fragment_gesture = self._pending_paste = None
            self._energy_only_context = None
            self._view_document = self._scene_document = None
            self._pending_view_camera = None
            self._plane_fit = self._plane_context = None
        shift = 1 if replacement is None else 0
        if replacement is None:
            self.documents.pop(index)
            self.undo_stack = remap_undo_after_unload(self.undo_stack, index)
        else:
            self.documents[index] = replacement
            self.undo_stack = [u for u in self.undo_stack if u[1 if isinstance(u[0], str) else 0] != index]
            state = self._document_views.get(id(document))
            if state is not None and document.frames:
                self._document_views[id(replacement)] = state
            if id(document) in self._document_labels:
                self._document_labels[id(replacement)] = self._document_labels[id(document)]
            expanded[id(replacement)] = {()}
        for name in ('_document_views', '_document_labels', '_trajectory_alignments',
                     '_geometry_parameters', '_sequence_cache'):
            getattr(self, name, {}).pop(id(document), None)
        self._aligned_documents.discard(id(document))
        self._vibration_references = {(di - shift * (di > index), ai): frame
            for (di, ai), frame in self._vibration_references.items() if di != index}
        if self._active_vibration is not None:
            di, *rest = self._active_vibration
            self._active_vibration = (di - shift * (di > index), *rest)
        if self._energy_only_context is not None:
            di, step = self._energy_only_context
            self._energy_only_context = (di - shift * (di > index), step)
        sequence = getattr(self, '_result_sequence', None)
        if sequence is not None and sequence[0] is document:
            self._result_sequence = None
        self.current_doc = (-1 if document is active else self._document_index(active))
        self._replace_loaded_document_tree(expanded)
        if replacement is not None:
            self.change_frame(max(0, len(replacement.frames)-1), switch_doc=index,
                              reset_camera=id(replacement) not in self._document_views)
        elif not self.documents:
            self._show_no_loaded_documents()
        elif document is active:
            next_index = min(index, len(self.documents) - 1)
            next_doc = self.documents[next_index]
            view = self._document_views.get(id(next_doc))
            self.change_frame(getattr(view, 'frame_index', len(next_doc.frames)-1), switch_doc=next_index)
        else:
            # Keep the current view, selected atoms, animation and sequence.
            # Restore the matching energy/mode/frame item without reactivation.
            if current_data:
                wanted = (self.current_doc, *current_data[1:])
                def find(item):
                    if item.data(0, Qt.ItemDataRole.UserRole) == wanted:
                        return item
                    for k in range(item.childCount()):
                        result = find(item.child(k))
                        if result is not None:
                            return result
                    return None
                head = self.files_tree.topLevelItem(self.current_doc)
                target = find(head)
                with QSignalBlocker(self.files_tree):
                    self.files_tree.setCurrentItem(target or head)
        self.statusBar().showMessage(f'Unloaded {document.path.name}', 5000)
        return True

    def _show_no_loaded_documents(self):
        self.current_doc = -1; self.frame_index = 0
        self._project_path = None
        self._result_sequence = None
        self._set_frame_controls_enabled(False)
        self.fps_spin.setEnabled(False); self.charge_spin.setEnabled(False)
        with QSignalBlocker(self.frame_spin):
            self.frame_spin.setRange(0, 0)
        self.frame_count_label.setText('No file loaded')
        self._refresh_coordinates(); self._refresh_element_choices(); self._refresh_measurement()
        self.info_view.clear(); self.summary_label.clear()
        self.results_only_info.clear()
        if self.renderer is not None:
            self.renderer.detach_corner_labels()
            self.renderer.clear()
            self.renderer.frame = self.renderer.source_frame = self.renderer.volume = None
            self.renderer.boundary_display = self.renderer.periodic_preview = None
            self.renderer._boundary_cache = None
        if self.axes_widget is not None and self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        self.refresh_scene(); self._update_gif_action()
        self.canvas_stack.setCurrentWidget(self.welcome_page)
