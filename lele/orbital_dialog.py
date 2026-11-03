"""Printed orbital occupations and frontier energies; default unit is eV."""
from ase.units import Hartree
from .operations import gui_operation
from .output_text import progress_items
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,
    QTableWidget,QTableWidgetItem,QAbstractItemView)


class OrbitalDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document=document
        self.snapshots=document.calculation_results.orbitals if document.calculation_results else []
        self.setWindowTitle('HOMO / LUMO — '+document.path.name);self.resize(820,650)
        layout=QVBoxLayout(self);row=QHBoxLayout();layout.addLayout(row)
        self.calculation=QComboBox()
        for snapshot in progress_items(self.snapshots,'Preparing orbital snapshots'):
            frame='unmatched' if snapshot.frame_index is None else str(snapshot.frame_index+1)
            self.calculation.addItem(f'Job {snapshot.job_index+1} · frame {frame} · line {snapshot.source_line}')
        row.addWidget(self.calculation,1)
        self.unit=QComboBox();self.unit.addItems(['eV','Hartree']);row.addWidget(self.unit)
        self.summary=QTableWidget(0,6)
        self.summary.setHorizontalHeaderLabels(['Channel','HOMO MO','HOMO energy','LUMO MO','LUMO energy','Gap'])
        self.summary.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.summary)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['Channel','MO (as printed)','Occupation','Energy'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        self.calculation.currentIndexChanged.connect(self.redraw);self.unit.currentIndexChanged.connect(self.redraw)
        self.calculation.setCurrentIndex(len(self.snapshots)-1);self.redraw()

    @gui_operation('Preparing orbital energies')
    def redraw(self,*_):
        index=self.calculation.currentIndex()
        if index<0:
            self.note.setText('No recognizable printed orbital-energy table was found.');return
        snapshot=self.snapshots[index];factor=1. if self.unit.currentIndex()==0 else 1./Hartree
        self.summary.setRowCount(len(snapshot.channels));rows=[]
        for i,(channel,orbitals) in enumerate(snapshot.channels.items()):
            homo,lumo,gap=snapshot.frontier(channel)
            values=[channel,None if homo is None else homo.number,None if homo is None else homo.energy_ev*factor,
                    None if lumo is None else lumo.number,None if lumo is None else lumo.energy_ev*factor,
                    None if gap is None else gap*factor]
            for j,value in enumerate(values):
                self.summary.setItem(i,j,QTableWidgetItem('Not printed' if value is None else f'{value:.6f}' if j in (2,4,5) else str(value)))
            rows += [(channel,row.number,row.occupation,row.energy_ev*factor) for row in orbitals]
        self.table.setRowCount(len(rows))
        for i,row in enumerate(progress_items(rows,'Building orbital table')):
            for j,value in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(f'{value:.6f}' if j==3 else str(value)))
        self.summary.resizeColumnsToContents();self.table.resizeColumnsToContents()
        identification=('Frontiers use explicit source HOMO/LUMO labels, including fractional occupations.'
                        if snapshot.frontier_numbers else 'Occupied/unoccupied levels are identified from printed occupations.')
        reported=(' Source summary HOMO–LUMO gap: '+f'{snapshot.reported_gap_ev*factor:.9f} '+self.unit.currentText()+'.'
                  if snapshot.reported_gap_ev is not None else '')
        self.note.setText(snapshot.numbering+'. Energies and gaps: '+self.unit.currentText()+'. '+identification+
            ' Missing virtual levels are not guessed.'+reported+'\n'
            'These are source-file orbital energies; editing a structure does not recalculate them.')
