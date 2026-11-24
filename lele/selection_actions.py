"""Named selections in the current frame, with stable atom-order editing."""
from .dialog_policy import QDialog, QMessageBox


class SelectionActions:
    def set_selected_atoms_fixed(self, fixed):
        if self.frame is None or not self.selection or self._text_editor_active() or not self._geometry_edit_allowed():
            return
        from .atom_constraints import edited_constraints
        try:
            updates = edited_constraints(self.frame, self.selection, fixed)
        except ValueError as exc:
            QMessageBox.warning(self, 'Fixed atoms', str(exc))
            return
        if updates:
            self._pause_selection_playback()
            self._record_fragment_metadata_undo()
            self.frame.info.update(updates)
            self._refresh_selection_panels()
        verb = 'Fixed' if fixed else 'Cleared fixed axes on'
        self.statusBar().showMessage(f'{verb} {len(self.selection)} selected atom(s) in this frame.', 6000)

    def select_fixed_atoms(self):
        if self.frame is None or self._text_editor_active():
            return
        from .atom_constraints import fixed_atom_indices
        try:
            indices = fixed_atom_indices(self.frame)
        except ValueError as exc:
            QMessageBox.warning(self, 'Fixed atoms', str(exc))
            return
        self._pause_selection_playback()
        self.select_named_fragment(indices)
        self.statusBar().showMessage(f'Selected {len(indices)} fully fixed atom(s) in this frame.', 6000)

    def select_by_expression(self, text):
        """Evaluate against a captured source selection; commit only on success."""
        from .selection_expression import evaluate_selection_expression
        from .operations import run_data_task
        from .output_text import LoadCancelled
        frame = self.frame
        if frame is None:
            self.atoms_selection_panel.set_expression_error('Open a structure before selecting atoms.')
            return False
        document = self.doc
        selected = tuple(self.selection)
        snapshot = frame.clone()
        from copy import deepcopy
        for key in ('site_occupancies', 'atom_source_order'):
            if key in snapshot.info:snapshot.info[key] = deepcopy(snapshot.info[key])
        try:
            indices = run_data_task(self, 'Selecting atoms by expression',
                lambda: evaluate_selection_expression(snapshot, text, selected), cancellable=True)
        except LoadCancelled:
            self.statusBar().showMessage('Selection cancelled; previous selection retained.', 5000)
            return False
        except ValueError as exc:
            self.atoms_selection_panel.set_expression_error(str(exc))
            self.statusBar().showMessage('Selection expression was not applied.', 5000)
            return False
        import numpy as np
        unchanged = (not self._closing and self.doc is document and self.frame is frame
                     and tuple(self.selection) == selected and frame.symbols == snapshot.symbols
                     and tuple(frame.pbc) == tuple(snapshot.pbc)
                     and np.array_equal(frame.positions, snapshot.positions)
                     and np.array_equal(frame.cell, snapshot.cell)
                     and all(frame.info.get(key) == snapshot.info.get(key)
                             for key in ('site_occupancies', 'atom_source_order')))
        if not unchanged:
            self.statusBar().showMessage('Source structure or selection changed; apply the expression again.', 5000)
            return False
        self.atoms_selection_panel.set_expression_error('')
        self.select_named_fragment(indices)
        self.statusBar().showMessage(f'Selected {len(indices)} atom(s) by expression. Ctrl+Z to undo.', 5000)
        return True

    def show_selection_expression_help(self, _checked=False):
        from PySide6.QtWidgets import QVBoxLayout, QPlainTextEdit, QPushButton
        from PySide6.QtGui import QFontDatabase
        from .selection_expression import SELECTION_EXPRESSION_HELP
        dialog = QDialog(self)
        dialog.setWindowTitle('Atom selection expression syntax')
        dialog.resize(800, 650)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        text.setPlainText(SELECTION_EXPRESSION_HELP)
        layout.addWidget(text)
        close = QPushButton('Close');close.clicked.connect(dialog.close)
        layout.addWidget(close)
        return self._show_analysis_window(dialog)

    def rotate_about_selected_axis(self):
        if self.frame is None or len(self.selection) < 2 or not self._geometry_edit_allowed():
            return
        from .rotation_dialog import RotationDialog
        from .rotation_preview import RotationPreview
        dialog = RotationDialog(self.frame, self.selection, parent=self)
        preview = RotationPreview(self, dialog)
        try:
            return preview.finish(dialog.exec() == QDialog.DialogCode.Accepted)
        finally:
            preview.finish(False)
            dialog.deleteLater()

    def set_selected_dihedral(self):
        if self.frame is None or len(self.selection) != 4 or not self._geometry_edit_allowed():
            return
        from .core import measure
        from .rotation_dialog import RotationDialog
        try:
            _, current = measure(self.frame, self.selection)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, 'Cannot set dihedral', str(exc))
            return
        dialog = RotationDialog(self.frame, self.selection, dihedral=current, parent=self)
        from .rotation_preview import RotationPreview
        preview = RotationPreview(self, dialog, dihedral=True)
        try:
            return preview.finish(dialog.exec() == QDialog.DialogCode.Accepted)
        finally:
            preview.finish(False)
            dialog.deleteLater()

    def _commit_rotation_edit(self, edit, message):
        import numpy as np
        if np.allclose(self.frame.positions, edit.positions, atol=1.e-12, rtol=0):
            return False
        self.playback.stop()
        self.play_btn.setText('Play')
        self._record_undo()
        self.frame.positions[:] = edit.positions
        if edit.periodic_edges is not None:
            self.frame.periodic_bond_snapshot = edit.periodic_edges
        self.frame.hbond_added = edit.hbond_added
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(message + f'; moved {len(edit.moving)} atom(s). Ctrl+Z to undo.', 6000)
        return True

    def apply_axis_rotation(self, degrees):
        if self.frame is None or len(self.selection) < 2 or not self._geometry_edit_allowed():
            return False
        from .axis_rotation import plan_axis_rotation
        try:
            if abs(float(degrees) % 360) < 1.e-12:
                return False
            edit = plan_axis_rotation(self.frame, self.selection, degrees, self.render_options.bond_cutoff)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, 'Cannot rotate fragment', str(exc))
            return False
        return self._commit_rotation_edit(edit, f'Rotated about selected axis by {degrees:.4f}°')

    def apply_selected_dihedral(self, target):
        if self.frame is None or len(self.selection) != 4 or not self._geometry_edit_allowed():
            return False
        from .core import measure
        from .internal_coordinates import plan_internal_edit
        try:
            _, current = measure(self.frame, self.selection)
            if abs((float(target) - current + 180) % 360 - 180) < 1.e-10:
                return False
            edit = plan_internal_edit(self.frame, self.selection, target, self.render_options.bond_cutoff)
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, 'Cannot set dihedral', str(exc))
            return False
        return self._commit_rotation_edit(edit, f'Set dihedral to {target:.4f}°')

    def _record_fragment_metadata_undo(self):
        # Saving a selection does not alter geometry or inferred bonds.
        frame, volume = self.frame, self.doc.volume
        geometry = None if volume is None else (volume.origin.copy(), volume.voxel_vectors.copy())
        self.undo_stack.append((self.current_doc, self.frame_index, frame.clone(),
                               geometry, list(self.selection), volume, self._active_vibration))
        self.undo_stack = self.undo_stack[-50:]

    def _refresh_selection_panels(self):
        frame = self.frame
        self.selection_panel.set_frame(frame, self.selection)
        editable = (frame is not None and self._active_vibration is None
                    and not self._alignment_enabled())
        self.fragment_panel.set_frame(frame, self.selection, editable=editable)
        self.atoms_selection_panel.set_frame(frame, options=self.render_options)
        self.apply_coordinates_action.setEnabled(bool(editable and frame.symbols))
        self.fix_atoms_action.setEnabled(bool(editable and self.selection))
        self.unfix_atoms_action.setEnabled(bool(editable and self.selection))
        self.select_fixed_action.setEnabled(bool(frame is not None and frame.symbols))

    def save_named_fragment(self):
        if self.frame is None or not self.selection or not self._geometry_edit_allowed():
            return
        from .saved_fragments import add_fragment
        self._record_fragment_metadata_undo()
        record = add_fragment(self.frame, self.selection)
        self.doc.modified = True
        self._refresh_selection_panels()
        self.fragment_panel.select_fragment_name(record['name'])
        self.statusBar().showMessage(f"Saved {record['name']} ({len(record['indices'])} atoms). Ctrl+Z to undo.", 5000)

    def fragment_slot_shortcut(self, operation, slot):
        """Canvas signal entry point; numbered slots use normal frame metadata."""
        if self.frame is None or self.doc is None:
            return
        from .saved_fragments import fragment_slot_name, get_fragment, save_fragment_slot
        try:
            name = fragment_slot_name(slot)
        except ValueError:
            return
        if operation == 'select':
            try:
                record = get_fragment(self.frame, name)
            except ValueError:
                self.statusBar().showMessage(f'{name} has not been saved in this frame.', 3500)
                return
            self.select_named_fragment(record['indices'])
            self.fragment_panel.select_fragment_name(name)
            self.statusBar().showMessage(f'Selected {name} ({len(record["indices"])} atoms).', 3500)
            return
        if operation not in ('save', 'append') or not self._geometry_edit_allowed():
            return
        if not self.selection:
            self.statusBar().showMessage('Select one or more atoms before saving a fragment.', 3500)
            return
        # Validate and compare without changing live metadata, so a no-op does
        # not consume undo history or mark an otherwise clean document dirty.
        from copy import copy
        candidate = copy(self.frame)
        try:
            record, changed = save_fragment_slot(candidate, slot, self.selection,
                                                  append=operation == 'append')
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 5000)
            return
        if changed:
            self._record_fragment_metadata_undo()
            self.frame.info = candidate.info
            self.doc.modified = True
        self._refresh_selection_panels()
        self.fragment_panel.select_fragment_name(name)
        verb = 'Updated' if operation == 'append' else 'Saved'
        suffix = ' Ctrl+Z to undo.' if changed else ' Already up to date.'
        self.statusBar().showMessage(f'{verb} {name} ({len(record["indices"])} atoms).{suffix}', 5000)

    def delete_named_fragment(self, name):
        if self.frame is None or not self._geometry_edit_allowed():
            return
        from .saved_fragments import get_fragment, remove_fragment
        try:
            get_fragment(self.frame, name)
        except ValueError:
            # A queued UI action can outlive a frame switch or an undo.
            self._refresh_selection_panels()
            return
        self._record_fragment_metadata_undo()
        remove_fragment(self.frame, name)
        self.doc.modified = True
        self._refresh_selection_panels()
        self.statusBar().showMessage(f'Deleted {name}. Ctrl+Z to undo.', 5000)

    def select_named_fragment(self, indices):
        if self.frame is None:
            return
        indices = sorted({int(i) for i in indices if 0 <= int(i) < len(self.frame.symbols)})
        if indices != self.selection:
            self._record_selection_undo()
        self.selection = indices
        if self.renderer is not None:
            self.renderer.periodic_preview = None
        self._sync_selection_to_table()
        self.refresh_scene()

    def move_named_fragment(self, name, destination):
        if self.frame is None or not self._geometry_edit_allowed():
            return
        from .saved_fragments import fragment_order
        from .atom_indices import reorder_atoms
        try:
            order = fragment_order(self.frame, name, destination)
        except ValueError as exc:
            QMessageBox.warning(self, 'Could not reorder fragment', str(exc))
            return
        if order == list(range(len(self.frame.symbols))):
            return
        self._record_undo()
        mapping = reorder_atoms(self.frame, order)
        self.selection = [mapping[i] for i in self.selection]
        self.doc.modified = True
        self._refresh_after_geometry_edit(preserve_results=True)
        self.fragment_panel.select_fragment_name(name)
        self.statusBar().showMessage(f'Moved {name} to the {destination}; atom order and selections updated. Ctrl+Z to undo.', 7000)
