"""Read-only planar scalar-field inspection; never changes source grids."""
import numpy as np
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QDoubleSpinBox,
    QCheckBox,QLabel,QPushButton,QFileDialog,QMessageBox,QLineEdit)
from .field_slice import grid_plane_slice, export_slice_csv, display_slice_samples
from .operations import run_data_task
from .output_text import LoadCancelled


class FieldSliceDialog(QDialog):
    def __init__(self, volume, parent=None):
        super().__init__(parent)
        self.volume=volume;self.section=None
        self.setWindowTitle('Scalar field slice — '+(volume.label or 'Field'));self.resize(920,760)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.axis=QComboBox();self.axis.addItems(['Grid plane 2–3 (fixed index 1)',
            'Grid plane 1–3 (fixed index 2)','Grid plane 1–2 (fixed index 3)']);self.axis.setCurrentIndex(2)
        row.addWidget(self.axis)
        self.position=QDoubleSpinBox();self.position.setRange(0,100);self.position.setDecimals(2)
        self.position.setSuffix(' %');self.position.setKeyboardTracking(False);self.position.setValue(50);row.addWidget(QLabel('Position'));row.addWidget(self.position)
        self.contours=QCheckBox('Contour lines');row.addWidget(self.contours)
        self.symmetric=QCheckBox('Symmetric color range');self.symmetric.setChecked(True);row.addWidget(self.symmetric)
        ranges=QHBoxLayout();layout.addLayout(ranges)
        self.manual_range=QCheckBox('Fixed color range');ranges.addWidget(self.manual_range)
        self.range_min=QLineEdit('-0.1');self.range_max=QLineEdit('0.1')
        ranges.addWidget(QLabel('Min'));ranges.addWidget(self.range_min);ranges.addWidget(QLabel('Max'));ranges.addWidget(self.range_max)
        self.range_min.editingFinished.connect(self.redraw);self.range_max.editingFinished.connect(self.redraw)
        self.manual_range.toggled.connect(self.redraw)
        self.figure=Figure(figsize=(8,5),tight_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas,self));layout.addWidget(self.canvas,1)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.export=QPushButton('Export slice samples CSV…');self.export.clicked.connect(self.export_csv);layout.addWidget(self.export)
        for signal in (self.axis.currentIndexChanged,self.position.valueChanged,self.contours.toggled,self.symmetric.toggled):
            signal.connect(self.redraw)
        self.redraw()

    def redraw(self,*_):
        self.figure.clear();self.section=None
        try:section=grid_plane_slice(self.volume,self.axis.currentIndex(),self.position.value()/100)
        except ValueError as exc:
            self.note.setText(str(exc));self.export.setEnabled(False);self.canvas.draw_idle();return
        self.section=section;self.export.setEnabled(True)
        ax=self.figure.add_subplot(111);lo,hi=section.minimum,section.maximum
        if self.symmetric.isChecked():
            bound=max(abs(lo),abs(hi),1e-30);vmin,vmax=-bound,bound;cmap='RdBu_r'
        else:
            vmin,vmax=lo,hi;cmap='viridis'
            if vmin==vmax:delta=max(abs(vmin)*1e-6,1e-12);vmin-=delta;vmax+=delta
        if self.manual_range.isChecked():
            try:
                vmin,vmax=float(self.range_min.text()),float(self.range_max.text())
                if not np.isfinite([vmin,vmax]).all() or vmin>=vmax:raise ValueError
            except ValueError:
                self.note.setText('Enter finite color limits with Min < Max.');self.canvas.draw_idle();return
        display_x,display_y,display_values,reduced=display_slice_samples(section)
        mesh=ax.pcolormesh(display_x,display_y,display_values,shading='gouraud',cmap=cmap,vmin=vmin,vmax=vmax)
        if self.contours.isChecked() and lo<hi:
            lines=ax.contour(display_x,display_y,display_values,levels=np.linspace(lo,hi,9)[1:-1],colors='black',linewidths=.5)
            ax.clabel(lines,inline=True,fontsize=8,fmt='%.3g')
        ax.set_aspect('equal');ax.set_xlabel('In-plane u (Å)');ax.set_ylabel('In-plane v (Å)')
        ax.set_title(self.volume.label or 'Scalar field')
        self.figure.colorbar(mesh,ax=ax,label=self.volume.unit or 'source-file units')
        origin=', '.join(f'{x:.5g}' for x in section.origin)
        self.note.setText(f'Slice origin (Å): ({origin}); grid index {section.sample_index:.5g}. '
            f'Sample min {lo:.6g}; max {hi:.6g}; mean {section.mean:.6g}.\n'
            f'Cartesian u unit vector {np.array2string(section.u,precision=4)}; v {np.array2string(section.v,precision=4)}.\n'
            'Planes follow the grid vectors, including skew cells. Position is linear between adjacent grid planes. '
            'The color plot interpolates sample colors; it does not add computed data. '
            +('Display reduced to at most 201 samples per axis; fine features can be missed. Statistics and CSV retain all slice samples. ' if reduced else '')
            +('100% spans a full periodic cell; duplicated display edges are excluded from statistics.' if self.volume.periodic else
              '100% is the last sampled plane, not an inferred cell boundary.'))
        self.canvas.draw_idle()

    def export_csv(self):
        if self.section is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export slice samples','field_slice.csv','CSV (*.csv)')
        if not path:return
        try:
            section=self.section
            unit=self.volume.unit or 'source-file units'
            run_data_task(self,'Exporting slice samples',lambda:export_slice_csv(section,path,unit),cancellable=True)
        except LoadCancelled:return
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'Could not export slice',str(exc))
