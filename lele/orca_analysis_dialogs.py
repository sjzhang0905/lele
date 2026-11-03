"""ORCA result browsers with independent sources and explicit geometry links."""
from pathlib import Path
import csv,json
from .operations import gui_operation,ui_operation,run_data_task
from .output_text import progress_items
import numpy as np
from ase.units import Hartree
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QTableWidget,
    QTableWidgetItem,QAbstractItemView,QPushButton,QFileDialog,QDoubleSpinBox,QCheckBox,QTabWidget,QWidget)


def table(parent,headers):
    widget=QTableWidget(0,len(headers),parent);widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return widget


def fill(widget,headers,rows):
    column=widget.horizontalHeader().sortIndicatorSection() if widget.isSortingEnabled() else 0
    order=widget.horizontalHeader().sortIndicatorOrder() if widget.isSortingEnabled() else Qt.SortOrder.AscendingOrder
    widget.setSortingEnabled(False);widget.setColumnCount(len(headers));widget.setHorizontalHeaderLabels(headers);widget.setRowCount(len(rows))
    for i,row in enumerate(progress_items(rows,'Building result table')):
        for j,value in enumerate(row):
            item=QTableWidgetItem()
            if isinstance(value,(int,float,np.floating)) and not isinstance(value,bool):item.setData(Qt.ItemDataRole.DisplayRole,float(value) if isinstance(value,(float,np.floating)) else int(value))
            else:item.setText('Not printed' if value is None else str(value))
            item.setData(Qt.ItemDataRole.UserRole,i);widget.setItem(i,j,item)
    widget.resizeColumnsToContents();widget.setSortingEnabled(True)
    widget.sortItems(max(0,min(column,len(headers)-1)),order)


def selected_row(widget):
    item=widget.item(widget.currentRow(),0)
    return None if item is None else item.data(Qt.ItemDataRole.UserRole)


def figure(layout):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
    fig=Figure(figsize=(9,5),tight_layout=True);canvas=FigureCanvasQTAgg(fig)
    layout.addWidget(NavigationToolbar2QT(canvas,layout.parentWidget()));layout.addWidget(canvas,2)
    return fig,canvas


def export_rows(parent,document,suffix,headers,rows):
    path,_=QFileDialog.getSaveFileName(parent,'Export results',str(document.path.with_name(document.path.stem+suffix)),'CSV (*.csv)')
    if path:
        def write():
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(headers);writer.writerows(progress_items(rows,'Writing result CSV'))
        run_data_task(parent,'Exporting results',write)


