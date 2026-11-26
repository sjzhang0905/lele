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

ENERGY=re.compile(r'ENERGY\|\s+Total FORCE_EVAL.*?energy\s*(?:\[|\()([A-Za-z.]+)(?:\]|\))\s*:?\s*('+NUMBER+r')',re.I)
RUN_HEADER=re.compile(r'CP2K\|\s*version string',re.I)
COORDINATE_ROW=re.compile(r'^\s*(\d+)\s+\d+\s+([A-Za-z]+)\s+\d+\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')')
ATOM_COUNT=re.compile(r'(?:-\s*Atoms:|Number of atoms:)\s*(\d+)',re.I)
CELL_VECTOR=re.compile(r'CELL\|\s*Vector\s+([abc])\s*\[(angstrom|bohr)\]:\s*(.*)',re.I)
CELL_PERIODICITY=re.compile(r'CELL\|\s*Periodicity\s+(NONE|XYZ|XY|XZ|YZ|X|Y|Z)\s*$',re.I)
OPT_STEP=re.compile(r'OPTIMIZATION STEP:\s*(\d+)')
MD_STEP=re.compile(r'MD\|\s*Step number\s+(\d+)')
MD_STEP_BANNER=re.compile(r'MD STEP:\s*(\d+)\s*/\s*(\d+)')
SCF_CONVERGED=re.compile(r'SCF run converged in\s+(\d+)\s+steps')
LBFGS_CONVERGED=re.compile(r'\s*\*+\s*SATISFIED\s+\.+\s*RUN CONVERGED!\s*\**\s*')
OPT_RECORD=re.compile(r'\s*(?:OPT\|\s*Step number\s+|(?:-+\s*)?Informations? at step\s*=\s*)(\d+)', re.I)
TD_ROW=re.compile(r'\s*TDDFPT\|\s*(\d+)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s*$')
TD_KPOINT=re.compile(r'\s*TDDFPT_KPOINT\|\s*(\d+)\s+(.*)')
METRIC=re.compile(r'^\s*(?:OPT\|\s*)?(Convergence limit for\s+)?(Maximum gradient|Max\. gradient|RMS gradient|Maximum step size|Max\. step size|RMS step size)\s*(?:=|:)?\s*('+NUMBER+r')\s*$',re.I)
RECORD_PREFIXES=('GLOBAL|','DFT|','FUNCTIONAL|','CELL|','MO|','ENERGY|','OPT|','MD|',
    'TDDFPT|','TDDFPT_KPOINT|','CP2K|','QS|','DFT+U|','MD_PAR|','MD_INI|','THERMOSTAT|','SCF PARAMETERS',
    'EPS_SCF','MAX_SCF','OUTER LOOP SCF','OUTER SCF LOOP CONVERGED','ORBITAL BASIS SET','AUXILIARY BASIS SET',
    'GTH POTENTIAL INFORMATION','POTENTIAL INFORMATION','U(EFF)','ANGULAR QUANTUM MOMENTUM',
    'SPIN ','INTEGRATED SPIN DENSITY:','IDEAL AND SINGLE DETERMINANT S**2','MODULE QUICKSTEP:','OPTIMIZATION STEP:','MD STEP:',
    'SCF WAVEFUNCTION','SCF RUN','***','* SATISFIED','PROGRAM ENDED AT','GEOMETRY OPTIMIZATION COMPLETED',
    'INFORMATION AT STEP','INFORMATIONS AT STEP','MAX. GRADIENT','MAXIMUM GRADIENT','RMS GRADIENT',
    'INITIAL POTENTIAL ENERGY','INITIAL KINETIC ENERGY','INITIAL TEMPERATURE','STEP NUMBER','TIME [FS]',
    'TEMPERATURE [K]','TEMPERATURE[K]','POTENTIAL ENERGY','KINETIC ENERGY','CONSERVED QUANTITY',
    'MAX. STEP SIZE','MAXIMUM STEP SIZE','RMS STEP SIZE','CONVERGENCE LIMIT FOR','CONV. LIMIT FOR','TOTAL ENERGY ','ATOMIC FORCES IN','FORCES|','REEVALUATING ENERGY AT THE MINIMUM',
    'TRANSITION DIPOLES','STATE','EXCITATION ANALYSIS','DIPOLE MOMENT',
    '- ATOMS:','NUMBER OF','ONLY KERNEL','KERNEL|')


