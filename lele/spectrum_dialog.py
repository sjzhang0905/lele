"""IR, Raman and UV-Vis plots with raw-line and broadened-curve exports."""
from pathlib import Path
import csv
from .operations import run_data_task,gui_operation,ui_checkpoint,ui_operation
from .output_text import progress_items
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QGridLayout,QComboBox,QDoubleSpinBox,
    QLabel,QPushButton,QTableWidget,QTableWidgetItem,QFileDialog,QMessageBox,QAbstractItemView)


class SpectrumDialog(QDialog):
    def __init__(self,document,kind='IR',parent=None):
        super().__init__(parent);self.document=document;self.setWindowTitle('Simulated spectra — '+document.path.name);self.resize(1000,800)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
        layout=QVBoxLayout(self);grid=QGridLayout();layout.addLayout(grid)
        self.kind=QComboBox();self.kind.addItems(['IR','Raman','UV-Vis']);self.kind.setCurrentText(kind)
        self.calculation=QComboBox();self.shape=QComboBox();self.shape.addItems(['Gaussian','Lorentzian'])
        self.fwhm=QDoubleSpinBox();self.fwhm.setRange(.001,4000);self.fwhm.setDecimals(3)
        self.scale=QDoubleSpinBox();self.scale.setRange(.1,2);self.scale.setValue(1);self.scale.setDecimals(4)
        self.laser=QDoubleSpinBox();self.laser.setRange(100,2000);self.laser.setValue(532);self.laser.setSuffix(' nm')
        self.temperature=QDoubleSpinBox();self.temperature.setRange(1,2000);self.temperature.setValue(298.15);self.temperature.setSuffix(' K')
        self.fwhm.setPrefix('FWHM ');self.scale.setPrefix('Frequency scale ')
        self.laser.setPrefix('Laser ');self.temperature.setPrefix('T ')
        self.scale.setToolTip('Multiply printed frequencies by this factor; printed intensities are retained.')
        self.laser.setToolTip('Incident laser wavelength for relative Stokes Raman weights.')
        self.axis=QComboBox();self.axis.addItems(['Wavelength (nm)','Energy (eV)'])
        for j,w in enumerate((self.kind,self.calculation,self.shape,self.fwhm)):grid.addWidget(w,0,j)
        for j,w in enumerate((self.scale,self.laser,self.temperature,self.axis)):grid.addWidget(w,1,j)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.figure=Figure(figsize=(8,4),tight_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename=lambda:str(document.path.with_name(document.path.stem+'_spectrum.png'))
        layout.addWidget(NavigationToolbar2QT(self.canvas,self));layout.addWidget(self.canvas,2)
        self.table=QTableWidget();self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        self.save_curve=QPushButton('Save spectrum CSV…');self.save_curve.clicked.connect(self.export_curve);layout.addWidget(self.save_curve)
        self.save_transitions=QPushButton('Export transition table CSV…');self.save_transitions.clicked.connect(self.export_transitions);layout.addWidget(self.save_transitions)
        self.kind.currentTextChanged.connect(self._set_kind)
        for widget in (self.calculation,self.shape,self.axis):widget.currentIndexChanged.connect(self.redraw)
        for widget in (self.fwhm,self.scale,self.laser,self.temperature):widget.valueChanged.connect(self.redraw)
        self._set_kind()

    def _set_kind(self,*_):
        from PySide6.QtCore import QSignalBlocker
        uv=self.kind.currentText()=='UV-Vis'
        with QSignalBlocker(self.calculation):
            self.calculation.clear();count=len(self.document.electronic_spectra if uv else self.document.vibrations)
            self.calculation.addItems([f'Calculation {i+1}'+(' · '+self.document.electronic_spectra[i].label
                if uv and self.document.electronic_spectra[i].label else '') for i in range(count)])
        with QSignalBlocker(self.fwhm):self.fwhm.setValue(.3 if uv else 15.);self.fwhm.setSuffix(' eV' if uv else ' cm⁻¹')
        self.scale.setEnabled(not uv);self.laser.setEnabled(self.kind.currentText()=='Raman');self.temperature.setEnabled(self.laser.isEnabled())
        self.axis.setEnabled(uv);self.save_transitions.setVisible(uv);self.redraw()

    @gui_operation('Preparing spectrum')
    def redraw(self,*_):
        if not hasattr(self,'canvas'):return
        import numpy as np
        from .spectra import simulated_spectrum,vibrational_lines
        from .gaussian_properties import AU_TO_DEBYE,transition_state_label,contribution_text
        kind=self.kind.currentText();calc=self.calculation.currentIndex();self.figure.clear();ax=self.figure.add_subplot(111)
        self._curve=None
        try:
            if calc<0:raise ValueError('This file has no corresponding calculations')
            options=dict(fwhm=self.fwhm.value(),shape=self.shape.currentText(),scale=self.scale.value(),
                laser_nm=self.laser.value(),temperature=self.temperature.value(),wavelength=self.axis.currentIndex()==0)
            x,y,label=run_data_task(self,'Calculating spectrum',lambda:simulated_spectrum(self.document,kind,calc,**options))
            self._curve=(x,y,label);ax.plot(x,y,lw=1.3);ax.set_xlabel(label);ax.set_ylabel('Relative intensity')
            if kind=='UV-Vis':
                columns=['State','Energy (eV)','Wavelength (nm)','Oscillator strength f','μx (au)','μy (au)','μz (au)','Dip. strength (au²)','|μ| (D)','Major transitions (printed coefficients)'];rows=[]
                for t in self.document.electronic_spectra[calc].transitions:
                    mu=t.electric_dipole_au
                    rows.append([f'{t.number} {transition_state_label(t.state)}',t.energy_ev,t.wavelength_nm,t.oscillator_strength,*(['']*3 if mu is None else mu),
                                 t.dipole_strength_au2,'' if mu is None else np.linalg.norm(mu)*AU_TO_DEBYE,contribution_text(t)])
                self.note.setText('Energy-domain broadening; absorption evaluated at E = hc/λ. Transition moments use length-gauge electric au.')
                if any(t.metadata for t in self.document.electronic_spectra[calc].transitions):
                    columns=['State','Energy (eV)','Wavelength (nm)','Oscillator strength f','Printed x (au)','Printed y (au)','Printed z (au)','Dipole form','Source detail']
                    rows=[]
                    for t in self.document.electronic_spectra[calc].transitions:
                        mu=t.electric_dipole_au if t.electric_dipole_au is not None else t.velocity_dipole_au
                        if mu is None:mu=t.metadata.get('component_magnitudes_au',t.metadata.get('printed_components_au'))
                        rows.append([f'{t.number} {t.state}',t.energy_ev,t.wavelength_nm,t.oscillator_strength,
                                     *(['']*3 if mu is None else mu),t.metadata.get('dipole_form',''),t.source_label])
                    self.note.setText('Printed CP2K transition energies and oscillator strengths. Energy-domain broadening is a simulated spectrum. '
                        'Component magnitudes have no vector direction or phase and do not generate dipole arrows. K-point auxiliary fields stay as printed; they are not excitation amplitudes.')
            else:
                units={m.ir_intensity_unit for m in self.document.vibrations[calc].modes if m.ir_intensity is not None}
                ir_unit=next(iter(units)) if len(units)==1 else 'source units'
                columns=['Mode','Frequency (cm⁻¹)','Scaled (cm⁻¹)',f'IR ({ir_unit})','Raman activity (Å⁴/amu)','Relative Stokes weight']
                weights={id(row[2]):row[1] for row in vibrational_lines(self.document.vibrations[calc],'Raman',self.scale.value(),self.laser.value(),self.temperature.value())}
                rows=[[m.number,m.frequency_cm1,m.frequency_cm1*self.scale.value(),m.ir_intensity,m.raman_activity,weights.get(id(m))]
                      for m in self.document.vibrations[calc].modes]
                self.note.setText('Positive modes only in simulated curves. IR uses printed intensities; Raman uses laser/temperature-corrected relative Stokes weights. No experimental fit.')
            self.table.setColumnCount(len(columns));self.table.setHorizontalHeaderLabels(columns);self.table.setRowCount(len(rows))
            for i,row in enumerate(progress_items(rows,'Building spectrum table')):
                for j,value in enumerate(row):self.table.setItem(i,j,QTableWidgetItem('' if value is None else f'{value:.6f}' if isinstance(value,(float,np.floating)) else str(value)))
            self.table.resizeColumnsToContents()
        except (ValueError,IndexError) as ex:
            self.note.setText(str(ex));self.table.setRowCount(0)
        ax.set_title(kind+' · '+self.document.path.name);ax.grid(True,alpha=.15);self.canvas.draw()
        self.save_curve.setEnabled(self._curve is not None)

    def export_curve(self):
        if self._curve is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save simulated spectrum',str(self.document.path.with_name(self.document.path.stem+'_spectrum.csv')),'CSV (*.csv)')
        if path:
            try:
                x,y,label=self._curve
                with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
                    with ui_operation(self,'Exporting spectrum'):
                        writer=csv.writer(f);writer.writerow([label,'relative_intensity']);writer.writerows(progress_items(zip(x,y),'Writing spectrum CSV',len(x)))
            except OSError as ex:QMessageBox.warning(self,'Export failed',str(ex))

    def export_transitions(self):
        from .property_export import export_transitions
        calc=self.calculation.currentIndex()
        path,_=QFileDialog.getSaveFileName(self,'Export transition table',str(self.document.path.with_name(f'{self.document.path.stem}_td_{calc+1}_transitions.csv')),'CSV (*.csv)')
        if path:
            try:run_data_task(self,'Exporting transitions',lambda:export_transitions(path,self.document,calc))
            except (ValueError,OSError) as ex:QMessageBox.warning(self,'Export failed',str(ex))
