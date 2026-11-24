"""Time one first-file open in a fresh LELE process.

Run this script from the source tree to measure. On a desktop, use the normal
Qt/VTK backend. For a headless Linux run, --egl uses a real EGL framebuffer
because a Qt offscreen widget does not provide a native drawable.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--when', choices=('welcome', 'ready'), default='welcome')
    parser.add_argument('--egl', action='store_true')
    args = parser.parse_args()
    path = args.file.resolve(strict=True)
    if args.egl:
        os.environ.update(QT_QPA_PLATFORM='offscreen', VTK_DEFAULT_OPENGL_WINDOW='vtkEGLRenderWindow',
                          EGL_PLATFORM='surfaceless')
    sys.path.insert(0, str(Path.cwd()))
    start = perf_counter()
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from lele.app import LELEWindow

    times = {}
    app = QApplication(['LELE first open benchmark'])
    app.setStyle('Fusion')

    class Window(LELEWindow):
        def _start_backend_loading(self):
            times['welcome_s'] = perf_counter() - start
            if args.when == 'welcome':
                self.request_file()
            super()._start_backend_loading()

        def request_file(self):
            times['request_s'] = perf_counter() - start
            self.open_paths([str(path)])

        def _ensure_3d_view(self):
            creating = self.vtk is None
            if creating and args.egl:
                import vtkmodules.qt.QVTKRenderWindowInteractor as adapter
                from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow

                class Pbuffer(vtkEGLRenderWindow):
                    def __init__(self):
                        super().__init__()
                        self.SetOffScreenRendering(1)

                    def SetWindowInfo(self, _widget_id):
                        pass  # EGL owns the render target in this benchmark.

                adapter.vtkRenderWindow = Pbuffer
            super()._ensure_3d_view()
            if creating:
                self.vtk.GetRenderWindow().AddObserver('EndEvent', self.rendered)

        def rendered(self, *_):
            if ('updated_s' not in times and self.doc is not None
                    and self.canvas_stack.currentWidget() is self.structure_page
                    and getattr(self.renderer, 'source_frame', None) is not None):
                times['render_s'] = perf_counter() - start

        def _show_file_load_error(self, filename, error):
            print(f'{filename}\n{error}', file=sys.stderr)
            app.exit(1)

        def _attach_loaded_document(self, document):
            super()._attach_loaded_document(document)
            times['updated_s'] = perf_counter() - start
            QTimer.singleShot(0, self, self.finish)

        def finish(self):
            if self.doc.path != path or 'render_s' not in times:
                self._show_file_load_error(path, 'The file did not produce a rendered structure.')
                return
            import hashlib
            import numpy as np
            from vtkmodules.util.numpy_support import vtk_to_numpy
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
            readback = vtkWindowToImageFilter()
            readback.SetInput(self.vtk.GetRenderWindow())
            readback.ReadFrontBufferOff()
            readback.ShouldRerenderOff()
            readback.Update()
            pixels = vtk_to_numpy(readback.GetOutput().GetPointData().GetScalars())
            times['open_to_render_s'] = times['render_s'] - times['request_s']
            times['open_to_updated_s'] = times['updated_s'] - times['request_s']
            print(json.dumps({**times, 'atoms': len(self.frame.symbols),
                              'rgb_sha256': hashlib.sha256(pixels.tobytes()).hexdigest(),
                              'pixel_range': int(np.ptp(pixels))}), flush=True)
            self.close()

    def check():
        if window._backend_state == 'failed':
            window._show_file_load_error(path, window._backend_loader.error)
        elif window._backend_state == 'ready' and 'ready_s' not in times:
            times['ready_s'] = perf_counter() - start
            if args.when == 'ready':
                QTimer.singleShot(0, window, window.request_file)

    window = Window()
    timer = QTimer(window)
    timer.setInterval(3)
    timer.timeout.connect(check)
    timer.start()
    QTimer.singleShot(120_000, window, lambda: app.exit(2))
    window.showMaximized()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
