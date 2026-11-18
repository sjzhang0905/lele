"""Independent, rotatable offscreen canvas for a VASP path illustration."""
from PySide6.QtCore import Qt
from .legend_canvas import LegendCanvas


class NebCanvas(LegendCanvas):
    """Qt handles interaction; a second native OpenGL child is not required."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('vaspNebCanvas')
        self.scene = None
        self._drag = None
        self.setToolTip('Left drag rotates; right drag rolls; wheel zooms.')

    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._drag = (event.position(), event.button())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is None or self.scene is None:
            return super().mouseMoveEvent(event)
        old, button = self._drag
        now = event.position()
        camera = self.scene.GetActiveCamera()
        if button == Qt.MouseButton.LeftButton:
            camera.Azimuth(-.45 * (now.x() - old.x()))
            camera.Elevation(.45 * (now.y() - old.y()))
        else:
            camera.Roll(-.65 * (now.x() - old.x()))
        camera.OrthogonalizeViewUp()
        self.scene.ResetCameraClippingRange()
        self._drag = (now, button)
        self.render()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._drag = None
        event.accept()

    def focusOutEvent(self, event):
        self._drag = None
        super().focusOutEvent(event)

    def wheelEvent(self, event):
        if self.scene is not None:
            camera = self.scene.GetActiveCamera()
            factor = 1.15 ** (event.angleDelta().y() / 120.)
            if camera.GetParallelProjection():
                camera.SetParallelScale(camera.GetParallelScale() / factor)
            else:
                camera.Dolly(factor)
            self.scene.ResetCameraClippingRange()
            self.render()
        event.accept()
