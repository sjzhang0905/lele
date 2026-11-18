"""Qt-only progress dialogs with LELE's existing walking parrot artwork.

The bird's pose uses the welcome animation clock; its position is driven only
by reported progress. A busy (0, 0) range walks in place and shows no percent.
This dialog owns its layout, avoiding QProgressDialog's native child geometry
management when an animation is inserted above its progress bar.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout
from .dialog_policy import QDialog

from .welcome import ParrotWalk


class ProgressParrot(ParrotWalk):
    """The same four original poses, walking at an independently set position."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('progressParrotWalk')
        self.setFixedHeight(80)
        self.fraction = None
        self._stopped = False
        self.setAccessibleName('乐乐 walking with operation progress')

    def sizeHint(self):
        return QSize(420, 80)

    def bird_rect(self):
        width = max(1., min(80., self.width() - 24.))
        height = width * 350. / 400.
        distance = max(0., self.width() - width - 24.)
        fraction = 0. if self.fraction is None else self.fraction
        return QRectF(12. + distance*fraction, self.height()-height-2., width, height)

    def set_progress(self, fraction):
        self.fraction = None if fraction is None else max(0., min(1., float(fraction)))
        if self.fraction is not None and self.fraction >= 1.:
            self.pose_timer.stop()
        elif self.isVisible() and not self._stopped and not self.pose_timer.isActive():
            self.pose_timer.start()
        self.update()

    def _next_pose(self):
        # Progress updates never reset the gait. Timer ticks never move the
        # bird horizontally, including while the underlying work is unknown.
        self.step_index = (self.step_index + 1) % len(self.poses)
        self.update()

    def stop(self):
        self._stopped = True
        self.pose_timer.stop()

    def showEvent(self, event):
        super().showEvent(event)
        if self._stopped or (self.fraction is not None and self.fraction >= 1.):
            self.pose_timer.stop()


class LeleProgressDialog(QDialog):
    """QProgressDialog-compatible API used by LELE import/process/export code.

Programmatic close is a silent cleanup; a user close, Escape, Cancel button
or cancel() marks the operation cancelled and emits canceled exactly once.
"""

    canceled = Signal()

    def __init__(self, labelText='', cancelButtonText='Cancel', minimum=0,
                 maximum=100, parent=None):
        super().__init__(parent)
        self.setObjectName('leleProgressDialog')
        self.setWindowTitle('LELE')
        self.setMinimumWidth(420)
        self._cancelled = False
        self._programmatic_close = False
        self._closed = False
        self._auto_close = True
        self._auto_reset = True
        self._minimum_duration = 4000
        self._cancel_button = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(7)
        self.label = QLabel(str(labelText), self)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.parrot_walk = ProgressParrot(self)
        layout.addWidget(self.parrot_walk)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setObjectName('operationProgressBar')
        layout.addWidget(self.progress_bar)
        self._button_row = QHBoxLayout()
        self._button_row.addStretch(1)
        layout.addLayout(self._button_row)
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.timeout.connect(self._show_if_active)
        if cancelButtonText:
            self.setCancelButton(QPushButton(str(cancelButtonText), self))
        self.setRange(minimum, maximum)
        self._show_timer.start(self._minimum_duration)

    def setCancelButton(self, button):
        old = self._cancel_button
        if old is not None:
            self._button_row.removeWidget(old)
            old.hide()
            old.deleteLater()
        self._cancel_button = button
        if button is not None:
            button.setParent(self)
            button.setAutoDefault(False)
            button.clicked.connect(self.cancel)
            self._button_row.addWidget(button)

    def setCancelButtonText(self, text):
        if not text:
            self.setCancelButton(None)
        elif self._cancel_button is None:
            self.setCancelButton(QPushButton(str(text), self))
        else:
            self._cancel_button.setText(str(text))

    def setLabelText(self, text):
        self.label.setText(str(text))

    def labelText(self):
        return self.label.text()

    def setRange(self, minimum, maximum):
        self.progress_bar.setRange(int(minimum), int(maximum))
        self._sync_progress()

    def setMinimum(self, minimum):
        self.setRange(minimum, self.maximum())

    def setMaximum(self, maximum):
        self.setRange(self.minimum(), maximum)

    def minimum(self):
        return self.progress_bar.minimum()

    def maximum(self):
        return self.progress_bar.maximum()

    def value(self):
        return self.progress_bar.value()

    def setValue(self, value):
        if self._cancelled or self._closed:
            return
        self.progress_bar.setValue(int(value))
        self._sync_progress()
        if self.maximum() > self.minimum() and self.value() >= self.maximum():
            if self._auto_close:
                self.close()
            if self._auto_reset:
                self.progress_bar.reset()

    def _sync_progress(self):
        minimum, maximum = self.minimum(), self.maximum()
        known = maximum > minimum
        self.progress_bar.setTextVisible(known)
        fraction = (self.value()-minimum)/(maximum-minimum) if known else None
        self.parrot_walk.set_progress(fraction)

    def setAutoClose(self, enabled):
        self._auto_close = bool(enabled)

    def autoClose(self):
        return self._auto_close

    def setAutoReset(self, enabled):
        self._auto_reset = bool(enabled)

    def autoReset(self):
        return self._auto_reset

    def setMinimumDuration(self, milliseconds):
        self._minimum_duration = max(0, int(milliseconds))
        if not self.isVisible() and not self._closed and not self._cancelled:
            self._show_timer.start(self._minimum_duration)

    def minimumDuration(self):
        return self._minimum_duration

    def _show_if_active(self):
        parent = self.parentWidget()
        if parent is not None and getattr(parent.window(), '_closing', False):
            self._stop_timers()
            return
        if not self._closed and not self._cancelled:
            self.show()

    def showEvent(self, event):
        self._show_timer.stop()
        super().showEvent(event)

    def hideEvent(self, event):
        self._show_timer.stop()
        self.parrot_walk.pose_timer.stop()
        super().hideEvent(event)

    def wasCanceled(self):
        return self._cancelled

    def cancel(self):
        if self._cancelled or self._closed:
            return
        self._cancelled = True
        self._stop_timers()
        self.hide()
        self.canceled.emit()

    def mark_complete(self):
        """Put the bird at the known successful endpoint before cleanup."""
        if not self._cancelled and not self._closed:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(1000)
            self._sync_progress()

    def close(self):
        self._programmatic_close = True
        self._closed = True
        self._stop_timers()
        return super().close()

    def _stop_timers(self):
        self.parrot_walk.stop()
        for timer in self.findChildren(QTimer):
            timer.stop()

    def reject(self):
        if self._cancel_button is not None:
            self.cancel()

    def closeEvent(self, event):
        if self._programmatic_close:
            event.accept()
        elif self._cancel_button is not None:
            self.cancel()
            event.accept()
        else:
            event.ignore()

    def done(self, result):
        self._stop_timers()
        super().done(result)