# Pre-2024 motion summaries use unprefixed KEY = value records.
_LEGACY_MD = re.compile(r'^\s*(INITIAL\s+)?(STEP NUMBER|TIME\s*\[fs\]|TEMPERATURE\s*\[K\]|'
                        r'(?:POTENTIAL ENERGY|KINETIC ENERGY|CONSERVED QUANTITY)\s*\[hartree\])\s*=\s*(.*)$',re.I)
_MD_LABELS = {'STEPNUMBER':'Step number','TIME[FS]':'Time [fs]','TEMPERATURE[K]':'Temperature [K]',
              'POTENTIALENERGY[HARTREE]':'Potential energy [hartree]','KINETICENERGY[HARTREE]':'Kinetic energy [hartree]',
              'CONSERVEDQUANTITY[HARTREE]':'Conserved quantity [hartree]'}


@dataclass
class Cp2kStep(CalculationStep):
    info: dict=field(default_factory=dict)


@dataclass
class Cp2kResults(CalculationResults):
    spectra: list=field(default_factory=list)
    dipoles: list=field(default_factory=list)
    metadata: dict=field(default_factory=dict)

    def frames(self,max_frames=None,*,store=None):
        frames=[]
        for _,step in scan_lines(self.steps,'CP2K: collecting structure frames'):
            check_load_cancelled()
            step.frame_index=None
            if step.geometry is None:continue
            if max_frames is not None and len(frames)>=max_frames:raise ValueError(f'Trajectory exceeds {max_frames} frames')
            frame=step.geometry.clone() if store is None else store.editable_frame(step.geometry)
            frame.energy_ev=step.energy_ev
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


def _md_force_table(lines, start, natoms):
    """Maximum and RMS of the per-atom Cartesian force magnitudes, in Eh/bohr."""
    header=lines[start].upper()
    if '[A.U.]' in header or '[HARTREE/BOHR]' in header:
        factor=1.
    elif '[EV/ANGSTROM]' in header:
        factor=Bohr/Hartree
    else:
        return None, start+1
    modern=header.lstrip().startswith('FORCES|')
    squares=[]
    for j in range(start+1,len(lines)):
        if (j-start)%1024==0:check_load_cancelled()
        text=lines[j].strip()
        if modern:text=text.removeprefix('FORCES|').strip()
        if text.upper().startswith('SUM'):
            if not squares or (natoms and len(squares)!=natoms):
                break
            return {'max_force':(float(np.sqrt(max(squares))), None),
                    'rms_force':(float(np.sqrt(np.mean(squares))), None)}, j+1
        fields=text.split()
        if not fields or fields[0] in ('#','Atom'):
            continue
        if not fields[0].isdigit() or int(fields[0])!=len(squares)+1:
            break
        xyz=fields[1:4] if modern else fields[3:6]
        if len(xyz)!=3:break
        try:squares.append(sum((real(x)*factor)**2 for x in xyz))
        except ValueError:break
    return None, start+1


def optimization_trial_indices(steps):
    """Find extra evaluations superseded by a printed optimizer summary."""
    summarized = {(s.job_index, s.stage_index, s.cycle) for s in steps
                  if s.info.get('cp2k_opt_summary') and s.energy_ev is not None}
    if not summarized:
        return set()
    return {i for i, s in enumerate(steps)
            if s.frame_index is None and s.energy_ev is not None
            and (s.job_index, s.stage_index, s.cycle) in summarized
            and not s.info.get('cp2k_opt_summary') and not s.info.get('cp2k_final_reevaluation')}


