"""Compact editors for the sidebar and lower settings tabs."""
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox, QComboBox, QFormLayout, QLineEdit, QSlider, QToolTip,
)


SIDEBAR_MIN_WIDTH = 295
COMBO_WIDTH = 90
NUMBER_WIDTH = 90
SCIENTIFIC_NUMBER_WIDTH = 140
SLIDER_MAX_WIDTH = SIDEBAR_MIN_WIDTH - 30


class PanelComboBox(QComboBox):
    """Keep the closed editor short, without shortening the option list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(COMBO_WIDTH)

    def showPopup(self):
        # Recalculate on opening: fields, elements and presets can be populated
        # after startup. Windows styles do not always widen the popup for us.
        metrics = self.view().fontMetrics()
        text_width = max((metrics.horizontalAdvance(self.itemText(i))
                          for i in range(self.count())), default=0)
        width = max(self.width(), text_width + self.iconSize().width() + 32)
        screen = self.screen()
        if screen is not None:
            width = min(width, screen.availableGeometry().width() - 20)
        self.view().setMinimumWidth(width)
        super().showPopup()

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip and self.currentText():
            text = self.currentText()
            if self.toolTip():
                text += '\n\n' + self.toolTip()
            QToolTip.showText(event.globalPos(), text, self)
            return True
        return super().event(event)


def compact_panel_sliders(*panels):
    """Cap track length, retaining normal shrinking in narrow form rows."""
    for panel in panels:
        for slider in panel.findChildren(QSlider):
            if slider.orientation() == Qt.Orientation.Horizontal:
                slider.setMaximumWidth(SLIDER_MAX_WIDTH)


def compact_panel_editors(panel):
    """Keep lower-tab editors left-aligned instead of filling form fields."""
    from .numeric_controls import IsovalueSpinBox

    for form in panel.findChildren(QFormLayout):
        # Sliders can still use the available space up to their separate cap;
        # regular editors and buttons keep their own bounded/natural width.
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    for combo in panel.findChildren(QComboBox):
        combo.setFixedWidth(COMBO_WIDTH)
    for editor in panel.findChildren(QAbstractSpinBox):
        editor.setFixedWidth(SCIENTIFIC_NUMBER_WIDTH if isinstance(editor, IsovalueSpinBox)
                             else NUMBER_WIDTH)
    for editor in panel.findChildren(QLineEdit):
        # Native spin/combo editors manage their own arrow/clear-button space.
        if not isinstance(editor.parentWidget(), (QAbstractSpinBox, QComboBox)):
            editor.setFixedWidth(SCIENTIFIC_NUMBER_WIDTH)
