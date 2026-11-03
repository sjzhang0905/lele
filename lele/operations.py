"""Delayed progress for data work, and cooperative main-thread Qt/VTK work.

Data callbacks must not access Qt widgets or VTK render windows. The nested
event loop keeps the synchronous call sites simple while a modal progress
window prevents edits to their inputs. GUI construction uses ui_operation and
checkpoints instead; it never moves Qt/VTK objects to another thread.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from time import monotonic

from PySide6.QtCore import QEventLoop, QThread, QTimer, Qt, Signal, QObject, QEvent
from PySide6.QtWidgets import QApplication, QProgressDialog, QWidget

from .output_text import output_read_session, LoadCancelled, check_load_cancelled

DELAY_MS = 400
_ui_scope = ContextVar('lele_ui_operation', default=None)


class OperationProgress(QProgressDialog):
    def __init__(self, parent, title, cancellable=False):
        super().__init__(title + '…', 'Cancel' if cancellable else '', 0, 0, parent)
        self.setWindowTitle(title)
        if not cancellable:self.setCancelButton(None)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumDuration(2_000_000_000)  # show only after our delay
        self.setAutoClose(False);self.setAutoReset(False)
        self.cancellable=cancellable
        self._finishing=False
        self.started=monotonic();self.stage=(title, 0, 0)
        self.timer=QTimer(self);self.timer.setInterval(100)
        self.timer.timeout.connect(self.refresh);self.timer.start()
        self._pumping=False;self._last_pump=0.

    def report(self, label, value=0, total=0):
        self.stage=(label, value, total)
        self.refresh()

    def refresh(self):
        if self.wasCanceled():return
        label,value,total=self.stage
        elapsed=monotonic()-self.started
        self.setRange(0, 1000 if total else 0)
        if total:self.setValue(round(1000*max(0.,min(1.,value/total))))
        percentage=f' · {value/total:.0%}' if total else ''
        self.setLabelText(f'{label}{percentage}\nElapsed {elapsed:.1f} s')
        if elapsed*1000>=DELAY_MS and not self.isVisible():self.show()

    def checkpoint(self, label=None, value=0, total=0):
        now=monotonic()
        if label is not None:self.stage=(label,value,total)
        if self._pumping or now-self._last_pump<.05:return
        self._last_pump=now;self._pumping=True
        try:
            self.refresh()
            # Once visible it is modal. Until then exclude input so a long
            # scene update cannot recursively trigger another edit.
            QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        finally:self._pumping=False

    def finish(self):
        self._finishing=True;self.timer.stop();self.close();self.deleteLater()

    def reject(self):
        if self.cancellable or self._finishing:super().reject()

    def closeEvent(self,event):
        if self.cancellable or self._finishing:super().closeEvent(event)
        else:event.ignore()


class InputGuard(QObject):
    """Block input during the invisible delay without disabling the dialog."""
    blocked={QEvent.Type.MouseButtonPress,QEvent.Type.MouseButtonRelease,
        QEvent.Type.MouseButtonDblClick,QEvent.Type.MouseMove,QEvent.Type.Wheel,
        QEvent.Type.KeyPress,QEvent.Type.KeyRelease,QEvent.Type.Shortcut,
        QEvent.Type.ShortcutOverride,QEvent.Type.Close,QEvent.Type.Drop}

    def __init__(self,dialog):super().__init__(dialog);self.dialog=dialog

    def eventFilter(self,target,event):
        if event.type() not in self.blocked:return False
        widget=target
        while widget is not None:
            if widget is self.dialog:return False
            widget=widget.parent() if hasattr(widget,'parent') else None
        return True


class DataWorker(QThread):
    progress=Signal(str, object, object)

    def __init__(self, function, cancellable):
        super().__init__();self.function=function;self.cancellable=cancellable
        self.value=None;self.error=None;self.cancelled=False

    def run(self):
        try:
            with output_read_session(cancelled=(self.isInterruptionRequested if self.cancellable else None),
                                     progress=self.progress.emit):
                self.value=self.function()
                check_load_cancelled()
        except BaseException as exc:self.error=exc


def run_data_task(parent, title, function, *, cancellable=False):
    """Return a completed value or raise the original error on the GUI thread."""
    app=QApplication.instance()
    if app is None or QThread.currentThread()!=app.thread():return function()
    # Pause source animation while a worker reads a document. Restore it even
    # after an exception. The modal dialog blocks other mutations immediately,
    # while remaining invisible for fast operations.
    root=QWidget.window(parent);timers=[]
    for name in ('playback','vibration_timer'):
        timer=getattr(root,name,None)
        if timer is not None and timer.isActive():timer.stop();timers.append(timer)
    progress=OperationProgress(parent,title,cancellable)
    outer=_ui_scope.get()
    if outer is not None:outer.timer.stop();outer.hide()
    worker=DataWorker(function,cancellable);loop=QEventLoop()
    worker.progress.connect(progress.report,Qt.ConnectionType.QueuedConnection)
    worker.finished.connect(loop.quit,Qt.ConnectionType.QueuedConnection)
    if cancellable:progress.canceled.connect(worker.requestInterruption)
    guard=InputGuard(progress);app.installEventFilter(guard)
    try:
        worker.start();loop.exec();worker.wait()
        if worker.error is not None:raise worker.error
        return worker.value
    finally:
        app.removeEventFilter(guard);progress.finish();worker.deleteLater()
        for timer in timers:timer.start()
        if outer is not None:outer.started=monotonic();outer.timer.start()


@contextmanager
def ui_operation(parent,title):
    """Cooperative progress for Qt/VTK updates that must stay on the GUI thread."""
    if not isinstance(parent,QWidget) or QApplication.instance() is None:
        yield None;return
    if _ui_scope.get() is not None:
        yield _ui_scope.get();return
    progress=OperationProgress(parent,title)
    token=_ui_scope.set(progress)
    try:
        with output_read_session(progress=progress.checkpoint):
            yield progress
    finally:
        _ui_scope.reset(token);progress.finish()


def ui_busy():
    return _ui_scope.get() is not None


def ui_checkpoint(label=None,value=0,total=0):
    progress=_ui_scope.get()
    if progress is not None:progress.checkpoint(label,value,total)


def gui_operation(title):
    """Wrap widget construction/redraw while retaining normal signal signatures."""
    def decorate(method):
        @wraps(method)
        def wrapped(self,*args,**kwargs):
            with ui_operation(self,title):return method(self,*args,**kwargs)
        return wrapped
    return decorate