def summary_lines(results, job_index):
    """Human-readable, per-run CP2K records, including LOW-print-level runs."""
    metadata=getattr(results,'metadata',{}).get('jobs',{}).get(str(job_index),{})
    lines=[]
    for label,value in metadata.items():
        if label=='Atomic kinds':
            lines.append('Atomic kinds (printed basis / potential):')
            for kind in value:
                name=kind.get('Kind','?')
                fields=[f'{key}: {item}' for key,item in kind.items() if key!='Kind']
                lines.append('  '+name+' — '+ '; '.join(fields))
        elif label=='Spin electrons':
            lines.append('Last printed electrons by spin: '+', '.join(f'{key} = {item}' for key,item in value.items()))
        else:lines.append(f'{label}: '+(f'{value:.12g}' if isinstance(value,float) else str(value)))
    steps=[s for s in results.steps if s.job_index==job_index]
    if steps:
        energy_steps=[s for s in steps if s.energy_ev is not None and not s.info.get('trajectory_only')]
        lines.append(f'Printed energy evaluations: {len(energy_steps)}')
        state=next((s for s in reversed(steps) if getattr(s,'info',{}).get('cp2k_md_step') is not None),None)
        if state is not None:
            info=state.info
            lines.append(f'Last printed MD step: {info["cp2k_md_step"]}')
            statistics=next((s for s in reversed(steps) if 'time_fs' in getattr(s,'info',{})
                             and 'cp2k_md_step' in s.info),None)
            if statistics is not None and statistics is not state:
                lines.append(f'Last MD statistics are from step {statistics.info["cp2k_md_step"]} (not the final energy evaluation).')
                info=statistics.info
            for key,label in (('time_fs','Last printed MD time (fs)'),
                              ('cp2k_md_temperature_K','Last MD temperature (K)'),
                              ('cp2k_md_kinetic_hartree','Last MD kinetic energy (Hartree)'),
                              ('cp2k_md_conserved_hartree','Last MD conserved quantity (Hartree)')):
                if key in info:lines.append(f'{label}: {info[key]:.12g}')
        if energy_steps:
            last=energy_steps[-1]
            status=getattr(last,'info',{}).get('cp2k_scf_converged')
            if status is not None:lines.append('Last SCF convergence: '+('converged (printed)' if status else 'not converged (printed)'))
    return lines


_SUMMARY_GROUPS={
        'GLOBAL|': (('Project name','Project'),('Run type','Run type'),
                    ('Basis set file name','Basis file'),('Potential file name','Potential file'),
                    ('Global print level','Print level'),
                    ('Total number of message passing processes','MPI processes'),
                    ('Number of threads for this process','Threads per process')),
        'QS|': (('Method:','Quickstep method'),('Number of grid levels:','Grid levels'),
                ('Density cutoff [a.u.]:','Density cutoff (Hartree)'),
                ('Relative density cutoff [a.u.]:','Relative density cutoff (Hartree)')),
        'DFT+U|': (('Method','DFT+U method'),),
        'MD_PAR|': (('Ensemble type','MD ensemble'),('Number of time steps','MD requested steps'),
                   ('Time step [fs]','MD time step (fs)'),('Temperature [K]','MD target temperature (K)'),
                   ('Temperature tolerance [K]','MD temperature tolerance (K)')),
        'THERMOSTAT|': (('Type of thermostat','Thermostat'),('CSVR time constant [fs]','Thermostat time constant (fs)')),
        'OPT|': (('Optimization method','Optimizer'),),
    }


