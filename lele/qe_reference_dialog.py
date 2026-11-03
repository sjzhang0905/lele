"""Explicit atom-order and reciprocal-scale association for structure-free modes."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,
    QSpinBox,QDoubleSpinBox,QPushButton,QDialogButtonBox,QFileDialog,QMessageBox)
from .operations import run_data_task


class QeReferenceDialog(QDialog):
    def __init__(self,window,mode_document):
        super().__init__(window);self.setWindowTitle('Assign QE phonon reference');self.resize(620,300)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.entries=[];self.combo=QComboBox();form.addRow('Reference structure',self.combo)
        self.frame_number=QSpinBox();form.addRow('Reference frame',self.frame_number)
        self.alat=QDoubleSpinBox();self.alat.setRange(0.,1.e6);self.alat.setDecimals(8);self.alat.setSuffix(' Å')
        form.addRow('QE alat (q scale)',self.alat)
        note=QLabel('Match the mode rows to the same atoms in the same order. A mode-only file has no element labels.\n'
                    'q is Cartesian in units 2π/alat. Use the alat of the calculation that produced the mode file; '
                    'the value below comes from the selected QE record when available.')
        note.setWordWrap(True);layout.addWidget(note)
        self.details=QLabel();self.details.setWordWrap(True);layout.addWidget(self.details)
        choose=QPushButton('Choose a reference structure file…');choose.clicked.connect(self.choose_file);layout.addWidget(choose)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.combo.currentIndexChanged.connect(self.update_choice);self.frame_number.valueChanged.connect(self.update_frame)
        for doc in window.documents:
            if doc.frames:self.add_document(doc)
        preferred=next((i for i,doc in enumerate(self.entries) if 'PHONON' in doc.format_name),len(self.entries)-1)
        if preferred>=0:self.combo.setCurrentIndex(preferred)
        self.update_choice()

    def add_document(self,doc):
        self.entries.append(doc);self.combo.addItem(f'{doc.path.name} · {len(doc.frames)} frame(s)')

    def update_choice(self,*_):
        i=self.combo.currentIndex()
        if not 0<=i<len(self.entries):self.details.setText('Choose or open a reference structure.');return
        self.frame_number.setRange(1,len(self.entries[i].frames));self.frame_number.setValue(len(self.entries[i].frames));self.update_frame()

    def update_frame(self,*_):
        reference=self.reference()
        if reference is None:return
        self.alat.setValue(float(reference.info.get('qe_alat_ang',0.)))
        self.details.setText(f'{len(reference.symbols)} atoms, order: '+', '.join(reference.symbols[:20])+('…' if len(reference.symbols)>20 else ''))

    def reference(self):
        i=self.combo.currentIndex()
        return self.entries[i].frames[self.frame_number.value()-1] if 0<=i<len(self.entries) else None

    def reference_name(self):
        i=self.combo.currentIndex()
        return f'{self.entries[i].path.name}, frame {self.frame_number.value()}' if i>=0 else ''

    def choose_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Choose the structure used by these phonon modes','','All files (*)')
        if not path:return
        try:
            from .formats import load_document
            doc=run_data_task(self,'Loading phonon reference',lambda:load_document(path))
            if not doc.frames:raise ValueError('This file has no complete structure')
            self.add_document(doc);self.combo.setCurrentIndex(len(self.entries)-1)
        except Exception as exc:QMessageBox.warning(self,'Could not load reference',str(exc))
