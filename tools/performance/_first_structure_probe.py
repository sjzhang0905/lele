"""Fresh-process native-canvas probe used by benchmark_first_structure.py."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

started = time.perf_counter()
sys.path.insert(0, os.getcwd())
from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication, QWidget
from lele.app import LELEWindow

marks = {'imports_s': time.perf_counter() - started}


class EglCanvas(QWidget):
    """Real EGL renderer without a platform-invalid Qt offscreen native ID.

    Qt offscreen does not provide an X11/Windows native drawable, so attaching
    its synthetic winId to QVTK would report shader errors and invalidate the
    render timing. Keep the real renderer/interactor and pipeline work here;
    this benchmark does not measure native Windows QVTK embedding.
    """
    atomClick = Signal(float, float)
    clearSelectionClick = Signal()
    fragmentGestureBegin = Signal(str, float, float)
    fragmentGestureMove = Signal(str, float, float)
    fragmentGestureEnd = Signal(str)

    def __init__(self):
        super().__init__()
        from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderWindowInteractor
        self.window = vtkRenderWindow()
        self.window.SetOffScreenRendering(True)
        self.window.SetSize(640, 480)
        self.interactor = vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.window)

    def GetRenderWindow(self):
        return self.window

    def Initialize(self):
        self.interactor.Initialize()

    def TerminateApp(self):
        self.interactor.TerminateApp()

    def resizeEvent(self, event):
        self.window.SetSize(max(1, self.width()), max(1, self.height()))
        super().resizeEvent(event)


original_ensure = LELEWindow._ensure_3d_view
def ensure_egl_canvas(window):
    with patch('lele.interaction.InteractiveVTKView', EglCanvas):
        original_ensure(window)
LELEWindow._ensure_3d_view = ensure_egl_canvas
app = QApplication(['First structure benchmark'])
app.setStyle('Fusion')
window = LELEWindow()
marks['constructed_s'] = time.perf_counter() - started
temporary = tempfile.TemporaryDirectory()
directory = Path(temporary.name)
scenario = sys.argv[1] if len(sys.argv) > 1 else 'xyz'
if scenario == 'xyz':
    payload = '6\nStartup benchmark\nO 0 0 0\nH .96 0 0\nH -.24 .92 0\nC 3 0 0\nN 4.3 .3 0\nH 4.4 1.2 .2\n'
    paths = [directory / 'first.xyz', directory / 'second.xyz']
elif scenario == 'poscar':
    payload = 'Startup benchmark\n1\n10 0 0\n0 10 0\n0 0 10\nO H C N\n1 3 1 1\nCartesian\n2 2 2\n2.96 2 2\n1.76 2.92 2\n6.4 3.2 2.2\n5 2 2\n6.3 2.3 2\n'
    paths = [directory / 'POSCAR', directory / 'CONTCAR']
elif scenario == 'pdb':
    payload = ('HETATM    1  O   HOH A   1       0.000   0.000   0.000  1.00  0.00           O\n'
               'HETATM    2  H1  HOH A   1       0.960   0.000   0.000  1.00  0.00           H\n'
               'HETATM    3  H2  HOH A   1      -0.240   0.920   0.000  1.00  0.00           H\nEND\n')
    paths = [directory / 'first.pdb', directory / 'second.pdb']
elif scenario == 'orca':
    payload = (Path.cwd() / 'examples' / 'synthetic_orca_full_v190.out').read_text()
    paths = [directory / 'first.out', directory / 'second.out']
else:
    raise ValueError(scenario)
for path in paths:
    path.write_text(payload, encoding='utf-8')


class PaintProbe(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint:
            if obj is window.welcome_page.title_label:
                marks.setdefault('first_paint_s', time.perf_counter() - started)
            if obj is window.welcome_page.parrot_walk:
                marks.setdefault('welcome_paint_s', time.perf_counter() - started)
        return False


probe = PaintProbe(window)
window.welcome_page.title_label.installEventFilter(probe)
window.welcome_page.parrot_walk.installEventFilter(probe)


def files():
    try:
        before = set(sys.modules)
        for number, path in enumerate(paths):
            begin = time.perf_counter()
            window._open_path_now(path)
            duration = time.perf_counter() - begin
            marks['first_file_s' if number == 0 else 'second_file_s'] = duration
            if window.doc is None or window.doc.path.resolve() != path.resolve():
                raise RuntimeError('The benchmark file did not become the active document.')
            if number == 0:
                marks['first_file_new_heavy_modules'] = sorted(
                    name for name in set(sys.modules) - before
                    if name.split('.')[0] in ('numpy', 'scipy', 'ase', 'vtkmodules', 'PIL'))
        marks['scenario'] = scenario
        marks['render_backend'] = window.vtk.GetRenderWindow().GetClassName()
        marks['opengl_supported'] = bool(window.vtk.GetRenderWindow().SupportsOpenGL())
        if not marks['opengl_supported']:
            raise RuntimeError('The benchmark render window has no working OpenGL context.')
        marks['ready_plus_first_file_s'] = marks['ready_s'] + marks['first_file_s']
        print(json.dumps(marks), flush=True)
        window.close()
    except Exception:
        import traceback
        traceback.print_exc()
        app.exit(1)


def check():
    if window._backend_state == 'failed':
        print(window._backend_loader.error, file=sys.stderr)
        app.exit(1)
    elif window._backend_state == 'ready':
        timer.stop()
        marks['ready_s'] = time.perf_counter() - started
        marks['native_initialized_at_ready'] = window._vtk_initialized
        marks['first_file_dependencies_at_ready'] = {
            name: name in sys.modules for name in
            ('ase.io', 'ase.neighborlist', 'scipy.spatial', 'lele.orca_results',
             'lele.cp2k_results', 'lele.surface_rendering')}
        QTimer.singleShot(0, files)


timer = QTimer()
timer.timeout.connect(check)
timer.start(5)
QTimer.singleShot(30000, lambda: app.exit(2))
window.show()
result = app.exec()
temporary.cleanup()
raise SystemExit(result)
