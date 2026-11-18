"""Wheel scrolling cannot accidentally change combo or numeric parameters."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from lele.wheel_guard import install_wheel_guard


@pytest.fixture
def app():
    application = QApplication.instance() or QApplication(['wheel-tests'])
    install_wheel_guard(application)
    yield application


def wheel(widget, delta=-120):
    center = widget.rect().center()
    event = QWheelEvent(QPointF(center), QPointF(widget.mapToGlobal(center)),
        QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, event)


@pytest.mark.parametrize('kind', [QSpinBox, QDoubleSpinBox, QComboBox])
def test_focused_editor_and_child_wheel_keep_value(app, kind):
    widget = kind()
    if isinstance(widget, QComboBox):
        widget.addItems(['one', 'two', 'three'])
        widget.setCurrentIndex(1)
        widget.setEditable(True)
        value = widget.currentIndex
    else:
        widget.setValue(15)
        value = widget.value
    widget.show()
    widget.setFocus()
    app.processEvents()
    before = value()
    wheel(widget)
    wheel(widget.lineEdit(), 120)
    assert value() == before
    if not isinstance(widget, QComboBox):
        widget.stepUp()
        assert value() > before
    widget.close()


def test_wheel_over_editor_scrolls_enclosing_panel(app):
    scroll = QScrollArea()
    content = QWidget()
    layout = QVBoxLayout(content)
    editor = QSpinBox()
    editor.setValue(42)
    layout.addWidget(editor)
    content.setMinimumHeight(1500)
    scroll.setWidget(content)
    scroll.resize(220, 200)
    scroll.show()
    app.processEvents()
    assert scroll.verticalScrollBar().value() == 0
    wheel(editor)
    assert editor.value() == 42
    assert scroll.verticalScrollBar().value() > 0
    scroll.close()


def test_install_is_idempotent_and_other_wheel_receivers_are_untouched(app):
    assert install_wheel_guard(app) is install_wheel_guard(app)
    class Canvas(QWidget):
        count = 0
        def wheelEvent(self, event):
            self.count += 1
            event.accept()
    canvas = Canvas()
    wheel(canvas)
    assert canvas.count == 1
