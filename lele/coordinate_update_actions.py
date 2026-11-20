"""Preview and apply coordinates between the active structure and a local file."""
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)
from .dialog_policy import QDialog, QFileDialog, QMessageBox

from .operations import run_data_task


class CoordinateUpdateDialog(QDialog):
    def __init__(self, active_path, frame, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Apply new coordinates')
        self.resize(780, 580)
        self.plan = None
        self.active_path = Path(active_path).resolve()
        self.local_path = None
        self._frame = frame.clone()
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        self.direction = QComboBox()
        self.direction.addItems(['Current coordinates → local input file', 'Local coordinates → current input file'])
        if not self.active_path.is_file():
            self.direction.model().item(1).setEnabled(False)
        form.addRow('Apply direction', self.direction)
        active = QLineEdit(str(self.active_path))
        active.setReadOnly(True)
        form.addRow('Current file', active)
        row = QHBoxLayout()
        self.local_name = QLineEdit()
        self.local_name.setReadOnly(True)
        self.local_name.setPlaceholderText('Choose a file from disk')
        self.browse = QPushButton('Browse…')
        self.browse.clicked.connect(self._browse)
        row.addWidget(self.local_name, 1)
        row.addWidget(self.browse)
        form.addRow('Local file', row)
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
        self.direction.currentIndexChanged.connect(self._prepare)
        self._prepare()

    def _browse(self):
        directory = (self.local_path or self.active_path).parent
        files = ('Calculation inputs (POSCAR* CONTCAR* *.vasp *.poscar *.contcar *.gjf *.com *.inp *.in *.nw *.nwi *.fdf);;All files (*)'
                 if self.direction.currentIndex() == 0 else 'All structure files (*)')
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a local file', str(directory), files)
        if path:
            self.local_path = Path(path).resolve()
            self.local_name.setText(str(self.local_path))
            self._prepare()

    def _prepare(self, *_):
        from .coordinate_update import prepare_coordinate_update
        self.plan = None
        self.apply_button.setEnabled(False)
        self.preview.clear()
        if self.local_path is None:
            self.summary.setText('Choose a local file to preview the changes. Apply saves a backup of the target.')
            return
        incoming = self.direction.currentIndex() == 1
        local = self.local_path
        target = self.active_path if incoming else local

        def prepare():
            source = self._frame
            source_label = f'Current frame of {self.active_path.name}'
            if incoming:
                from .formats import load_document
                document = load_document(local)
                if not document.frames:
                    raise ValueError('The selected file has no atomic coordinates.')
                source = document.frames[-1]
                source_label = str(local)
                if len(document.frames) > 1:
                    source_label += f' (last frame, {len(document.frames)})'
            return prepare_coordinate_update(target, source), source_label

        try:
            plan, source_label = run_data_task(self, 'Preparing coordinate changes', prepare)
        except Exception as exc:
            self.summary.setText(str(exc))
            return
        self.plan = plan
        detail = plan.summary if plan.changed else 'The input already contains these coordinates and cell.'
        self.summary.setText(f'Coordinates from {source_label}\nFile to update: {target}\n{detail}')
        self.preview.setPlainText(plan.preview_text)
        self.apply_button.setEnabled(plan.changed)


class CoordinateUpdateActions:
    def apply_new_coordinates_dialog(self):
        if self.frame is None or not self._geometry_edit_allowed():
            return False
        was_playing = self.playback.isActive()
        self.playback.stop()
        source_document = self.doc
        source_frame = self.frame
        dialog = None
        try:
            dialog = CoordinateUpdateDialog(source_document.path, source_frame, self)
            if dialog.exec() != QDialog.DialogCode.Accepted or dialog.plan is None:
                return False
            return self.apply_coordinate_update(dialog.plan, source_frame=dialog._frame, source_document=source_document)
        finally:
            if dialog is not None:
                dialog.deleteLater()
            if was_playing and not self._closing and self.doc is source_document and self.frame is source_frame:
                self.playback.start()

    def apply_coordinate_update(self, plan, target_document=None, *, source_frame=None, source_document=None):
        from .coordinate_update import save_coordinate_update
        if target_document is not None and Path(target_document.path).resolve() != plan.path:
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
            if (document is source_document and source is not None and updated.frames
                    and source.symbols == updated.frames[0].symbols):
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
        if self.doc is not None and Path(self.doc.path).resolve() == path:
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
