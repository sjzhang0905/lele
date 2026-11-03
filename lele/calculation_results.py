"""Printed calculation records, molecular orbitals and geometry convergence.

No quantum calculation is run. Records retain calculation segments, geometry
and source lines so identical coordinates with different charge states are not
silently merged.
"""
from dataclasses import dataclass, field
from pathlib import Path
from .output_text import read_output_lines, check_load_cancelled, load_progress
import re
import numpy as np
from ase.units import Hartree
from ase.data import chemical_symbols
from .core import Frame
from .gaussian_vibrations import _orientation, _ORIENTATION, _CHARGE, _SCF, _number

NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DdEe][-+]?\d+)?'
EIGEN = re.compile(r'\s*(Alpha|Beta)\s+(occ\.|virt\.)\s+eigenvalues\s*--(.*)', re.I)
METRIC = re.compile(rf'^\s*(Maximum Force|RMS Force|Maximum Displacement|RMS Displacement)\s+({NUMBER})\s+({NUMBER})', re.I)
METRIC_KEYS = {'maximum force':'max_force', 'rms force':'rms_force',
               'maximum displacement':'max_displacement', 'rms displacement':'rms_displacement'}


@dataclass
class Orbital:
    number: int
    occupation: float
    energy_ev: float


@dataclass
class OrbitalSet:
    job_index: int
    source_line: int
    channels: dict = field(default_factory=dict)
    step_index: int | None = None
    frame_index: int | None = None
    numbering: str = '1-based Gaussian orbital numbers'
    frontier_numbers: dict = field(default_factory=dict)
    printed_gaps: dict = field(default_factory=dict)
    reported_gap_ev: float | None = None

    def frontier(self, channel):
        rows = self.channels[channel]
        labels = self.frontier_numbers.get(channel)
        if labels:
            homo = next((r for r in rows if r.number==labels.get('homo')),None)
            lumo = next((r for r in rows if r.number==labels.get('lumo')),None)
            gap = self.printed_gaps.get(channel)
            if gap is None and homo is not None and lumo is not None:gap=lumo.energy_ev-homo.energy_ev
            return homo,lumo,gap
        occupied = [row for row in rows if row.occupation > 1.e-6]
        empty = [row for row in rows if row.occupation <= 1.e-6]
        homo = max(occupied, key=lambda row: (row.energy_ev,row.number)) if occupied else None
        lumo = min(empty, key=lambda row: (row.energy_ev,row.number)) if empty else None
        return homo, lumo, None if homo is None or lumo is None else lumo.energy_ev-homo.energy_ev


@dataclass
class CalculationJob:
    index: int
    start_line: int
    route: str = ''
    method: str = ''
    basis: str = ''
    solvent: str = ''
    charge: int | None = None
    multiplicity: int | None = None
    termination: str = 'Incomplete / termination not printed'
    tasks: set = field(default_factory=set)
    energy_ev: float | None = None
    scf_cycles: int | None = None
    spin_squared: float | None = None
    imaginary_modes: int = 0
    frequency_count: int = 0
    wavefunction: str = ''


@dataclass
class CalculationStep:
    job_index: int
    source_line: int
    geometry: Frame | None = None
    energy_ev: float | None = None
    convergence: dict = field(default_factory=dict)
    converged: bool = False
    frame_index: int | None = None
    stage_index: int | None = None
    cycle: int | None = None


@dataclass
class CalculationStage:
    index: int
    job_index: int
    name: str
    kind: str
    start_line: int
    end_line: int | None = None
    status: str = 'Not confirmed'


@dataclass
class HessianEvent:
    source_line: int
    stage_index: int | None
    cycle: int | None
    kind: str
    reference: object = None
    filename: str = ''
    negative_eigenvalues: int | None = None
    end_line: int | None = None