def _summary_record(line, job, metadata, state):
    """Read only explicit parameter records; never infer from names/references."""
    stripped=line.strip()
    if stripped.startswith('CP2K| version string'):
        metadata['Version']=stripped.split(':',1)[-1].strip();return
    prefix,sep,body=stripped.partition('|')
    for source,label in _SUMMARY_GROUPS.get(prefix+'|',()):
        if body.strip().startswith(source):
            value=body.strip()[len(source):].strip()
            if value:metadata[label]=value
            break
    if prefix+'|' in _SUMMARY_GROUPS:return
    if stripped.startswith('DFT|') and 'Kohn-Sham' in stripped:
        metadata['Spin treatment']=stripped.rsplit(None,1)[-1]
    kind=(re.match(r'\d+\.\s+Atomic kind:\s+(\S+)\s+Number of atoms:\s*(\d+)',stripped)
          if 'Atomic kind:' in stripped else None)
    if kind:
        item={'Kind':kind[1],'Atoms':int(kind[2])}
        metadata.setdefault('Atomic kinds',[]).append(item);state['kind']=item
    item=state.get('kind')
    if item is not None:
        for source,label in (('Orbital Basis Set','Basis'),('Auxiliary Basis Set','Auxiliary basis'),
                             ('GTH Potential information for','Potential'),('Potential information for','Potential'),
                             ('Angular quantum momentum number L:','DFT+U L'),
                             ('U(eff) = (U - J) value in [eV]:','Ueff (eV)')):
            if stripped.startswith(source):
                item[label]=stripped[len(source):].strip();break
    if stripped.startswith('SCF PARAMETERS'):
        state['scf_parameters']=True;state['outer_scf']=False
        guess=re.search(r'Density guess:\s*(\S+)',stripped)
        if guess:metadata['Requested SCF density guess']=guess[1]
    if state.get('scf_parameters'):
        if stripped.startswith('Outer loop SCF'):state['outer_scf']=True
        match=re.match(r'(eps_scf|max_scf)(?::|\s)\s*('+NUMBER+r')\s*$',stripped)
        if match:
            label=('Outer SCF ' if state.get('outer_scf') else 'SCF ')+match[1]
            metadata[label]=match[2]
        if stripped.startswith(('SCF WAVEFUNCTION','MD_PAR|','MODULE QUICKSTEP:')):
            state['scf_parameters']=False
    spin=re.fullmatch(r'Spin\s+(\d+)',stripped) if stripped.startswith('Spin ') else None
    if spin:state['spin']=spin[1]
    electrons=(re.fullmatch(r'Number of electrons:\s*('+NUMBER+r')',stripped)
               if stripped.startswith('Number of electrons:') else None)
    if electrons:
        if state.get('spin'):
            metadata.setdefault('Spin electrons',{})[state['spin']]=real(electrons[1])
        else:metadata['Last printed electrons']=real(electrons[1])
    if stripped.startswith('Integrated spin density:'):
        values=re.findall(NUMBER,stripped.split(':',1)[1])
        if values:metadata['Last integrated spin density']=real(values[0])
    if stripped.startswith('Ideal and single determinant S**2'):
        values=re.findall(NUMBER,stripped.split(':',1)[1])
        if len(values)>=2:
            metadata['Ideal S²']=real(values[0]);job.spin_squared=real(values[1])
            metadata['Last single-determinant S²']=job.spin_squared
    count=ATOM_COUNT.search(line) if 'Atoms:' in line or 'atoms:' in line else None
    if count and 'Atomic kind:' not in line:metadata['Atoms']=int(count[1])


