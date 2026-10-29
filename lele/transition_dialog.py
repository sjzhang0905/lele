"""Electronic states and all printed orbital contributions, including signs."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QComboBox,QLabel,QTableWidget,
    QTableWidgetItem,QAbstractItemView,QPushButton,QFileDialog)
from .gaussian_properties import contribution_text,transition_state_label


class TransitionDialog(QDialog):
    def __init__(self,document,parent=None):
        super().__init__(parent);self.document=document
        self.setWindowTitle('Excited-state transitions — '+document.path.name);self.resize(1100,750)
        layout=QVBoxLayout(self);self.calculation=QComboBox()
        self.calculation.addItems([f'Calculation {i+1}'+(' · '+s.label if s.label else '')+
            f' · line {s.source_line}' for i,s in enumerate(document.electronic_spectra)])
        layout.addWidget(self.calculation)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['State','Energy (eV)','Wavelength (nm)','Oscillator strength','Major transitions (printed c)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.table,1)
        self.details=QTableWidget(0,7);self.details.setHorizontalHeaderLabels(['From MO','Spin','Direction','To MO','Spin','Signed coefficient','Printed weight (if available)'])
        self.details.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);layout.addWidget(self.details,1)
        note=QLabel('Orbital numbers and signed coefficients are preserved as printed. Gaussian forward/backward rows remain separate.\n'
            'Only printed contributions are available; their squared coefficients are not normalized into claimed percentages.')
        note.setWordWrap(True);layout.addWidget(note)
        button=QPushButton('Export transitions + contributions CSV…');button.clicked.connect(self.export_data);layout.addWidget(button)
        self.calculation.currentIndexChanged.connect(self.redraw);self.table.itemSelectionChanged.connect(self.show_details);self.redraw()

    def redraw(self,*_):
        index=self.calculation.currentIndex();self.details.setRowCount(0)
        self.transitions=[] if index<0 else self.document.electronic_spectra[index].transitions
        self.table.setRowCount(len(self.transitions))
        for i,t in enumerate(self.transitions):
            for j,value in enumerate([f'{t.number} {transition_state_label(t.state)}',f'{t.energy_ev:.6f}',f'{t.wavelength_nm:.4f}',
                                     t.oscillator_strength,contribution_text(t)]):
                self.table.setItem(i,j,QTableWidgetItem('Not printed' if value is None else str(value)))
        self.table.resizeColumnsToContents()
        if self.transitions:self.table.selectRow(0)

    def show_details(self):
        i=self.table.currentRow()
        if not 0<=i<len(self.transitions):return
        rows=sorted(self.transitions[i].contributions,key=lambda c:abs(c.coefficient or 0),reverse=True)
        self.details.setRowCount(len(rows))
        for i,c in enumerate(rows):
            values=[c.from_orbital,c.from_spin,c.direction,c.to_orbital,c.to_spin,c.coefficient,c.printed_weight]
            for j,value in enumerate(values):self.details.setItem(i,j,QTableWidgetItem('' if value is None else str(value)))
        self.details.resizeColumnsToContents()

    def export_data(self):
        from .property_export import export_transitions
        path,_=QFileDialog.getSaveFileName(self,'Export transitions',str(self.document.path.with_name(self.document.path.stem+'_transitions.csv')),'CSV (*.csv)')
        if path:export_transitions(path,self.document,self.calculation.currentIndex())
