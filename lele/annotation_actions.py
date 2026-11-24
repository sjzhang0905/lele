"""Canvas-text actions; keep scientific/VTK imports lazy for first paint."""
from copy import deepcopy
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu
from .dialog_policy import QDialog, QInputDialog


class AnnotationActions:
    def _install_annotation_actions(self):
        self._annotation_manager = None
        self._annotation_document = None
        self._selected_annotation = None
        self._pending_annotation = None
        self._annotation_gesture = None
        menu = self.edit_menu.addMenu('Canvas text')
        self.add_text_action = self._action(menu, 'Add text…', self.add_canvas_text)
        self.edit_text_action = self._action(menu, 'Edit selected text…', self.edit_canvas_text)
        self.delete_text_action = self._action(menu, 'Delete selected text', self.delete_canvas_text)
        self.manage_text_action = self._action(menu, 'Choose text…', self.choose_canvas_text)
        for action in (self.add_text_action, self.edit_text_action, self.delete_text_action, self.manage_text_action):
            action.setEnabled(False)

    def _sync_annotations(self):
        doc = self.doc
        if doc is not self._annotation_document:
            self._annotation_document = doc
            self._selected_annotation = None
            self._pending_annotation = None
            self._annotation_gesture = None
        if self.selection:
            self._selected_annotation = None
            self._annotation_gesture = None
        available = doc is not None and self.frame is not None
        items = doc.annotations if available else []
        if self._selected_annotation is not None and not 0 <= self._selected_annotation < len(items):
            self._selected_annotation = None
        self.add_text_action.setEnabled(available)
        self.edit_text_action.setEnabled(self._selected_annotation is not None)
        self.delete_text_action.setEnabled(self._selected_annotation is not None)
        self.manage_text_action.setEnabled(bool(items))
        if self.scene is None:
            return
        if self._annotation_manager is None:
            from .annotations import AnnotationRenderer
            self._annotation_manager = AnnotationRenderer(self.scene)
        from .annotations import EspExtremum, extremum_display_transform
        transform = (extremum_display_transform(doc.volume, self.renderer)
                     if any(isinstance(a, EspExtremum) for a in items) else None)
        self._annotation_manager.set_annotations(items, self._selected_annotation, transform)

    def _render_annotations(self):
        self._sync_annotations()
        if self.scene is not None:
            self.scene.ResetCameraClippingRange()
            self.vtk.GetRenderWindow().Render()

    def _annotation_display_point(self, x, y):
        from .interaction import vtk_display_from_qt
        width, height = self.vtk.GetRenderWindow().GetSize()
        return vtk_display_from_qt(x, y, self.vtk.width(), self.vtk.height(), width, height)

    def _annotation_pick_index(self, x, y):
        manager = self._annotation_manager
        if manager is None or not manager.actors:
            return None
        try:
            return manager.pick(*self._annotation_display_point(x, y))
        except ValueError:
            # The native render window can still be 0 x 0 before first show.
            return None

    def _annotation_world_point(self, x, y):
        import numpy as np
        dx, dy = self._annotation_display_point(x, y)
        center = self.scene.GetActiveCamera().GetFocalPoint()
        self.scene.SetWorldPoint(*center, 1.)
        self.scene.WorldToDisplay()
        depth = self.scene.GetDisplayPoint()[2]
        self.scene.SetDisplayPoint(dx, dy, depth)
        self.scene.DisplayToWorld()
        point = np.asarray(self.scene.GetWorldPoint(), float)
        return (point[:3] / point[3]).tolist()

    def _record_annotation_undo(self):
        self.undo_stack.append(('annotation', self.current_doc, self.frame_index,
                                deepcopy(self.doc.annotations), self._selected_annotation))
        self.undo_stack = self.undo_stack[-50:]

    def _undo_annotation_item(self, item):
        if item[0] != 'annotation':
            return False
        _, document, frame, annotations, selected = item
        self.documents[document].annotations = annotations
        self.change_frame(frame, switch_doc=document)
        self._selected_annotation = selected
        self._render_annotations()
        return True

    def _can_add_esp_extrema(self, document):
        if not document.frames or not document.volumes:
            return False
        from .field_mapping import is_esp_field
        from .field_pair import TITLES
        if document.format_name == TITLES['esp']:
            return True
        # Manual surface mapping belongs to the clicked file's own view.
        view = self._document_views.get(id(document))
        if view is None:
            return False
        for layer in view.options.volume_surfaces:
            mapped = layer.get('map_dataset', -1)
            if 0 <= mapped < len(document.volumes):
                source = document.volumes[mapped]
                surface = layer.get('dataset', -1)
                if (surface != mapped and (surface >= 0 or document.volume is not source)
                        and is_esp_field(source)):
                    return True
        return False

    def _add_esp_extrema(self, document):
        from .esp_extrema_dialog import EspExtremaDialog
        from .color_controls import color_value
        if self._document_index(document) is None or not self._can_add_esp_extrema(document):
            return False
        view = self._document_views.get(id(document))
        options = view.options if view is not None else self.render_options
        name = self._document_labels.get(id(document), document.path.name)
        dialog = EspExtremaDialog(document, name, options.label_color, self)
        try:
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.rows is None:
                return False
            return self._place_esp_extrema(document, dialog.rows, dialog.unit.currentData(),
                                           dialog.height.value(), color_value(dialog.color))
        finally:
            dialog.deleteLater()

    def _place_esp_extrema(self, document, rows, unit, height, color):
        import numpy as np
        from .annotations import extremum_display_transform
        from .esp_extrema import make_extremum_labels
        from .fragment import camera_basis
        index = self._document_index(document)
        if self._closing or index is None or not self._can_add_esp_extrema(document):
            return False
        if document is not self.doc or self.frame is None or self._active_vibration is not None:
            view = self._document_views.get(id(document))
            self.change_frame(view.frame_index if view is not None else 0, switch_doc=index)
        if document is not self.doc or self.scene is None:
            return False
        forward, right, up = camera_basis(self.scene.GetActiveCamera())
        rotation, _ = extremum_display_transform(document.volume, self.renderer)
        labels = make_extremum_labels(rows, unit, height, color,
                                      np.column_stack((right, up, -forward)), rotation)
        self.cancel_pointer_action()
        self._record_annotation_undo()
        document.annotations.extend(labels)
        self._selected_annotation = None
        self._render_annotations()
        self.statusBar().showMessage(f'Added {len(labels)} ESP extrema. Right-click a value to edit its label.', 7000)
        return True

    def add_canvas_text(self, _checked=False, *, at=None):
        if self.doc is None or self.frame is None or self.scene is None:
            return False
        from .annotations import TextAnnotation
        from .annotation_dialog import AnnotationDialog
        from .fragment import camera_basis
        import numpy as np
        forward, right, up = camera_basis(self.scene.GetActiveCamera())
        # Face the camera only on creation. Later camera rotation also rotates
        # the text on screen because this is an ordinary world-space object.
        default = TextAnnotation('Text', rotation=np.column_stack((right, up, -forward)).tolist())
        dialog = AnnotationDialog(default, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        annotation = dialog.result_annotation()
        self.cancel_pointer_action()
        if at is None:
            self._pending_annotation = annotation
            self._selected_annotation = None
            self.statusBar().showMessage('Click the canvas to place text. Esc cancels.', 0)
        else:
            annotation.position = self._annotation_world_point(*at)
            self._append_annotation(annotation)
        return True

    def _append_annotation(self, annotation):
        annotation.__post_init__()
        self._record_annotation_undo()
        self.doc.annotations.append(annotation)
        self._selected_annotation = len(self.doc.annotations)-1
        self.selection.clear()
        self._sync_selection_to_table()
        self.refresh_scene()
        self.statusBar().showMessage('Text added. Alt + middle drag moves; Alt + left rotates; Alt + right rolls. Right-click to edit.', 7000)

    def _pick_annotation_from_canvas(self, x, y):
        if self.doc is None or self.frame is None or self.scene is None:
            return False
        if self._pending_annotation is not None:
            annotation = self._pending_annotation
            try:
                annotation.position = self._annotation_world_point(x, y)
            except ValueError:
                return False
            self._pending_annotation = None
            self._append_annotation(annotation)
            return True
        manager = self._annotation_manager
        if manager is None:
            return False
        index = self._annotation_pick_index(x, y)
        if index is None:
            if self._selected_annotation is not None:
                self._selected_annotation = None
                self._render_annotations()
            return False
        self._selected_annotation = index
        self.selection.clear();self._sync_selection_to_table();self.refresh_scene()
        from .annotations import EspExtremum
        message = ('ESP label selected. Alt + middle drag moves the label.'
                   if isinstance(self.doc.annotations[index], EspExtremum)
                   else 'Text selected. Alt + middle drag moves; Alt + left rotates; Alt + right rolls.')
        self.statusBar().showMessage(message, 5000)
        return True

    def _clear_annotation_selection(self):
        self._selected_annotation = None
        self._annotation_gesture = None
        if self._annotation_manager is not None:
            self._render_annotations()

    def _cancel_annotation_placement(self):
        active = self._pending_annotation is not None
        self._pending_annotation = None
        self._annotation_gesture = None
        return active

    def edit_canvas_text(self, _checked=False):
        index = self._selected_annotation
        if self.doc is None or index is None or not 0 <= index < len(self.doc.annotations):
            return False
        from .annotation_dialog import AnnotationDialog
        dialog = AnnotationDialog(self.doc.annotations[index], self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._record_annotation_undo()
        self.doc.annotations[index] = dialog.result_annotation()
        self._render_annotations()
        return True

    def delete_canvas_text(self, _checked=False):
        index = self._selected_annotation
        if self.doc is None or index is None or not 0 <= index < len(self.doc.annotations):
            return False
        self._record_annotation_undo()
        del self.doc.annotations[index]
        self._selected_annotation = None;self._annotation_gesture = None
        self._render_annotations()
        return True

    def choose_canvas_text(self):
        if self.doc is None or not self.doc.annotations:
            return
        labels = [f'{i+1}: {item.text.replace(chr(10), " ")[:70]}' for i, item in enumerate(self.doc.annotations)]
        value, ok = QInputDialog.getItem(self, 'Canvas text', 'Choose text to edit:', labels, 0, False)
        if ok:
            self._selected_annotation = labels.index(value)
            self._render_annotations();self.edit_canvas_text()

    def _annotation_context_from_canvas(self, x, y, *, empty=False):
        if self.doc is None or self.frame is None or self.scene is None:
            return False
        index = self._annotation_pick_index(x, y)
        if index is None and not empty:
            return False
        menu = QMenu(self)
        if index is not None:
            self._selected_annotation = index
            self.selection.clear();self._sync_selection_to_table();self.refresh_scene()
            menu.addAction('Edit text…', self.edit_canvas_text)
            menu.addAction('Delete text', self.delete_canvas_text)
            menu.addSeparator()
        menu.addAction('Add text here…', lambda: self.add_canvas_text(at=(x, y)))
        if empty:
            menu.addAction('Clear selection', self.clear_selection)
        menu.exec(self.vtk.mapToGlobal(QPoint(round(x), round(y))))
        return True

    def _begin_annotation_gesture(self, kind, x, y):
        self._annotation_gesture = None
        if self.doc is None or self.scene is None:
            return False
        index = self._selected_annotation
        if index is None:
            index = self._annotation_pick_index(x, y)
        if index is None or not 0 <= index < len(self.doc.annotations):
            return False
        from .annotations import EspExtremum
        if kind != 'pan' and isinstance(self.doc.annotations[index], EspExtremum):
            self.statusBar().showMessage('ESP labels face the camera. Alt + middle drag moves the label.', 4000)
            return True
        self._selected_annotation = index
        self.selection.clear();self._sync_selection_to_table()
        self.playback.stop();self.vibration_timer.stop()
        self.play_btn.setText('Play')
        self.vibration_controls.play_button.setText('Play')
        self._annotation_gesture = dict(kind=kind, document=self.doc, index=index, edited=False)
        self.refresh_scene()
        return True

    def _move_annotation_gesture(self, kind, dx, dy):
        state = self._annotation_gesture
        if state is None:
            return False
        if state['document'] is not self.doc or kind != state['kind']:
            self._annotation_gesture = None
            return True
        if abs(dx) + abs(dy) < 1e-10:
            return True
        from .fragment import screen_translation, screen_rotation
        from .annotations import EspExtremum, transform_annotation
        if not state['edited']:
            self._record_annotation_undo();state['edited'] = True
        annotation = self.doc.annotations[state['index']]
        camera = self.scene.GetActiveCamera()
        if kind == 'pan':
            anchor = annotation.position
            basis = None
            if isinstance(annotation, EspExtremum):
                basis = self._annotation_manager.extremum_rotation
                anchor = anchor @ basis + self._annotation_manager.extremum_shift
            delta = screen_translation(camera, dx, dy, self.vtk.height(), anchor)
            transform_annotation(annotation, translation=delta if basis is None else delta @ basis.T)
        else:
            transform_annotation(annotation, rotation=screen_rotation(camera, kind, dx, dy))
        self._annotation_manager.update_transform(state['index'])
        self.scene.ResetCameraClippingRange()
        self.vtk.GetRenderWindow().Render()
        return True

    def _end_annotation_gesture(self, kind):
        if self._annotation_gesture is None:
            return False
        self._annotation_gesture = None
        self.statusBar().showMessage('Text moved. Ctrl+Z to undo.' if kind == 'pan'
                                     else 'Text rotated. Ctrl+Z to undo.', 4000)
        return True
