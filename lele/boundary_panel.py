"""Integer whole-cell display ranges; no scientific startup import."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from .lattice_tiles import ONE_CELL, repeat_bounds


class BoundaryPanel(QWidget):
    applyRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        row = QHBoxLayout()
        row.setSpacing(3)
        self.growth = QComboBox()
        self.growth.addItems(['Alternate', 'Manual'])
        self.growth.setAccessibleName('Boundary ranges')
        self.growth.setFixedWidth(self.growth.sizeHint().width())
        row.addWidget(self.growth)
        self.repeat_spins = []
        for axis in ('a/x', 'b/y', 'c/z'):
            spin = QSpinBox()
            spin.setRange(1, 100)
            spin.setPrefix(axis + ' ')
            spin.setAccessibleName(axis + ' cell count')
            spin.setKeyboardTracking(False)
            spin.setFixedWidth(spin.sizeHint().width())
            self.repeat_spins.append(spin)
            row.addWidget(spin)
        row.addStretch(1)
        layout.addLayout(row)

        grid = QGridLayout()
        grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(grid)
        self.spins = []
        for column, text in enumerate(('Cells', 'Start', 'End (cell limit)')):
            grid.addWidget(QLabel(text), 0, column)
        for axis, name in enumerate(('a / x', 'b / y', 'c / z')):
            grid.addWidget(QLabel(name), axis + 1, 0)
            pair = []
            for column, value in enumerate((0, 1)):
                spin = QSpinBox()
                spin.setRange(-100, 101)
                spin.setValue(value)
                spin.setKeyboardTracking(False)
                grid.addWidget(spin, axis + 1, column + 1)
                pair.append(spin)
            self.spins.append(pair)

        self.preserve = QCheckBox('Keep original atom coordinates and cell origin')
        self.preserve.setChecked(True)
        layout.addWidget(self.preserve)
        self.apply = QPushButton('Apply')
        self.apply.clicked.connect(lambda: self.applyRequested.emit(self.bounds()))
        self.reset = QPushButton('Reset to one cell')
        self.reset.clicked.connect(self.reset_bounds)
        actions = QHBoxLayout()
        actions.addWidget(self.apply)
        actions.addWidget(self.reset)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch()
        self.setEnabled(False)
        self.growth.currentIndexChanged.connect(self._growth_changed)
        for spin in self.repeat_spins:
            spin.valueChanged.connect(self._growth_changed)
        self._growth_changed()

    def _growth_changed(self, *_):
        alternating = self.growth.currentIndex() == 0
        for spin in self.repeat_spins:
            spin.setEnabled(alternating)
        for pair in self.spins:
            for spin in pair:
                spin.setEnabled(not alternating)
        if alternating:
            for pair, values in zip(self.spins, repeat_bounds(tuple(s.value() for s in self.repeat_spins))):
                for spin, value in zip(pair, values):
                    spin.setValue(value)

    def bounds(self):
        return tuple(tuple(spin.value() for spin in pair) for pair in self.spins)

    def reset_bounds(self):
        self.set_values(ONE_CELL)
        self.applyRequested.emit(ONE_CELL)

    def set_values(self, bounds, preserve_origin=None):
        if preserve_origin is not None:
            with QSignalBlocker(self.preserve):
                self.preserve.setChecked(preserve_origin)
        repeats = tuple(max(1, int(hi)-int(lo)) for lo, hi in bounds)
        alternating = (all(n <= spin.maximum() for n, spin in zip(repeats, self.repeat_spins))
                       and tuple(tuple(int(v) for v in pair) for pair in bounds) == repeat_bounds(repeats))
        with QSignalBlocker(self.growth):
            self.growth.setCurrentIndex(0 if alternating else 1)
        for spin, value in zip(self.repeat_spins, repeats):
            with QSignalBlocker(spin):
                spin.setValue(value)
        for pair, values in zip(self.spins, bounds):
            for spin, value in zip(pair, values):
                with QSignalBlocker(spin):
                    spin.setRange(min(spin.minimum(), int(value)), max(spin.maximum(), int(value)))
                    spin.setValue(int(value))
        self._growth_changed()
