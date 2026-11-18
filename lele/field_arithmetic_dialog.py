"""Build A + B − C expressions from loaded or privately imported fields."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QLabel, QLineEdit, QDialogButtonBox
from .dialog_policy import QDialog, QFileDialog
from .field_arithmetic import (FieldTerm, DECLARED_UNITS, combine_fields,
                               expression_formula, unit_spec)
from .operations import run_data_task
from .output_text import LoadCancelled, check_load_cancelled


class FieldArithmeticDialog(QDialog):
    def __init__(self, documents, target_document, target_frame, parent=None):
        super().__init__(parent)
        self.target_document = target_document
        self.target_frame = target_frame
        self.expected_active = target_document.volume
        self.result = None
        self.sources = []
        self.private_documents = []
        self.setWindowTitle('Field arithmetic — add / subtract')
        self.resize(960, 560)
        layout = QVBoxLayout(self)
        intro = QLabel('Combine scalar datasets as A + B − C. The result is added to the current document. '
            'Grid shape, origin, voxel vectors and periodicity must agree; no interpolation or alignment is performed. '
            'Atom lists may differ, so matching fragment densities can be subtracted.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Term', 'Operation', 'Source dataset', 'Physical unit'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        layout.addLayout(row)
        for title, callback in [('Add term', self.add_term), ('Remove selected terms', self.remove_terms),
                                ('Choose field files…', self.import_files)]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        form = QFormLayout()
        layout.addLayout(form)
        self.label = QLineEdit()
        self.label.setPlaceholderText('Automatic label from formula')
        form.addRow('Result label', self.label)
        self.formula = QLabel()
        self.formula.setWordWrap(True)
        layout.addWidget(self.formula)
        self.unit_note = QLabel('Compatible physical units are converted to the first term’s unit. '
            'Unknown CUBE units must be declared explicitly in the Physical unit column. '
            'An ordinary CUBE without periodic metadata is not silently treated as a periodic VASP grid.')
        self.unit_note.setWordWrap(True)
        layout.addWidget(self.unit_note)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color:#a32626')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Calculate and add field')
        buttons.accepted.connect(self.calculate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        seen = set()
        for document in [target_document, *documents]:
            if id(document) in seen or document.volume is None:
                continue
            seen.add(id(document))
            self._register_document(document)
        active = next((i for i, (doc, index) in enumerate(self.sources)
                       if doc is target_document and doc.volumes[index] is self.expected_active), -1)
        self.add_term(source_index=active)
        self.add_term()

    def _register_document(self, document):
        for index in range(len(document.volumes)):
            self.sources.append((document, index))

    def _source_title(self, source_index):
        document, index = self.sources[source_index]
        volume = document.volumes[index]
        return f'{document.path.name} · {index+1}: {volume.label or "Field"} [{volume.unit or "unknown units"}]'

    def _fill_sources(self, combo):
        old = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('Choose a dataset…', -1)
        for i in range(len(self.sources)):
            combo.addItem(self._source_title(i), i)
            combo.setItemData(combo.count()-1, str(self.sources[i][0].path), Qt.ItemDataRole.ToolTipRole)
        combo.setCurrentIndex(max(0, combo.findData(old)))
        combo.blockSignals(False)

    def add_term(self, _checked=False, *, source_index=-1):
        if self.table.rowCount() >= 64:
            self.error.setText('At most 64 terms are supported.')
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        sign = QComboBox()
        sign.addItem('+', 1)
        sign.addItem('−', -1)
        source = QComboBox()
        self._fill_sources(source)
        source.setCurrentIndex(max(0, source.findData(source_index)))
        unit = QComboBox()
        self.table.setCellWidget(row, 1, sign)
        self.table.setCellWidget(row, 2, source)
        self.table.setCellWidget(row, 3, unit)
        source.currentIndexChanged.connect(lambda *_: self.update_units(source))
        sign.currentIndexChanged.connect(self.update_formula)
        unit.currentIndexChanged.connect(self.update_formula)
        self.update_units(source)
        self.update_formula()

    def update_units(self, source):
        row = next((r for r in range(self.table.rowCount()) if self.table.cellWidget(r, 2) is source), -1)
        if row < 0:
            return
        unit = self.table.cellWidget(row, 3)
        source_index = source.currentData()
        unit.blockSignals(True)
        unit.clear()
        if source_index is None or source_index < 0:
            unit.addItem('Select a source first', None)
            unit.setEnabled(False)
        else:
            document, index = self.sources[source_index]
            volume = document.volumes[index]
            try:
                unit_spec(volume.unit)
            except ValueError:
                unit.addItem('Declare unknown units…', None)
                for name in DECLARED_UNITS:
                    unit.addItem(name, name)
                unit.setEnabled(True)
                unit.setToolTip('This source does not specify recognized scalar units. Choose only the unit known from the calculation that produced it.')
            else:
                unit.addItem(volume.unit, None)
                unit.setEnabled(False)
                unit.setToolTip('Recognized source unit. Compatible unit scales are converted automatically, without relabeling the source.')
        unit.blockSignals(False)
        self.update_formula()

    def remove_terms(self):
        rows = sorted({item.row() for item in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.table.removeRow(row)
        self.update_formula()

    def selected_terms(self):
        terms = []
        for row in range(self.table.rowCount()):
            index = self.table.cellWidget(row, 2).currentData()
            if index is None or index < 0:
                raise ValueError(f'Choose a source dataset for term {row+1}.')
            document, dataset = self.sources[index]
            terms.append(FieldTerm(document, dataset, self.table.cellWidget(row, 1).currentData(),
                                   self.table.cellWidget(row, 3).currentData()))
        return terms

    def update_formula(self, *_):
        from .field_arithmetic import _symbol
        for row in range(self.table.rowCount()):
            item = QTableWidgetItem(_symbol(row))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
        try:
            terms = self.selected_terms()
        except ValueError:
            self.formula.setText('Choose the source dataset and + / − operation for every term.')
        else:
            text = 'Result = ' + expression_formula(terms)
            try:
                from .field_arithmetic import _effective_unit, _term_volume
                units = [_effective_unit(term, _term_volume(term)) for term in terms]
                if units and all(unit[0] == units[0][0] for unit in units):
                    text += f' · output {units[0][2]}'
                    conversions = [f'{_symbol(i)} × {unit[1]/units[0][1]:.7g}'
                                   for i, unit in enumerate(units) if unit[1] != units[0][1]]
                    if conversions:
                        text += '\nUnit conversions: ' + '; '.join(conversions)
            except ValueError:
                pass
            self.formula.setText(text)
        self.error.clear()

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Choose scalar field files', str(self.target_document.path.parent),
            'Scalar grids (*.cube *.cub CHGCAR* CHG PARCHG* ELFCAR* LOCPOT* AECCAR*);;All files (*)')
        if not paths:
            return
        from .formats import load_document
        def load():
            result = []
            count = sum(v.data.size for doc in self.private_documents for v in doc.volumes)
            for path in paths:
                check_load_cancelled()
                document = load_document(Path(path))
                if document.volume is None or not document.volumes:
                    raise ValueError(f'{Path(path).name}: no complete scalar grid. {document.note}')
                count += sum(v.data.size for v in document.volumes)
                if count > 128_000_000:
                    raise ValueError('Private field imports exceed 128 million scalar values. Load fewer files at a time.')
                result.append(document)
            return result
        try:
            incoming = run_data_task(self, 'Reading field operands', load, cancellable=True)
        except LoadCancelled:
            return
        except (ValueError, OSError, MemoryError) as exc:
            self.error.setText(str(exc))
            return
        # Commit the source list only when the entire selection loaded.
        first_indices = []
        for document in incoming:
            first_indices.append(len(self.sources))
            self._register_document(document)
        self.private_documents.extend(incoming)
        for row in range(self.table.rowCount()):
            self._fill_sources(self.table.cellWidget(row, 2))
        for index in first_indices:
            empty = next((r for r in range(self.table.rowCount())
                          if self.table.cellWidget(r, 2).currentData() == -1), None)
            if empty is not None:
                combo = self.table.cellWidget(empty, 2)
                combo.setCurrentIndex(combo.findData(index))
            else:
                self.add_term(source_index=index)
        self.update_formula()

    def calculate(self):
        from .dialog_policy import ensure_source_current
        if not ensure_source_current(self):return
        try:
            terms = self.selected_terms()
            label = self.label.text()
            result = run_data_task(self, 'Adding / subtracting scalar fields',
                lambda: combine_fields(terms, target_document=self.target_document,
                    target_frame=self.target_frame, label=label), cancellable=True)
        except LoadCancelled:
            return
        except (ValueError, OSError, MemoryError) as exc:
            self.error.setText(str(exc))
            return
        self.result = result
        self.accept()
