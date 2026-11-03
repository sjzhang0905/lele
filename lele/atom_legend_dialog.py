"""Modeless legend window with its own VTK canvas and PNG export."""
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QFileDialog,QMessageBox
from .operations import gui_operation,ui_operation,ui_checkpoint


def create_legend_canvas(parent):
    from .legend_canvas import LegendCanvas
    return LegendCanvas(parent)


class AtomLegendDialog(QDialog):
    def __init__(self,window):
        super().__init__(window);self.source_window=window;self._initialized=False;self._finalized=False
        self.setWindowTitle('Atom legend');self.resize(760,350)
        layout=QVBoxLayout(self);self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.canvas=create_legend_canvas(self);self.canvas.setMinimumSize(350,180);layout.addWidget(self.canvas,1)
        from vtkmodules.vtkRenderingCore import vtkRenderer
        from .atom_legend import AtomLegend
        self.scene=vtkRenderer();self.canvas.GetRenderWindow().AddRenderer(self.scene)
        self.canvas.GetRenderWindow().GetInteractor().SetInteractorStyle(None)
        self.legend=AtomLegend(self.scene)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.refresh_button=QPushButton('Use current structure');self.refresh_button.clicked.connect(self.refresh)
        self.save_button=QPushButton('Save legend PNG…');self.save_button.clicked.connect(self.save_png)
        buttons.addWidget(self.refresh_button);buttons.addStretch(1);buttons.addWidget(self.save_button)
        self.refresh()

    @gui_operation('Preparing atom legend')
    def refresh(self,*_):
        from .atom_legend import legend_samples
        window=self.source_window
        samples=legend_samples(window.renderer) if window.renderer is not None and window.frame is not None else []
        self.options=deepcopy(window.render_options)
        self.source_path=window.doc.path if window.doc is not None else Path('lele')
        self.legend.set_samples(samples,self.options)
        self.summary.setText(f'{self.source_path.name} · {len(samples)} elements' if samples else 'No visible atoms in the current structure.')
        self.save_button.setEnabled(bool(samples))
        if self._initialized:self.canvas.render()

    def showEvent(self,event):
        super().showEvent(event)
        if not self._initialized:QTimer.singleShot(0,self,self._initialize)

    def _initialize(self):
        if self._initialized or self._finalized:return
        self._initialized=True;self.canvas.Initialize();self.canvas.render()

    def save_png(self):
        default=self.source_path.with_name(self.source_path.stem+'_atom_legend.png')
        path,_=QFileDialog.getSaveFileName(self,'Save atom legend',str(default),'PNG image (*.png)')
        if not path:return
        try:self.write_png(path)
        except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))

    def write_png(self,path):
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
        from vtkmodules.vtkIOImage import vtkPNGWriter
        self._initialize()
        with ui_operation(self,'Exporting atom legend'):
            image=vtkWindowToImageFilter();image.SetInput(self.canvas.GetRenderWindow())
            image.SetScale(2);image.ReadFrontBufferOff()
            image.AddObserver('ProgressEvent',lambda obj,_:ui_checkpoint('Capturing legend',obj.GetProgress(),1));image.Update()
            writer=vtkPNGWriter();writer.SetFileName(str(path));writer.SetInputConnection(image.GetOutputPort())
            writer.AddObserver('ProgressEvent',lambda obj,_:ui_checkpoint('Writing legend PNG',obj.GetProgress(),1));writer.Write()

    def closeEvent(self,event):
        if not self._finalized:
            self._finalized=True
            if hasattr(self.canvas,'shutdown'):self.canvas.shutdown()
            else:self.canvas.GetRenderWindow().Finalize()
        super().closeEvent(event)
