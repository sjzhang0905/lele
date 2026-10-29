"""Energy and maximum/RMS geometry convergence, linked to loaded frames."""
import csv
import numpy as np
from ase.units import Hartree
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
    QCheckBox,QPushButton,QFileDialog)


class ConvergenceDialog(QDialog):
    def __init__(self,document,jump,parent=None):
        super().__init__(parent);self.document=document;self.jump=jump
        self.results=document.calculation_results
        self.is_xtb=self.results is not None and self.results.program=='xTB'
        self.line_frames={}
        self.setWindowTitle('Energy / geometry convergence — '+document.path.name);self.resize(950,820)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg,NavigationToolbar2QT
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.job=QComboBox()
        jobs=[] if self.results is None else self.results.jobs
        for job in jobs:self.job.addItem(f'Job {job.index+1} · '+(' / '.join(sorted(job.tasks)) or 'Results'),job.index)
        if not jobs:self.job.addItem('Loaded geometry frames',None)
        self.stage_combo=QComboBox()
        self._prepare_stages()
        self.metric_combo=QComboBox();self.metric_combo.addItems(['Maximum / RMS force','Maximum / RMS displacement'])
        self.unit=QComboBox();self.unit.addItems(['eV','Hartree','kcal/mol'])
        if self.is_xtb:self.unit.setCurrentText('kcal/mol')
        self.metric_combo.setVisible(not self.is_xtb)
        self.scan_only=QCheckBox('Converged scan points only')
        self.scan_only.setVisible(not self.is_xtb)
        self.scan_only.setChecked(bool(jobs and 'Scan' in jobs[0].tasks
            and any(step.job_index==jobs[0].index and step.converged for step in self.results.steps)))
        for widget in (self.job,self.stage_combo,self.metric_combo,self.unit,self.scan_only):controls.addWidget(widget)
        self.note=QLabel('Click a plotted point to display its geometry frame.');self.note.setWordWrap(True);layout.addWidget(self.note)
        self.figure=Figure(figsize=(8,6),tight_layout=True)
        self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename=lambda:str(document.path.with_name(document.path.stem+'_convergence.png'))
        layout.addWidget(NavigationToolbar2QT(self.canvas,self));layout.addWidget(self.canvas,1)
        self.export_button=QPushButton('Export curve data CSV…');self.export_button.clicked.connect(self.export_data);layout.addWidget(self.export_button)
        self.canvas.mpl_connect('pick_event',self.pick_point)
        self.job.currentIndexChanged.connect(self._job_changed)
        for widget in (self.stage_combo,self.metric_combo,self.unit):widget.currentIndexChanged.connect(self.redraw)
        self.scan_only.toggled.connect(self.redraw);self.redraw()

    def _prepare_stages(self):
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.stage_combo):
            self.stage_combo.clear()
            stages=[] if self.results is None else [s for s in self.results.stages if s.job_index==self.job.currentData() and any(p.stage_index==s.index and (p.frame_index is not None or self.is_xtb) for p in self.results.steps)]
            for stage in stages:self.stage_combo.addItem(stage.name+' · '+stage.status,stage.index)
            if not stages:self.stage_combo.addItem('Loaded geometry steps',None)
            self.stage_combo.setVisible(bool(stages))

    def _job_changed(self):
        self._prepare_stages();self.redraw()

    def points(self):
        index=self.job.currentData()
        if self.is_xtb:
            self.scan_only.setEnabled(False)
            stage=self.stage_combo.currentData()
            return [dict(frame=s.frame_index,energy_ev=s.energy_ev,metrics={},x=s.cycle or i+1,source_line=s.source_line)
                    for i,s in enumerate(self.results.steps) if s.job_index==index and (stage is None or s.stage_index==stage)]
        steps=[] if self.results is None else [s for s in self.results.steps if s.job_index==index and s.frame_index is not None]
        stage=self.stage_combo.currentData()
        if stage is not None:steps=[s for s in steps if s.stage_index==stage]
        job=None if self.results is None or index is None else self.results.jobs[index]
        self.scan_only.setEnabled(job is not None and 'Scan' in job.tasks)
        if job is not None and 'Scan' in job.tasks and self.scan_only.isChecked():
            steps=[step for step in steps if step.converged]
        result={}
        for step in steps:
            row=result.setdefault(step.frame_index,dict(frame=step.frame_index,energy_ev=step.energy_ev,metrics={}))
            row['metrics'].update(step.convergence)
            if step.energy_ev is not None:row['energy_ev']=step.energy_ev
        if not steps and (self.results is None or not self.results.steps):
            for i,frame in enumerate(self.document.frames):
                metrics={}
                for name in ('max_force','rms_force'):
                    value=frame.info.get('cartesian_'+name+'_ev_ang')
                    if value is not None:metrics[name]=(value,None)
                result[i]=dict(frame=i,energy_ev=frame.energy_ev,metrics=metrics)
        return [result[i] for i in sorted(result)]

    def _plot(self,axes,rows,values,label,**kwargs):
        valid=[(row.get('x',row['frame']+1 if row['frame'] is not None else 0),row['frame'],value)
               for row,value in zip(rows,values) if value is not None and np.isfinite(value)]
        if not valid:return None
        line,=axes.plot([x for x,_,_ in valid],[v for _,_,v in valid],'.-',label=label,picker=7,**kwargs)
        self.line_frames[line]=[i for _,i,_ in valid]
        return line

    def redraw(self,*_):
        self.figure.clear();self.line_frames={}
        self.energy_axes=self.figure.add_subplot(111 if self.is_xtb else 211)
        self.metric_axes=None if self.is_xtb else self.figure.add_subplot(212)
        rows=self.points();self._rows=rows
        factor={'eV':1.,'Hartree':1./Hartree,'kcal/mol':23.0605478306}[self.unit.currentText()]
        energies=[r['energy_ev'] for r in rows if r['energy_ev'] is not None]
        baseline=min(energies) if energies else 0.
        self._plot(self.energy_axes,rows,[None if r['energy_ev'] is None else (r['energy_ev']-baseline)*factor for r in rows],'Energy')
        self.energy_axes.set_ylabel('Relative energy ('+self.unit.currentText()+')')
        if not energies:self.energy_axes.text(.5,.5,'No printed energies for this segment',ha='center',transform=self.energy_axes.transAxes)
        if self.is_xtb:
            trajectory='Optimization trajectory' in self.results.jobs[self.job.currentData()].tasks
            self.energy_axes.set_xlabel('Trajectory record' if trajectory else 'Optimization cycle')
            self.energy_axes.grid(True,alpha=.2)
            matched=sum(r['frame'] is not None for r in rows)
            self.note.setText(f'{len(rows)} energy records · {matched} with geometry. Relative energies use the minimum shown. '
                'Click a point with matched coordinates to display that structure.\n'+self.document.note)
            self.canvas.draw();return
        names=('max_force','rms_force') if self.metric_combo.currentIndex()==0 else ('max_displacement','rms_displacement')
        any_metric=False
        for key,color in zip(names,('#be3f45','#257db5')):
            values=[r['metrics'].get(key,(None,None))[0] for r in rows]
            line=self._plot(self.metric_axes,rows,values,key.replace('_',' ').title(),color=color)
            if line is not None:
                any_metric=True
                thresholds=[r['metrics'].get(key,(None,None))[1] for r in rows]
                valid=[(r['frame']+1,v) for r,v in zip(rows,thresholds) if v is not None]
                if valid:self.metric_axes.plot([x for x,_ in valid],[v for _,v in valid],'--',color=color,alpha=.65,label=key+' threshold')
        unit='source units' if self.results is None else (self.results.force_unit if self.metric_combo.currentIndex()==0 else self.results.displacement_unit)
        if rows and not any(r['metrics'] for r in rows):unit='not printed'
        if any_metric and self.results is not None and not self.results.steps:unit='eV/Å (Cartesian forces)'
        self.metric_axes.set_ylabel(('Force / gradient' if self.metric_combo.currentIndex()==0 else 'Displacement')+' ('+unit+')')
        if any_metric:self.metric_axes.legend(fontsize=8)
        else:self.metric_axes.text(.5,.5,'Maximum/RMS values were not printed for these frames',ha='center',transform=self.metric_axes.transAxes)
        for axes in (self.energy_axes,self.metric_axes):
            axes.set_xlabel('Geometry frame');axes.grid(True,alpha=.2)
        self.note.setText('Click a data point to display its geometry frame. Each calculation segment is plotted separately.\n'
            'Values are from the source output; structural edits do not recalculate convergence or orbital properties.')
        self.canvas.draw()

    def pick_point(self,event):
        frames=self.line_frames.get(event.artist)
        if frames is not None and len(event.ind):
            point=int(event.ind[0])
            if 0<=point<len(frames):
                if frames[point] is not None:self.jump(frames[point])
                else:self.note.setText(self.note.text().split('\nNo matched geometry')[0]+'\nNo matched geometry for this energy point.')

    def export_data(self):
        path,_=QFileDialog.getSaveFileName(self,'Export curve data',str(self.document.path.with_name(self.document.path.stem+'_convergence.csv')),'CSV (*.csv)')
        if not path:return
        if self.is_xtb:
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['cycle_or_record','geometry_frame','energy_Eh','energy_eV','energy_kcal_mol','source_line'])
                for r in self._rows:
                    energy=r['energy_ev']
                    writer.writerow([r['x'],None if r['frame'] is None else r['frame']+1,
                        None if energy is None else energy/Hartree,energy,
                        None if energy is None else energy*23.0605478306,r['source_line']])
            return
        keys=('max_force','rms_force','max_displacement','rms_displacement')
        with open(path,'w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['frame','energy_eV',*keys,*[k+'_threshold' for k in keys]])
            for row in self._rows:
                writer.writerow([row['frame']+1,row['energy_ev'],*[row['metrics'].get(k,(None,None))[0] for k in keys],
                                 *[row['metrics'].get(k,(None,None))[1] for k in keys]])
