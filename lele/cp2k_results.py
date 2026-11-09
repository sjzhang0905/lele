"""Independent CP2K printed results; never open input or trajectory companions."""
from dataclasses import dataclass,field
import re
import numpy as np
from ase.data import atomic_numbers
from ase.units import Hartree,Bohr
from .core import Frame
from .calculation_results import CalculationResults,CalculationStep,CalculationJob,CalculationStage,OrbitalSet,Orbital,NUMBER
from .gaussian_properties import ElectronicSpectrum,Transition,TransitionContribution,DipoleRecord,AU_TO_DEBYE
from .output_text import read_output_lines, check_load_cancelled, load_progress, scan_lines
from .cp2k_input import real

ENERGY=re.compile(r'ENERGY\|\s+Total FORCE_EVAL.*?energy\s*\[([^]]+)\]\s*('+NUMBER+r')',re.I)
RUN_HEADER=re.compile(r'CP2K\|\s*version string',re.I)
COORDINATE_ROW=re.compile(r'^\s*(\d+)\s+\d+\s+([A-Za-z]+)\s+\d+\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')')
ATOM_COUNT=re.compile(r'(?:-\s*Atoms:|Number of atoms:)\s*(\d+)',re.I)
CELL_VECTOR=re.compile(r'CELL\|\s*Vector\s+([abc])\s*\[(angstrom|bohr)\]:\s*(.*)',re.I)
CELL_PERIODICITY=re.compile(r'CELL\|\s*Periodicity\s+(NONE|XYZ|XY|XZ|YZ|X|Y|Z)\s*$',re.I)
OPT_STEP=re.compile(r'OPTIMIZATION STEP:\s*(\d+)')
MD_STEP=re.compile(r'MD\|\s*Step number\s+(\d+)')
SCF_CONVERGED=re.compile(r'SCF run converged in\s+(\d+)\s+steps')
OPT_RECORD=re.compile(r'\s*OPT\|\s*Step number\s+(\d+)')
TD_ROW=re.compile(r'\s*TDDFPT\|\s*(\d+)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s*$')
TD_KPOINT=re.compile(r'\s*TDDFPT_KPOINT\|\s*(\d+)\s+(.*)')
METRIC=re.compile(r'^\s*OPT\|\s*(Convergence limit for\s+)?(Maximum gradient|Max\. gradient|RMS gradient|Maximum step size|Max\. step size|RMS step size)\s+('+NUMBER+r')\s*$',re.I)
RECORD_PREFIXES=('GLOBAL|','DFT|','FUNCTIONAL|','CELL|','MO|','ENERGY|','OPT|','MD|',
    'TDDFPT|','TDDFPT_KPOINT|','MODULE QUICKSTEP:','OPTIMIZATION STEP:',
    'SCF WAVEFUNCTION','SCF RUN','***','PROGRAM ENDED AT','GEOMETRY OPTIMIZATION COMPLETED',
    'TRANSITION DIPOLES','STATE','EXCITATION ANALYSIS','DIPOLE MOMENT',
    '- ATOMS:','NUMBER OF','ONLY KERNEL','KERNEL|')


@dataclass
class Cp2kStep(CalculationStep):
    info: dict=field(default_factory=dict)


@dataclass
class Cp2kResults(CalculationResults):
    spectra: list=field(default_factory=list)
    dipoles: list=field(default_factory=list)
    metadata: dict=field(default_factory=dict)

    def frames(self,max_frames=None):
        frames=[]
        for _,step in scan_lines(self.steps,'CP2K: collecting structure frames'):
            check_load_cancelled()
            step.frame_index=None
            if step.geometry is None:continue
            if max_frames is not None and len(frames)>=max_frames:raise ValueError(f'Trajectory exceeds {max_frames} frames')
            frame=step.geometry.clone();frame.energy_ev=step.energy_ev
            frame.info.update(step.info,source_line=step.source_line,
                              calculation_index=step.job_index,stage_index=step.stage_index)
            frame.info.setdefault('source_kind','cp2k_out')
            if step.converged:frame.info['optimization_converged']=True
            step.frame_index=len(frames);frames.append(frame)
        for orbitals in self.orbitals:
            if orbitals.step_index is not None:orbitals.frame_index=self.steps[orbitals.step_index].frame_index
        return frames