@dataclass
class CalculationResults:
    program: str
    jobs: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    orbitals: list = field(default_factory=list)
    force_unit: str = 'source units'
    displacement_unit: str = 'source units'
    periodic_geometry_seen: bool = False
    stages: list = field(default_factory=list)
    hessians: list = field(default_factory=list)
    note: str = ''

    def frames(self, max_frames=None):
        frames = []
        progress=load_progress('Collecting structure frames',len(self.steps))
        for record,step in enumerate(self.steps):
            check_load_cancelled()
            progress(record)
            if step.geometry is None:
                continue
            current = step.geometry.clone()
            current.energy_ev = step.energy_ev
            current.info.update(calculation_index=step.job_index, source_line=step.source_line)
            if step.stage_index is not None:
                current.info.update(stage_index=step.stage_index, optimization_cycle=step.cycle)
            duplicate = False
            if frames:
                previous = frames[-1]
                duplicate = (previous.symbols == current.symbols
                    and previous.info.get('stage_index') == current.info.get('stage_index')
                    and np.allclose(previous.positions, current.positions, atol=1.e-7, rtol=0)
                    and all(previous.info.get(k)==current.info.get(k) for k in ('converter_charge','converter_mult'))
                    and (current.energy_ev is None or (previous.energy_ev is not None
                         and abs(previous.energy_ev-current.energy_ev)<1.e-7)))
            if not duplicate:
                if max_frames is not None and len(frames)>=max_frames:
                    raise ValueError(f'Trajectory exceeds {max_frames} frames')
                frames.append(current)
            step.frame_index = len(frames)-1
            if step.converged:frames[-1].info['optimization_converged']=True
        for orbitals in self.orbitals:
            if orbitals.step_index is not None:
                orbitals.frame_index = self.steps[orbitals.step_index].frame_index
        progress(len(self.steps))
        return frames


def _route(job, text):
    job.route = text.strip()
    match = re.search(r'\b([A-Za-z][\w+().-]*)/([^\s,]+)', text)
    if match and match[1].lower() not in ('iop', 'scrf'):
        job.method, job.basis = match[1], match[2]
    solvent = re.search(r'solvent\s*=\s*([^,\s)]+)', text, re.I)
    if solvent:job.solvent = solvent[1]
    for token, name in [('opt', 'Optimization'), ('freq', 'Frequency'), ('scan', 'Scan'), ('td', 'Excited states'), ('irc', 'IRC')]:
        if re.search(r'\b'+token+r'\b', text, re.I):job.tasks.add(name)
    if not job.tasks:job.tasks.add('Single point / properties')


