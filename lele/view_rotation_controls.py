"""Fixed-angle view controls for the View menu and Axes tab."""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from .panel_controls import PanelComboBox


class ViewRotationControls(QWidget):
    def __init__(self, menu, rotate):
        super().__init__()
        self.menu = menu
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

        def menu_step(index, degrees):
            self.axis.setCurrentIndex(index)
            rotate(*self.axis.currentData(), degrees)

        for basis, axes in (('Screen', 'XYZ'), ('Cartesian', 'XYZ'), ('Lattice', 'abc')):
            submenu = menu if basis == 'Screen' else menu.addMenu(f'{basis} axes')
            if basis == 'Lattice':
                self.lattice_menu = submenu
            for axis in axes:
                index = self.axis.count()
                self.axis.addItem(f'{basis} {axis}', (basis, axis))
                name = f'Screen {axis}' if basis == 'Screen' else axis
                actions = []
                for angle, label in steps:
                    action = submenu.addAction(f'{name}  {label}')
                    action.triggered.connect(lambda checked=False, i=index, n=angle: menu_step(i, n))
                    actions.append(action)
                if basis == 'Lattice':
                    self.lattice_choices.append((axis, index, actions))
            if basis == 'Screen':
                menu.addSeparator()
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
        self.menu.setEnabled(has_frame)
        if self._available_axes == lattice_axes:
            return
        self._available_axes = lattice_axes
        self.lattice_menu.setEnabled(bool(lattice_axes))
        for axis, index, actions in self.lattice_choices:
            enabled = axis in lattice_axes
            for action in actions:
                action.setEnabled(enabled)
            self.axis.model().item(index).setEnabled(enabled)
        basis, selected = self.axis.currentData()
        if basis == 'Lattice' and selected not in lattice_axes:
            self.axis.setCurrentIndex(0)
