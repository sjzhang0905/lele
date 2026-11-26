"""Energy and maximum/RMS geometry convergence, linked to loaded frames."""
import csv
import numpy as np
from .operations import gui_operation,ui_checkpoint,ui_operation,run_data_task
from .output_text import progress_items
from ase.units import Hartree
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QPushButton
from .dialog_policy import QDialog, QFileDialog


MD_SERIES = {
    'cp2k_md_temperature_K': 'Temperature (K)',
    'cp2k_md_kinetic_hartree': 'Kinetic energy (Eh)',
    'cp2k_md_conserved_hartree': 'Conserved quantity (Eh)',
}


class ConvergenceDialog(QDialog):
    def __init__(self,document,jump,parent=None):
        super().__init__(parent);self.document=document;self.jump=jump
        self.results=document.calculation_results
        self.is_xtb=self.results is not None and self.results.program=='xTB'
        self.is_vasp=self.results is not None and self.results.program=='VASP'
        self.is_cp2k=self.results is not None and self.results.program=='CP2K'
        self.has_orca_scan=bool(getattr(self.results,'scans',[]))
        self.cp2k_trials = set()
        self._cp2k_frame_axis = False
        if self.is_cp2k and any(s.kind == 'optimization' for s in self.results.stages):
            from .cp2k_results import optimization_trial_indices
            self.cp2k_trials = optimization_trial_indices(self.results.steps)
        self.line_frames={}
        self.setWindowTitle('Energy / geometry convergence — '+document.path.name);self.resize(950,820)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from .figure_export import FigureExportToolbar as NavigationToolbar2QT
        layout=QVBoxLayout(self);controls=QHBoxLayout();layout.addLayout(controls)
        self.job=QComboBox()
        jobs=[] if self.results is None else self.results.jobs
        for job in jobs:self.job.addItem(f'Job {job.index+1} · '+(' / '.join(sorted(job.tasks)) or 'Results'),job.index)
        if not jobs:self.job.addItem('Loaded geometry frames',None)
        self.stage_combo=QComboBox()
        self._prepare_stages()
        self.all_cp2k_evaluations = QCheckBox('Show all energy evaluations')
        self.metric_combo=QComboBox();self._prepare_metrics()
        self.unit=QComboBox();self.unit.addItems(['eV','Hartree','kcal/mol'])
        if self.is_xtb:self.unit.setCurrentText('kcal/mol')
        self.scan_only=QCheckBox('Converged scan points only')
        self.scan_only.setVisible(not (self.is_xtb or self.is_cp2k or self.has_orca_scan))
        self.scan_only.setChecked(bool(not self.has_orca_scan and jobs and 'Scan' in jobs[0].tasks
            and any(step.job_index==jobs[0].index and step.converged for step in self.results.steps)))
        for widget in (self.job,self.stage_combo,self.metric_combo,self.unit,self.scan_only,
                       self.all_cp2k_evaluations):controls.addWidget(widget)
        self.note=QLabel('Click a plotted point to display its geometry frame.');self.note.setWordWrap(True);layout.addWidget(self.note)
        self.figure=Figure(figsize=(8,6),tight_layout=True)
        self.canvas=FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename=lambda:str(document.path.with_name(document.path.stem+'_convergence.png'))
        layout.addWidget(NavigationToolbar2QT(self.canvas,self));layout.addWidget(self.canvas,1)
        self.export_button=QPushButton('Export curve data CSV…');self.export_button.clicked.connect(self.export_data);layout.addWidget(self.export_button)
        self.canvas.mpl_connect('pick_event',self.pick_point)
        self.job.currentIndexChanged.connect(self._job_changed)
        self.stage_combo.currentIndexChanged.connect(self._stage_changed)
        for widget in (self.metric_combo,self.unit):widget.currentIndexChanged.connect(self.redraw)
        self.scan_only.toggled.connect(self.redraw)
        self.all_cp2k_evaluations.toggled.connect(self.redraw)
        self.redraw()

    def _prepare_stages(self):
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.stage_combo):
            self.stage_combo.clear()
            stages=[] if self.results is None else [s for s in self.results.stages if s.job_index==self.job.currentData() and any(p.stage_index==s.index and (p.frame_index is not None or self.is_xtb or self.is_vasp or self.is_cp2k) for p in self.results.steps)]
            for stage in stages:self.stage_combo.addItem(stage.name+' · '+stage.status,stage.index)
            if not stages:self.stage_combo.addItem('Loaded geometry steps',None)
            self.stage_combo.setVisible(bool(stages))

    def _job_changed(self):
        self._prepare_stages();self._stage_changed()

    def _stage_changed(self, *_):
        self._prepare_metrics()
        self.redraw()

    def _prepare_metrics(self):
        from PySide6.QtCore import QSignalBlocker
        with QSignalBlocker(self.metric_combo):
            self.metric_combo.clear()
            stage = self.stage_combo.currentData()
            cp2k_stage = next((s for s in self.results.stages if s.index == stage), None) if self.is_cp2k else None
            self.is_md = cp2k_stage is not None and cp2k_stage.kind == 'md'
            self.is_cp2k_optimization = cp2k_stage is not None and cp2k_stage.kind == 'optimization'
            self.all_cp2k_evaluations.setVisible(any(self.results.steps[i].stage_index == stage for i in self.cp2k_trials))
            if self.is_xtb:
                here = [s for s in self.results.steps if s.stage_index == stage]
                if self.document.trajectory_link:
                    if any(s.geometry is not None and 'xtb_trajectory_gnorm' in s.geometry.info for s in here):
                        self.metric_combo.addItem('Trajectory gradient norm (Eh/bohr)', 'gnorm')
                    if any(s.optimizer_gradient_norm is not None for s in here):
                        self.metric_combo.addItem('Optimizer gradient norm (Eh/α)', 'optimizer_norm')
                self.metric_combo.setVisible(self.metric_combo.count() > 1)
                return
            if self.is_md:
                here = [s for s in self.results.steps if s.stage_index == stage]
                for key, label in MD_SERIES.items():
                    if any(key in s.info for s in here):
                        self.metric_combo.addItem(label, key)
            self.metric_combo.addItem('Maximum / RMS force', 'force')
            if not self.is_md:
                self.metric_combo.addItem('Maximum / RMS displacement', 'displacement')

    def points(self):
        index=self.job.currentData()
        if self.is_vasp or self.is_cp2k:
            self.scan_only.setEnabled(False)
            stage=self.stage_combo.currentData()
            from .vasp_results import ENERGY_KEY
            steps = [(i,s) for i,s in enumerate(self.results.steps)
                     if s.job_index==index and (stage is None or s.stage_index==stage)]
            if self.cp2k_trials and not self.all_cp2k_evaluations.isChecked():
                steps = [(i,s) for i,s in steps if i not in self.cp2k_trials]
            self._cp2k_frame_axis = bool(self.is_cp2k_optimization and self.document.trajectory_link
                                        and steps and all(s.frame_index is not None for _,s in steps))
            rows = []
            for i, s in steps:
                step = s.info.get('cp2k_reevaluation_output_step', s.cycle)
                if step is None:
                    step = i + 1
                rows.append(dict(frame=s.frame_index, energy_ev=s.info.get(ENERGY_KEY) if self.is_vasp else s.energy_ev,
                                 metrics=s.convergence, x=s.frame_index+1 if self._cp2k_frame_axis else step,
                                 step=step, extra=s.info, source_line=None if s.info.get('trajectory_only') else s.source_line,
                                 trajectory_line=s.geometry.info.get('trajectory_source_line') if s.geometry else None))
            return rows
        if self.is_xtb:
            self.scan_only.setEnabled(False)
            stage=self.stage_combo.currentData()
            return [dict(frame=s.frame_index,energy_ev=s.energy_ev,metrics={},x=s.cycle or i+1,source_line=s.source_line,
                         gnorm=s.geometry.info.get('xtb_trajectory_gnorm') if s.geometry else None,
                         optimizer_norm=s.optimizer_gradient_norm)
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
            if self.has_orca_scan and step.cycle is not None:row['x']=step.cycle
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

    def _plot(self,axes,rows,values,label,*,gaps=False,**kwargs):
        valid=[(row.get('x',row['frame']+1 if row['frame'] is not None else 0),row['frame'],value)
               for row,value in zip(rows,values) if value is not None and np.isfinite(value)]
        if not valid:return None
        if gaps:
            valid=[(row.get('x',row['frame']+1 if row['frame'] is not None else 0),row['frame'],
                    np.nan if value is None else value) for row,value in zip(rows,values)]
        line,=axes.plot([x for x,_,_ in valid],[v for _,_,v in valid],'.-',label=label,picker=7,**kwargs)
        self.line_frames[line]=[i for _,i,_ in valid]
        return line

    @gui_operation('Preparing convergence curves')
    def redraw(self,*_):
        self.figure.clear();self.line_frames={}
        rows=self.points();self._rows=rows
        xtb_norm = self.is_xtb and self.metric_combo.currentData() in ('gnorm', 'optimizer_norm')
        one_plot = self.is_xtb and not xtb_norm
        self.energy_axes=self.figure.add_subplot(111 if one_plot else 211)
        self.metric_axes=None if one_plot else self.figure.add_subplot(212)
        factor={'eV':1.,'Hartree':1./Hartree,'kcal/mol':23.0605478306}[self.unit.currentText()]
        energies=[r['energy_ev'] for r in rows if r['energy_ev'] is not None]
        baseline=min(energies) if energies else 0.
        self._plot(self.energy_axes,rows,[None if r['energy_ev'] is None else (r['energy_ev']-baseline)*factor for r in rows],
                   'E0' if self.is_vasp else 'Energy',gaps=self.is_vasp or self.is_cp2k)
        self.energy_axes.set_ylabel(('Relative E0' if self.is_vasp else 'Relative energy')+' ('+self.unit.currentText()+')')
        if not energies:self.energy_axes.text(.5,.5,'No printed E0 for this segment' if self.is_vasp else 'No printed energies for this segment',ha='center',transform=self.energy_axes.transAxes)
        if self.is_xtb:
            trajectory='Optimization trajectory' in self.results.jobs[self.job.currentData()].tasks
            self.energy_axes.set_xlabel('Trajectory record' if trajectory else 'Optimization cycle')
            self.energy_axes.grid(True,alpha=.2)
            if xtb_norm:
                self._plot(self.metric_axes, rows, [r[self.metric_combo.currentData()] for r in rows], 'Gradient norm', gaps=True)
                self.metric_axes.set_ylabel(self.metric_combo.currentText())
                self.metric_axes.set_xlabel('Optimization cycle')
                self.metric_axes.grid(True, alpha=.2)
            matched=sum(r['frame'] is not None for r in rows)
            self.note.setText(f'{len(rows)} energy records · {matched} with geometry. Relative energies use the minimum shown. '
                'Click a point with matched coordinates to display that structure.\n'+self.document.note)
            self.canvas.draw();return
        metric = self.metric_combo.currentData()
        if metric in MD_SERIES:
            self._plot(self.metric_axes, rows, [r['extra'].get(metric) for r in rows], MD_SERIES[metric], gaps=True)
            self.metric_axes.set_ylabel(MD_SERIES[metric])
            for axes in (self.energy_axes, self.metric_axes):
                axes.set_xlabel('MD step')
                axes.grid(True, alpha=.2)
            self.note.setText(f'{len(rows)} MD records · {sum(r["frame"] is not None for r in rows)} with coordinates. '
                              'Click a point to display its matched trajectory frame.')
            self.canvas.draw()
            return
        names=('max_force','rms_force') if metric=='force' else ('max_displacement','rms_displacement')
        any_metric=False
        for key,color in zip(names,('#be3f45','#257db5')):
            values=[r['metrics'].get(key,(None,None))[0] for r in rows]
            line=self._plot(self.metric_axes,rows,values,key.replace('_',' ').title(),color=color,gaps=self.is_cp2k)
            if line is not None:
                any_metric=True
                thresholds=[r['metrics'].get(key,(None,None))[1] for r in rows]
                valid=[(r.get('x',r['frame']+1 if r['frame'] is not None else 0),v) for r,v in zip(rows,thresholds) if v is not None]
                if valid:self.metric_axes.plot([x for x,_ in valid],[v for _,v in valid],'--',color=color,alpha=.65,label=key+' threshold')
        unit='source units' if self.results is None else (self.results.force_unit if metric=='force' else self.results.displacement_unit)
        if self.is_md:unit='Eh/bohr, per-atom force magnitude'
        if rows and not any(r['metrics'] for r in rows):unit='not printed'
        if any_metric and self.results is not None and not self.results.steps:unit='eV/Å (Cartesian forces)'
        self.metric_axes.set_ylabel(('Force / gradient' if metric=='force' else 'Displacement')+' ('+unit+')')
        if any_metric:self.metric_axes.legend(fontsize=8)
        else:self.metric_axes.text(.5,.5,'Maximum/RMS values were not printed for these frames',ha='center',transform=self.metric_axes.transAxes)
        x_label = ('Trajectory frame' if self._cp2k_frame_axis else 'MD step' if self.is_md else
                   'Ionic record' if self.is_vasp else 'CP2K record / printed step' if self.is_cp2k else
                   'Optimization cycle' if self.has_orca_scan else 'Geometry frame')
        for axes in (self.energy_axes,self.metric_axes):
            axes.set_xlabel(x_label);axes.grid(True,alpha=.2)
        self.note.setText('Click a data point to display its geometry frame. Each calculation segment is plotted separately.\n'
            'Values are from the source output; structural edits do not recalculate convergence or orbital properties.')
        if self.is_vasp:
            self.note.setText(f'{len(rows)} ionic records · {sum(r["frame"] is not None for r in rows)} with geometry. '
                'E0 (σ→0) only; relative energies use the minimum shown. Missing E0 values are gaps. '
                'Points without geometry do not change the 3D view.\n'+self.document.note)
        elif self.has_orca_scan:
            self.note.setText('Optimization history for the selected scan step. Use Scan curve… for the energy profile across scan points.\n'
                'Click a point to display its geometry. Energies and convergence are from the source output.')
        elif self.is_cp2k:
            self.note.setText(f'{len(rows)} printed records · {sum(r["frame"] is not None for r in rows)} with coordinates. '
                'Click a point with coordinates to display its structure. Relative energy uses the minimum shown.\n'+self.document.note)
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
        run_data_task(self,'Exporting convergence data',lambda:self._write_csv(path))

    def _write_csv(self,path):
        if self.is_cp2k:
            keys=('max_force','rms_force','max_displacement','rms_displacement')
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['step_or_record','geometry_frame','energy_Eh','energy_eV',
                    *keys,*[k+'_threshold' for k in keys],'force_unit','displacement_unit','source_line','trajectory_line',
                    *(['time_fs', *MD_SERIES] if self.is_md else [])])
                for row in progress_items(self._rows,'Writing convergence CSV'):
                    value=row['energy_ev']
                    writer.writerow([row['step'],None if row['frame'] is None else row['frame']+1,
                        None if value is None else value/Hartree,value,*[row['metrics'].get(k,(None,None))[0] for k in keys],
                        *[row['metrics'].get(k,(None,None))[1] for k in keys],('Eh/bohr (atomic force magnitudes)' if self.is_md else self.results.force_unit),self.results.displacement_unit,row['source_line'],row['trajectory_line'],
                        *([row['extra'].get(k) for k in ('time_fs', *MD_SERIES)] if self.is_md else [])])
            return
        if self.is_vasp:
            keys=('max_force','rms_force')
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream)
                writer.writerow(['ionic_record','geometry_frame','energy_E0_eV',
                    *[key+'_eV_A' for key in keys],'source_line'])
                for row in progress_items(self._rows,'Writing convergence CSV'):
                    writer.writerow([row['x'],None if row['frame'] is None else row['frame']+1,row['energy_ev'],
                        *[row['metrics'].get(key,(None,None))[0] for key in keys],row['source_line']])
            return
        if self.is_xtb:
            with open(path,'w',encoding='utf-8-sig',newline='') as stream:
                writer=csv.writer(stream);writer.writerow(['cycle_or_record','geometry_frame','energy_Eh','energy_eV','energy_kcal_mol','source_line','trajectory_gnorm_Eh_bohr','optimizer_gnorm_Eh_per_alpha'])
                for r in progress_items(self._rows,'Writing convergence CSV'):
                    energy=r['energy_ev']
                    writer.writerow([r['x'],None if r['frame'] is None else r['frame']+1,
                        None if energy is None else energy/Hartree,energy,
                        None if energy is None else energy*23.0605478306,r['source_line'],r['gnorm'],r['optimizer_norm']])
            return
        keys=('max_force','rms_force','max_displacement','rms_displacement')
        with open(path,'w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['frame','energy_eV',*keys,*[k+'_threshold' for k in keys]])
            for row in progress_items(self._rows,'Writing convergence CSV'):
                writer.writerow([row['frame']+1,row['energy_ev'],*[row['metrics'].get(k,(None,None))[0] for k in keys],
                                 *[row['metrics'].get(k,(None,None))[1] for k in keys]])
