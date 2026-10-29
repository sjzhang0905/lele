"""High-contrast unfilled selection outline rendered inside the VTK window."""
from PySide6.QtCore import QObject, QRect


class SelectionOutline(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        from vtkmodules.vtkRenderingCore import vtkRenderer, vtkActor2D, vtkPolyDataMapper2D
        from vtkmodules.vtkCommonDataModel import vtkPolyData
        self.view = parent
        self.window = parent.GetRenderWindow()
        self.rect = QRect()
        self.visible = False
        self.renderer = vtkRenderer()
        self.renderer.SetLayer(self.window.GetNumberOfLayers())
        self.window.SetNumberOfLayers(self.renderer.GetLayer() + 1)
        self.renderer.SetInteractive(False)
        self.renderer.SetPreserveColorBuffer(True)
        self.renderer.SetDraw(False)
        self.window.AddRenderer(self.renderer)
        self.geometry = vtkPolyData()
        self.actors = []
        for color, width in (((.05, .05, .05), 5.), ((1., .82, .12), 2.5)):
            mapper = vtkPolyDataMapper2D()
            mapper.SetInputData(self.geometry)
            actor = vtkActor2D()
            actor.SetMapper(mapper)
            actor.GetProperty().SetColor(*color)
            actor.GetProperty().SetLineWidth(width)
            self.renderer.AddViewProp(actor)
            self.actors.append(actor)

    def setGeometry(self, rect):
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkCellArray
        self.rect = QRect(rect).normalized()
        width, height = self.window.GetSize()
        sx = width / max(1, self.view.width())
        sy = height / max(1, self.view.height())
        x1, x2 = self.rect.left() * sx, self.rect.right() * sx
        y1, y2 = (self.view.height()-self.rect.top())*sy, (self.view.height()-self.rect.bottom())*sy
        corners = ((x1,y1),(x2,y1),(x2,y2),(x1,y2))
        points = vtkPoints(); lines = vtkCellArray()
        dash, gap = 8 * sx, 4 * sx
        for index in range(4):
            a, b = corners[index], corners[(index+1)%4]
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = (dx*dx+dy*dy)**.5
            start = 0.
            while start < length:
                end = min(start+dash, length)
                i = points.InsertNextPoint(a[0]+dx*start/length,a[1]+dy*start/length,0)
                j = points.InsertNextPoint(a[0]+dx*end/length,a[1]+dy*end/length,0)
                lines.InsertNextCell(2);lines.InsertCellPoint(i);lines.InsertCellPoint(j)
                start += dash+gap
        self.geometry.SetPoints(points);self.geometry.SetLines(lines)
        self.geometry.Modified()
        if self.visible:self.window.Render()

    def show(self):
        self.window.SetNumberOfLayers(max(self.window.GetNumberOfLayers(),self.renderer.GetLayer()+1))
        self.visible=True;self.renderer.SetDraw(True);self.window.Render()

    def hide(self):
        self.visible=False;self.renderer.SetDraw(False);self.window.Render()

    def close(self):
        self.window.RemoveRenderer(self.renderer)
