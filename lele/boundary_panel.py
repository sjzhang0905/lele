"""Integer whole-cell display ranges; no scientific startup import."""
from PySide6.QtCore import Signal,QSignalBlocker
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QSpinBox,QCheckBox,QPushButton,QLabel


class BoundaryPanel(QWidget):
    applyRequested=Signal(bool,object)
    def __init__(self,parent=None):
        super().__init__(parent);layout=QVBoxLayout(self)
        self.enabled=QCheckBox('Enable boundary display');layout.addWidget(self.enabled)
        grid=QGridLayout();layout.addLayout(grid);self.spins=[]
        for j,text in enumerate(('Cells','Start (included)','End (excluded)')):grid.addWidget(QLabel(text),0,j)
        for i,name in enumerate(('a / x','b / y','c / z')):
            grid.addWidget(QLabel(name),i+1,0);row=[]
            for j,value in enumerate((0,1)):
                spin=QSpinBox();spin.setRange(-10,10);spin.setValue(value);spin.setKeyboardTracking(False)
                grid.addWidget(spin,i+1,j+1);row.append(spin)
            self.spins.append(row)
        self.apply=QPushButton('Apply');self.apply.clicked.connect(lambda:self.applyRequested.emit(self.enabled.isChecked(),self.bounds()))
        self.reset=QPushButton('Reset to one cell');self.reset.clicked.connect(self.reset_bounds)
        layout.addWidget(self.apply);layout.addWidget(self.reset)
        self.count=QLabel();layout.addWidget(self.count)
        note=QLabel('Repeat complete cells: 0–2, 0–2, 0–1 displays 2×2×1 cells.\n'
                    'Every cell keeps its original size and all its atoms; cell edges separate the copies.\n'
                    'Display copies retain source atom IDs; source coordinates and unit cell are unchanged.\n'
                    'For real atoms and a larger cell, use Edit → Build supercell.')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch();self.setEnabled(False)

    def bounds(self):return tuple(tuple(spin.value() for spin in row) for row in self.spins)

    def reset_bounds(self):
        self.set_values(False,((0,1),)*3);self.applyRequested.emit(False,self.bounds())

    def set_values(self,enabled,bounds):
        with QSignalBlocker(self.enabled):self.enabled.setChecked(enabled)
        for row,values in zip(self.spins,bounds):
            for spin,value in zip(row,values):
                with QSignalBlocker(spin):spin.setValue(int(value))
