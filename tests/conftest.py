"""Allow Qt integration tests to render real pixels on a headless EGL runner."""
import os


def pytest_configure(config):
    if (os.environ.get('QT_QPA_PLATFORM') != 'offscreen'
            or os.environ.get('VTK_DEFAULT_OPENGL_WINDOW') != 'vtkEGLRenderWindow'):
        return

    import vtkmodules.qt
    vtkmodules.qt.PyQtImpl = 'PySide6'
    from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
    from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow

    class OffscreenRenderWindow(vtkEGLRenderWindow):
        def __init__(self):
            super().__init__()
            self.SetOffScreenRendering(1)

        def SetWindowInfo(self, window_id):
            # The offscreen Qt widget has no native window. EGL owns its pbuffer.
            pass

    adapter.vtkRenderWindow = OffscreenRenderWindow
