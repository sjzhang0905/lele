"""Qt-only controls for building a real supercell of the current frame."""
from math import prod

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
                               QSpinBox, QLabel, QCheckBox, QDialogButtonBox)


class SupercellDialog(QDialog):
    def __init__(self, frame, *, has_volume=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Build supercell')
        self.resize(420, 350)
        self._frame = frame
        layout = QVBoxLayout(self)
        note = QLabel('Repeat the current geometry frame along its lattice vectors.\n'
                      'This changes the actual atom count and unit cell. Ctrl+Z to undo.')
        note.setWordWrap(True); layout.addWidget(note)
        form = QFormLayout()
        self.spins = []
        for axis, name in enumerate(('a', 'b', 'c')):
            spin = QSpinBox()
            spin.setObjectName('supercell_' + name)
            spin.setRange(1, 100)
            spin.setValue(2 if frame.pbc[axis] else 1)
            spin.setEnabled(frame.pbc[axis])
            spin.valueChanged.connect(self._update_preview)
            self.spins.append(spin)
            row = QHBoxLayout(); row.addWidget(spin)
            vector = ', '.join(f'{v:.5f}' for v in frame.cell[axis])
            row.addWidget(QLabel(f'× ({vector}) Å'), 1)
            form.addRow(name, row)
        layout.addLayout(form)
        self.wrap = QCheckBox('Wrap atoms into the original unit cell before repeating')
        self.wrap.setChecked(True); layout.addWidget(self.wrap)
        self.preview = QLabel(); self.preview.setWordWrap(True); layout.addWidget(self.preview)
        details = 'Only this frame is changed; other trajectory frames remain available.\n'
        details += 'Source energy and spin multiplicity are cleared. Known net charge scales with the cell count.'
        if has_volume:
            details += '\nThe attached volume will be detached; Undo restores it.'
        label = QLabel(details); label.setWordWrap(True); layout.addWidget(label)
        layout.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Build supercell')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._update_preview()

    def repeats(self):
        return tuple(spin.value() for spin in self.spins)

    def _update_preview(self):
        if len(self.spins) != 3 or not hasattr(self, 'buttons'):
            return
        from .supercell import MAX_SUPERCELL_ATOMS
        factor = prod(self.repeats())
        atoms = len(self._frame.symbols) * factor
        valid = factor > 1 and atoms <= MAX_SUPERCELL_ATOMS
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
        message = f'{len(self._frame.symbols):,} → {atoms:,} atoms · {factor:,} cells'
        if factor == 1:
            message += '\nIncrease at least one repeat factor.'
        elif atoms > MAX_SUPERCELL_ATOMS:
            message += f'\nLimit: {MAX_SUPERCELL_ATOMS:,} atoms. Reduce the repeat factors.'
        self.preview.setText(message)
