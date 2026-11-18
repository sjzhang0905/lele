"""Apply an active geometry to a loaded calculation input, with a diff preview."""
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QComboBox, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout
from .dialog_policy import QDialog, QMessageBox

from .operations import run_data_task


class CoordinateUpdateDialog(QDialog):
    def __init__(self, candidates, frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Apply new coordinates')
        self.resize(780, 580)
        self.plan = None
        self.target_document = None
        self._candidates = candidates
        self._frame = frame.clone()
        layout = QVBoxLayout(self)
        label = QLabel('Select a loaded input file. Apply replaces its structure data and keeps a backup of the original.')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.targets = QComboBox()
        for document in candidates:
            self.targets.addItem(str(document.path))
        layout.addWidget(self.targets)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.preview, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        self.apply_button.setAutoDefault(False)
        self.apply_button.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.targets.currentIndexChanged.connect(self._prepare)
        self._prepare()

    def _prepare(self, *_):
        from .coordinate_update import prepare_coordinate_update
        self.plan = None
        self.apply_button.setEnabled(False)
        index = self.targets.currentIndex()
        if index < 0:
            return
        self.target_document = self._candidates[index]
        try:
            plan = run_data_task(self, 'Preparing coordinate changes',
                                 lambda: prepare_coordinate_update(self.target_document.path, self._frame))
        except Exception as exc:
            self.summary.setText(str(exc))
            self.preview.clear()
            return
        self.plan = plan
        self.summary.setText(str(plan.summary))
        self.preview.setPlainText(plan.preview_text)
        self.apply_button.setEnabled(plan.original_bytes != plan.new_bytes)
        if plan.original_bytes == plan.new_bytes:
            self.summary.setText('The input already contains these coordinates and cell.')


class CoordinateUpdateActions:
    def apply_new_coordinates_dialog(self):
        if self.frame is None or not self._geometry_edit_allowed():
            return False
        from .coordinate_update import supported_input_kind
        candidates = []
        seen = set()
        for document in self.documents:
            path = Path(document.path).resolve()
            if path in seen:
                continue
            try:
                kind = supported_input_kind(path)
            except (OSError, ValueError):
                continue
            if kind:
                candidates.append(document)
                seen.add(path)
        if not candidates:
            QMessageBox.information(self, 'Apply new coordinates',
                'Open a supported calculation input first (Gaussian, ORCA, CP2K, QE, SIESTA, NWChem or POSCAR).')
            return False
        was_playing = self.playback.isActive()
        self.playback.stop()
        source_document = self.doc
        source_frame = self.frame
        dialog = None
        try:
            dialog = CoordinateUpdateDialog(candidates, source_frame, self)
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.plan is None:
                return False
            return self.apply_coordinate_update(dialog.plan, dialog.target_document,
                source_frame=dialog._frame, source_document=source_document)
        finally:
            if dialog is not None:
                dialog.deleteLater()
            if was_playing and not self._closing and self.doc is source_document and self.frame is source_frame:
                self.playback.start()

    def apply_coordinate_update(self, plan, target_document, *, source_frame=None, source_document=None):
        from .coordinate_update import save_coordinate_update
        if not any(doc is target_document for doc in self.documents):
            return False
        if Path(target_document.path).resolve() != plan.path:
            raise ValueError('The preview does not belong to the selected input file.')
        source = self.frame if source_frame is None else source_frame
        source_document = self.doc if source_document is None else source_document
        try:
            path = run_data_task(self, 'Applying new coordinates', lambda: save_coordinate_update(plan))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Could not apply coordinates', str(exc))
            return False
        parsed = plan.validated_document
        # Refresh every loaded occurrence of the same on-disk input, retaining
        # the document identities used by cameras and existing file-tree rows.
        for index, document in enumerate(self.documents):
            if Path(document.path).resolve() != Path(path).resolve():
                continue
            updated = deepcopy(parsed)
            if document is source_document and source is not None and updated.frames:
                for key in ('saved_fragments', 'fragment_next_id'):
                    if key in source.info:
                        updated.frames[0].info[key] = deepcopy(source.info[key])
                for key in ('atom_appearance', 'bond_added', 'bond_removed', 'bond_snapshot',
                            'periodic_bond_snapshot', 'hbond_added', 'hbond_removed'):
                    setattr(updated.frames[0], key, deepcopy(getattr(source, key)))
            # Text is a document decoration, not a parsed calculation result.
            annotations = document.annotations
            for field in fields(document):
                setattr(document, field.name, getattr(updated, field.name))
            document.annotations = annotations
            document.path = Path(path)
            document.modified = False
            self._frame_tree_items = {key: value for key, value in self._frame_tree_items.items() if key[0] != index}
            self._vibration_tree_items = {key: value for key, value in self._vibration_tree_items.items() if key[0] != index}
            self._vibration_references = {key: value for key, value in self._vibration_references.items() if key[0] != index}
            self._trajectory_alignments.pop(id(document), None)
            self._aligned_documents.discard(id(document))
            self._geometry_parameters.pop(id(document), None)
            self.undo_stack = [item for item in self.undo_stack if not self._undo_for_document(item, index)]
            with QSignalBlocker(self.files_tree):
                self.files_tree.takeTopLevelItem(index)
                self._add_document_tree(index, document)
                item = self.files_tree.takeTopLevelItem(self.files_tree.topLevelItemCount() - 1)
                self.files_tree.insertTopLevelItem(index, item)
        self.change_frame(self.frame_index)
        self.statusBar().showMessage(f'Applied new coordinates to {Path(path).name}; original input backed up.', 8000)
        return True

    @staticmethod
    def _undo_for_document(item, index):
        if isinstance(item[0], int):
            return item[0] == index
        if item[0] in ('selection', 'appearance'):
            return item[1] == index
        return False
