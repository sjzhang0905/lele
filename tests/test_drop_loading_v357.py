"""Return native drags before parsing and keep failed import queues responsive."""
from pathlib import Path
from time import monotonic, sleep
import threading
from unittest.mock import patch

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication

from lele.app import LELEWindow
from lele.formats import load_document


@pytest.fixture
def window():
    app=QApplication.instance() or QApplication([])
    with patch.object(LELEWindow,'_start_backend_loading',lambda self:None):
        w=LELEWindow()
    w._backend_state='ready'
    w.show();app.processEvents()
    yield w
    w._closing=True;w._cancel_file_imports()
    wait_for(lambda:getattr(w,'_file_load_active',None) is None)
    wait_for(lambda:not getattr(app,'_lele_file_loaders',set()))
    w.close();w.deleteLater();app.processEvents()


def wait_for(predicate, timeout=5):
    app=QApplication.instance();deadline=monotonic()+timeout
    while not predicate() and monotonic()<deadline:
        app.processEvents();sleep(.002)
    assert predicate()


def drop(paths):
    mime=QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    event=QDropEvent(QPointF(100,100),Qt.DropAction.CopyAction|Qt.DropAction.MoveAction,mime,
                     Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    return mime,event


def xyz(tmp_path,name='good.xyz'):
    path=tmp_path/name;path.write_text('1\ntest\nH 0 0 0\n')
    return path


def test_drop_copies_urls_and_returns_before_filesystem_parser_or_attachment(window,tmp_path):
    path=xyz(tmp_path);mime,event=drop([path]);attached=[];reads=[]
    def read(*args,**kwargs):
        reads.append(threading.get_ident())
        return load_document(*args,**kwargs)
    with patch('lele.formats.load_document',side_effect=read), \
         patch.object(window,'_attach_loaded_document',side_effect=attached.append):
        with patch.object(Path,'is_file',side_effect=AssertionError('Filesystem access during native drop')):
            window.dropEvent(event)
        assert event.isAccepted() and event.dropAction()==Qt.DropAction.CopyAction
        assert not reads and not attached
        # The originating event/mime data may disappear as soon as Drop returns.
        mime.clear();del event
        wait_for(lambda:len(attached)==1)
    assert attached[0].path==path.resolve()


def test_cif_failure_releases_loader_and_continues_queue_without_dismissing_error(window,tmp_path):
    broken=tmp_path/'broken.cif';broken.write_text('data_broken\n')
    good=xyz(tmp_path);attached=[];error_state=[]
    show=window._show_file_load_error
    def error(filename,message):
        error_state.append((window._file_load_active,window._file_load_progress))
        show(filename,message)
    with patch.object(window,'_attach_loaded_document',side_effect=attached.append), \
         patch.object(window,'_show_file_load_error',side_effect=error), \
         patch('lele.file_loading.QMessageBox.warning',side_effect=AssertionError('Blocking error dialog')):
        mime,event=drop([broken,good]);window.dropEvent(event)
        wait_for(lambda:len(attached)==1 and window._file_load_active is None)
        dialog=window._file_error_dialog
        assert dialog.isVisible() and dialog.windowModality()==Qt.WindowModality.NonModal
        assert not dialog.isModal()
        assert 'broken.cif' in dialog.text()
        assert error_state==[(None,None)]
        assert not window._file_load_queue
        # Unacknowledged failure also leaves later independent opens usable.
        window.open_path(good)
        assert len(attached)==2


def test_small_cif_parsing_uses_worker_thread(window,tmp_path):
    path=tmp_path/'small.cif';path.write_text('data_test\n')
    threads=[];attached=[]
    document=load_document(xyz(tmp_path))
    def read(*args,**kwargs):threads.append(threading.get_ident());return document
    with patch('lele.formats.load_document',side_effect=read), \
         patch.object(window,'_attach_loaded_document',side_effect=attached.append):
        window.open_path(path)
        assert window._file_load_active is not None
        wait_for(lambda:window._file_load_active is None)
    assert threads and threads[0]!=threading.get_ident() and attached==[document]


def test_close_before_deferred_drop_does_not_open_files(window,tmp_path):
    mime,event=drop([xyz(tmp_path)])
    with patch.object(window,'open_path') as opened:
        window.dropEvent(event)
        window._closing=True
        QApplication.instance().processEvents()
        opened.assert_not_called()
        mime,event=drop([xyz(tmp_path,'second.xyz')]);window.dropEvent(event)
        assert not event.isAccepted()


def test_move_only_drag_is_rejected_instead_of_confirming_source_removal(window,tmp_path):
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(xyz(tmp_path)))])
    event=QDropEvent(QPointF(100,100),Qt.DropAction.MoveAction,mime,
                     Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    with patch.object(window,'open_path') as opened:
        window.dropEvent(event)
        QApplication.instance().processEvents()
        assert not event.isAccepted()
        opened.assert_not_called()


def test_drop_waits_for_backend_and_keeps_folder_batch_but_rejects_remote_urls(window,tmp_path):
    path=xyz(tmp_path);window._backend_state='loading'
    mime,event=drop([tmp_path,path]);window.dropEvent(event)
    wait_for(lambda:bool(window._pending_open_paths))
    from lele.import_paths import ImportBatch
    assert window._pending_open_paths == [ImportBatch((str(tmp_path), str(path)))]
    remote=QMimeData();remote.setUrls([QUrl('https://example.invalid/structure.cif')])
    event=QDropEvent(QPointF(100,100),Qt.DropAction.CopyAction,remote,
                     Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    window.dropEvent(event)
    assert not event.isAccepted()


def test_view_preparation_error_also_releases_queue(window,tmp_path):
    first=tmp_path/'first.cif';first.write_text('data_test\n');second=xyz(tmp_path)
    document=load_document(second);attempts=[]
    def attach(doc):
        attempts.append(doc)
        if len(attempts)==1:raise ValueError('Could not prepare this view')
    with patch('lele.formats.load_document',return_value=document), \
         patch.object(window,'_attach_loaded_document',side_effect=attach):
        window.open_path(first);window.open_path(second)
        wait_for(lambda:len(attempts)==2 and window._file_load_active is None)
    assert 'Could not prepare this view' in window._file_error_dialog.text()


def test_new_open_during_scheduled_queue_handoff_cannot_jump_earlier_files(window,tmp_path):
    second,third,fourth=[xyz(tmp_path,name+'.xyz') for name in ('second','third','fourth')]
    window._file_load_queue=[second,third]
    callbacks=[];opened=[]
    with patch('lele.file_loading.QTimer.singleShot',side_effect=lambda *args:callbacks.append(args[-1])), \
         patch.object(window,'_open_path_now',side_effect=opened.append):
        window._start_next_file_import()
        window.open_path(fourth)
        assert not opened and window._file_load_queue==[second,third,fourth]
        while callbacks:callbacks.pop(0)()
    assert opened==[second,third,fourth]
    assert not window._file_load_queue and not window._file_load_drain_pending


def test_reentrant_open_during_small_file_nested_event_loop_is_queued(window,tmp_path):
    first,second=[xyz(tmp_path,name+'.xyz') for name in ('first','second')]
    opened=[]
    def open_now(path):
        opened.append(path)
        if path==first:
            window.open_path(second)
            assert opened==[first]
    with patch.object(window,'_open_path_now',side_effect=open_now):
        window.open_path(first)
        assert opened==[first]
        wait_for(lambda:len(opened)==2)
    assert opened==[first,second]
