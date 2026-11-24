"""LELE-owned modeless dialogs, source guards and popup lifetime management.

These adapters never modify Qt classes globally. Synchronous forms use a local
nonmodal event loop so their established return-value workflows can coexist
with main-window interaction. Source-dependent acceptance is checked again
before a waiting workflow resumes. Read-only windows use ordinary show().
"""
from hashlib import blake2b
from pathlib import Path
import sys

from PySide6.QtCore import Qt, QEvent, QEventLoop, QObject, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QApplication, QWidget, QDialog as _QtDialog,
    QMessageBox as _QtMessageBox, QFileDialog as _QtFileDialog,
    QInputDialog as _QtInputDialog, QColorDialog as _QtColorDialog)
from shiboken6 import isValid

_live_dialogs = {}
_waiting = {}


def owner_window(widget):
    """Find LELE rather than treating a child dialog as the application owner."""
    current = widget
    last = widget
    while current is not None and isValid(current):
        last = current
        if hasattr(current, 'documents') and hasattr(current, 'current_doc'):
            return current
        current = current.parentWidget() if hasattr(current, 'parentWidget') else None
    return last


def configure_dialog(dialog):
    """Keep a popup above its owner without blocking the owner or other dialogs."""
    if not isValid(dialog):return dialog
    dialog.setWindowModality(Qt.WindowModality.NonModal)
    if hasattr(dialog, 'setModal'):dialog.setModal(False)
    # Native dialog ownership keeps the popup above LELE while allowing other
    # applications to cover the whole family. A global topmost flag defeats
    # that behavior (especially on Windows) and must never be inherited.
    if dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    parent = dialog.parentWidget()
    if parent is not None and isValid(parent):
        # Some analysis windows expose their source as an instance attribute
        # named `window`; call the QWidget method explicitly in that case.
        parent_window = QWidget.window(parent)
        parent_window.winId()
        dialog.winId()
        dialog.windowHandle().setTransientParent(parent_window.windowHandle())
    return dialog


class _PopupOwnerGuard(QObject):
    """Close modeless popups only after their owner actually accepts Close."""
    def __init__(self,dialog,owner):
        super().__init__(dialog);self.dialog=dialog;self.owner=owner;self.pending=False
    def eventFilter(self,obj,event):
        if obj is self.owner and event.type()==QEvent.Type.Close and not self.pending:
            self.pending=True
            QTimer.singleShot(0,self._after_close)
        return False
    def _after_close(self):
        self.pending=False
        if not isValid(self.dialog):return
        if not isValid(self.owner) or not self.owner.isVisible():
            _QtDialog.reject(self.dialog)


def _retain(dialog):
    key = id(dialog)
    if key not in _live_dialogs:
        _live_dialogs[key] = dialog
        owner=owner_window(dialog.parentWidget())
        guard=None
        if owner is not None and isValid(owner):
            guard=_PopupOwnerGuard(dialog,owner);owner.installEventFilter(guard)
        def release(*_):
            _live_dialogs.pop(key, None)
            if guard is not None and isValid(guard):
                if isValid(owner):owner.removeEventFilter(guard)
                guard.deleteLater()
        dialog.destroyed.connect(release)
        if hasattr(dialog, 'finished'):dialog.finished.connect(release)
    return dialog


def show_dialog(dialog):
    """Present and retain a read-only or live-settings window until it closes."""
    configure_dialog(dialog);_retain(dialog)
    dialog.show();dialog.raise_();dialog.activateWindow()
    return dialog


def _array_token(value):
    if value is None:return None
    if hasattr(value, 'tobytes'):
        return (getattr(value, 'shape', None), str(getattr(value, 'dtype', '')),
                blake2b(value.tobytes(), digest_size=16).digest())
    return repr(value)


def _frame_token(frame):
    if frame is None:return None
    info = getattr(frame, 'info', {})
    return (id(frame),tuple(getattr(frame,'symbols',())),
            _array_token(getattr(frame,'positions',None)),_array_token(getattr(frame,'cell',None)),
            tuple(getattr(frame,'pbc',())),
            tuple((key,repr(info.get(key))) for key in ('atom_source_order','site_occupancies','fixed_axes','vasp_fixed_axes')),
            tuple(repr(getattr(frame,key,None)) for key in ('bond_added','bond_removed','bond_snapshot','periodic_bond_snapshot')))


