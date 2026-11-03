"""Start the production window on a headless EGL target for acceptance probes."""
from pathlib import Path
import sys
import os
import time

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow

class OffscreenWindow(vtkEGLRenderWindow):
    def SetWindowInfo(self, handle):
        self.SetOffScreenRendering(True)

adapter.vtkRenderWindow = OffscreenWindow
from lele.app import LELEWindow
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy

samples, out = (Path(v).resolve() for v in sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
app = QApplication(['LELE independent axis comparison'])
if 'LELE_PROBE_STYLE' in os.environ:
    app.setStyle(os.environ['LELE_PROBE_STYLE'])
    font=app.font()
    font.setPointSize(int(os.environ['LELE_PROBE_PT']))
    app.setFont(font)
w = LELEWindow()
w.show()
deadline = time.monotonic() + 30
while w._backend_state != 'ready' and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(.005)
assert w._backend_state == 'ready'

def screenshot(window):
    window.Render()
    f = vtkWindowToImageFilter()
    f.SetInput(window)
    f.ReadFrontBufferOff()
    f.ShouldRerenderOff()
    f.Update()
    pixels = vtk_to_numpy(f.GetOutput().GetPointData().GetScalars())
    width, height = window.GetSize()
    return Image.fromarray(pixels.reshape(height,width,3)[::-1].copy())