class NebDialog(QDialog):
    def __init__(self,document,jump,parent=None):
        super().__init__(parent);self.document=document;self.jump=jump;self.links={};self._rows=[]
        self.setWindowTitle('NEB / NEB-TS — '+document.path.name);self.resize(1100,900)
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.run=QComboBox();self.run.addItems([r.label for r in document.neb_runs])
        self.view=QComboBox();self.view.addItems(['Path snapshot','Image history','NEB convergence'])
        self.profile=QComboBox();self.image=QComboBox();self.unit=QComboBox();self.unit.addItems(['kcal/mol','eV','Hartree'])
        for w in (self.run,self.view,self.profile,self.image,self.unit):controls.addWidget(w)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.fig,self.canvas=figure(layout);self.canvas.mpl_connect('pick_event',self.pick)
        self.table=table(self,[]);layout.addWidget(self.table,1);self.table.itemSelectionChanged.connect(self.select_table)
        buttons=QHBoxLayout();layout.addLayout(buttons)
        self.ts_button=QPushButton('View refined TS');self.ts_button.clicked.connect(self.show_ts);buttons.addWidget(self.ts_button)
        export=QPushButton('Export displayed data CSV…');export.clicked.connect(lambda:export_rows(self,document,'_neb.csv',self._headers,self._rows));buttons.addWidget(export)
        self.run.currentIndexChanged.connect(self.prepare)
        for w in (self.view,self.profile,self.image,self.unit):w.currentIndexChanged.connect(self.redraw)
        self.prepare()

    def prepare(self,*_):
        with QSignalBlocker(self.profile),QSignalBlocker(self.image):
            self.profile.clear();self.image.clear()
            if self.run.currentIndex()<0:return
            run=self.document.neb_runs[self.run.currentIndex()]
            for p in run.profiles:self.profile.addItem(p.label+f' · {sum(f is not None for f in p.frame_indices)}/{len(p.energies)} structures')
            self.image.addItems([f'Image {i}' for i in range(run.nimages or 0)])
            available=[i for i,p in enumerate(run.profiles) if p.frame_indices and all(f is not None for f in p.frame_indices)]
            logged=[i for i in available if run.profiles[i].source.endswith('.NEB.log')]
            if available:self.profile.setCurrentIndex((logged or available)[-1])
        self.redraw()

    def _plot(self,ax,x,y,label,frames,sequence,**kw):
        values=[(a,b,f) for a,b,f in zip(x,y,frames) if b is not None and np.isfinite(b)]
        if not values:return
        line,=ax.plot([v[0] for v in values],[v[1] for v in values],'.-',label=label,picker=6,**kw)
        self.links[line]=([v[2] for v in values],sequence,label)

    @gui_operation('Preparing result display')
    def redraw(self,*_):
        if not hasattr(self,'canvas'):return
        self.fig.clear();self.links={};self._rows=[];self._frames=[];self._sequence=[]
        energy=self.fig.add_subplot(211);forces=self.fig.add_subplot(212)
        if self.run.currentIndex()<0:self.canvas.draw();return
        run=self.document.neb_runs[self.run.currentIndex()];mode=self.view.currentIndex()
        factor={'Hartree':1.,'eV':Hartree,'kcal/mol':Hartree*23.0605478306}[self.unit.currentText()]
        self.profile.setEnabled(mode==0);self.image.setEnabled(mode==1);self.ts_button.setEnabled(run.ts_frame is not None)
        notes=list(run.notes)
        if mode==0 and self.profile.currentIndex()>=0:
            p=run.profiles[self.profile.currentIndex()];n=len(p.energies)
            x=p.distances if len(p.distances)==n else list(range(n));xlabel='Path distance (Å)' if len(p.distances)==n else 'Image'
            baseline=p.energies[0];y=[(e-baseline)*factor for e in p.energies]
            frames=p.frame_indices if len(p.frame_indices)==n else [None]*n
            self._sequence=[f for f in frames if f is not None]
            self._plot(energy,x,y,'Image energies',frames,self._sequence)
            if p.interpolation:
                energy.plot([a for a,b in p.interpolation],[b*factor for a,b in p.interpolation],'-',alpha=.7,label='ORCA interpolation')
            if p.ci is not None and p.ci<n:energy.plot([x[p.ci]],[y[p.ci]],'r*',ms=13,label=f'CI {p.ci}')
            self._headers=['image',xlabel,'relative energy ('+self.unit.currentText()+')','printed energy (Hartree; relative if flagged)','energy is relative','max perpendicular force (Eh/Bohr)','global max force (Eh/Bohr)','geometry frame','source']
            for i in range(n):
                fp=p.forces.get('max(|Fr_perp|)',[None]*n);fg=p.forces.get('max(|Force|)',[None]*n)
                self._rows.append([i,x[i],y[i],p.energies[i],p.relative,fp[i] if len(fp)==n else None,fg[i] if len(fg)==n else None,None if frames[i] is None else frames[i]+1,p.source])
            for key in ('max(|Fr_perp|)','RMS(Fp)','max(|Force|)'):
                vals=p.forces.get(key,[])
                if len(vals)==n:self._plot(forces,x,vals,key,frames,self._sequence)
            self._frames=frames
            notes.insert(0,p.label+'. Relative energies use image 0. Click an image to show its matched geometry.')
        elif mode==1:
            image=self.image.currentIndex()
            profiles=sorted([p for p in run.profiles if p.iteration is not None and p.frame_indices and '.NEB.log' in p.source],key=lambda p:p.iteration)
            frames=[p.frame_indices[image] for p in profiles if image<len(p.frame_indices)]
            self._sequence=[f for f in frames if f is not None];self._frames=frames
            x=[p.iteration for p in profiles];y=[(p.energies[image]-p.energies[0])*factor for p in profiles]
            self._plot(energy,x,y,f'Image {image} energy relative to reactant',frames,self._sequence)
            fp=[p.forces.get('max(|Fr_perp|)',[None]*len(p.energies))[image] for p in profiles]
            self._plot(forces,x,fp,'Max perpendicular force',frames,self._sequence)
            self._headers=['iteration','image','relative energy ('+self.unit.currentText()+')','max perpendicular force (Eh/Bohr)','geometry frame','source']
            self._rows=[[p.iteration,image,e,f,None if fr is None else fr+1,p.source] for p,e,f,fr in zip(profiles,y,fp,frames)]
            xlabel='NEB iteration';notes.insert(0,f'Fixed image {image}; optimization history from matched NEB.log/XYZ snapshots.')
        else:
            rows=run.convergence;x=[r['iteration'] for r in rows];empty=[None]*len(rows)
            self._plot(energy,x,[r['barrier']*factor for r in rows],'Reported highest/climbing-image energy',empty,[])
            for key in ('max_perp','rms_perp','max_ci','rms_ci'):
                self._plot(forces,x,[r.get(key) for r in rows],key,empty,[])
            self._headers=['iteration','highest / CI image','relative energy ('+self.unit.currentText()+')','max perpendicular','RMS perpendicular','max CI global force','RMS CI global force']
            self._rows=[[r['iteration'],r['image'],r['barrier']*factor,r['max_perp'],r['rms_perp'],r['max_ci'],r['rms_ci']] for r in rows]
            xlabel='NEB iteration';notes.insert(0,'Main-output convergence: perpendicular regular-image forces and global CI forces remain separate.')
            if not rows:notes.append('No main-output convergence table in this file. Select path snapshots for per-image forces.')
        fill(self.table,self._headers,self._rows)
        axes=(energy,forces)
        if not forces.lines:
            forces.remove();energy.set_subplotspec(self.fig.add_gridspec(1,1)[0]);axes=(energy,)
            notes.append('No force table for this source. NEB.log snapshots may provide per-image forces.')
        for ax in axes:
            ax.set_xlabel(xlabel);ax.grid(True,alpha=.2)
            if ax.lines:ax.legend(fontsize=8)
        energy.set_ylabel('Relative energy ('+self.unit.currentText()+')');forces.set_ylabel('Force (Hartree/Bohr)')
        self.note.setText('\n'.join(notes));self.canvas.draw()

    def pick(self,event):
        link=self.links.get(event.artist)
        if link and len(event.ind):
            frames,sequence,label=link;index=int(event.ind[0])
            if index<len(frames):self.navigate(frames[index],sequence,label)

    def navigate(self,index,sequence,label):
        if index is None:self.note.setText(self.note.text()+'\nNo matched coordinates for this point.');return
        self.jump(index,sequence,label)

    def select_table(self):
        row=selected_row(self.table)
        if row is not None and row<len(self._frames):self.navigate(self._frames[row],self._sequence,'NEB '+self.view.currentText())

    def show_ts(self):
        run=self.document.neb_runs[self.run.currentIndex()]
        if run.ts_frame is not None:self.jump(run.ts_frame,[], 'Refined TS')