def energy_factor(unit):
    unit=unit.strip().lower()
    if unit in ('hartree','a.u.','au'):return Hartree
    if unit=='ev':return 1.
    raise ValueError('Unsupported printed CP2K energy unit: '+unit)


def coordinate_table(lines,start,cell,pbc,info,natoms):
    from .trajectory_io import numeric_array
    bohr='BOHR' in lines[start].upper();rows=[];symbols=[];j=start+1
    while j<len(lines) and (j<start+6 or rows):
        if (j-start)%1024==0:check_load_cancelled()
        match=COORDINATE_ROW.match(lines[j])
        if match:
            if int(match[1])!=len(rows)+1 or match[2] not in atomic_numbers:break
            symbols.append(match[2]);rows.append([match[k] for k in (3,4,5)])
        elif rows:break
        j+=1
    if not rows or (natoms and len(rows)!=natoms):return None,max(start+1,j)
    data={**info,'cp2k_coordinate_source_line':start+1}
    return Frame(symbols,numeric_array(rows)*(Bohr if bohr else 1.),cell.copy(),pbc,info=data),j


def _segment(lines,offset,results):
    ji=len(results.jobs);si=len(results.stages)
    job=CalculationJob(ji,offset+1,tasks=set());results.jobs.append(job)
    stage=CalculationStage(si,ji,'Printed CP2K records','single_point',offset+1,offset+len(lines))
    results.stages.append(stage)
    run='';info={};cell=np.zeros((3,3));pbc=(False,)*3;vectors={};natoms=0
    current=None;current_used=False;last=None;cycle=0;mo={};mo_line=0;channel='';spectrum=None
    form='unspecified';magnitudes=False;multiplicity='';analysis_transition=None;in_analysis=False
    scf_converged=None;pending_spectra=[]
    progress=load_progress('CP2K: geometry, energies and properties',len(lines))
    def flush_orbitals(step_index=None):
        nonlocal mo,mo_line
        if not mo:return
        results.orbitals.append(OrbitalSet(ji,mo_line,dict(mo),step_index=step_index,
            numbering='1-based CP2K orbital numbers. Channels keep k points and spins separate; only the last printed table per SCF evaluation is retained'))
        mo={};mo_line=0
    i=0;next_checkpoint=0
    while i<len(lines):
        # Keep progress/cancellation bounded without a ContextVar and clock
        # lookup for every SCF diagnostic line in a long molecular dynamics run.
        if i>=next_checkpoint:
            check_load_cancelled();progress(i);next_checkpoint=i+512
        line=lines[i];source=offset+i+1;upper=line.upper()
        # SCF iteration rows, integration-grid diagnostics and other numeric
        # tables dominate long stdout files. They contain no records read here.
        if (not in_analysis and not upper.lstrip().startswith(RECORD_PREFIXES)
                and 'NUMBER OF ATOMS:' not in upper and 'TRANSITION DIPOLE' not in upper
                and 'STATES OF MULTIPLICITY' not in upper):
            i+=1;continue
        if 'GLOBAL|' in line and 'Run type' in line:
            run=line.split('Run type',1)[1].strip().upper();info['cp2k_run_type']=run;job.tasks.add(run)
            stage.kind='optimization' if run in ('GEO_OPT','CELL_OPT') else 'md' if run=='MD' else 'single_point'
            stage.name={'optimization':'Geometry / cell optimization','md':'Molecular dynamics'}.get(stage.kind,'Single point / properties')
        if 'GLOBAL|' in line and 'Project name' in line:
            info['cp2k_project']=line.split('Project name',1)[1].strip()
        if 'DFT|' in line:
            for label,key in (('Charge','converter_charge'),('Multiplicity','converter_mult')):
                m=re.search(r'\b'+label+r'\s+([-+]?\d+)\s*$',line)
                if m:info[key]=int(m[1]);setattr(job,'charge' if label=='Charge' else 'multiplicity',int(m[1]))
            if 'Kohn-Sham' in line:info['cp2k_spin']=line.rsplit(None,1)[-1]
        if 'FUNCTIONAL|' in line:
            m=re.match(r'\s*FUNCTIONAL\|\s+([A-Za-z][\w-]+):',line)
            if m and m[1] not in job.method.split(' / '):job.method=' / '.join(filter(None,(job.method,m[1])))
        atom_count=ATOM_COUNT.search(line) if 'ATOMS:' in upper else None
        if atom_count and 'Atomic kind:' not in line:natoms=int(atom_count[1])
        v=CELL_VECTOR.search(line) if 'CELL|' in upper else None
        if v:
            numbers=re.findall(NUMBER,v[3]);vector=np.asarray([real(x) for x in numbers[:3]])
            norm=re.search(r'\|[abc]\|\s*=\s*('+NUMBER+r')',v[3],re.I)
            if norm is not None and np.linalg.norm(vector)>0:vector*=real(norm[1])/np.linalg.norm(vector)
            vectors[v[1].lower()]=vector*(Bohr if v[2].lower()=='bohr' else 1.)
            if all(key in vectors for key in 'abc'):cell=np.asarray([vectors[key] for key in 'abc'])
        periodic=CELL_PERIODICITY.search(line) if 'CELL|' in upper else None
        if periodic:pbc=tuple(a in periodic[1].upper() for a in 'XYZ')
        if 'ATOMIC COORDINATES IN ' in upper:
            current,end=coordinate_table(lines,i,cell,pbc,info,natoms)
            current_used=False
            if current is None:results.note+=' Incomplete coordinate table retained as unavailable.'
            i=end;continue
        opt=OPT_STEP.search(line) if 'OPTIMIZATION STEP:' in line else None
        if opt:
            cycle=int(opt[1]);current=None;last=None;scf_converged=None
        md=MD_STEP.search(line) if 'MD|' in line else None
        if md and int(md[1])!=cycle:cycle=int(md[1]);current=None;last=None
        if 'SCF WAVEFUNCTION OPTIMIZATION' in line:
            flush_orbitals();scf_converged=None
        converged=SCF_CONVERGED.search(line) if 'SCF run converged in' in line else None
        if converged:job.scf_cycles=int(converged[1]);scf_converged=True
        if 'SCF run NOT converged' in line:
            scf_converged=False;results.note+=f' SCF not converged (printed at line {source}).'
        if line.lstrip().startswith('MO|') and 'EIGENVALUES AND OCCUPATION NUMBERS' in line:
            k=re.search(r'K POINT\s+(\d+)',line);spin=re.search(r'SPIN\s+(\d+)',line)
            channel=('k '+k[1] if k else 'Γ')+(' / spin '+spin[1] if spin else '')
            rows=[];j=i+1
            while j<len(lines) and j<=i+5 and not re.match(r'\s*MO\|\s*\d+\s+',lines[j]):j+=1
            while j<len(lines):
                row=re.match(r'\s*MO\|\s*(\d+)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s*$',lines[j])
                if row is None:break
                rows.append(Orbital(int(row[1]),real(row[4]),real(row[3])));j+=1
            if rows:mo[channel]=rows;mo_line=source
            i=max(i+1,j);continue
        e=ENERGY.search(line) if 'ENERGY|' in upper else None
        if e:
            value=real(e[2])*energy_factor(e[1]);data={'cp2k_energy_hartree':value/Hartree,'energy_source':'CP2K FORCE_EVAL',
                'cp2k_scf_converged':scf_converged}
            last=Cp2kStep(ji,source,None if current is None else current.clone(),value,stage_index=si,cycle=cycle,info=data)
            results.steps.append(last);job.energy_ev=value
            if last.geometry is not None:last.geometry.info.update(data)
            current_used=current is not None
            flush_orbitals(len(results.steps)-1)
            # Only spectra awaiting their next printed energy need updating.
            # Revisiting all earlier spectra at every ionic step was quadratic.
            for s in pending_spectra:s.reference.energy_ev=value
            pending_spectra.clear()
            if stage.kind in ('optimization','md'):current=None
        record=OPT_RECORD.match(line) if 'OPT|' in line else None
        if record is not None and last is not None:last.cycle=int(record[1])
        metric=METRIC.match(line) if 'OPT|' in upper else None
        if metric is not None:
            if last is None:
                last=Cp2kStep(ji,source,None if current is None else current.clone(),stage_index=si,cycle=cycle)
                results.steps.append(last);current_used=current is not None
            name=metric[2].lower();key=('rms_' if name.startswith('rms') else 'max_')+('force' if 'gradient' in name else 'displacement')
            pair=list(last.convergence.get(key,(None,None)));pair[1 if metric[1] else 0]=real(metric[3]);last.convergence[key]=tuple(pair)
        if 'GEOMETRY OPTIMIZATION COMPLETED' in upper:
            stage.status='Completed (printed)'
            if last is not None and len(last.convergence)==4 and all(v is not None and t is not None and v<=t for v,t in last.convergence.values()):
                stage.status='Converged (printed criteria)';last.converged=True
        if 'PROGRAM ENDED AT' in upper:job.termination='Normal completion (printed)'
        # A final TD table is distinct from Davidson iterations and initial guesses.
        if 'Transition dipoles calculated using' in line:
            match=re.search(r'using\s+(\S+)',line,re.I);form=match[1].lower() if match else 'unspecified';magnitudes=False
        if 'transition dipole magnitudes are shown' in line.lower():magnitudes=True;form='component magnitudes'
        mult=re.search(r'states of multiplicity\s+(\d+)',line) if 'states of multiplicity' in line else None
        if mult:multiplicity=mult[1]
        if 'State' in line and 'Excitation' in line and 'Transition dipole' in line:
            spectrum=ElectronicSpectrum(None if current is None else current.clone(),source_line=source,
                label='CP2K '+('independent-particle / KERNEL NONE' if magnitudes else 'TDDFPT')+' · '+form)
            results.spectra.append(spectrum);job.tasks.add('TDDFPT');in_analysis=False
            if spectrum.reference is not None and spectrum.reference.energy_ev is None:
                pending_spectra.append(spectrum)
        td=TD_ROW.match(line) if 'TDDFPT|' in line else None
        if td and spectrum is not None:
            number=int(td[1]);energy=real(td[2]);vector=np.asarray([real(td[k]) for k in (3,4,5)]);strength=real(td[6])
            if energy>0 and strength>=0:
                t=Transition(number,'Multiplicity '+multiplicity if multiplicity else 'Printed transition',energy,1239.841984332/energy,strength,
                    source_line=source,source_label='CP2K '+form,metadata={'dipole_form':form})
                if magnitudes:t.metadata['component_magnitudes_au']=vector.tolist()
                elif form=='velocity':t.velocity_dipole_au=vector;t.oscillator_strength_velocity=strength
                elif form=='length':t.electric_dipole_au=vector;t.oscillator_strength_length=strength
                else:t.metadata['printed_components_au']=vector.tolist()
                spectrum.transitions.append(t)
        kp=TD_KPOINT.match(line) if 'TDDFPT_KPOINT|' in line else None
        if kp and spectrum is not None:
            t=next((t for t in reversed(spectrum.transitions) if t.number==int(kp[1])),None)
            values=kp[2].split()
            if t is not None:
                t.metadata['kpoint_source_fields']=values
                t.source_label+=' · TDDFPT_KPOINT '+kp[2].strip()
        if 'Excitation analysis' in line:in_analysis=True;analysis_transition=None
        if in_analysis and spectrum is not None:
            state=re.match(r'\s*(\d+)\s+('+NUMBER+r')\s+eV\s*$',line)
            if state:analysis_transition=next((t for t in spectrum.transitions if t.number==int(state[1])),None)
            contribution=re.match(r'\s*(\d+)\s+(\d+)\s+('+NUMBER+r')\s*$',line)
            if contribution and analysis_transition is not None:
                analysis_transition.contributions.append(TransitionContribution(int(contribution[1]),int(contribution[2]),real(contribution[3])))
        if 'Dipole moment [Debye]' in line and i+1<len(lines):
            values=re.findall(NUMBER,lines[i+1])
            if len(values)>=3:
                vector=np.asarray([real(x) for x in values[:3]])
                results.dipoles.append(DipoleRecord(None if current is None else current.clone(),vector,float(np.linalg.norm(vector)),source,'CP2K'))
        i+=1
    flush_orbitals()
    progress(len(lines))
    if current is not None and not current_used:
        results.steps.append(Cp2kStep(ji,offset+1,current,stage_index=si,cycle=cycle))
    if not job.tasks:job.tasks.add('Printed results')
    job.route='; '.join(f'{key}={value}' for key,value in info.items() if key.startswith('cp2k_'))
    results.spectra[:]=[s for s in results.spectra if s.transitions]


