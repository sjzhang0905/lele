"""Coordinate-axis options for the lower Axes tab."""
from math import log10

from PySide6.QtCore import Qt, QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QSlider, QToolButton, QWidget,
)


class AxisButtons(QWidget):
    chosen = Signal(str)

    def __init__(self, choices):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(3)
        self.buttons = {}
        group = QButtonGroup(self)
        for value, label, tip in choices:
            button = QToolButton()
            button.setText(label)
            button.setToolTip(tip)
            button.setCheckable(True)
            group.addButton(button)
            button.clicked.connect(lambda checked=False, key=value: self.chosen.emit(key))
            self.buttons[value] = button
            row.addWidget(button)
        row.addStretch(1)

    def set_value(self, value):
        button = self.buttons.get(value)
        if button is not None:
            button.setChecked(True)


class CoordinateAxesControls(QGroupBox):
    optionChanged = Signal(str, object)

    def __init__(self, options):
        super().__init__('Coordinate axes')
        form = QFormLayout(self)
        self.position = AxisButtons((('Off', 'Hidden', 'Hide coordinate axes'),
                                     ('Corner', 'Bottom-left', 'Axes in the bottom-left corner'),
                                     ('Origin', 'Origin', 'Axes at the world origin (0, 0, 0)')))
        self.basis = AxisButtons((('Auto', 'Auto', 'Use abc for crystals and XYZ for molecules'),
                                  ('XYZ', 'XYZ', 'Cartesian axes'),
                                  ('abc', 'abc', 'Direct lattice axes')))
        self.position.chosen.connect(lambda value: self.optionChanged.emit('axes_position', value))
        self.basis.chosen.connect(lambda value: self.optionChanged.emit('axes_basis', value))
        form.addRow('Position', self.position)
        form.addRow('Axes type', self.basis)
        self.length = QDoubleSpinBox()
        self.length.setRange(.1, 1000.)
        self.length.setDecimals(2)
        self.length.setSingleStep(.5)
        self.length.setKeyboardTracking(False)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setAccessibleName('XYZ length (Å)')
        self.slider.setToolTip('Cartesian axis length, 0.10–1000 Å')
        # Equal distances along the track cover equal ratios across four decades.
        self.slider.setRange(-100, 300)
        row = QHBoxLayout()
        row.addWidget(self.length)
        row.addWidget(self.slider, 1)
        form.addRow('XYZ length (Å)', row)
        self.slider.valueChanged.connect(lambda step: self.length.setValue(10 ** (step / 100.)))
        self.length.valueChanged.connect(self._length_changed)
        self.set_values(options)

    def _length_changed(self, length):
        with QSignalBlocker(self.slider):
            self.slider.setValue(round(100 * log10(length)))
        self.optionChanged.emit('axes_length', length)

    def set_values(self, options):
        self.position.set_value(options.axes_position)
        self.basis.set_value(options.axes_basis)
        with QSignalBlocker(self.length), QSignalBlocker(self.slider):
            self.length.setValue(options.axes_length)
            self.slider.setValue(round(100 * log10(self.length.value())))