class GoatDialog(QDialog):
    def __init__(self,document,jump,parent=None):
        super().__init__(parent);self.document=document;self.jump=jump;self.setWindowTitle('GOAT conformer ensemble — '+document.path.name);self.resize(1050,820)
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.ensemble=QComboBox();self.ensemble.addItems([f'Ensemble {i+1} · line {e.source_line}' for i,e in enumerate(document.conformer_ensembles)])
        self.temperature=QDoubleSpinBox();self.temperature.setRange(1,3000);self.temperature.setValue(298.15);self.temperature.setSuffix(' K');self.temperature.setKeyboardTracking(False)
        self.reference=QComboBox();self.heavy=QCheckBox('Heavy-atom RMSD');self.heavy.setChecked(True)
        for w in (self.ensemble,self.temperature,self.reference,self.heavy):controls.addWidget(w)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        self.fig,self.canvas=figure(layout);self.table=table(self,[]);layout.addWidget(self.table,1)
        self.table.itemSelectionChanged.connect(self.select)
        button=QPushButton('Export conformer analysis CSV…');button.clicked.connect(lambda:export_rows(self,document,'_goat.csv',self.headers,self.rows));layout.addWidget(button)
        self.ensemble.currentIndexChanged.connect(self.prepare)
        self.reference.currentIndexChanged.connect(self.redraw);self.temperature.valueChanged.connect(self.redraw);self.heavy.toggled.connect(self.redraw)
        self.prepare()

    def prepare(self,*_):
        with QSignalBlocker(self.reference),QSignalBlocker(self.temperature):
            self.reference.clear()
            if self.ensemble.currentIndex()<0:return
            e=self.document.conformer_ensembles[self.ensemble.currentIndex()]
            self.reference.addItems([f'RMSD reference: conformer {c.number}' for c in e.conformers]);self.temperature.setValue(e.temperature or 298.15)
        self.redraw()

    @gui_operation('Preparing result display')
    def redraw(self,*_):
        from .orca_goat import aligned_rmsd
        self.fig.clear();self.rows=[];self.headers=['Conformer','Relative energy (kcal/mol)','Degeneracy','Printed population (%)','Printed cumulative (%)','Calculated population (%)','Aligned RMSD (Å)','Geometry frame','Analysis temperature (K)']
        if self.ensemble.currentIndex()<0:fill(self.table,self.headers,[]);self.canvas.draw();return
        e=self.document.conformer_ensembles[self.ensemble.currentIndex()];weights=e.populations(self.temperature.value())
        ref=e.conformers[max(0,self.reference.currentIndex())].reference
        for i,c in enumerate(e.conformers):
            rmsd=None if ref is None or c.reference is None else aligned_rmsd(ref,c.reference,self.heavy.isChecked())
            self.rows.append([c.number,c.relative_kcal,c.degeneracy,c.printed_percent,c.cumulative_percent,None if weights is None else weights[i],rmsd,None if c.frame_index is None else c.frame_index+1,self.temperature.value()])
        fill(self.table,self.headers,self.rows)
        ax=self.fig.add_subplot(211);pop=self.fig.add_subplot(212);x=[c.number for c in e.conformers]
        ax.plot(x,[np.nan if c.relative_kcal is None else c.relative_kcal for c in e.conformers],'.-');ax.set_ylabel('Relative energy (kcal/mol)')
        pop.bar(np.asarray(x)-.18,[np.nan if c.printed_percent is None else c.printed_percent for c in e.conformers],width=.36,label='Printed')
        if weights is not None:pop.bar(np.asarray(x)+.18,weights,width=.36,label=f'Calculated {self.temperature.value():g} K')
        pop.set_ylabel('Population (%)');pop.legend();pop.set_xlabel('Conformer (printed number)')
        self.note.setText(e.note+'\nCalculated populations use printed relative energies and degeneracies; missing degeneracy uses 1. '
            'RMSD uses rigid alignment and identical atom order, without atom permutation. '+
            ('Printed ensemble temperature: '+str(e.temperature)+' K.' if e.temperature else 'Ensemble temperature was not printed; initial analysis uses 298.15 K.'))
        self.canvas.draw()

    def select(self):
        row=selected_row(self.table)
        if row is None:return
        e=self.document.conformer_ensembles[self.ensemble.currentIndex()];c=e.conformers[row]
        if c.frame_index is not None:self.jump(c.frame_index,[c.frame_index for c in e.conformers if c.frame_index is not None],f'GOAT ensemble {self.ensemble.currentIndex()+1}')


