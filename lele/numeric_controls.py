"""Numeric editors for scientific display parameters."""
from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDoubleSpinBox
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
