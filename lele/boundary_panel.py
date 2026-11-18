"""Integer whole-cell display ranges; no scientific startup import."""
from PySide6.QtCore import Qt,Signal,QSignalBlocker
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QSpinBox,QCheckBox,QPushButton,QLabel,QComboBox
from .lattice_tiles import repeat_bounds


class BoundaryPanel(QWidget):
    applyRequested=Signal(bool,object)
    def __init__(self,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.enabled=QCheckBox('Enable boundary display');self.enabled.setChecked(True);layout.addWidget(self.enabled)
        self.growth=QComboBox();self.growth.addItems(['Alternate + / − around original cell','Manual cell ranges'])
        layout.addWidget(self.growth)
        counts=QGridLayout();layout.addLayout(counts);self.repeat_spins=[]
        for axis,name in enumerate(('a / x','b / y','c / z')):
            counts.addWidget(QLabel(name),0,axis)
            spin=QSpinBox();spin.setRange(1,100);spin.setValue(1);spin.setKeyboardTracking(False)
            counts.addWidget(spin,1,axis);self.repeat_spins.append(spin)
        grid=QGridLayout();grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(grid);self.spins=[]
        for j,text in enumerate(('Cells','Start','End (cell limit)')):grid.addWidget(QLabel(text),0,j)
        for i,name in enumerate(('a / x','b / y','c / z')):
            grid.addWidget(QLabel(name),i+1,0);row=[]
            for j,value in enumerate((0,1)):
                spin=QSpinBox();spin.setRange(-100,101);spin.setValue(value);spin.setKeyboardTracking(False)
                grid.addWidget(spin,i+1,j+1);row.append(spin)
            self.spins.append(row)
        self.preserve=QCheckBox('Keep original atom coordinates and cell origin')
        self.preserve.setChecked(True);layout.addWidget(self.preserve)
        self.apply=QPushButton('Apply');self.apply.clicked.connect(lambda:self.applyRequested.emit(self.enabled.isChecked(),self.bounds()))
        self.reset=QPushButton('Reset to one cell');self.reset.clicked.connect(self.reset_bounds)
        layout.addWidget(self.apply);layout.addWidget(self.reset)
        self.count=QLabel();layout.addWidget(self.count)
        note=QLabel('Counts grow along each axis as 0, +1, −1, +2, −2. The original cell stays in place.\n'
                    'Manual ranges use an inclusive start and exclusive end; 0–2 gives two cells.\n'
                    'Every cell keeps its original size and all its atoms; cell edges separate the copies.\n'
                    'Atoms on outer cell faces are shown on both sides with the same index and count once.\n'
                    'Display copies retain source atom IDs; source coordinates and unit cell are unchanged.\n'
                    'For real atoms and a larger cell, use Edit → Build supercell.')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch();self.setEnabled(False)
        self.growth.currentIndexChanged.connect(self._growth_changed)
        for spin in self.repeat_spins:spin.valueChanged.connect(self._growth_changed)
        self._growth_changed()

    def _growth_changed(self,*_):
        alternating=self.growth.currentIndex()==0
        for spin in self.repeat_spins:spin.setEnabled(alternating)
        for row in self.spins:
            for spin in row:spin.setEnabled(not alternating)
        if alternating:
            for row,values in zip(self.spins,repeat_bounds(tuple(s.value() for s in self.repeat_spins))):
                for spin,value in zip(row,values):spin.setValue(value)

    def bounds(self):return tuple(tuple(spin.value() for spin in row) for row in self.spins)

    def reset_bounds(self):
        self.set_values(False,((0,1),)*3);self.applyRequested.emit(False,self.bounds())

    def set_values(self,enabled,bounds,preserve_origin=None):
        with QSignalBlocker(self.enabled):self.enabled.setChecked(enabled)
        if preserve_origin is not None:
            with QSignalBlocker(self.preserve):self.preserve.setChecked(preserve_origin)
        repeats=tuple(max(1,int(hi)-int(lo)) for lo,hi in bounds)
        alternating=(all(value<=spin.maximum() for value,spin in zip(repeats,self.repeat_spins))
            and tuple(tuple(int(v) for v in row) for row in bounds)==repeat_bounds(repeats))
        with QSignalBlocker(self.growth):self.growth.setCurrentIndex(0 if alternating else 1)
        for spin,value in zip(self.repeat_spins,repeats):
            with QSignalBlocker(spin):spin.setValue(value)
        for row,values in zip(self.spins,bounds):
            for spin,value in zip(row,values):
                with QSignalBlocker(spin):
                    spin.setRange(min(spin.minimum(),int(value)),max(spin.maximum(),int(value)))
                    spin.setValue(int(value))
        self._growth_changed()