def read_cp2k_output(path):
    lines=read_output_lines(path);results=Cp2kResults('CP2K',force_unit='Hartree/bohr (printed gradients)',displacement_unit='bohr')
    boundaries=[i for i,line in scan_lines(lines,'CP2K: identifying runs')
                if 'CP2K|' in line.upper() and RUN_HEADER.search(line)]
    starts=[0]+boundaries[1:]
    for start,end in zip(starts,starts[1:]+[len(lines)]):
        # Avoid a second file-sized pointer array for the common single run.
        _segment(lines if start==0 and end==len(lines) else lines[start:end],start,results)
    results.note=('CP2K files are read independently; no companion file supplies missing structures, cells or results. '
        'Only printed coordinates are linked to energy records. XYZ trajectory energies are Hartree; internal energies are eV. '
        'Output cells and coordinates retain their printed precision. '+results.note).strip()
    return results


def read_cp2k_xyz(path,max_frames=None):
    from .trajectory_io import xyz_blocks,IncompleteXYZ
    results=Cp2kResults('CP2K');results.jobs.append(CalculationJob(0,1,tasks={'Structure trajectory'}))
    results.stages.append(CalculationStage(0,0,'CP2K XYZ trajectory','trajectory',1))
    step_pattern=re.compile(r'\bi\s*=\s*(\d+)')
    energy_pattern=re.compile(r'\bE\s*=\s*('+NUMBER+r')')
    time_pattern=re.compile(r'\btime\s*=\s*('+NUMBER+r')',re.I)
    try:
        for source,comment,symbols,positions in xyz_blocks(path):
            if max_frames is not None and len(results.steps)>=max_frames:
                raise ValueError(f'Trajectory exceeds {max_frames} frames')
            step=step_pattern.search(comment);energy=energy_pattern.search(comment);time=time_pattern.search(comment)
            value=real(energy[1])*Hartree if energy else None
            info={'source_kind':'cp2k_xyz','cp2k_xyz_comment':comment,'source_line':source}
            if value is not None:info.update(cp2k_energy_hartree=real(energy[1]),energy_source='CP2K XYZ E (Hartree)')
            if time is not None:info['time_fs']=real(time[1])
            frame=Frame(symbols,positions,energy_ev=value,info=info)
            results.steps.append(Cp2kStep(0,source,frame,value,stage_index=0,cycle=int(step[1]) if step else len(results.steps)+1,info=info))
            if value is not None:results.jobs[0].energy_ev=value
    except IncompleteXYZ:
        results.note+=' Incomplete trailing XYZ frame omitted.'
    results.note=('CP2K XYZ coordinates are Angstrom and E is Hartree. No cell or periodicity is inferred from neighbouring files. '+results.note).strip()
    return results
