"""Cancellable scientific-file parsing away from the GUI thread."""
from pathlib import Path
from time import monotonic, sleep
from PySide6.QtCore import QCoreApplication, QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import QProgressDialog, QMessageBox

ASYNC_THRESHOLD = 4 * 1024 * 1024


class FileLoader(QThread):
    completed = Signal(object, str, bool)
    progress = Signal(str, object, object)

    def __init__(self, filename):
        super().__init__(QCoreApplication.instance())
        self.filename = filename
        self._cancelled_flag=False
        self.setObjectName('LELE scientific file import')

    def requestInterruption(self):
        self._cancelled_flag=True
        super().requestInterruption()

    def run(self):
        from .formats import load_document
        from .output_text import LoadCancelled
        def report(label,value,total):
            self.progress.emit(label,value,total)
            # Bounded progress checkpoints also give Qt time to service paint,
            # cancel and mouse events during CPU-heavy Python parsing.
            sleep(.001)
        try:
            # Readers check cancellation very often. A Python flag avoids a
            # Qt/GIL transition on every source line in a long optimization.
            document = load_document(self.filename, cancelled=lambda:self._cancelled_flag,
                                     progress=report)
        except LoadCancelled:
            self.completed.emit(None, '', True)
        except Exception as exc:
            self.completed.emit(None, str(exc), False)
        else:
            self.completed.emit(document, '', self.isInterruptionRequested())


def _keep_until_finished(loader):
    app = QCoreApplication.instance()
    if not hasattr(app, '_lele_file_loaders'):
        app._lele_file_loaders = set()
        def shutdown():
            loaders = list(app._lele_file_loaders)
            for active in loaders:active.requestInterruption()
            for active in loaders:active.wait()
        app.aboutToQuit.connect(shutdown)
    app._lele_file_loaders.add(loader)
    def finished():
        app._lele_file_loaders.discard(loader)
    loader.finished.connect(finished)


class FileLoadActions:
    def _open_or_queue_file(self, filename):
        if self._closing:return
        if getattr(self, '_file_load_active', None) is not None:
            self._file_load_queue.append(filename)
            self.statusBar().showMessage(f'Queued {Path(filename).name}')
            return
        try:large = Path(filename).stat().st_size >= ASYNC_THRESHOLD
        except OSError:large = False
        path=Path(filename)
        # Even a short optimization output can contain many costly tables.
        # Keep only small, direct structure readers on the synchronous path.
        simple=path.suffix.lower() in ('.xyz','.cif','.mol','.sdf','.pdb','.vasp','.poscar','.xsf') or path.name.upper() in ('POSCAR','CONTCAR')
        if path.suffix.lower() == '.lele' or (not large and simple):
            try:return self._open_path_now(filename)
            finally:self._start_next_file_import()
        self._file_load_queue = getattr(self, '_file_load_queue', [])
        loader = FileLoader(filename)
        self._file_load_active = loader
        progress = QProgressDialog(f'Loading {Path(filename).name}…', 'Cancel', 0, 0, self)
        progress.setWindowTitle('Open file')
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setMinimumDuration(350)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(loader.requestInterruption)
        self._file_load_progress = progress
        self._file_load_started=monotonic()
        self._file_load_stage=('Starting parser',0,0)
        self._file_load_update_timer=QTimer(progress)
        self._file_load_update_timer.setInterval(500)
        self._file_load_update_timer.timeout.connect(self._update_file_load_progress)
        self._file_load_update_timer.start()
        loader.progress.connect(self._file_load_progress_changed,Qt.ConnectionType.QueuedConnection)
        loader.completed.connect(self._file_load_completed, Qt.ConnectionType.QueuedConnection)
        _keep_until_finished(loader)
        self.statusBar().showMessage(f'Loading {Path(filename).name}…')
        def show_if_loading():
            if getattr(self,'_file_load_active',None) is loader and not progress.wasCanceled() and not self._closing:
                progress.show()
        QTimer.singleShot(350,self,show_if_loading)
        loader.start()

    def _file_load_progress_changed(self,label,value,total):
        if getattr(self,'_file_load_active',None) is None:return
        self._file_load_stage=(label,value,total)
        self._update_file_load_progress()

    def _update_file_load_progress(self):
        progress=getattr(self,'_file_load_progress',None)
        if progress is None or progress.wasCanceled():return
        label,value,total=self._file_load_stage
        elapsed=monotonic()-self._file_load_started
        fraction=max(0.,min(1.,value/total)) if total else None
        progress.setRange(0,1000 if total else 0)
        if total:progress.setValue(round(fraction*1000))
        percent=f' · {fraction:.0%}' if total else ''
        progress.setLabelText(f'{Path(self._file_load_active.filename).name}\n{label}{percent}\nElapsed {elapsed:.1f} s')

    def _file_load_completed(self, document, error, cancelled):
        loader = self._file_load_active
        filename = loader.filename
        progress = self._file_load_progress
        was_cancelled = cancelled or progress.wasCanceled() or loader.isInterruptionRequested()
        self._file_load_update_timer.stop()
        if self._closing:
            self._finish_file_load(None)
            return
        if was_cancelled:
            self.statusBar().showMessage(f'Cancelled loading {Path(filename).name}', 5000)
        elif error:
            QMessageBox.warning(self, 'Could not open file', f'{Path(filename).name}\n\n{error}')
        else:
            self._file_load_stage=('Preparing structure view',0,0)
            self._update_file_load_progress()
            # Let the last phase paint before the main-thread VTK/tree update.
            QTimer.singleShot(0,self,lambda:self._finish_file_load(document))
            return
        self._finish_file_load(None)

    def _finish_file_load(self,document):
        progress=self._file_load_progress
        loader=self._file_load_active
        try:
            if document is not None and not self._closing and not progress.wasCanceled():
                self._attach_loaded_document(document)
        finally:
            self._file_load_active=None
            self._file_load_progress=None
            progress.close();progress.deleteLater()
            if loader.isRunning():loader.finished.connect(loader.deleteLater)
            else:loader.deleteLater()
        self._start_next_file_import()

    def _start_next_file_import(self):
        if self._closing:return
        if getattr(self,'_file_load_queue',None):
            next_file = self._file_load_queue.pop(0)
            QTimer.singleShot(0,self,lambda:self._open_or_queue_file(next_file))

    def _cancel_file_imports(self):
        if hasattr(self, '_file_load_queue'):self._file_load_queue.clear()
        active = getattr(self, '_file_load_active', None)
        if active is not None:active.requestInterruption()
