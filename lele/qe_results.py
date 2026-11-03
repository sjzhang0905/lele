"""QE input and linear PWSCF results; source energies are retained in Ry."""
from dataclasses import dataclass, field
import re
import numpy as np
from ase.io.espresso import units
Bohr,Ry=units['Bohr'],units['Ry']
from .core import Frame
from .calculation_results import CalculationResults, CalculationJob, CalculationStep
from .output_text import read_output_lines, load_progress, check_load_cancelled

NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?'
def number(text):return float(text.replace('D','E').replace('d','e'))
def numbers(text):return [number(s) for s in re.findall(NUMBER,text)]
TAU = re.compile(r'^\s*\d+\s+(\S+).*?tau\(\s*\d+\s*\)\s*=\s*\(([^)]+)\)')
BFGS_CONVERGED = re.compile(r'^\s*bfgs\s+converged\b',re.I)
OPTIMIZATION_FAILED = re.compile(
    r'\bmaximum\s+(?:number\s+of\s+)?steps\s+(?:has\s+been\s+)?reached\b'
    r'|\bbfgs\s+(?:failed|not\s+converged)\b'
    r'|\bconvergence\s+(?:not\s+achieved|has\s+not\s+been\s+achieved)\b'
    r'|\bError\s+in\s+routine\b|\bMaximum\s+CPU\s+time\s+exceeded\b',re.I)


@dataclass
class QeResults(CalculationResults):
    settings: dict = field(default_factory=dict)
    phonon_sets: list = field(default_factory=list)

    @property
    def frequency_records(self):
        return [dict(number=m.number,frequency_cm1=m.frequency_cm1,qpoint=s.qpoint,q_index=i+1)
                for i,s in enumerate(self.phonon_sets) for m in s.modes]

    def frames(self,max_frames=None):
        frames=[];report=load_progress('Quantum ESPRESSO: collecting structure frames',len(self.steps))
        for index,step in enumerate(self.steps):
            if index%256==0:report(index);check_load_cancelled()
            if step.geometry is None:continue
            if max_frames is not None and len(frames)>=max_frames:raise ValueError(f'Trajectory exceeds {max_frames} frames')
            current=step.geometry.clone();current.energy_ev=step.energy_ev
            current.info.update(calculation_index=step.job_index,source_line=step.source_line)
            if step.converged:current.info['optimization_converged']=True
            step.frame_index=len(frames);frames.append(current)
        report(len(self.steps));return frames


def read_qe_input(path):
    from io import StringIO
    from ase.io.espresso import read_espresso_in,read_fortran_namelist
    text='\n'.join(read_output_lines(path))
    settings,cards=read_fortran_namelist(StringIO(text));atoms=read_espresso_in(StringIO(text))
    from collections.abc import Mapping
    def plain(value):
        if isinstance(value,Mapping):return {key:plain(item) for key,item in value.items()}
        if isinstance(value,(tuple,list)):return [plain(item) for item in value]
        return value
    settings=plain(settings)
    system=settings.get('system',{});control=settings.get('control',{})
    info=dict(source_kind='qe_in',qe_settings=dict(settings),qe_input_cards=list(cards),qe_masses_amu=atoms.get_masses().tolist())
    if 'celldm(1)' in system:info['qe_alat_ang']=float(system['celldm(1)'])*Bohr
    elif 'a' in system:info['qe_alat_ang']=float(system['a'])
    if 'tot_charge' in system:info['converter_charge']=float(system['tot_charge'])
    if 'nspin' in system or 'noncolin' in system:info['spin_polarized']=system.get('nspin',1)==2 or bool(system.get('noncolin',False))
    frame=Frame(atoms.get_chemical_symbols(),atoms.positions,atoms.cell.array,tuple(atoms.pbc),info=info)
    result=QeResults('Quantum ESPRESSO',periodic_geometry_seen=True,settings=dict(settings),force_unit='eV/Å')
    job=CalculationJob(0,1,route=str(control.get('calculation','scf')),termination='Input file')
    job.tasks.add('input');result.jobs.append(job);result.steps.append(CalculationStep(0,1,frame))
    return result


def same_geometry(first,second):
    return first.symbols==second.symbols and np.allclose(first.positions,second.positions,atol=1.e-7,rtol=0) and np.allclose(first.cell,second.cell,atol=1.e-7,rtol=0)


def header_geometry(lines,start,stop=None):
    """First bounded Cartesian tau table, including PH's additional mass column."""
    from ase.io.espresso import label_to_symbol
    stop=len(lines) if stop is None else stop
    nat=None;alat=None;scaled=None;i=start
    while i<stop:
        text=lines[i]
        if i>start and re.search(r'Program\s+(?:PWSCF|PHONON)',text):break
        if 'number of atoms/cell' in text:nat=int(text.split('=')[-1])
        if 'lattice parameter (alat)' in text:alat=numbers(text.split('=')[-1])[0]*Bohr
        match=re.search(r'celldm\(1\)\s*=\s*('+NUMBER+')',text)
        if match:alat=number(match[1])*Bohr
        if 'crystal axes:' in text and i+3<stop:
            scaled=np.asarray([numbers(lines[i+k].split('=')[-1])[:3] for k in (1,2,3)])
        if nat and alat and scaled is not None and 'positions (alat units)' in text:
            parsed=[TAU.match(row) for row in lines[i+1:i+1+nat]]
            if len(parsed)!=nat or not all(parsed):raise ValueError('Incomplete QE Cartesian atom table')
            return Frame([label_to_symbol(m[1]) for m in parsed],np.asarray([numbers(m[2])[:3] for m in parsed])*alat,
                         scaled*alat,(True,)*3,info={'qe_alat_ang':alat,'source_kind':'qe_out'}),i+1+nat
        i+=1
    raise ValueError('No complete QE cell and Cartesian atom table')


