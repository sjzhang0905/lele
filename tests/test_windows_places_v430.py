import json
import ntpath
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QEventLoop, QProcess, QTimer, QUrl, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QListView

from lele import dialog_policy, windows_places
from test_dialog_policy_v3130 import app, owner, run_static, NativeFileDialog


class SamplePlaces(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.folders = []

    def refresh(self):
        pass


@pytest.mark.parametrize('method', ['getOpenFileName', 'getOpenFileNames', 'getSaveFileName',
                                    'getExistingDirectory'])
def test_live_quick_access_in_file_pickers(app, owner, monkeypatch, tmp_path, method):
    source = SamplePlaces()
    monkeypatch.setattr(app, '_lele_explorer_places', source, raising=False)
    monkeypatch.setattr(dialog_policy, 'sys', SimpleNamespace(platform='win32'))
    known = windows_places.QStandardPaths.StandardLocation
    folders = {known.DesktopLocation: tmp_path / 'redirected' / 'Desktop',
               known.DownloadLocation: tmp_path / 'Downloads',
               known.DocumentsLocation: tmp_path / 'Documents'}
    for path in folders.values():
        path.mkdir(parents=True)
    monkeypatch.setattr(windows_places, 'QStandardPaths', SimpleNamespace(
        StandardLocation=known, writableLocation=lambda kind: str(folders[kind]),
        displayName=lambda kind: folders[kind].name))
    pin = tmp_path / '结构 2026'
    pin.mkdir()
    for name in ('one.xyz', 'two.xyz'):
        (pin / name).touch()
    title = 'Choose ' + method

    def choose(dialog):
        sidebar = dialog.findChild(QListView, 'sidebar')
        edit = dialog.findChild(QLineEdit, 'fileNameEdit')
        model = sidebar.model()
        urls = dialog.sidebarUrls()
        desktop = QUrl.fromLocalFile(str(folders[known.DesktopLocation]))
        assert all(QUrl.fromLocalFile(str(path)) in urls for path in folders.values())
        assert QUrl('file:') in urls
        if method == 'getSaveFileName':
            edit.setText('export.xyz')
        source.folders = [(str(pin), '计算结果'), (str(folders[known.DesktopLocation]), '桌面')]
        source.changed.emit()
        app.processEvents()
        urls = dialog.sidebarUrls()
        assert urls.count(desktop) == 1
        assert model.data(model.index(urls.index(desktop), 0)) == '桌面'
        idx = model.index(urls.index(QUrl.fromLocalFile(str(pin))), 0)
        assert model.data(idx) == '计算结果'
        assert Path(dialog.directory().absolutePath()) == tmp_path
        if method == 'getSaveFileName':
            assert edit.text() == 'export.xyz'
        sidebar.scrollTo(idx)
        QTest.mouseClick(sidebar.viewport(), Qt.MouseButton.LeftButton, pos=sidebar.visualRect(idx).center())
        app.processEvents()
        assert Path(dialog.directory().absolutePath()) == pin
        source.folders = []
        source.changed.emit()
        assert QUrl.fromLocalFile(str(pin)) not in dialog.sidebarUrls()
        assert Path(dialog.directory().absolutePath()) == pin
        if method == 'getOpenFileName':
            dialog.selectFile(str(pin / 'one.xyz'))
        elif method == 'getOpenFileNames':
            edit.setText('"one.xyz" "two.xyz"')
        elif method == 'getSaveFileName':
            edit.setText('export.xyz')
        dialog.accept()

    picker = getattr(dialog_policy.QFileDialog, method)
    result = run_static(app, owner, NativeFileDialog, title,
                        lambda: picker(owner, title, str(tmp_path)), choose)
    if method == 'getOpenFileNames':
        assert {Path(item) for item in result[0]} == {pin / 'one.xyz', pin / 'two.xyz'}
    elif method == 'getExistingDirectory':
        assert Path(result) == pin
    else:
        assert Path(result[0]) == pin / ('export.xyz' if method == 'getSaveFileName' else 'one.xyz')
    # Opening another picker must not turn transient pins into saved Qt bookmarks.
    fresh = dialog_policy.QFileDialog(owner)
    assert QUrl.fromLocalFile(str(folders[known.DesktopLocation])) not in fresh.sidebarUrls()
    fresh.deleteLater()


def test_explorer_process_cache_failure_and_unpin(app, monkeypatch):
    source = windows_places.ExplorerPlaces(app)
    original_start = source.process.start
    launched = []
    raw = json.dumps([{'path': 'C:/用户/Projects', 'name': '项目'}, {'path': 'shell:Home'},
                      {'path': r'\\server\shared\DFT', 'name': 'DFT'}],
                     ensure_ascii=False).encode()

    def launch(exe, args):
        assert ntpath.isabs(exe) and exe.endswith('powershell.exe')
        assert '-NonInteractive' in args and '-NoProfile' in args
        assert 'Shell.Application' in args[-1]
        launched.append(exe)
        original_start(sys.executable, ['-c', 'import sys; sys.stdout.buffer.write(bytes.fromhex(sys.argv[1]))',
                                        raw.hex()])

    monkeypatch.setenv('SystemRoot', r'C:\Windows')
    monkeypatch.setattr(source.process, 'start', launch)
    loop = QEventLoop()
    source.process.finished.connect(loop.quit)
    changed = []
    source.changed.connect(lambda: changed.append(list(source.folders)))

    def query():
        timer = QTimer(singleShot=True)
        timer.timeout.connect(loop.quit)
        timer.start(5000)
        source.refresh()
        source.refresh()
        loop.exec()
        assert timer.isActive() and source.process.state() == QProcess.ProcessState.NotRunning
        timer.stop()

    query()
    expected = [('C:/用户/Projects', '项目'), (r'\\server\shared\DFT', 'DFT')]
    assert changed == [expected] and len(launched) == 1
    source.refresh()
    assert len(launched) == 1
    source.next_query = 0.
    raw = b'bad shell output'
    query()
    assert source.folders == expected and len(changed) == 1
    source.next_query = 0.
    raw = b'[]'
    query()
    assert changed == [expected, []]
    source.deleteLater()


@pytest.mark.skipif(sys.platform != 'win32', reason='Requires a Windows desktop with Explorer')
def test_read_live_explorer_namespace_on_windows(app):
    source = windows_places.ExplorerPlaces(app)
    pending = [('pending', '')]
    source.folders = pending
    loop = QEventLoop()
    timeout = QTimer(singleShot=True)
    timeout.timeout.connect(loop.quit)
    source.process.finished.connect(loop.quit)
    source.process.errorOccurred.connect(loop.quit)
    try:
        timeout.start(15000)
        source.refresh()
        loop.exec()
        assert timeout.isActive()
        assert source.folders is not pending  # An empty, successfully enumerated list is valid.
        assert all(ntpath.isabs(path) for path, label in source.folders)
    finally:
        timeout.stop()
        source.deleteLater()
