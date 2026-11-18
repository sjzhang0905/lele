"""Keep scrolling from silently changing scientific parameters.

The application-level filter also covers editors created later in dialogs.
Keyboard arrows, typed input, and the spin-box buttons remain available.
"""
from PySide6.QtCore import QEvent, QObject, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QAbstractScrollArea, QAbstractSpinBox,
    QComboBox, QWidget,
)


class ParameterWheelGuard(QObject):
    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Wheel or not isinstance(watched, QWidget):
            return False
        widget = watched
        control = None
        while widget is not None:
            # An opened combo popup must still scroll its list of choices.
            if isinstance(widget, QAbstractItemView):
                return False
            if isinstance(widget, (QComboBox, QAbstractSpinBox)):
                control = widget
                break
            widget = widget.parentWidget()
        if control is None:
            return False

        # Consuming the control's event avoids value changes even when it has
        # keyboard focus. Forward the scroll to the enclosing panel instead.
        parent = control.parentWidget()
        while parent is not None and not isinstance(parent, QAbstractScrollArea):
            parent = parent.parentWidget()
        if parent is not None:
            viewport = parent.viewport()
            position = QPointF(viewport.mapFromGlobal(event.globalPosition().toPoint()))
            forwarded = QWheelEvent(
                position, event.globalPosition(), event.pixelDelta(), event.angleDelta(),
                event.buttons(), event.modifiers(), event.phase(), event.inverted(),
                event.source(), event.pointingDevice())
            QApplication.sendEvent(viewport, forwarded)
        event.accept()
        return True


def install_wheel_guard(application=None):
    """Install once per QApplication; return the persistent filter object."""
    application = application or QApplication.instance()
    if application is None:
        raise RuntimeError('Create QApplication before installing the wheel guard.')
    guard = getattr(application, '_lele_parameter_wheel_guard', None)
    if guard is None:
        guard = ParameterWheelGuard(application)
        application.installEventFilter(guard)
        application._lele_parameter_wheel_guard = guard
    return guard
