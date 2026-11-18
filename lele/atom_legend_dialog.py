"""Modeless legend window with its own VTK canvas and PNG export."""
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from .dialog_policy import QDialog, QFileDialog, QMessageBox
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
        from .png_dialog import PngExportDialog
        dialog = PngExportDialog(self, view_size=self.canvas.GetRenderWindow().GetSize())
        if dialog.exec() != QDialog.DialogCode.Accepted:return
        path = Path(path)
        if path.suffix.lower() != '.png':path = path.with_name(path.name + '.png')
        try:self.write_png(path, dialog.settings())
        except Exception as exc:QMessageBox.warning(self,'Export failed',str(exc))

    def write_png(self, path, settings=None):
        from .png_export import export_png, PngSettings
        self._initialize()
        window = self.canvas.GetRenderWindow()
        if settings is None:
            width, height = window.GetSize()
            settings = PngSettings(min(8192, 2 * width), min(8192, 2 * height))
        with ui_operation(self, 'Exporting atom legend'):
            return export_png(path, window, settings, mesh_items=self.legend.spheres,
                              progress=ui_checkpoint)

    def closeEvent(self,event):
        if not self._finalized:
            self._finalized=True
            if hasattr(self.canvas,'shutdown'):self.canvas.shutdown()
            else:self.canvas.GetRenderWindow().Finalize()
        super().closeEvent(event)
