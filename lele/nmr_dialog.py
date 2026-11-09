"""NMR tables and explicitly referenced, uncoupled stick/broadened spectra."""
from pathlib import Path
import csv
import numpy as np
from PySide6.QtCore import Qt,Signal,QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QComboBox,
    QDoubleSpinBox,QLineEdit,QLabel,QPushButton,QTableWidget,QTableWidgetItem,
    QFileDialog,QMessageBox,QAbstractItemView,QSplitter)
from .nmr import spectrum,chemical_shift,export_nmr_csv
from .operations import run_data_task


class NMRDialog(QDialog):
    atomRequested=Signal(int,int)       # result index, 1-based atom number

    def __init__(self,document,parent=None):
        super().__init__(parent);self.document=document;self.setWindowTitle('NMR — '+document.path.name)
        self.resize(1120,850);self._curve=None;self._display_nuclei=[]
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
        layout=QVBoxLayout(self);grid=QGridLayout();layout.addLayout(grid)
        self.calculation=QComboBox()
        for i,r in enumerate(document.nmr_results):
            self.calculation.addItem(f'{i+1} · {r.program} · {r.label} · line {r.source_line}',i)
        self.element=QComboBox();self.axis=QComboBox()
        self.axis.addItems(['Shielding σ (ppm)','Chemical shift δ (ppm)'])
        self.reference=QLineEdit();self.reference.setPlaceholderText('No reference assumed')
        self.reference.setToolTip('Reference shielding for the selected element, calculated with the same method and basis. δ = σref − σ. Saved with this result in the project.')
        self.shape=QComboBox();self.shape.addItems(['Lorentzian','Gaussian','Sticks'])
        self.width=QDoubleSpinBox();self.width.setRange(.001,1000);self.width.setDecimals(3);self.width.setValue(.3)
        self.width.setPrefix('FWHM ');self.width.setSuffix(' ppm');self.width.setKeyboardTracking(False)
        grid.addWidget(QLabel('Calculation / dataset'),0,0);grid.addWidget(self.calculation,0,1,1,5)
        for col,widget in enumerate((QLabel('Element'),self.element,self.axis,QLabel('σref (ppm)'),self.reference)):
            grid.addWidget(widget,1,col)
        grid.addWidget(self.shape,2,1);grid.addWidget(self.width,2,2)
        self.notice=QLabel();self.notice.setWordWrap(True);layout.addWidget(self.notice)
        split=QSplitter(Qt.Orientation.Vertical);layout.addWidget(split,1)
        from PySide6.QtWidgets import QWidget
        plot=QWidget();plot_layout=QVBoxLayout(plot);plot_layout.setContentsMargins(0,0,0,0)
        self.figure=Figure(figsize=(9,3.5),tight_layout=True);self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename=lambda:str(document.path.with_name(document.path.stem+'_nmr.png'))
        plot_layout.addWidget(NavigationToolbar2QT(self.canvas,self));plot_layout.addWidget(self.canvas)
        split.addWidget(plot)
        self.table=QTableWidget();self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        split.addWidget(self.table);split.setSizes([410,230])
        self.tensor=QLabel('Select a table row to inspect its printed tensor. Double-click to locate its atom when a matching source frame exists.')
        self.tensor.setWordWrap(True);self.tensor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.tensor)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.export_table=QPushButton('Export all nuclei CSV…');self.export_table.clicked.connect(self.save_table)
        self.export_curve=QPushButton('Export displayed spectrum CSV…');self.export_curve.clicked.connect(self.save_curve)
        self.export_image=QPushButton('Save plot PNG / SVG…');self.export_image.clicked.connect(self.save_image)
        for widget in (self.export_table,self.export_curve,self.export_image):
            widget.setAutoDefault(False);buttons.addWidget(widget)
        self.calculation.currentIndexChanged.connect(self.change_result)
        self.element.currentIndexChanged.connect(self.change_element)
        self.reference.editingFinished.connect(self.set_reference)
        self.axis.currentIndexChanged.connect(self.refresh)
        self.shape.currentTextChanged.connect(self.refresh);self.width.valueChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.show_tensor)
        self.table.itemDoubleClicked.connect(self.request_atom)
        preferred=[i for i,r in enumerate(document.nmr_results) if 'valence + core · excluding' in r.label]
        index=preferred[-1] if preferred else len(document.nmr_results)-1
        with QSignalBlocker(self.calculation):self.calculation.setCurrentIndex(index)
        self.change_result()

    @property
    def result(self):
        return self.document.nmr_results[self.calculation.currentIndex()]

    def change_result(self,*_):
        if self.calculation.currentIndex()<0:return
        old=self.element.currentText()
        with QSignalBlocker(self.element):
            self.element.clear();self.element.addItems(self.result.elements())
            index=self.element.findText(old)
            if index<0:index=self.element.findText('H')
            self.element.setCurrentIndex(max(0,index))
        self.change_element()

    def change_element(self,*_):
        value=self.result.reference_shieldings.get(self.element.currentText())
        self.reference.setText('' if value is None else f'{value:.12g}')
        self.refresh()

    def set_reference(self):
        text=self.reference.text().strip();element=self.element.currentText()
        if not text:self.result.reference_shieldings.pop(element,None)
        else:
            try:
                value=float(text)
                if not np.isfinite(value):raise ValueError()
            except ValueError:
                QMessageBox.warning(self,'Invalid reference','Enter a finite reference shielding in ppm, or leave it empty.')
                self.change_element();return
            self.result.reference_shieldings[element]=value
        self.refresh()

    def refresh(self,*_):
        if self.calculation.currentIndex()<0:return
        r=self.result;element=self.element.currentText();shift=self.axis.currentIndex()==1
        self._display_nuclei=[n for n in r.nuclei if n.symbol==element]
        self.width.setEnabled(self.shape.currentText()!='Sticks')
        note='One equal-area line per printed nucleus. Broadening is a display model; J splitting, isotope abundance, equivalent-site averaging and conformer populations are not simulated.'
        if r.note:note+='\n'+r.note
        blocker=QSignalBlocker(self.table)
        self.table.setSortingEnabled(False);self.table.setRowCount(len(self._display_nuclei))
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(['Atom','Element','σ iso / ppm','δ / ppm','Anisotropy / ppm','Span / ppm','Source atom','Source line'])
        ref=r.reference_shieldings.get(element)
        for row,n in enumerate(self._display_nuclei):
            values=(n.number,n.symbol,n.shielding_ppm,None if ref is None else chemical_shift(n.shielding_ppm,ref),
                    n.anisotropy_ppm,n.span_ppm,n.source_number,n.source_line)
            for col,value in enumerate(values):
                item=QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole,'' if value is None else round(value,6) if isinstance(value,float) else value)
                item.setData(Qt.ItemDataRole.UserRole,row)
                self.table.setItem(row,col,item)
        self.table.resizeColumnsToContents();self.table.setSortingEnabled(True)
        del blocker
        self.figure.clear();ax=self.figure.add_subplot(111)
        self._curve=None
        try:
            width=self.width.value();shape=self.shape.currentText()
            calculate=lambda:spectrum(r,element,shift=shift,fwhm=width,shape=shape)
            x,y,peaks=(run_data_task(self,'Building NMR spectrum',calculate)
                       if len(self._display_nuclei)>200 else calculate())
            if len(peaks):
                if self.shape.currentText()=='Sticks':ax.vlines(peaks,0,1,color='#315ab5',lw=1.5);ax.set_ylim(0,1.18)
                else:
                    ax.plot(x,y,color='#315ab5',lw=1.5);ax.fill_between(x,y,alpha=.12,color='#315ab5')
                    ax.vlines(peaks,0,max(y)*.12,color='#b54637',lw=1)
                ax.set_xlim((x[-1],x[0]) if shift else (x[0],x[-1]))
                self._curve=(x,y,peaks)
                if len(peaks)<=35:
                    top=1.02 if self.shape.currentText()=='Sticks' else max(y)*1.02
                    for n,p in zip(self._display_nuclei,peaks):ax.annotate(str(n.number),(p,top),fontsize=8,ha='center',rotation=90)
        except ValueError as exc:
            note+='\n'+str(exc);ax.text(.5,.5,str(exc),ha='center',va='center',wrap=True,transform=ax.transAxes)
        ax.set_xlabel('Chemical shift δ (ppm)' if shift else 'Absolute shielding σ (ppm)')
        ax.set_ylabel('Line weight' if self.shape.currentText()=='Sticks' else 'Relative intensity (area per nucleus)')
        ax.set_title(f'{element} · {r.program} · '+('Referenced NMR' if shift else 'Shielding distribution'))
        ax.spines[['top','right']].set_visible(False);self.canvas.draw_idle()
        self.notice.setText(note);self.export_curve.setEnabled(self._curve is not None)
        self.export_image.setEnabled(self._curve is not None)
        self.tensor.setText('Select a table row to inspect its printed shielding tensor. Double-click locates a matched source atom.')

    def selected_nucleus(self):
        item=self.table.currentItem()
        index=None if item is None else item.data(Qt.ItemDataRole.UserRole)
        return self._display_nuclei[index] if isinstance(index,int) and 0<=index<len(self._display_nuclei) else None

    def show_tensor(self):
        n=self.selected_nucleus()
        if n is None:return
        if n.tensor is None:self.tensor.setText(f'Atom {n.number} {n.symbol}: complete shielding tensor not printed / not available.');return
        values=np.asarray(n.tensor)
        rows=['  '.join(f'{v: .6f}' for v in row) for row in values]
        self.tensor.setText(f'Atom {n.number} {n.symbol} — shielding tensor / ppm, Cartesian rows X/Y/Z:<br>'+
                            '<pre style="margin:0">'+'\n'.join(rows)+'</pre>'+f'trace / 3 = {np.trace(values)/3:.6f} ppm')

    def request_atom(self,_):
        n=self.selected_nucleus()
        if n is not None:self.atomRequested.emit(self.calculation.currentIndex(),n.number)

    def save_table(self):
        path,_=QFileDialog.getSaveFileName(self,'Export NMR nuclei',str(self.document.path.with_name(self.document.path.stem+'_nmr.csv')),'CSV (*.csv)')
        if path:
            result=self.result
            try:run_data_task(self,'Exporting NMR table',lambda:export_nmr_csv(path,result))
            except (OSError,ValueError) as exc:QMessageBox.warning(self,'Export failed',str(exc))

    def save_curve(self):
        if self._curve is None:return
        path,_=QFileDialog.getSaveFileName(self,'Export displayed NMR spectrum',str(self.document.path.with_name(self.document.path.stem+'_nmr_curve.csv')),'CSV (*.csv)')
        if not path:return
        x,y,peaks=self._curve
        try:
            with Path(path).open('w',encoding='utf-8-sig',newline='') as out:
                writer=csv.writer(out);writer.writerow(['chemical_shift_ppm' if self.axis.currentIndex()==1 else 'shielding_ppm','line_weight' if self.shape.currentText()=='Sticks' else 'relative_intensity'])
                writer.writerows(zip(peaks,np.ones(len(peaks))) if self.shape.currentText()=='Sticks' else zip(x,y))
        except OSError as exc:QMessageBox.warning(self,'Export failed',str(exc))

    def save_image(self):
        if self._curve is None:return
        path,_=QFileDialog.getSaveFileName(self,'Save NMR plot',str(self.document.path.with_name(self.document.path.stem+'_nmr.png')),'PNG (*.png);;SVG (*.svg)')
        if path:
            try:self.figure.savefig(path,dpi=300)
            except (OSError,ValueError) as exc:QMessageBox.warning(self,'Export failed',str(exc))