def _context(owner):
    """No scientific imports: startup help must remain lightweight."""
    if owner is None or not isValid(owner) or not hasattr(owner,'documents'):return None
    document = getattr(owner,'doc',None)
    frame = getattr(owner,'frame',None)
    volumes = getattr(document,'volumes',()) if document is not None else ()
    volume_tokens = tuple((id(volume),id(getattr(volume,'data',None)),
                           getattr(getattr(volume,'data',None),'shape',None),
                           _array_token(getattr(volume,'origin',None)),
                           _array_token(getattr(volume,'voxel_vectors',None))) for volume in volumes)
    return (id(document),_frame_token(frame),tuple(getattr(owner,'selection',())),
            getattr(owner,'_active_vibration',None),getattr(owner,'_energy_only_context',None),
            tuple((id(doc),tuple(id(f) for f in getattr(doc,'frames',()))) for doc in getattr(owner,'documents',())),
            id(getattr(document,'volume',None)),volume_tokens,
            tuple((id(item),repr(item)) for item in getattr(document,'annotations',())))


def _explain_stale(dialog, owner):
    reason = ('The source document, frame, selected atoms or source data changed while this dialog was open. '
              'No changes were applied. Reopen the dialog for the current source.')
    dialog._lele_context_rejection = reason
    if owner is not None and isValid(owner):
        if hasattr(owner,'statusBar'):owner.statusBar().showMessage(reason,12000)
        QMessageBox.information(owner, 'Source changed', reason)


def ensure_source_current(dialog):
    """Check before a form handler indexes a captured geometry or calculation."""
    if not getattr(dialog,'_lele_guard_active',False):return True
    owner=getattr(dialog,'_lele_source_owner',None)
    before=getattr(dialog,'_lele_source_context',None)
    if before is None or before==_context(owner):return True
    _QtDialog.reject(dialog)
    if not getattr(dialog,'_lele_context_rejection',None):_explain_stale(dialog,owner)
    return False


class _OwnerCloseGuard(QObject):
    def __init__(self, owner, abort):
        super().__init__();self.owner=owner;self.abort=abort
    def eventFilter(self, obj, event):
        if obj is self.owner and event.type() == QEvent.Type.Close:self.abort()
        return False


def _wait(dialog, *, guard=True):
    configure_dialog(dialog)
    parent = dialog.parentWidget()
    owner = owner_window(parent)
    if getattr(dialog,'independent_files',False) or getattr(parent,'independent_files',False):
        guard = False
    # Same operation cannot stack recursively while its first call is waiting.
    key = (id(owner),type(dialog),dialog.windowTitle())
    existing = _waiting.get(key)
    if existing is not None and isValid(existing):
        existing.show();existing.raise_();existing.activateWindow()
        dialog._lele_duplicate_dialog = True
        return int(_QtDialog.DialogCode.Rejected)
    before = _context(owner) if guard else None
    dialog._lele_guard_active=guard
    dialog._lele_source_owner=owner
    dialog._lele_source_context=before
    dialog._lele_context_rejection=''
    dialog._lele_wait_aborted=False
    loop = QEventLoop()
    aborted = [False]
    def abort(*_):
        aborted[0] = True
        if isValid(dialog):
            dialog._lele_wait_aborted=True
            _QtDialog.reject(dialog)
        loop.quit()
    def finish(*_):loop.quit()
    app = QApplication.instance()
    close_guard = _OwnerCloseGuard(owner,abort)
    delete_on_close = dialog.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    dialog.finished.connect(finish);dialog.destroyed.connect(finish)
    if owner is not None and isValid(owner):
        owner.installEventFilter(close_guard);owner.destroyed.connect(abort)
    if parent is not None and parent is not owner and isValid(parent):
        parent.destroyed.connect(abort)
        if isinstance(parent,_QtDialog):parent.finished.connect(abort)
    if app is not None:app.aboutToQuit.connect(abort)
    _waiting[key]=dialog
    try:
        show_dialog(dialog)
        loop.exec()
        result = int(_QtDialog.result(dialog)) if isValid(dialog) and not aborted[0] else int(_QtDialog.DialogCode.Rejected)
        accepted = bool(result)
        if isValid(dialog) and isinstance(dialog,_QtMessageBox):
            button=dialog.clickedButton()
            accepted=(button is not None and dialog.buttonRole(button) not in
                      (_QtMessageBox.ButtonRole.RejectRole,_QtMessageBox.ButtonRole.NoRole))
        if accepted and not aborted[0] and guard and before is not None and before != _context(owner):
            if isValid(dialog):
                _QtDialog.reject(dialog)
                _explain_stale(dialog,owner)
            return int(_QtDialog.DialogCode.Rejected)
        return result
    finally:
        _waiting.pop(key,None)
        if owner is not None and isValid(owner):
            owner.removeEventFilter(close_guard)
            try:owner.destroyed.disconnect(abort)
            except (RuntimeError,TypeError):pass
        if parent is not None and parent is not owner and isValid(parent):
            try:
                parent.destroyed.disconnect(abort)
                if isinstance(parent,_QtDialog):parent.finished.disconnect(abort)
            except (RuntimeError,TypeError):pass
        if app is not None:
            try:app.aboutToQuit.disconnect(abort)
            except (RuntimeError,TypeError):pass
        if isValid(dialog):
            dialog._lele_guard_active=False
            try:dialog.finished.disconnect(finish);dialog.destroyed.disconnect(finish)
            except (RuntimeError,TypeError):pass
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,delete_on_close)
        _live_dialogs.pop(id(dialog),None)


