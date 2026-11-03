"""Element-pair rule editor; Qt-only until a structure is loaded."""
from copy import deepcopy
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QCheckBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QHeaderView)
from .element_rules import default_rule
from .crystal_panel import decimal


class ElementRulesPanel(QWidget):
    applyRequested = Signal(object, bool)

    def __init__(self):
        super().__init__();layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 3);self.table.setHorizontalHeaderLabels(['Pair', 'Range (Å)', 'Use'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide();self.table.setMinimumHeight(150);layout.addWidget(self.table)
        row = QHBoxLayout();layout.addLayout(row)
        self.add = QPushButton('New');self.remove = QPushButton('Remove')
        self.up = QPushButton('↑');self.down = QPushButton('↓')
        self.up.setFixedWidth(30);self.down.setFixedWidth(30)
        for button in (self.add, self.remove, self.up, self.down):row.addWidget(button)
        self.editor = QWidget();form = QFormLayout(self.editor);form.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox('Enable this rule');form.addRow(self.enabled)
        self.first = QLineEdit();self.second = QLineEdit()
        form.addRow('Center / element 1', self.first);form.addRow('Ligand / element 2', self.second)
        self.minimum = decimal(0., 0., 20.);self.maximum = decimal(2.5, .0001, 20.)
        form.addRow('Minimum (Å)', self.minimum);form.addRow('Maximum (Å)', self.maximum)
        self.bonds = QCheckBox('Allow ordinary bonds for this pair')
        self.polyhedra = QCheckBox('Allow center → ligand coordination')
        form.addRow(self.bonds);form.addRow(self.polyhedra);layout.addWidget(self.editor)
        self.only = QCheckBox('Only listed pairs (disable fallback)');layout.addWidget(self.only)
        self.apply = QPushButton('Apply rules + rebuild bonds')
        self.apply.setToolTip('Apply to this document and rebuild ordinary bonds in all frames; keep manual overrides.')
        layout.addWidget(self.apply)
        self.info = QLabel('');self.info.setWordWrap(True);layout.addWidget(self.info)
        note = QLabel('Ordinary pairs are symmetric; coordination is center → ligand.\n'
            'Use element symbols or *. Specific pairs override wildcards; the last equally specific row wins.\n'
            'An unchecked use excludes that pair from that search. Unlisted pairs use the existing settings unless Only listed is enabled.\n'
            'Apply rebuilds this document’s frames and keeps manual bond overrides. Coordinate edits continue to keep frozen bonds. Ctrl+Z restores the previous rules and bonds.')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch()
        self.records = [];self._loading = False
        self.table.itemSelectionChanged.connect(self._load_row)
        self.add.clicked.connect(self.add_rule);self.remove.clicked.connect(self.remove_rule)
        self.up.clicked.connect(lambda:self.move_rule(-1));self.down.clicked.connect(lambda:self.move_rule(1))
        for widget in (self.enabled, self.bonds, self.polyhedra):widget.toggled.connect(self._edited)
        for widget in (self.first, self.second):widget.textChanged.connect(self._edited)
        for widget in (self.minimum, self.maximum):widget.valueChanged.connect(self._edited)
        self.apply.clicked.connect(lambda:self.applyRequested.emit(deepcopy(self.records), self.only.isChecked()))
        self.set_values([], False);self.setEnabled(False)

    def _row(self, index):
        p = self.records[index]
        uses = ('B ' if p['bonds'] else '')+('P' if p['polyhedra'] else '')
        values = [p['a1']+' → '+p['a2'], f'{p["minimum"]:g}–{p["maximum"]:g}', uses.strip() if p['enabled'] else 'Off']
        for column, value in enumerate(values):self.table.setItem(index, column, QTableWidgetItem(value or 'Exclude'))

    def set_values(self, values, only):
        self._loading = True;self.records = deepcopy(values);self.only.setChecked(only)
        self.table.setRowCount(len(values))
        for i in range(len(values)):self._row(i)
        self._loading = False
        if values:self.table.selectRow(0)
        self._load_row()

    def _load_row(self):
        if self._loading:return
        index = self.table.currentRow();valid = 0 <= index < len(self.records)
        self.editor.setEnabled(valid);self.remove.setEnabled(valid)
        self.up.setEnabled(valid and index > 0);self.down.setEnabled(valid and index+1 < len(self.records))
        if not valid:return
        p = self.records[index];self._loading = True
        self.enabled.setChecked(p['enabled']);self.first.setText(p['a1']);self.second.setText(p['a2'])
        self.minimum.setValue(p['minimum']);self.maximum.setValue(p['maximum'])
        self.bonds.setChecked(p['bonds']);self.polyhedra.setChecked(p['polyhedra']);self._loading = False

    def _edited(self, *_):
        if self._loading:return
        index = self.table.currentRow()
        if not 0 <= index < len(self.records):return
        self.records[index].update(enabled=self.enabled.isChecked(), a1=self.first.text().strip(), a2=self.second.text().strip(),
            minimum=self.minimum.value(), maximum=self.maximum.value(), bonds=self.bonds.isChecked(), polyhedra=self.polyhedra.isChecked())
        self._loading = True;self._row(index);self._loading = False

    def add_rule(self):
        self.records.append(default_rule());self.table.setRowCount(len(self.records))
        self._row(len(self.records)-1);self.table.selectRow(len(self.records)-1);self._load_row()

    def remove_rule(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.records):
            values = deepcopy(self.records);values.pop(index);self.set_values(values, self.only.isChecked())

    def move_rule(self, step):
        index = self.table.currentRow();other = index+step
        if 0 <= other < len(self.records):
            values = deepcopy(self.records);values[index], values[other] = values[other], values[index]
            self.set_values(values, self.only.isChecked());self.table.selectRow(other)
