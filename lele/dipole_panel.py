"""Qt-only source selection, printed moment statistics and export buttons."""
from PySide6.QtCore import Signal,QSignalBlocker,QLocale
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QFormLayout,QComboBox,QDoubleSpinBox,
    QLabel,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView)


class DipolePanel(QWidget):
    sourceChanged=Signal(str)
    modeChanged=Signal(str)
    scaleChanged=Signal(float)
    saveImageRequested=Signal()
    exportDataRequested=Signal()
    exportTransitionsRequested=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self._document=None
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.source=QComboBox();self.source.currentIndexChanged.connect(lambda:self.sourceChanged.emit(self.source.currentData() or 'permanent'))
        form.addRow('Data',self.source)
        self.mode=QComboBox();self.mode.addItems(['Off','Total','Components','Total + components'])
        self.mode.currentTextChanged.connect(self.modeChanged);form.addRow('Arrows',self.mode)
        self.scale=QDoubleSpinBox();self.scale.setRange(.001,10);self.scale.setDecimals(6);self.scale.setValue(.3)
        self.scale.setLocale(QLocale.c());self.scale.setKeyboardTracking(False);self.scale.setReadOnly(False)
        self.scale.setSingleStep(.05);self.scale.lineEdit().setClearButtonEnabled(True)
        self.scale.setToolTip('Type a value, then press Enter or leave the field to apply. Arrow buttons also work.')
        self.scale.valueChanged.connect(self.scaleChanged);form.addRow('Scale (Å/D)',self.scale)
        self.values=QLabel('No printed dipole data');self.values.setWordWrap(True);layout.addWidget(self.values)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Record','Kind / state','Density','X (D)','Y (D)','Z (D)','|μ| (D)'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        self.save_image=QPushButton('Save view + dipole arrows PNG…');self.save_image.clicked.connect(self.saveImageRequested)
        self.export_data=QPushButton('Export dipole data CSV…');self.export_data.clicked.connect(self.exportDataRequested)
        self.export_transitions=QPushButton('Export transition table CSV…');self.export_transitions.clicked.connect(self.exportTransitionsRequested)
        for button in (self.save_image,self.export_data,self.export_transitions):layout.addWidget(button);button.setEnabled(False)
        self.note=QLabel('Transition arrows describe electric polarization. Overall sign depends on electronic-state phase.')
        self.note.setWordWrap(True);layout.addWidget(self.note)

    def prepare_document(self,document,requested='permanent'):
        if document is not self._document:
            self._document=document
            with QSignalBlocker(self.source):
                self.source.clear();self.source.addItem('Permanent · matching geometry','permanent')
                for i,r in enumerate(document.dipoles):
                    self.source.addItem(f'{r.kind.title()} · state {r.state_number or "—"} · record {i+1}',f'permanent:{i}')
                for i,s in enumerate(document.electronic_spectra):
                    for t in s.transitions:
                        if t.electric_dipole_au is not None:self.source.addItem(f'Transition 0 → {t.number} {t.state} · {t.wavelength_nm:g} nm · TD {i+1}',f'transition:{i}:{t.number}')
            self.table.setRowCount(len(document.dipoles))
            for i,r in enumerate(document.dipoles):
                for j,value in enumerate([i+1,r.kind+(' '+str(r.state_number) if r.state_number else ''),r.density,*[f'{v:.4f}' for v in r.vector],f'{r.printed_total:.4f}']):
                    self.table.setItem(i,j,QTableWidgetItem(str(value)))
            self.export_data.setEnabled(bool(document.dipoles or document.electronic_spectra))
            self.export_transitions.setEnabled(bool(document.electronic_spectra))
        index=self.source.findData(requested)
        with QSignalBlocker(self.source):self.source.setCurrentIndex(max(0,index))
        return self.source.currentData() or 'permanent'

    def set_vector(self,vector,mode,scale):
        with QSignalBlocker(self.mode):self.mode.setCurrentText(mode)
        # Redrawing must not replace an unfinished number with the old value.
        if self.scale.value()!=scale:
            with QSignalBlocker(self.scale):self.scale.setValue(scale)
        self.save_image.setEnabled(vector is not None)
        text='No matching moment for this geometry'
        if vector is not None:
            import numpy as np
            text='\n'.join(f'{a} = {v:.4f} D' for a,v in zip('XYZ',vector))+f'\n|μ| = {np.linalg.norm(vector):.4f} D'
        if self._document is not None and self._document.dipoles:
            import numpy as np
            norms=[np.linalg.norm(r.vector) for r in self._document.dipoles]
            text+=f'\n{len(norms)} printed records · mean |μ| {np.mean(norms):.4f} D · SD {np.std(norms):.4f} D'
        self.values.setText(text)
