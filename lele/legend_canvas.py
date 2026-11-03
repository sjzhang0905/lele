"""Read-only Qt canvas for a standalone VTK-rendered legend.

The image is rendered offscreen and painted by Qt. This avoids coupling a
second native OpenGL child window to the main viewport or its camera.
"""
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QImage,QPainter
from PySide6.QtWidgets import QWidget
from vtkmodules.vtkRenderingCore import vtkRenderWindow,vtkRenderWindowInteractor,vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy


class LegendCanvas(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self._initialized=False;self._closed=False;self._image=None
        self.setObjectName('atomLegendCanvas')
        self.rw=vtkRenderWindow();self.rw.SetOffScreenRendering(True);self.rw.SetMultiSamples(0)
        self.interactor=vtkRenderWindowInteractor();self.interactor.SetRenderWindow(self.rw)
        self._resize_timer=QTimer(self);self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.render)

    def GetRenderWindow(self):return self.rw

    def Initialize(self):self._initialized=True

    def render(self):
        if not self._initialized or self._closed:return
        ratio=self.devicePixelRatioF();width=max(1,round(self.width()*ratio));height=max(1,round(self.height()*ratio))
        self.rw.SetSize(width,height);self.rw.Render()
        capture=vtkWindowToImageFilter();capture.SetInput(self.rw);capture.SetInputBufferTypeToRGB()
        capture.ReadFrontBufferOff();capture.ShouldRerenderOff();capture.Update()
        data=vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars()).reshape(height,width,3)
        pixels=data[::-1].copy()
        self._image=QImage(pixels.data,width,height,width*3,QImage.Format.Format_RGB888).copy()
        self._image.setDevicePixelRatio(ratio);self.update()

    def paintEvent(self,event):
        painter=QPainter(self)
        if self._image is not None:painter.drawImage(self.rect(),self._image)
        else:painter.fillRect(self.rect(),Qt.GlobalColor.white)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self._initialized and not self._closed:self._resize_timer.start(30)

    def shutdown(self):
        if self._closed:return
        self._closed=True;self._resize_timer.stop();self.rw.Finalize()
