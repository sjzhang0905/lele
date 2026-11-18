"""Numeric and slider fragment rotation with selection-order guidance."""
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QSlider, QVBoxLayout
from .dialog_policy import QDialog


class RotationDialog(QDialog):
    angleChanged = Signal(float)

    def __init__(self, frame, selection, *, dihedral=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Set dihedral' if dihedral is not None else 'Rotate about selected axis')
        layout = QVBoxLayout(self)
        names = [f'{frame.symbols[i]}: index {i + 1}' for i in selection]
        label = QLabel('Selection order\n' + '\n'.join(f'{n + 1}. {text}' for n, text in enumerate(names[:12])))
        if len(names) > 12:
            label.setText(label.text() + f'\n… and {len(names) - 12} more moving seeds')
        label.setWordWrap(True)
        layout.addWidget(label)
        if dihedral is not None:
            explanation = ('The second → third atoms define the axis. The fourth atom and its connected terminal fragment move; the first side stays fixed. Enter the target dihedral angle.')
        else:
            explanation = ('The first → second atoms define the axis and remain fixed. With two selected atoms, the bonded fragment on the second side rotates. If more atoms are selected, the third and later atoms select the moving connected fragments. Positive angles use the right-hand rule along the axis.')
        note = QLabel(explanation)
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        layout.addLayout(form)
        self.angle = QDoubleSpinBox()
        self.angle.setDecimals(4)
        self.angle.setRange(-180. if dihedral is not None else -3600., 180. if dihedral is not None else 3600.)
        self.angle.setSuffix(' °')
        self.angle.setSingleStep(5.)
        self.angle.setValue(dihedral if dihedral is not None else 15.)
        form.addRow('Target dihedral' if dihedral is not None else 'Rotation angle', self.angle)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(-1800, 1800)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(150)
        self.slider.setTickInterval(900)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTracking(True)
        self.slider.setValue(round(self.angle.value() * 10))
        self.slider.setAccessibleName('Rotation angle preview')
        self.slider.setToolTip('Drag from −180° to +180° in 0.1° steps. Use the numeric box for finer or larger angles.')
        form.addRow('−180° … +180°', self.slider)
        self.slider.valueChanged.connect(lambda value: self.angle.setValue(value / 10.))
        self.angle.valueChanged.connect(self._angle_changed)
        action = 'Set dihedral' if dihedral is not None else 'Rotate'
        hint = QLabel(f'Live preview. {action} applies one undoable edit; Cancel keeps the original coordinates.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.preview_error = QLabel()
        self.preview_error.setWordWrap(True)
        self.preview_error.setStyleSheet('color: #b33b29;')
        self.preview_error.hide()
        layout.addWidget(self.preview_error)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Set dihedral' if dihedral is not None else 'Rotate')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(520, 450)

    def _angle_changed(self, value):
        # A large/fine numeric angle is never rounded back through the slider.
        with QSignalBlocker(self.slider):
            self.slider.setValue(max(-1800, min(1800, round(value * 10))))
        self.angleChanged.emit(value)

    def set_preview_error(self, message):
        self.preview_error.setText(message)
        self.preview_error.setVisible(bool(message))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not message)

    def value(self):
        return self.angle.value()
