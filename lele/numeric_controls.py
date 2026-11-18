"""Numeric editors for scientific display parameters."""
from PySide6.QtCore import QEvent, QLocale, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QAbstractSlider, QDoubleSpinBox, QHBoxLayout, QSlider, QWidget
from .render_options import MIN_ISOVALUE


class IsovalueSpinBox(QDoubleSpinBox):
    """Accept decimal/scientific text and commit after editing, not per digit."""
    def __init__(self, parent=None):
        super().__init__(parent)
        locale = QLocale.c()
        locale.setNumberOptions(QLocale.NumberOption.RejectGroupSeparator |
                                QLocale.NumberOption.OmitGroupSeparator)
        self.setLocale(locale)
        self.setDecimals(12)
        self.setRange(MIN_ISOVALUE, 10000)
        self.setSingleStep(.005)
        self.setKeyboardTracking(False)
        self.setReadOnly(False)
        self.lineEdit().setClearButtonEnabled(True)
        self.setToolTip(
            'Type a positive decimal or scientific value, e.g. 0.01234567 or 1.25e-5. '
            'Press Enter, click Apply, or leave the field to update. Up to 12 decimal places.')

    def textFromValue(self, value):
        return f'{value:.12f}'.rstrip('0').rstrip('.')

    def valueFromText(self, text):
        value, valid = self.locale().toDouble(text.strip())
        return value if valid else self.value()

    def validate(self, text, position):
        validator = QDoubleValidator(self.minimum(), self.maximum(), self.decimals())
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        validator.setLocale(self.locale())
        return validator.validate(text, position)


class CenteredScaleSlider(QWidget):
    """Expose physical percentages, with half the track on either side of a default."""
    valueChanged = Signal(float)
    HALF = 1000

    def __init__(self, low, center, high, *, decimals=0):
        super().__init__()
        self._low, self._center, self._high = low, center, high
        self._decimals = decimals
        self._value = center
        self.track = QSlider(Qt.Orientation.Horizontal, self)
        self.track.setRange(0, 2 * self.HALF)
        self.track.setValue(self.HALF)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.track)
        self.setFocusProxy(self.track)
        self.track.valueChanged.connect(self._track_changed)
        self.track.actionTriggered.connect(self._step)
        self.track.installEventFilter(self)

    def minimum(self):
        return self._low

    def maximum(self):
        return self._high

    def value(self):
        return self._value

    def _position(self, value):
        extent = self._center - self._low if value <= self._center else self._high - self._center
        return round(self.HALF * (1 + (value - self._center) / extent))

    def setCenter(self, center):
        if self._center != center:
            self._center = center
            self.setValue(self._value)

    def setValue(self, value):
        value = min(self._high, max(self._low, value))
        position = self._position(value)
        if self.track.value() != position:
            self.track.setValue(position)
        else:
            self._track_changed(position)

    def _track_changed(self, position):
        delta = (position - self.HALF) / self.HALF
        extent = self._center - self._low if delta <= 0 else self._high - self._center
        value = round(self._center + delta * extent, self._decimals)
        if value != self._value:
            self._value = value
            self.valueChanged.emit(value)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Wheel:
            # Qt accumulates wheel/trackpad deltas in track units. Scale its
            # step to the active half before the native slider consumes them.
            delta = event.angleDelta().y() or event.angleDelta().x()
            below = self._value < self._center or (self._value == self._center and delta < 0)
            extent = self._center - self._low if below else self._high - self._center
            ticks = max(1, round(self.HALF * 10 ** -self._decimals / extent))
            self.track.setSingleStep(ticks)
            self.track.setPageStep(10 * ticks)
        return super().eventFilter(watched, event)

    def _step(self, action):
        # Mouse drags use track positions. Arrow and page actions must
        # advance at least one representable physical value on either half.
        step = 10 ** -self._decimals
        actions = QAbstractSlider.SliderAction
        amount = {actions.SliderSingleStepAdd.value: step, actions.SliderSingleStepSub.value: -step,
                  actions.SliderPageStepAdd.value: 10 * step, actions.SliderPageStepSub.value: -10 * step}
        if action in amount:
            value = min(self._high, max(self._low, self._value + amount[action]))
            self.track.setSliderPosition(self._position(value))