def _segment(lines,offset,results):
    ji=len(results.jobs);si=len(results.stages)
    job=CalculationJob(ji,offset+1,tasks=set());results.jobs.append(job)
    stage=CalculationStage(si,ji,'Printed CP2K records','single_point',offset+1,offset+len(lines))
    results.stages.append(stage)
    run='';info={};metadata={};summary_state={};md_target=None
    results.metadata.setdefault('jobs',{})[str(ji)]=metadata
    cell=np.zeros((3,3));pbc=(False,)*3;vectors={};natoms=0
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
    cell_record = None
    cell_fresh = False
    reevaluation = False
    opt_numbered = False
    pending_md = None
    pending_forces = None
    awaiting_scf_energy = False
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
                and 'STATES OF MULTIPLICITY' not in upper and 'INFORMATIONS AT STEP' not in upper):
            i+=1;continue
        if stage.kind=='md' and '=' in line and '|' not in line:
            old=_LEGACY_MD.match(line)
            if old:
                key=_MD_LABELS[''.join(old[2].upper().split())]
                line=('MD_INI| ' if old[1] else 'MD| ')+key+' '+old[3]
                upper=line.upper()
        if not run and stage.kind=='single_point':
            if 'OPTIMIZATION STEP:' in upper or OPT_RECORD.match(line):
                stage.kind='optimization';stage.name='Geometry optimization';job.tasks.add('GEO_OPT')
            elif MD_STEP_BANNER.search(line) or MD_STEP.search(line):
                stage.kind='md';stage.name='Molecular dynamics';job.tasks.add('MD')
        if upper.lstrip().startswith('MD| ENSEMBLE TYPE'):
            metadata['MD ensemble']=line.rsplit(None,1)[-1].strip().upper()
        if (upper.lstrip().startswith(('CP2K|','GLOBAL|','QS|','DFT|','DFT+U|','MD_PAR|','THERMOSTAT|',
                'OPT|','SCF PARAMETERS','SCF WAVEFUNCTION','EPS_SCF','MAX_SCF','OUTER LOOP SCF',
                'ORBITAL BASIS SET','AUXILIARY BASIS SET','GTH POTENTIAL INFORMATION','POTENTIAL INFORMATION',
                'U(EFF)','ANGULAR QUANTUM MOMENTUM','SPIN ','NUMBER OF ELECTRONS','- ATOMS:',
                'INTEGRATED SPIN DENSITY:','IDEAL AND SINGLE DETERMINANT S**2'))
                or 'ATOMIC KIND:' in upper or 'NUMBER OF ATOMS:' in upper):
            _summary_record(line,job,metadata,summary_state)
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
            if all(key in vectors for key in 'abc'):
                cell=np.asarray([vectors[key] for key in 'abc'])
                cell_record=cell.tolist();cell_fresh=True;vectors.clear()
        periodic=CELL_PERIODICITY.search(line) if 'CELL|' in upper else None
        if periodic:
            pbc=tuple(a in periodic[1].upper() for a in 'XYZ')
            info['cp2k_periodicity']=pbc
        if 'ATOMIC COORDINATES IN ' in upper:
            current,end=coordinate_table(lines,i,cell,pbc,info,natoms)
            current_used=False
            if current is None:results.note+=' Incomplete coordinate table retained as unavailable.'
            i=end;continue
        opt=OPT_STEP.search(line) if 'OPTIMIZATION STEP:' in line else None
        if 'REEVALUATING ENERGY AT THE MINIMUM' in upper:
            reevaluation=True
        if opt:
            opt_numbered=True
            cycle=int(opt[1]);current=None;last=None;scf_converged=None
        md_banner=MD_STEP_BANNER.search(line) if 'MD STEP:' in line else None
        if md_banner:
            pending_md=None;pending_forces=None
            cycle=int(md_banner[1]);current=None;last=None;md_target=None
            summary_state['md_before_energy']=True
            metadata.setdefault('MD requested steps',md_banner[2])
        md=MD_STEP.search(line) if 'MD|' in line else None
        if md:
            cycle=int(md[1]);current=None
            # CP2K normally prints MD step/time AFTER its FORCE_EVAL energy.
            # A stream beginning with MD| before any evaluation instead uses
            # pre-energy records; retain that ordering for its subsequent steps.
            position=summary_state.setdefault('md_record_position','before' if last is None else 'after')
            if last is not None and position=='after':
                last.cycle=cycle;last.info['cp2k_md_step']=cycle;last.info.pop('cp2k_unnumbered',None)
                md_target=last;summary_state['md_after_energy']=True
            else:
                pending_md=Cp2kStep(ji,source,stage_index=si,cycle=cycle,info={'cp2k_md_step':cycle})
                results.steps.append(pending_md)
                last=md_target=pending_md
                summary_state['md_before_energy']=True
        md_initial = line.lstrip().startswith('MD_INI|')
        if md_initial and last is None and 'Potential energy [hartree]' in line:
            last=Cp2kStep(ji,source,stage_index=si,cycle=cycle)
            results.steps.append(last)
        if md_initial and last is not None:last.info['cp2k_md_initial']=True
        md_info = (last.info if md_initial and last is not None else
                   md_target.info if md_target is not None else None)
        if md_info is not None and (md_initial or line.lstrip().startswith('MD|')):
            body=line.split('|',1)[1].strip()
            for label,key in (('Time [fs]','time_fs'),('Temperature [K]','cp2k_md_temperature_K'),
                              ('Potential energy [hartree]','cp2k_md_potential_hartree'),
                              ('Kinetic energy [hartree]','cp2k_md_kinetic_hartree'),
                              ('Conserved quantity [hartree]','cp2k_md_conserved_hartree')):
                if body.startswith(label):
                    values=re.findall(NUMBER,body[len(label):])
                    if values:
                        md_info[key]=real(values[0])
                        if key=='cp2k_md_potential_hartree' and last.energy_ev is None:
                            last.energy_ev=md_info[key]*Hartree
                            job.energy_ev=last.energy_ev
                            md_info['energy_source']='CP2K MD potential energy'
                    break
        if 'SCF WAVEFUNCTION OPTIMIZATION' in line:
            flush_orbitals();scf_converged=None;md_target=None;awaiting_scf_energy=True
        converged=SCF_CONVERGED.search(line) if 'SCF run converged in' in line else None
        if converged:job.scf_cycles=int(converged[1]);scf_converged=True
        if 'outer SCF loop converged' in line:
            outer=re.search(r'outer SCF loop converged in\s+(\d+)\s+iterations or\s+(\d+)\s+steps',line)
            if outer:
                metadata['Last outer SCF iterations']=int(outer[1])
                metadata['Last outer SCF total steps']=int(outer[2])
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
            awaiting_scf_energy=False
            value=real(e[2])*energy_factor(e[1]);data={'cp2k_energy_hartree':value/Hartree,'energy_source':'CP2K FORCE_EVAL',
                'cp2k_scf_converged':scf_converged}
            if summary_state.get('md_before_energy'):data['cp2k_md_step']=cycle
            elif (stage.kind=='optimization' and not opt_numbered) or stage.kind=='md':
                data['cp2k_unnumbered']=True
            if 'cp2k_periodicity' in info:data['cp2k_periodicity']=pbc
            fixed_cell = run=='GEO_OPT' or (run=='MD' and metadata.get('MD ensemble','').upper() in ('NVE','NVT','LANGEVIN'))
            if cell_record is not None and (fixed_cell or cell_fresh):
                data['cp2k_output_cell']=cell_record
            cell_fresh=False
            if metadata.get('MD ensemble')=='REFTRAJ' and current is not None and job.energy_ev is None:
                data['cp2k_reftraj_input_geometry']=True
            if reevaluation:
                data['cp2k_final_reevaluation']=True
                if opt_numbered:
                    data['cp2k_reevaluation_output_step']=cycle
                reevaluation=False
            if pending_md is not None:
                last=pending_md;pending_md=None
                last.info.update(data);last.source_line=source
                last.geometry=None if current is None else current.clone()
                last.energy_ev=value
            else:
                last=Cp2kStep(ji,source,None if current is None else current.clone(),value,stage_index=si,
                    cycle=cycle if summary_state.get('md_before_energy') or not summary_state.get('md_after_energy') else None,info=data)
                results.steps.append(last)
            summary_state['md_before_energy']=False
            job.energy_ev=value
            if pending_forces is not None:
                last.convergence.update(pending_forces);pending_forces=None
            if last.geometry is not None:last.geometry.info.update(data)
            current_used=current is not None
            flush_orbitals(len(results.steps)-1)
            # Only spectra awaiting their next printed energy need updating.
            # Revisiting all earlier spectra at every ionic step was quadratic.
            for s in pending_spectra:s.reference.energy_ev=value
            pending_spectra.clear()
            if stage.kind in ('optimization','md'):current=None
        if stage.kind=='md' and ('ATOMIC FORCES IN [' in upper or 'FORCES| ATOMIC FORCES [' in upper):
            forces,end=_md_force_table(lines,i,natoms)
            if forces is not None:
                if last is not None and not awaiting_scf_energy:
                    last.convergence.update(forces)
                else:pending_forces=forces
                i=end;continue
        record=OPT_RECORD.match(line) if 'OPT|' in line or 'AT STEP' in upper else None
        if record is not None:
            if last is None or (last.info.get('cp2k_opt_summary') and last.cycle!=int(record[1])):
                last=Cp2kStep(ji,source,stage_index=si)
                results.steps.append(last)
            last.cycle=int(record[1]);last.info['cp2k_opt_summary']=True;last.info.pop('cp2k_unnumbered',None)
        if last is not None and last.energy_ev is None and stage.kind=='optimization':
            total=re.match(r'\s*OPT\|\s*Total energy\s*\[([^]]+)\]\s*('+NUMBER+r')',line,re.I)
            if total:
                last.energy_ev=real(total[2])*energy_factor(total[1])
                last.info['energy_source']='CP2K optimization summary'
                job.energy_ev=last.energy_ev
        if last is not None and stage.kind=='optimization' and last.info.get('cp2k_opt_summary'):
            # Older CP2K optimizer summaries use unprefixed atomic-unit records.
            legacy=re.match(r'\s*Total Energy\s*=\s*('+NUMBER+r')\s*$',line,re.I)
            if legacy and last.energy_ev is None:
                last.energy_ev=real(legacy[1])*Hartree;job.energy_ev=last.energy_ev
            limit=re.match(r'\s*Conv\. limit for (step size|RMS step|gradients|RMS grad\.)\s*=\s*('+NUMBER+r')',line,re.I)
            if limit:
                key={'step size':'max_displacement','rms step':'rms_displacement',
                     'gradients':'max_force','rms grad.':'rms_force'}[limit[1].lower()]
                last.convergence[key]=(last.convergence.get(key,(None,None))[0],real(limit[2]))
        metric=METRIC.match(line) if stage.kind=='optimization' else None
        if metric is not None:
            if last is None:
                last=Cp2kStep(ji,source,None if current is None else current.clone(),stage_index=si,cycle=cycle)
                results.steps.append(last);current_used=current is not None
            name=metric[2].lower();key=('rms_' if name.startswith('rms') else 'max_')+('force' if 'gradient' in name else 'displacement')
            pair=list(last.convergence.get(key,(None,None)));pair[1 if metric[1] else 0]=real(metric[3]);last.convergence[key]=tuple(pair)
        if stage.kind=='optimization' and 'RUN CONVERGED!' in upper and LBFGS_CONVERGED.fullmatch(upper):
            stage.status='Converged (L-BFGS criteria)'
        if 'GEOMETRY OPTIMIZATION COMPLETED' in upper:
            if last is not None and len(last.convergence)==4 and all(v is not None and t is not None and v<=t for v,t in last.convergence.values()):
                stage.status='Converged (printed criteria)';last.converged=True
            elif stage.status=='Not confirmed':
                stage.status='Completed (printed)'
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
    kinds=metadata.get('Atomic kinds',[])
    bases=[f'{item["Kind"]}: {item["Basis"]}' for item in kinds if item.get('Basis')]
    if bases:job.basis='; '.join(bases)
    if 'DFT+U method' in metadata and job.method:job.method+=' + U ('+metadata['DFT+U method']+')'
    if job.method:metadata['XC method']=job.method
    if stage.kind=='md' and job.termination=='Normal completion (printed)':
        last_md=next((s for s in reversed(results.steps) if s.job_index==ji and s.info.get('cp2k_md_step') is not None),None)
        stage.status='Normal termination (printed); final MD step not confirmed'
        requested=metadata.get('MD requested steps')
        if last_md is not None and requested and str(last_md.info['cp2k_md_step'])==str(requested):
            stage.status='Completed (printed MD steps and normal termination)'
    job.route='; '.join(f'{label}={metadata[label]}' for label in ('Project','Run type','Quickstep method','Spin treatment') if label in metadata)
    results.spectra[:]=[s for s in results.spectra if s.transitions]