class QDialog(_QtDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);configure_dialog(self)
    def accept(self):
        if ensure_source_current(self):super().accept()
    def exec(self):return _wait(self)
    exec_ = exec
    def show(self):
        _retain(self);super().show()


class QMessageBox(_QtMessageBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);configure_dialog(self)
    def exec(self):return _wait(self)
    exec_ = exec
    def show(self):
        _retain(self);super().show()
    @classmethod
    def _notice(cls,icon,parent,title,text,buttons=None,defaultButton=None):
        message = cls(parent)
        message.setIcon(icon);message.setWindowTitle(title);message.setText(text)
        message.setStandardButtons(buttons if buttons is not None else cls.StandardButton.Ok)
        if defaultButton is not None and defaultButton != cls.StandardButton.NoButton:message.setDefaultButton(defaultButton)
        message.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        show_dialog(message)
        return cls.StandardButton.Ok
    @classmethod
    def information(cls,parent,title,text,buttons=None,defaultButton=None):
        return cls._notice(cls.Icon.Information,parent,title,text,buttons,defaultButton)
    @classmethod
    def warning(cls,parent,title,text,buttons=None,defaultButton=None):
        return cls._notice(cls.Icon.Warning,parent,title,text,buttons,defaultButton)
    @classmethod
    def critical(cls,parent,title,text,buttons=None,defaultButton=None):
        return cls._notice(cls.Icon.Critical,parent,title,text,buttons,defaultButton)
    @classmethod
    def about(cls,parent,title,text):
        return cls._notice(cls.Icon.Information,parent,title,text)
    @classmethod
    def question(cls,parent,title,text,buttons=None,defaultButton=None):
        message = cls(parent);message.setIcon(cls.Icon.Question)
        message.setWindowTitle(title);message.setText(text)
        message.setStandardButtons(buttons if buttons is not None else cls.StandardButton.Yes|cls.StandardButton.No)
        if defaultButton is not None and defaultButton != cls.StandardButton.NoButton:message.setDefaultButton(defaultButton)
        result=message.exec()
        message.deleteLater()
        return cls.StandardButton(result) if result else cls.StandardButton.Cancel


