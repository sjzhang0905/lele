"""Calculation overview with separate job records and explicit missing values."""
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QTableWidget,QTableWidgetItem,
    QPlainTextEdit,QAbstractItemView)


class CalculationOverview(QDialog):
    def __init__(self,document,parent=None):
        super().__init__(parent);self.document=document
        self.results=document.calculation_results
        self.jobs=[] if self.results is None else self.results.jobs
        self.setWindowTitle('Calculation overview — '+document.path.name);self.resize(1100,680)
        layout=QVBoxLayout(self)
        self.header=QLabel(f'{document.path.name} · {document.format_name}\n'+
            (f'{len(document.frames)} geometry frames · {len(document.frames[0].symbols)} atoms in the first frame · ' if document.frames else 'No structure · ')+
            f'{len(self.jobs)} calculation segment(s)')
        self.header.setWordWrap(True);layout.addWidget(self.header)
        available=[frame.energy_ev for frame in document.frames if frame.energy_ev is not None]
        self.header.setText(self.header.text()+'\nAvailable frame energies: '+str(len(available))+
            (' · last energy '+f'{available[-1]:.8f} eV' if available else '')+
            (' · '+('Periodic structure' if any(document.frames[0].pbc) else 'Isolated structure') if document.frames else ''))
        self.table=QTableWidget(len(self.jobs),10)
        self.table.setHorizontalHeaderLabels(['Job','Task','Method','Basis','Charge','Multiplicity','Energy (eV)','Termination','Last SCF cycles','Imaginary modes'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table,1)
        for i,job in enumerate(self.jobs):
            values=[job.index+1,' / '.join(sorted(job.tasks)) or 'Not printed',job.method,job.basis,job.charge,job.multiplicity,
                    None if job.energy_ev is None else f'{job.energy_ev:.8f}',job.termination,job.scf_cycles,
                    job.imaginary_modes if job.frequency_count else None]
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem('Not printed' if value is None or value=='' else str(value)))
        self.table.resizeColumnsToContents()
        stages=[] if self.results is None else self.results.stages
        self.stage_table=QTableWidget(len(stages),5)
        self.stage_table.setHorizontalHeaderLabels(['Stage','Kind','Status','Result steps','Hessian events'])
        self.stage_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i,s in enumerate(stages):
            count=sum(p.stage_index==s.index for p in self.results.steps)
            events=sum(e.stage_index==s.index for e in self.results.hessians)
            for j,v in enumerate((s.name,s.kind,s.status,count,events)):self.stage_table.setItem(i,j,QTableWidgetItem(str(v)))
        self.stage_table.resizeColumnsToContents();self.stage_table.setVisible(bool(stages));layout.addWidget(self.stage_table,1)
        self.details=QPlainTextEdit();self.details.setReadOnly(True);layout.addWidget(self.details,1)
        self.table.itemSelectionChanged.connect(self.show_details)
        if self.jobs:self.table.selectRow(0)
        else:self.details.setPlainText('The file exposes geometry/energy data, but no supported calculation-summary records. Missing metadata is not assumed.')
        note=QLabel('Source calculation results. Structure/display edits do not run a new electronic calculation.');layout.addWidget(note)

    def show_details(self):
        row=self.table.currentRow()
        if row<0:return
        job=self.jobs[row]
        steps=[s for s in self.results.steps if s.job_index==job.index]
        frames=sorted({s.frame_index+1 for s in steps if s.frame_index is not None})
        lines=[f'Job {job.index+1} · source line {job.start_line}',
               'Route / input: '+(job.route or 'Not printed'),
               'Solvent: '+(job.solvent or 'Not printed'),
               f'Geometry frames: {frames}',f'Printed frequency count: {job.frequency_count}',
               'Printed <S²>: '+('Not printed' if job.spin_squared is None else str(job.spin_squared))]
        last=next((s for s in reversed(steps) if s.convergence),None)
        if last:
            lines.append('Last printed geometry convergence:')
            lines += [f'  {key}: {value:g} / threshold {threshold:g}' for key,(value,threshold) in last.convergence.items()]
        if self.results.program=='xTB':
            lines += [f'Optimization / trajectory records: {len(steps)}',self.document.note]
        self.details.setPlainText('\n'.join(lines))
