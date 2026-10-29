"""Fresh-process checks for first-paint ordering and background startup."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


class StartupTests(unittest.TestCase):
    def run_child(self, code):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                   VTK_DEFAULT_OPENGL_WINDOW='vtkEGLRenderWindow')
        result = subprocess.run(
            [sys.executable, '-c', textwrap.dedent(code)],
            cwd=Path(__file__).resolve().parents[1], env=env,
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_first_paint_precedes_automatic_preload_and_gui_keeps_responding(self):
        self.run_child('''
            import importlib.abc
            import sys
            import threading
            import traceback
            from unittest.mock import patch

            scientific = {'numpy', 'scipy', 'ase', 'vtkmodules', 'matplotlib'}
            painted = False
            class FirstPaintGuard(importlib.abc.MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.split('.')[0] in scientific:
                        assert painted, 'Premature import: ' + fullname
            sys.meta_path.insert(0, FirstPaintGuard())

            from PySide6.QtCore import QEvent, QObject, QTimer, Signal
            from PySide6.QtWidgets import QApplication, QWidget
            from lele.app import LELEWindow
            from lele import backend_loader

            main_thread = threading.get_ident()
            entered, release = threading.Event(), threading.Event()
            import_threads, canvas_threads = [], []
            real_load = backend_loader.load_backend_modules
            def gated_load():
                import_threads.append(threading.get_ident())
                entered.set()
                assert release.wait(5), 'GUI did not respond during preload'
                real_load()
            backend_loader.load_backend_modules = gated_load

            class HeadlessCanvas(QWidget):
                atomClick = Signal(float, float)
                clearSelectionClick = Signal()
                fragmentGestureBegin = Signal(str, float, float)
                fragmentGestureMove = Signal(str, float, float)
                fragmentGestureEnd = Signal(str)
                def __init__(self):
                    super().__init__()
                    from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderWindowInteractor
                    self.window = vtkRenderWindow()
                    self.interactor = vtkRenderWindowInteractor()
                    self.interactor.SetRenderWindow(self.window)
                    self.window.Render = lambda: None
                    self.initialize_count = 0
                def GetRenderWindow(self): return self.window
                def Initialize(self): self.initialize_count += 1
                def TerminateApp(self): pass

            real_ensure = LELEWindow._ensure_3d_view
            def create_canvas(window):
                canvas_threads.append(threading.get_ident())
                with patch('lele.interaction.InteractiveVTKView', HeadlessCanvas):
                    real_ensure(window)
            LELEWindow._ensure_3d_view = create_canvas

            app = QApplication(['StartupTests'])
            def fail(*args):
                traceback.print_exception(*args)
                release.set()
                app.exit(1)
            sys.excepthook = fail
            with patch.object(LELEWindow, '_read_user_style_presets', return_value={}):
                window = LELEWindow()
            assert not entered.is_set() and window.vtk is None
            class PaintProbe(QObject):
                def eventFilter(self, watched, event):
                    global painted
                    if event.type() == QEvent.Type.Paint and not painted:
                        assert not (scientific & {n.split('.')[0] for n in sys.modules})
                        painted = True
                    return False
            probe = PaintProbe(window)
            window.welcome_page.title_label.installEventFilter(probe)
            ticks = 0
            def tick():
                global ticks
                if entered.is_set() and not release.is_set():
                    ticks += 1
                    # These run while the import thread is waiting, proving
                    # the GUI loop and welcome settings remain usable.
                    window.preset_combo.setCurrentIndex(window.preset_combo.findData('Soft pastel'))
                    window._set_option('background', '#eeeeee')
                    window._set_option('bond_cutoff', 1.3)
                    window.clear_selection()
                    window.reset_camera()
                    assert window.welcome_page.parrot_walk.pose_timer.isActive()
                    if ticks == 3:
                        release.set()
                if window._backend_state == 'failed':
                    raise AssertionError(window._backend_loader.error)
                if window._backend_state == 'ready':
                    assert painted and ticks >= 3
                    assert import_threads and main_thread not in import_threads
                    assert canvas_threads == [main_thread]
                    assert window.doc is None and window.vtk.initialize_count == 0
                    assert window.renderer.options is window.render_options
                    assert window.render_options.atom_palette == 'Pastel'
                    assert window.render_options.background == '#eeeeee'
                    assert window.render_options.bond_cutoff == 1.3
                    assert window.canvas_stack.currentWidget() is window.welcome_page
                    assert {'numpy', 'scipy', 'ase', 'vtkmodules'} <= {n.split('.')[0] for n in sys.modules}
                    timer.stop()
                    window.close()
            timer = QTimer()
            timer.timeout.connect(tick)
            timer.start(10)
            def timeout():
                release.set()
                app.exit(2)
            QTimer.singleShot(15000, timeout)
            window.show()
            result = app.exec()
            release.set()
            assert result == 0, result
            assert not window._backend_loader.isRunning()
        ''')

    def test_close_during_import_finishes_worker_before_application_teardown(self):
        self.run_child('''
            import sys
            import threading
            from unittest.mock import patch
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication
            from lele.app import LELEWindow
            from lele import backend_loader

            entered, release = threading.Event(), threading.Event()
            def gated_load():
                entered.set()
                assert release.wait(5)
            backend_loader.load_backend_modules = gated_load
            app = QApplication(['CloseDuringStartup'])
            with patch.object(LELEWindow, '_read_user_style_presets', return_value={}):
                window = LELEWindow(['queued.xyz'])
            def tick():
                if entered.is_set():
                    timer.stop()
                    assert window._backend_loader.isRunning()
                    threading.Timer(0.1, release.set).start()
                    window.close()
            timer = QTimer()
            timer.timeout.connect(tick)
            timer.start(10)
            def timeout():
                release.set()
                app.exit(2)
            QTimer.singleShot(10000, timeout)
            window.show()
            assert app.exec() == 0
            assert window._backend_loader.loaded
            assert not window._backend_loader.isRunning()
            assert window.vtk is None and window.doc is None
            assert not window._pending_open_paths
        ''')


if __name__ == '__main__':
    unittest.main()
