"""Cancellable scientific-file parsing away from the GUI thread."""
from pathlib import Path
from time import monotonic, sleep
from PySide6.QtCore import QCoreApplication, QThread, QTimer, Signal, Qt
from .dialog_policy import QMessageBox
from .progress_dialog import LeleProgressDialog
from .import_paths import ImportBatch

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


class ImportPathLoader(QThread):
    """Discover folders off-thread before any batch member starts parsing."""
    completed = Signal(object, str, bool)
    progress = Signal(str, object, object)

    def __init__(self, batch):
        super().__init__(QCoreApplication.instance())
        self.batch = batch
        self._cancelled_flag = False
        self.setObjectName('LELE import folder discovery')

    def requestInterruption(self):
        self._cancelled_flag = True
        super().requestInterruption()

    def run(self):
        from .import_paths import prepare_import_batch
        from .output_text import LoadCancelled
        try:
            result = prepare_import_batch(self.batch, cancelled=lambda: self._cancelled_flag,
                                          progress=self.progress.emit)
        except LoadCancelled:
            self.completed.emit(None, '', True)
        except Exception as exc:
            self.completed.emit(None, str(exc), False)
        else:
            self.completed.emit(result, '', self._cancelled_flag)


def _import_name(filename):
    return f'{len(filename.paths)} selected path(s)' if isinstance(filename, ImportBatch) else Path(filename).name


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
    def _show_file_load_error(self, filename, error):
        """Display failures without retaining a native drop or import queue."""
        if self._closing:return
        message = f'{Path(filename).name}\n\n{error}'
        dialog = getattr(self, '_file_error_dialog', None)
        if dialog is not None:
            dialog.setText(dialog.text() + '\n\n' + message)
            dialog.show()
            return
        dialog = QMessageBox(QMessageBox.Icon.Warning, 'Could not open file',
                             message, QMessageBox.StandardButton.Ok, self)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._file_error_dialog = dialog
        def finished(_):
            if getattr(self, '_file_error_dialog', None) is dialog:
                self._file_error_dialog = None
        dialog.finished.connect(finished)
        dialog.show()

    def _open_or_queue_file(self, filename):
        if self._closing:return
        self._file_load_queue = getattr(self, '_file_load_queue', [])
        self._file_load_queue.append(filename)
        if (getattr(self, '_file_batch_active', None) is not None
                or getattr(self, '_file_load_active', None) is not None
                or getattr(self, '_file_load_sync_active', False)
                or getattr(self, '_file_load_drain_pending', False)):
            self.statusBar().showMessage(f'Queued {_import_name(filename)}')
            return
        self._drain_file_import_queue()

    def _drain_file_import_queue(self):
        self._file_load_drain_pending=False
        if (self._closing or getattr(self,'_file_batch_active',None) is not None
                or getattr(self,'_file_load_active',None) is not None
                or getattr(self,'_file_load_sync_active',False)):
            return
        if self._file_load_queue:
            self._begin_file_import(self._file_load_queue.pop(0))

    def _begin_file_import(self, filename):
        if isinstance(filename, ImportBatch):
            self._begin_import_batch(filename)
            return
        try:large = Path(filename).stat().st_size >= ASYNC_THRESHOLD
        except OSError:large = False
        path=Path(filename)
        # Even a short optimization output can contain many costly tables.
        # Keep only small, direct structure readers on the synchronous path.
        # CIF symmetry expansion can be expensive even for a tiny source file.
        simple=path.suffix.lower() in ('.xyz','.mol','.sdf','.pdb','.vasp','.poscar','.xsf') or path.name.upper() in ('POSCAR','CONTCAR')
        if path.suffix.lower() == '.lele' or (not large and simple):
            self._file_load_sync_active=True
            try:return self._open_path_now(filename)
            finally:
                self._file_load_sync_active=False
                self._start_next_file_import()
        loader = FileLoader(filename)
        self._file_load_active = loader
        progress = LeleProgressDialog(f'Loading {Path(filename).name}…', 'Cancel', 0, 0, self)
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
        loader.start()

    def _begin_import_batch(self, batch):
        loader = ImportPathLoader(batch)
        self._file_batch_active = loader
        progress = LeleProgressDialog('Finding supported files…', 'Cancel', 0, 0, self)
        progress.setWindowTitle('Open files / folder')
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setMinimumDuration(350)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.canceled.connect(loader.requestInterruption)
        self._file_batch_progress = progress
        loader.progress.connect(self._file_batch_progress_changed, Qt.ConnectionType.QueuedConnection)
        loader.completed.connect(self._file_batch_completed, Qt.ConnectionType.QueuedConnection)
        _keep_until_finished(loader)
        self.statusBar().showMessage('Finding and sorting supported files…')
        loader.start()

    def _file_batch_progress_changed(self, label, value, total):
        progress = getattr(self, '_file_batch_progress', None)
        if progress is not None and not progress.wasCanceled():
            progress.setLabelText(label)
            progress.setRange(0, 0)

    def _file_batch_completed(self, result, error, cancelled):
        loader = getattr(self, '_file_batch_active', None)
        if loader is None:
            return
        progress = self._file_batch_progress
        cancelled = cancelled or progress.wasCanceled() or loader.isInterruptionRequested()
        self._file_batch_active = None
        self._file_batch_progress = None
        if not error and not cancelled and not self._closing:
            # Keep this batch ahead of requests received while its folders were
            # being scanned. The existing sequential parser preserves this order
            # in the Files tree, even when some documents fail to load.
            self._file_load_queue[0:0] = list(result.paths)
            progress.mark_complete()
            self.statusBar().showMessage(
                f'Found {len(result.paths)} files; skipped {result.skipped} unrecognized or project files', 5000)
        elif cancelled and not self._closing:
            self.statusBar().showMessage('Cancelled folder discovery', 5000)
        progress.close();progress.deleteLater()
        if loader.isRunning():loader.finished.connect(loader.deleteLater)
        else:loader.deleteLater()
        self._start_next_file_import()
        if not self._closing and not cancelled:
            if error:
                self._show_file_load_error('Selected paths', error)
            elif result.issues:
                self._show_file_load_error('Some paths could not be read', '\n'.join(result.issues))

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
        loader = getattr(self, '_file_load_active', None)
        if loader is None:return
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
            # Release the loader/progress first. Error acknowledgement must not
            # stop the remaining dropped files from being imported.
            self._finish_file_load(None)
            self._show_file_load_error(filename, error)
            return
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
        error=None
        try:
            if document is not None and not self._closing and not progress.wasCanceled():
                self._attach_loaded_document(document)
                progress.mark_complete()
        except Exception as exc:
            error=str(exc)
        finally:
            self._file_load_active=None
            self._file_load_progress=None
            progress.close();progress.deleteLater()
            if loader.isRunning():loader.finished.connect(loader.deleteLater)
            else:loader.deleteLater()
        self._start_next_file_import()
        if error is not None:self._show_file_load_error(loader.filename,error)

    def _start_next_file_import(self):
        if (self._closing or getattr(self,'_file_batch_active',None) is not None
                or getattr(self,'_file_load_active',None) is not None
                or getattr(self,'_file_load_sync_active',False)
                or getattr(self,'_file_load_drain_pending',False)):
            return
        if getattr(self,'_file_load_queue',None):
            # Leave the head queued until execution. New requests arriving in
            # this event-loop gap must append behind it instead of jumping it.
            self._file_load_drain_pending=True
            QTimer.singleShot(0,self,self._drain_file_import_queue)

    def _cancel_file_imports(self):
        if hasattr(self, '_file_load_queue'):self._file_load_queue.clear()
        active = getattr(self, '_file_load_active', None)
        if active is not None:active.requestInterruption()
        batch = getattr(self, '_file_batch_active', None)
        if batch is not None:batch.requestInterruption()
        if self._closing:
            batch_progress=getattr(self,'_file_batch_progress',None)
            if batch_progress is not None:batch_progress.close()
            progress=getattr(self,'_file_load_progress',None)
            if progress is not None:progress.close()
            dialog=getattr(self,'_file_error_dialog',None)
            if dialog is not None:dialog.close()