class SocDialog(QDialog):
    def __init__(self,document,parent=None):
        super().__init__(parent);self.document=document;self.setWindowTitle('Spin–orbit coupling — '+document.path.name);self.resize(1100,900)
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.analysis=QComboBox();self.analysis.addItems([f'{a.label} · line {a.source_line}' for a in document.soc_results])
        self.component=QComboBox();self.component.addItems(['Norm','|X|','|Y|','|Z|','Re X','Im X','Re Y','Im Y','Re Z','Im Z','|H|'])
        self.unit=QComboBox();self.unit.addItems(['cm⁻¹','eV'])
        for w in (self.analysis,self.component,self.unit):controls.addWidget(w)
        self.note=QLabel();self.note.setWordWrap(True);layout.addWidget(self.note)
        tabs=QTabWidget();layout.addWidget(tabs)
        page=QWidget();panel=QVBoxLayout(page);self.fig,self.canvas=figure(panel);self.table=table(page,[]);panel.addWidget(self.table,1);tabs.addTab(page,'Couplings')
        states=QWidget();s_layout=QVBoxLayout(states);self.states=table(states,['SOC state','Energy (cm⁻¹)','Energy (eV)']);self.details=table(states,['Basis (root / spin / Ms as printed)','Weight','Real coefficient','Imaginary coefficient']);s_layout.addWidget(self.states);s_layout.addWidget(self.details);tabs.addTab(states,'Mixed states')
        spec=QWidget();p_layout=QVBoxLayout(spec);self.spectrum_fig,self.spectrum_canvas=figure(p_layout);self.transitions=table(spec,[]);p_layout.addWidget(self.transitions);tabs.addTab(spec,'SOC absorption')
        export=QPushButton('Export SOC tables CSV…');export.clicked.connect(self.export_data);layout.addWidget(export)
        for w in (self.analysis,self.component,self.unit):w.currentIndexChanged.connect(self.redraw)
        self.states.itemSelectionChanged.connect(self.state_selected);self.redraw()

    @gui_operation('Preparing result display')
    def redraw(self,*_):
        if self.analysis.currentIndex()<0:return
        a=self.document.soc_results[self.analysis.currentIndex()];factor=1. if self.unit.currentIndex()==0 else 1239.841984332/1.e7
        self.headers=['Bra','Ket','Norm ('+self.unit.currentText()+')','Re X','Im X','Re Y','Im Y','Re Z','Im Z','Re H','Im H','Source line'];self.rows=[]
        for e in a.elements:
            values=[]
            for axis in ('X','Y','Z','H'):
                value=e.components.get(axis);values += [None,None] if value is None else [value.real*factor,value.imag*factor]
            self.rows.append([e.bra,e.ket,e.norm*factor,*values,e.source_line])
        fill(self.table,self.headers,self.rows)
        self.fig.clear();ax=self.fig.add_subplot(111);bras=list(dict.fromkeys(e.bra for e in a.elements));kets=list(dict.fromkeys(e.ket for e in a.elements))
        matrix=np.full((len(bras),len(kets)),np.nan)
        choice=self.component.currentText()
        for e in a.elements:
            if choice=='Norm':v=e.norm
            else:
                axis=choice[-2] if choice.startswith('|') else choice[-1];z=e.components.get(axis)
                v=np.nan if z is None else abs(z) if choice.startswith('|') else z.real if choice.startswith('Re') else z.imag
            matrix[bras.index(e.bra),kets.index(e.ket)]=v*factor
        if matrix.size:
            plot=ax.imshow(np.ma.masked_invalid(matrix),aspect='auto');self.fig.colorbar(plot,ax=ax,label=self.unit.currentText());ax.set_xticks(range(len(kets)),kets,rotation=90,fontsize=8);ax.set_yticks(range(len(bras)),bras,fontsize=8)
        ax.set_title(choice+' · printed SOC elements');self.canvas.draw()
        fill(self.states,['SOC state','Energy (cm⁻¹)','Energy (eV)'],[[s.number,s.energy_cm,s.energy_ev] for s in a.states]);self.details.setRowCount(0)
        if a.states:self.states.selectRow(0)
        self.spectrum_headers=['From SOC state','To SOC state','Energy (cm⁻¹)','Wavelength (nm)','Oscillator strength','Dipole strength','Complex dipole (Re, Im; au)']
        self.spectrum_rows=[[t['from_state'],t['to_state'],t['energy_cm'],t['wavelength_nm'],t['oscillator_strength'],t['dipole_strength'],json.dumps(t.get('complex_dipole',{}))] for t in a.transitions]
        fill(self.transitions,self.spectrum_headers,self.spectrum_rows)
        self.spectrum_fig.clear();sp=self.spectrum_fig.add_subplot(111)
        ground=[t for t in a.transitions if t['from_state']==0]
        if ground:
            x=[t['energy_cm']*1239.841984332/1.e7 for t in ground];sp.vlines(x,0,[t['oscillator_strength'] for t in ground]);sp.set_xlabel('Transition energy (eV)');sp.set_ylabel('Printed oscillator strength')
        sp.set_title('SOC-corrected ground-state absorption');self.spectrum_canvas.draw()
        self.note.setText(a.note+' Printed mixed-state coefficients and SOC spectra remain separate from spin-free TD/TDA data. '
            'Only printed composition terms are listed; weights are not renormalized.')

    def state_selected(self):
        index=selected_row(self.states)
        if index is None:return
        state=self.document.soc_results[self.analysis.currentIndex()].states[index]
        fill(self.details,['Basis (root / spin / Ms as printed)','Weight','Real coefficient','Imaginary coefficient'],[[c['basis'],c['weight'],c['real'],c['imag']] for c in state.composition])

    def export_data(self):
        a=self.document.soc_results[self.analysis.currentIndex()];rows=[]
        for e in a.elements:
            row=dict(record='coupling',bra=e.bra,ket=e.ket,norm_cm1=e.norm,source_line=e.source_line)
            for axis,value in e.components.items():row[axis+'_real_cm1']=value.real;row[axis+'_imag_cm1']=value.imag
            rows.append(row)
        for s in a.states:
            rows.append(dict(record='mixed_state',state=s.number,energy_cm1=s.energy_cm,energy_eV=s.energy_ev,composition_json=json.dumps(s.composition)))
        rows += [dict(record='SOC_absorption',**t,complex_dipole_json=json.dumps(t.get('complex_dipole',{}))) for t in a.transitions]
        for row in rows:row.pop('complex_dipole',None)
        headers=list(dict.fromkeys(k for row in rows for k in row))
        export_rows(self,self.document,'_soc.csv',headers,[[row.get(k) for k in headers] for row in rows])


