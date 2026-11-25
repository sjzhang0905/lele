"""Select a stored molecular orbital or a WAVECAR band for the Field panel."""
from typing import NamedTuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSignalBlocker, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialogButtonBox,
    QFormLayout, QHeaderView, QSpinBox, QTabBar, QTableView, QVBoxLayout)

from .dialog_policy import QDialog


def spin_label(spin):
    if isinstance(spin, int):
        return f'Spin {spin + 1}'
    return {'alpha': 'Alpha (α)', 'beta': 'Beta (β)', 'restricted': 'Restricted'}.get(spin, spin)


class OrbitalChoice(NamedTuple):
    spin: str | int
    kpoint: int | None  # WAVECAR array index
    number: int         # source MO or band, one-based

    def label(self):
        if self.kpoint is None:
            return f'{spin_label(self.spin)} · MO {self.number}'
        return f'{spin_label(self.spin)} · k {self.kpoint + 1} · band {self.number}'


def initial_choice(wavefunction, wavecar):
    if wavecar is not None:
        return OrbitalChoice(0, 0, 1)
    if wavefunction is None or not wavefunction.orbitals:
        return None
    rows = wavefunction.orbitals
    spin, number, _, _ = next((row for row in reversed(rows) if row[2] > 1.e-8), rows[0])
    return OrbitalChoice(spin, None, number)


class OrbitalTable(QAbstractTableModel):
    """Format only visible bands of the active spin and k-point."""
    def __init__(self, is_wavecar, parent):
        super().__init__(parent)
        self.headers = ('Band' if is_wavecar else 'MO',
                        'Raw occupation weight' if is_wavecar else 'Occupation', 'Energy (eV)')
        self.columns = ((), (), ())

    def set_columns(self, numbers, occupations, energies):
        self.beginResetModel()
        self.columns = (numbers, occupations, energies)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns[0])

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            value = self.columns[index.column()][index.row()]
            if value is None:
                return '—'
            return str(value) if index.column() == 0 else f'{value:.9g}'
        return None


class OrbitalPicker(QDialog):
    def __init__(self, document, current, parent=None):
        super().__init__(parent)
        self.wave = document.wavecar
        self.molecular_rows = {}
        if self.wave is None:
            for spin, number, occupation, energy in document.wavefunction.orbitals:
                self.molecular_rows.setdefault(spin, []).append((number, occupation, energy))
            spins = list(self.molecular_rows)
        else:
            spins = list(range(self.wave.spins))

        self.setWindowTitle('Select orbital — ' + document.path.name)
        self.resize(510, 440)
        layout = QVBoxLayout(self)
        self.spins = QTabBar()
        for spin in spins:
            tab = self.spins.addTab(spin_label(spin))
            self.spins.setTabData(tab, spin)
        self.spins.setCurrentIndex(spins.index(current.spin))
        layout.addWidget(self.spins)
        filters = QFormLayout()
        self.kpoints = QComboBox()
        filters.addRow('k-point', self.kpoints)
        self.number = QSpinBox()
        self.number.setKeyboardTracking(False)
        filters.addRow('Band number' if self.wave is not None else 'MO number', self.number)
        layout.addLayout(filters)
        self.model = OrbitalTable(self.wave is not None, self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        layout.addWidget(self.table, 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.table.doubleClicked.connect(self.accept)
        layout.addWidget(self.buttons)
        self.number.valueChanged.connect(self._select_number)
        self.table.selectionModel().currentRowChanged.connect(self._row_changed)
        self._set_kpoints(current.kpoint)
        self._set_rows(current.number)
        self.spins.currentChanged.connect(self._spin_changed)
        self.kpoints.currentIndexChanged.connect(lambda _: self._set_rows(self.choice().number))

    def _spin(self):
        return self.spins.tabData(self.spins.currentIndex())

    def _set_kpoints(self, index):
        with QSignalBlocker(self.kpoints):
            self.kpoints.clear()
            if self.wave is None:
                self.kpoints.addItem('Not specified in this file')
            else:
                for i, coordinates in enumerate(self.wave.kpoints[self._spin()]):
                    xyz = ', '.join(f'{x:.7g}' for x in coordinates)
                    self.kpoints.addItem(f'{i + 1}   ({xyz})', i)
                self.kpoints.setCurrentIndex(index)
        self.kpoints.setEnabled(self.kpoints.count() > 1)

    def _spin_changed(self, _):
        number = self.choice().number
        self._set_kpoints(self.kpoints.currentData())
        self._set_rows(number)

    def _set_rows(self, number):
        spin = self._spin()
        if self.wave is None:
            numbers, occupations, energies = zip(*self.molecular_rows[spin])
        else:
            kpoint = self.kpoints.currentData()
            numbers = range(1, self.wave.nbands + 1)
            occupations = self.wave.occupations[spin, kpoint]
            energies = self.wave.energies[spin, kpoint]
        self.model.set_columns(numbers, occupations, energies)
        with QSignalBlocker(self.number):
            self.number.setRange(numbers[0], numbers[-1])
        self._select_number(number if number in numbers else numbers[-1])

    def _select_number(self, number):
        numbers = self.model.columns[0]
        row = numbers.index(number)
        self.table.selectRow(row)
        self.table.scrollTo(self.model.index(row, 0), QAbstractItemView.ScrollHint.PositionAtCenter)

    def _row_changed(self, index, previous):
        if index.isValid():
            with QSignalBlocker(self.number):
                self.number.setValue(self.model.columns[0][index.row()])

    def choice(self):
        row = self.table.currentIndex().row()
        return OrbitalChoice(self._spin(), self.kpoints.currentData(), self.model.columns[0][row])