def read_gaussian_results(path):
    lines = read_output_lines(path)
    result = CalculationResults('Gaussian', force_unit='Hartree/Bohr', displacement_unit='Bohr')
    job = step = None
    i = 0
    progress=load_progress('Gaussian: geometry, energies and orbitals',len(lines))

    def ensure_job(line):
        nonlocal job
        if job is None:
            job = CalculationJob(len(result.jobs), line+1)
            result.jobs.append(job)
        return job

    while i < len(lines):
        check_load_cancelled()
        progress(i)
        line = lines[i]
        if 'Normal termination of Gaussian' in line or 'Error termination' in line:
            if job is not None:job.termination = 'Normal termination' if 'Normal termination' in line else 'Error termination'
            job = step = None;i += 1;continue
        if '--Link1--' in line or re.search(r'Link1:\s+Proceeding to internal job step', line):
            job = step = None;i += 1;continue
        if line.lstrip().startswith('#'):
            current = ensure_job(i);parts=[line.strip()];j=i+1
            while j<len(lines) and lines[j].strip() and not set(lines[j].strip())=={'-'}:
                if _CHARGE.search(lines[j]) or _ORIENTATION.match(lines[j]):break
                parts.append(lines[j].strip());j+=1
            _route(current,' '.join(parts));i=j;continue
        charge = _CHARGE.search(line)
        if charge:
            current=ensure_job(i);current.charge=int(charge[1]);current.multiplicity=int(charge[2])
        basis=re.search(r'Standard basis:\s+(.+?)(?:\s+\(|$)',line)
        if basis:ensure_job(i).basis=basis[1].strip()
        if _ORIENTATION.match(line):
            current=ensure_job(i)
            info={}
            if current.charge is not None:info['converter_charge']=current.charge
            if current.multiplicity is not None:info['converter_mult']=current.multiplicity
            geometry, end = _orientation(lines,i,info)
            if geometry is not None and -2 in geometry[1]:result.periodic_geometry_seen=True
            if geometry is not None and -2 not in geometry[1]:
                if step is not None and step.energy_ev is None and not step.convergence:
                    step.geometry=geometry[0];step.source_line=i+1
                else:
                    step=CalculationStep(current.index,i+1,geometry[0]);result.steps.append(step)
            i=end;continue
        energy=_SCF.search(line)
        if energy:
            current=ensure_job(i);current.energy_ev=_number(energy[1])*Hartree
            typ=re.search(r'E\(([^)]+)\)',line)
            if typ:
                current.wavefunction=typ[1]
                if not current.method:current.method=typ[1]
            cycles=re.search(r'after\s+(\d+)\s+cycles',line)
            if cycles:current.scf_cycles=int(cycles[1])
            if step is not None:step.energy_ev=current.energy_ev
        post=re.search(rf'(?:EUMP2|E\(CORR\)|CCSD\(T\)|Total Energy, E\(TD[^)]*\))\s*=\s*({NUMBER})',line,re.I)
        if post:
            current=ensure_job(i);current.energy_ev=_number(post[1])*Hartree
            if step is not None:step.energy_ev=current.energy_ev
        metric=METRIC.match(line)
        if metric and step is not None:
            step.convergence[METRIC_KEYS[metric[1].lower()]]=(_number(metric[2]),_number(metric[3]))
        if 'Optimization completed' in line and step is not None:
            step.converged=True
        if re.search(r'potential surface scan|scan point|scan step',line,re.I):ensure_job(i).tasks.add('Scan')
        frequencies=re.match(r'\s*Frequencies\s+--\s+(.+)',line)
        if frequencies:
            values=[_number(v) for v in frequencies[1].split()]
            current=ensure_job(i);current.frequency_count+=len(values);current.imaginary_modes+=sum(v<0 for v in values)
        spin=re.search(rf'(?:S\*\*2 before annihilation\s+|<S\*\*2>\s*=\s*)({NUMBER})',line)
        if spin:ensure_job(i).spin_squared=_number(spin[1])
        if EIGEN.match(line):
            current=ensure_job(i)
            snapshot=OrbitalSet(current.index,i+1,step_index=len(result.steps)-1 if step is not None else None)
            j=i
            while j<len(lines):
                match=EIGEN.match(lines[j])
                if match is None:break
                channel=match[1].title();rows=snapshot.channels.setdefault(channel,[])
                occupation=1. if match[2].lower()=='occ.' else 0.
                for value in re.findall(NUMBER,match[3]):rows.append(Orbital(len(rows)+1,occupation,_number(value)*Hartree))
                j+=1
            if 'Beta' not in snapshot.channels and ((current.wavefunction.startswith('R') and not current.wavefunction.startswith('RO'))
                    or (current.multiplicity==1 and not current.wavefunction.startswith('U'))):
                rows=snapshot.channels.pop('Alpha',[])
                for row in rows:row.occupation*=2
                snapshot.channels['Restricted']=rows
            result.orbitals.append(snapshot);i=j;continue
        i+=1
    progress(len(lines))
    return result


def read_orca_results(path):
    from .orca_results import read_orca_results as reader
    return reader(path)


def read_calculation_results(path, kind):
    if kind == 'vasp_out':
        from .vasp_results import read_vasp_results
        return read_vasp_results(path)
    if kind == 'vasp_oszicar':
        from .vasp_results import read_oszicar
        return read_oszicar(path)
    if kind=='gaussian_out':return read_gaussian_results(path)
    if kind=='orca_out':return read_orca_results(path)
    if kind in ('xtb_out','xtb_trj'):
        from .xtb_results import read_xtb_results
        return read_xtb_results(path,trajectory=kind=='xtb_trj')
    return CalculationResults(kind)