class HessianDialog(QDialog):
    def __init__(self,document,jump,modes,parent=None):
        super().__init__(parent);self.document=document;self.jump=jump;self.modes=modes;self.events=[]
        self.setWindowTitle('Hessian history — '+document.path.name);self.resize(1050,650)
        layout=QVBoxLayout(self);self.updates=QCheckBox('Include BFGS/Bofill updates');self.updates.toggled.connect(self.redraw);layout.addWidget(self.updates)
        note=QLabel('Exact calculations, model/read Hessians and updates retain their parent stage/cycle. Negative optimizer Hessian eigenvalues do not certify a final vibrational TS.');note.setWordWrap(True);layout.addWidget(note)
        self.table=table(self,[]);layout.addWidget(self.table)
        self.modes_button=QPushButton('Show modes for selected exact Hessian');self.modes_button.clicked.connect(self.show_modes);self.modes_button.setEnabled(False);layout.addWidget(self.modes_button)
        self.table.itemSelectionChanged.connect(self.select);self.redraw()

    def redraw(self):
        r=self.document.calculation_results
        self.events=[] if r is None else [e for e in r.hessians if self.updates.isChecked() or not e.kind.startswith('Update')]
        fill(self.table,['Stage','Cycle','Kind','Optimizer negative eigenvalues','Hessian file','Source line'],[[r.stages[e.stage_index].name if e.stage_index is not None else 'Frequency',e.cycle,e.kind,e.negative_eigenvalues,e.filename,e.source_line] for e in self.events])

    def select(self):
        row=selected_row(self.table)
        self.modes_button.setEnabled(False)
        if row is None:return
        e=self.events[row];r=self.document.calculation_results
        self.modes_button.setEnabled('exact' in e.kind.lower() and any(a.stage_index==e.stage_index and a.cycle==e.cycle for a in self.document.vibrations))
        step=next((s for s in r.steps if s.stage_index==e.stage_index and s.cycle==e.cycle and s.frame_index is not None),None)
        if step is not None:self.jump(step.frame_index,[],'Hessian reference')

    def show_modes(self):
        row=selected_row(self.table)
        if row is None:return
        e=self.events[row]
        match=next((i for i,a in enumerate(self.document.vibrations) if a.stage_index==e.stage_index and a.cycle==e.cycle),None)
        if match is not None:self.modes(match)