def read_qe_output(path):
    from ase.io.espresso import get_atomic_positions,get_cell_parameters,label_to_symbol
    lines=read_output_lines(path)
    result=QeResults('Quantum ESPRESSO',periodic_geometry_seen=True,force_unit='eV/Å')
    current=None;cell=None;alat=None;job=None;success=False;i=0;failed_jobs=set()
    report=load_progress('Quantum ESPRESSO: structures, energies and forces',len(lines))
    while i<len(lines):
        if i%256==0:report(i);check_load_cancelled()
        line=lines[i]
        if 'Program PWSCF' in line:
            job=CalculationJob(len(result.jobs),i+1);result.jobs.append(job)
            try:geometry,end=header_geometry(lines,i)
            except ValueError:
                if result.steps:
                    result.note+='Incomplete trailing PWSCF header; earlier records retained.';break
                raise
            current=CalculationStep(job.index,i+1,geometry);result.steps.append(current)
            cell=geometry.cell.copy();alat=geometry.info['qe_alat_ang'];success=False;i=end;continue
        if job is None:i+=1;continue
        if line.strip().upper().startswith('CELL_PARAMETERS'):
            if len(lines)-i<4:
                result.note+='Incomplete trailing QE cell; earlier records retained.';break
            explicit=any(unit in line.lower() for unit in ('angstrom','bohr')) or bool(re.search(r'alat\s*=',line,re.I))
            cell,new_alat=get_cell_parameters(lines[i:i+4],alat=None if explicit else alat)
            if new_alat is not None:alat=new_alat
            if cell is None:raise ValueError('Incomplete QE CELL_PARAMETERS')
            i+=4;continue
        if line.strip().upper().startswith('ATOMIC_POSITIONS'):
            nat=len(current.geometry.symbols)
            if len(lines)-i<nat+1:
                result.note+='Incomplete trailing QE coordinates; earlier records retained.';break
            rows=get_atomic_positions(lines[i:i+nat+1],nat,cell,alat)
            if rows is None or len(rows)!=nat:raise ValueError('Incomplete QE ATOMIC_POSITIONS')
            geometry=Frame([label_to_symbol(r[0]) for r in rows],np.asarray([r[1] for r in rows]),cell.copy(),(True,)*3,
                           info={'qe_alat_ang':alat,'source_kind':'qe_out'})
            success=success and same_geometry(current.geometry,geometry)
            current=CalculationStep(job.index,i+1,geometry,converged=success)
            result.steps.append(current);i+=nat+1;continue
        match=re.match(r'^\s*!\s+total energy\s*=\s*('+NUMBER+r')\s+Ry',line)
        if match:
            if current.energy_ev is not None:
                current=CalculationStep(job.index,i+1,current.geometry.clone(),converged=current.converged)
                result.steps.append(current)
            value=number(match[1]);current.energy_ev=value*Ry;job.energy_ev=current.energy_ev
            current.geometry.info.update(qe_total_energy_ry=value,energy_source='QE ! total energy (Ry)',qe_energy_source_line=i+1)
        if 'Forces acting on atoms' in line:
            data=[];j=i+1
            while j<min(len(lines),i+len(current.geometry.symbols)+10):
                force=re.search(r'force\s*=\s*(.*)',lines[j])
                if force:
                    values=numbers(force[1])
                    if len(values)==3:data.append(values)
                elif data:break
                j+=1
            if len(data)==len(current.geometry.symbols):
                values=np.asarray(data)*Ry/Bohr;maximum=float(np.abs(values).max());rms=float(np.sqrt(np.mean(values**2)))
                current.geometry.info.update(qe_forces_ev_ang=values,cartesian_max_force_ev_ang=maximum,cartesian_rms_force_ev_ang=rms)
                current.convergence.update(max_force=(maximum,None),rms_force=(rms,None))
        # The BFGS end banner and JOB DONE are also printed after failed or
        # exhausted optimizations. Only an explicit success confirms geometry.
        if OPTIMIZATION_FAILED.search(line):
            failed_jobs.add(job.index);success=False;current.converged=False
        elif BFGS_CONVERGED.search(line) and job.index not in failed_jobs:
            success=True;current.converged=True
        if 'JOB DONE.' in line:job.termination='Completed (JOB DONE)'
        if 'number of electrons' in line:
            values=numbers(line.split('=')[-1])
            if values:current.geometry.info['qe_valence_electrons']=values[0]
        i+=1
    if not result.jobs:raise ValueError('No PWSCF calculation header')
    if failed_jobs:
        # A later failure also invalidates earlier final-coordinate reprints in
        # this job. One pass keeps long/concatenated outputs linear in size.
        for step in result.steps:
            if step.job_index in failed_jobs:step.converged=False
    if len(result.steps)>1:
        a,b=result.steps[-2:]
        if b.energy_ev is None and b.job_index==a.job_index and same_geometry(a.geometry,b.geometry):a.converged|=b.converged;result.steps.pop()
    report(len(lines));return result