def read_cp2k_output(path):
    lines=read_output_lines(path);results=Cp2kResults('CP2K',force_unit='Hartree/bohr (printed gradients)',displacement_unit='bohr')
    boundaries=[i for i,line in scan_lines(lines,'CP2K: identifying runs')
                if 'CP2K|' in line.upper() and RUN_HEADER.search(line)]
    starts=[0]+boundaries[1:]
    for start,end in zip(starts,starts[1:]+[len(lines)]):
        # Avoid a second file-sized pointer array for the common single run.
        _segment(lines if start==0 and end==len(lines) else lines[start:end],start,results)
    results.note=('Output cells and coordinates retain their printed precision. '+results.note).strip()
    return results


def read_cp2k_xyz(path,max_frames=None,*,strict=False,store=None):
    from .trajectory_io import xyz_blocks,IncompleteXYZ,TruncatedXYZ
    results=Cp2kResults('CP2K');results.jobs.append(CalculationJob(0,1,tasks={'Structure trajectory'}))
    results.stages.append(CalculationStage(0,0,'CP2K XYZ trajectory','trajectory',1))
    step_pattern=re.compile(r'\b(?:i|Step)\s*=\s*(\d+)',re.I)
    energy_pattern=re.compile(r'\b(?:E|Energy)\s*=\s*('+NUMBER+r')',re.I)
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
            if step is not None:info['trajectory_step']=int(step[1])
            lattice=re.search(r'\bLattice\s*=\s*"([^"]+)"',comment,re.I)
            cell=np.zeros((3,3));pbc=(False,)*3
            if lattice:
                cell=np.asarray([real(x) for x in lattice[1].split()]).reshape(3,3)
                info['trajectory_cell']=True
                flags=re.search(r'\bpbc\s*=\s*"([^"]+)"',comment,re.I)
                if flags:
                    flags=flags[1].lower().split()
                    if len(flags)!=3 or any(x not in ('t','f','true','false','1','0') for x in flags):
                        raise ValueError(f'Invalid EXTXYZ periodic flags at line {source+1}')
                    pbc=tuple(x in ('t','true','1') for x in flags)
                    info['trajectory_pbc']=True
            frame=Frame(symbols,positions,cell,pbc,energy_ev=value,info=info)
            if store is not None:
                store.append(frame)
            results.steps.append(Cp2kStep(0,source,frame,value,stage_index=0,cycle=int(step[1]) if step else len(results.steps)+1,info=info))
            if value is not None:results.jobs[0].energy_ev=value
    except IncompleteXYZ as error:
        if strict and not isinstance(error,TruncatedXYZ):raise
        results.note+=' Incomplete trailing XYZ frame omitted.'
    results.note=('CP2K XYZ coordinates are Angstrom and E is Hartree. No cell or periodicity is inferred from neighbouring files. '+results.note).strip()
    return results
