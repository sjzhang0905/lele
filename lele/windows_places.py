"""Windows Explorer folders for LELE's nonmodal Qt file dialogs."""
import json
import ntpath
import os
from time import monotonic

from PySide6.QtCore import QObject, QProcess, QStandardPaths, Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import QApplication, QListView


_EXPLORER_QUERY = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$shell = New-Object -ComObject Shell.Application
$folder = $shell.NameSpace('shell:::{679F85CB-0220-4080-B29B-5540CC05AAB6}')
if ($null -eq $folder) {
    $folder = $shell.NameSpace('shell:::{F874310E-B6B7-47DC-BC84-B9E6B38F5903}')
}
if ($null -eq $folder) { exit 1 }
$places = @(foreach ($item in $folder.Items()) {
    try {
        if ($item.IsFolder -and $item.IsFileSystem) {
            $attrs = $item.ExtendedProperty('System.FileAttributes')
            if (-not $attrs -or ([long]$attrs -band 16)) {
                [PSCustomObject]@{path = $item.Path; name = $item.Name}
            }
        }
    } catch { continue }
})
ConvertTo-Json -InputObject $places -Compress
"""


def _folder_list(output):
    rows = json.loads(output.decode('utf-8-sig'))
    if not isinstance(rows, list):
        raise ValueError('Expected a list of Explorer folders')
    return [(row['path'], row.get('name', '')) for row in rows
            if isinstance(row, dict) and isinstance(row.get('path'), str)
            and ntpath.isabs(row['path']) and isinstance(row.get('name', ''), str)]


class ExplorerPlaces(QObject):
    """Share one asynchronous Shell query among all open dialogs."""
    changed = Signal()

    def __init__(self, app):
        super().__init__(app)
        self.folders = []
        self.next_query = 0.
        self.process = QProcess(self)
        self.timer = QTimer(self, singleShot=True)
        self.timer.timeout.connect(self.process.kill)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        app.aboutToQuit.connect(self.process.kill)

    def refresh(self):
        if monotonic() < self.next_query or self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.next_query = monotonic() + 30.
        system = os.environ.get('SystemRoot')
        if system:
            exe = ntpath.join(system, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
            self.timer.start(10000)
            self.process.start(exe, ['-NoLogo', '-NoProfile', '-NonInteractive', '-STA',
                                     '-WindowStyle', 'Hidden', '-Command', _EXPLORER_QUERY])

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.timer.stop()

    def _finished(self, code, status):
        self.timer.stop()
        output = bytes(self.process.readAllStandardOutput())
        if code or status != QProcess.ExitStatus.NormalExit:
            return
        try:
            folders = _folder_list(output)
        except ValueError:
            return
        if self.folders != folders:
            self.folders = folders
            self.changed.emit()


def _place_key(url):
    path = url.toLocalFile()
    return ntpath.normcase(ntpath.normpath(path)) if path else url.toString()


class WindowsSidebar(QObject):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        app = QApplication.instance()
        if not hasattr(app, '_lele_explorer_places'):
            app._lele_explorer_places = ExplorerPlaces(app)
        self.source = app._lele_explorer_places
        self.source.changed.connect(self.update_folders)
        # Qt resolves redirected and OneDrive-backed known folders for the current user.
        location = QStandardPaths.StandardLocation
        self.defaults = [(QStandardPaths.writableLocation(kind), QStandardPaths.displayName(kind))
                         for kind in (location.DesktopLocation, location.DownloadLocation,
                                      location.DocumentsLocation)]
        self.added = set()
        self.active = False
        self.labels = {}
        self.view = dialog.findChild(QListView, 'sidebar')
        if self.view is not None:
            self.view.model().dataChanged.connect(self._display_names)

    def show(self):
        self.active = True
        self.update_folders()
        self.source.refresh()

    def _user_urls(self):
        return [url for url in self.dialog.sidebarUrls() if _place_key(url) not in self.added]

    def hide(self):
        self.active = False
        # Qt saves the sidebar on close. Keep its own bookmarks separate from live pins.
        if self.added:
            self.dialog.setSidebarUrls(self._user_urls())
            self.added.clear()

    def update_folders(self):
        if not self.active:
            return
        urls = self._user_urls()
        original = {_place_key(url) for url in urls}
        seen = set(original)
        self.labels = {}
        for path, label in (*self.source.folders, *self.defaults):
            if not path:
                continue
            url = QUrl.fromLocalFile(path)
            key = _place_key(url)
            if label:
                self.labels.setdefault(key, label)
            if key not in seen:
                urls.append(url)
                seen.add(key)
        self.added = seen - original
        if urls != self.dialog.sidebarUrls():
            self.dialog.setSidebarUrls(urls)
        self._display_names()

    def _display_names(self, first=None, last=None, roles=None):
        # The Qt filesystem model can replace a shell display name when it loads an icon.
        if not self.active or self.view is None:
            return
        model = self.view.model()
        urls = self.dialog.sidebarUrls()
        rows = range(len(urls)) if first is None else range(first.row(), min(last.row()+1, len(urls)))
        for row in rows:
            label = self.labels.get(_place_key(urls[row]))
            index = model.index(row, 0)
            if label and model.data(index) != label:
                model.setData(index, label, Qt.ItemDataRole.DisplayRole)
