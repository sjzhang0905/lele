"""Fixed-angle view controls for the Axes tab."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from .panel_controls import PanelComboBox


class ViewRotationControls(QWidget):
    def __init__(self, rotate):
        super().__init__()
        self.axis = PanelComboBox()
        self.axis.setAccessibleName('Rotation axis')
        self.axis.setToolTip('Screen X points right, Y up and Z toward you.')
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        title = QLabel('Rotate view by 45°')
        title.setBuddy(self.axis)
        row.addWidget(title)
        row.addWidget(self.axis)
        self.lattice_choices = []
        self._available_axes = None
        steps = ((-45, '−45°'), (45, '+45°'))

        for basis, axes in (('Screen', 'XYZ'), ('Cartesian', 'XYZ'), ('Lattice', 'abc')):
            for axis in axes:
                index = self.axis.count()
                self.axis.addItem(f'{basis} {axis}', (basis, axis))
                if basis == 'Lattice':
                    self.lattice_choices.append((axis, index))
        for angle, label in steps:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(f'Rotate the view by {label} about the selected axis')
            button.clicked.connect(lambda checked=False, n=angle: rotate(*self.axis.currentData(), n))
            row.addWidget(button)
        row.addStretch()
        self.set_available(False, ())

    def set_available(self, has_frame, lattice_axes):
        self.setEnabled(has_frame)
        if self._available_axes == lattice_axes:
            return
        self._available_axes = lattice_axes
        for axis, index in self.lattice_choices:
            self.axis.model().item(index).setEnabled(axis in lattice_axes)
        basis, selected = self.axis.currentData()
        if basis == 'Lattice' and selected not in lattice_axes:
            self.axis.setCurrentIndex(0)