class QFileDialog(_QtFileDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setOption(self.Option.DontUseNativeDialog,True);configure_dialog(self)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == 'win32':
            from .windows_places import WindowsSidebar
            if not hasattr(self, '_windows_sidebar'):
                self._windows_sidebar = WindowsSidebar(self)
            self._windows_sidebar.show()

    def hideEvent(self, event):
        if hasattr(self, '_windows_sidebar'):
            self._windows_sidebar.hide()
        super().hideEvent(event)

    def exec(self):return _wait(self)
    exec_ = exec
    @classmethod
    def _choose(cls,parent,caption,directory,filter,*,mode,save=False,selectedFilter='',options=None):
        dialog=cls(parent,caption,directory,filter)
        if options is not None:dialog.setOptions(options)
        dialog.setOption(cls.Option.DontUseNativeDialog,True)
        dialog.setFileMode(mode)
        if save:
            dialog.setAcceptMode(cls.AcceptMode.AcceptSave)
            dialog.setOption(cls.Option.DontConfirmOverwrite,True)
        if selectedFilter:dialog.selectNameFilter(selectedFilter)
        paths=[];chosen=''
        try:
            if dialog.exec()==_QtDialog.DialogCode.Accepted:
                paths=dialog.selectedFiles();chosen=dialog.selectedNameFilter()
                if save and paths and Path(paths[0]).exists():
                    answer=QMessageBox.question(parent,'Replace file?',f'{Path(paths[0]).name} already exists. Replace it?',
                        QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                    if answer!=QMessageBox.StandardButton.Yes:paths=[]
            return paths,chosen
        finally:dialog.deleteLater()
    @classmethod
    def getOpenFileName(cls,parent=None,caption='',dir='',filter='',selectedFilter='',options=None):
        paths,chosen=cls._choose(parent,caption,dir,filter,mode=cls.FileMode.ExistingFile,selectedFilter=selectedFilter,options=options)
        return (paths[0] if paths else ''),chosen
    @classmethod
    def getOpenFileNames(cls,parent=None,caption='',dir='',filter='',selectedFilter='',options=None):
        return cls._choose(parent,caption,dir,filter,mode=cls.FileMode.ExistingFiles,selectedFilter=selectedFilter,options=options)
    @classmethod
    def getSaveFileName(cls,parent=None,caption='',dir='',filter='',selectedFilter='',options=None):
        paths,chosen=cls._choose(parent,caption,dir,filter,mode=cls.FileMode.AnyFile,save=True,selectedFilter=selectedFilter,options=options)
        return (paths[0] if paths else ''),chosen
    @classmethod
    def getExistingDirectory(cls,parent=None,caption='',dir='',options=None):
        paths,_=cls._choose(parent,caption,dir,'',mode=cls.FileMode.Directory,options=options)
        return paths[0] if paths else ''


class QInputDialog(_QtInputDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);configure_dialog(self)
    def exec(self):return _wait(self)
    exec_ = exec
    @classmethod
    def getText(cls,parent,title,label,echo=None,text='',flags=Qt.WindowType.Widget,inputMethodHints=Qt.InputMethodHint.ImhNone):
        dialog=cls(parent);dialog.setWindowTitle(title);dialog.setLabelText(label)
        dialog.setInputMode(cls.InputMode.TextInput);dialog.setTextValue(text)
        if echo is not None:dialog.setTextEchoMode(echo)
        dialog.setInputMethodHints(inputMethodHints)
        try:
            accepted=dialog.exec()==_QtDialog.DialogCode.Accepted
            return dialog.textValue(),accepted
        finally:dialog.deleteLater()
    @classmethod
    def getItem(cls,parent,title,label,items,current=0,editable=True,flags=Qt.WindowType.Widget,inputMethodHints=Qt.InputMethodHint.ImhNone):
        dialog=cls(parent);dialog.setWindowTitle(title);dialog.setLabelText(label)
        dialog.setComboBoxItems(items);dialog.setComboBoxEditable(editable)
        if items:dialog.setTextValue(items[max(0,min(current,len(items)-1))])
        dialog.setInputMethodHints(inputMethodHints)
        try:
            accepted=dialog.exec()==_QtDialog.DialogCode.Accepted
            return dialog.textValue(),accepted
        finally:dialog.deleteLater()


class QColorDialog(_QtColorDialog):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setOption(self.ColorDialogOption.DontUseNativeDialog,True);configure_dialog(self)
    def exec(self):return _wait(self)
    exec_ = exec
    @classmethod
    def getColor(cls,initial=QColor(),parent=None,title='',options=None):
        dialog=cls(initial,parent);dialog.setWindowTitle(title)
        if options is not None:dialog.setOptions(options)
        dialog.setOption(cls.ColorDialogOption.DontUseNativeDialog,True)
        try:return dialog.selectedColor() if dialog.exec()==_QtDialog.DialogCode.Accepted else QColor()
        finally:dialog.deleteLater()
