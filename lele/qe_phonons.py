"""QE PH stdout frequencies and complex matdyn normalized displacements.

Mode-only files are results-only until an explicit reference is supplied.
Cartesian q values are in 2*pi/alat; never assume they are reciprocal fractions.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from math import pi
import re
import numpy as np
from .core import NormalMode,VibrationalAnalysis,Document
from .qe_results import NUMBER,numbers,number,QeResults,header_geometry
from .calculation_results import CalculationJob,CalculationStep
from .output_text import read_output_lines,load_progress,check_load_cancelled

QPOINT=re.compile(r'^\s*q\s*=\s*\(?\s*('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')',re.I)
FREQUENCY=re.compile(r'^\s*(?:freq|omega)\s*\(\s*(\d+)\s*\)\s*=\s*('+NUMBER+r')\s*\[THz\]\s*=\s*('+NUMBER+r')\s*\[cm-1\]',re.I)


@dataclass
class PhononMode(NormalMode):
    imaginary_displacements: np.ndarray | None = None
    qpoint: tuple = (0.,0.,0.)
    q_fractional: tuple | None = None

    def __post_init__(self):
        super().__post_init__()
        self.qpoint=tuple(float(x) for x in self.qpoint)
        if len(self.qpoint)!=3 or not np.isfinite(self.qpoint).all():raise ValueError('Invalid phonon q point')
        if self.q_fractional is not None:
            self.q_fractional=tuple(float(x) for x in self.q_fractional)
            if len(self.q_fractional)!=3 or not np.isfinite(self.q_fractional).all():raise ValueError('Invalid fractional q point')
        if self.imaginary_displacements is not None:
            self.imaginary_displacements=np.asarray(self.imaginary_displacements,float).reshape(-1,3).copy()
            if self.displacements is None or self.imaginary_displacements.shape!=self.displacements.shape or not np.isfinite(self.imaginary_displacements).all():
                raise ValueError('Invalid complex QE displacement table')

    def peak(self):
        if self.displacements is None:return 0.
        a=self.displacements;b=self.imaginary_displacements
        if b is None:b=np.zeros_like(a)
        aa=np.sum(a*a,axis=1);bb=np.sum(b*b,axis=1);ab=np.sum(a*b,axis=1)
        return float(np.sqrt(np.max((aa+bb)/2+np.sqrt(((aa-bb)/2)**2+ab**2)))) if len(a) else 0.

    @property
    def can_animate(self):
        return self.peak()>0 and (self.q_fractional is not None or np.linalg.norm(self.qpoint)<1.e-10)

    def positions_at(self,reference,phase,amplitude):
        if not self.can_animate:return reference.positions.copy()
        imaginary=self.imaginary_displacements
        imaginary=np.zeros_like(self.displacements) if imaginary is None else imaginary
        # Re[u exp(i(q.R - phase + pi/2))]; real Gamma modes retain sin(phase).
        return reference.positions+(self.displacements*np.sin(phase)-imaginary*np.cos(phase))*(amplitude/self.peak())

    def arrow_vectors(self):
        if self.displacements is None:return None
        vector=self.displacements.astype(complex)
        if self.imaginary_displacements is not None:vector+=1j*self.imaginary_displacements
        pivot=vector.ravel()[np.argmax(np.abs(vector))]
        return (vector*np.exp(-1j*np.angle(pivot))).real

    def preview_frame(self,reference,phase,amplitude,cutoff=1.):
        from .core import freeze_bonds
        frame=reference.clone();freeze_bonds(frame,cutoff)
        frame.positions=self.positions_at(reference,phase,amplitude)
        if self.can_animate:
            vector=self.displacements+1j*(np.zeros_like(self.displacements) if self.imaginary_displacements is None else self.imaginary_displacements)
            gauge=-float(np.angle(vector.ravel()[np.argmax(np.abs(vector))]))
            frame.info['_qe_phonon_preview']=dict(reference_positions=reference.positions.copy(),arrow_phase=gauge,
                real=self.displacements,imaginary=(np.zeros_like(self.displacements) if self.imaginary_displacements is None else self.imaginary_displacements),
                q_fractional=np.asarray(self.q_fractional or (0.,0.,0.)),phase=float(phase),scale=float(amplitude/self.peak()))
        return frame


@dataclass
class QePhononSet:
    qpoint: tuple
    source_line: int
    modes: list = field(default_factory=list)
    atom_count: int | None = None

    @property
    def label(self):return 'q = ('+', '.join(f'{v:g}' for v in self.qpoint)+') · 2π/alat'


def read_phonon_sets(path,atom_count=None):
    lines=read_output_lines(path);sets=[];pending=None;block=None;i=0;notices=[]
    report=load_progress('QE phonons: q points, frequencies and complex displacements',len(lines))
    while i<len(lines):
        if i%128==0:report(i);check_load_cancelled()
        q=QPOINT.match(lines[i])
        if q:pending=tuple(number(v) for v in q.groups());block=None
        freq=FREQUENCY.match(lines[i])
        if freq and pending is not None:
            if block is None:
                block=QePhononSet(pending,i+1,atom_count=atom_count);sets.append(block)
            j=i+1;vectors=[]
            while j<len(lines) and lines[j].strip().startswith('('):
                values=numbers(lines[j])
                if len(values)!=6:break
                vectors.append(values);j+=1
            real=imaginary=None
            if vectors:
                if block.atom_count is None or len(vectors)==block.atom_count:
                    data=np.asarray(vectors);real=data[:,::2];imaginary=data[:,1::2]
                else:notices.append(f'Incomplete vectors at line {i+1}; frequency retained without animation.')
            block.modes.append(PhononMode(int(freq[1]),number(freq[3]),real,
                ir_intensity_unit='',imaginary_displacements=imaginary,qpoint=pending))
            i=j;continue
        i+=1
    if not sets:raise ValueError('No QE q-point frequency blocks found')
    for block in sets:
        if block.atom_count is None:
            sizes=[len(m.displacements) for m in block.modes if m.displacements is not None]
            block.atom_count=(len(block.modes)//3 if len(block.modes)%3==0 else max(sizes)) if sizes else None
            for mode in block.modes:
                if mode.displacements is not None and len(mode.displacements)!=block.atom_count:
                    mode.displacements=mode.imaginary_displacements=None
                    notices.append(f'Incomplete vectors for mode {mode.number}; frequency retained.')
    report(len(lines));return sets,'\n'.join(notices)


def read_qe_phonons(path,stdout=False):
    result=QeResults('Quantum ESPRESSO',periodic_geometry_seen=True,displacement_unit='dimensionless normalized Cartesian displacements')
    reference=None
    if stdout:
        lines=read_output_lines(path)
        start=next((i for i,line in enumerate(lines) if 'Program PHONON' in line),0)
        try:reference,_=header_geometry(lines,start)
        except ValueError:reference=None
        if reference is not None:
            reference.info['source_kind']='qe_phonon'
            result.steps.append(CalculationStep(0,reference.info.get('source_line',1),reference))
    result.phonon_sets,note=read_phonon_sets(path,len(reference.symbols) if reference is not None else None)
    count=sum(len(s.modes) for s in result.phonon_sets)
    result.jobs=[CalculationJob(0,1,route='PHONON stdout' if stdout else 'matdyn normalized displacements',
        frequency_count=count,imaginary_modes=sum(m.imaginary for s in result.phonon_sets for m in s.modes))]
    if stdout and any('JOB DONE.' in line for line in lines):result.jobs[0].termination='Completed (JOB DONE)'
    elif not stdout:result.jobs[0].termination='Mode data file (no run-status record)'
    result.note=note
    if reference is None:
        result.note+='\nNo element labels, structure or cell in this mode file. Use Analysis → Assign QE phonon reference to associate a known atom order and alat.'
        return Document(path,'QE PHONON output' if stdout else 'QE matdyn modes',[],calculation_results=result,note=result.note.strip())
    result.note+='\nPHONON frequencies are retained per q point. Missing displacement vectors are not inferred.'
    document=Document(path,'QE PHONON output',result.frames(),calculation_results=result,note=result.note.strip())
    document.vibrations=make_analyses(result.phonon_sets,reference,reference.info['qe_alat_ang'])
    return document


def make_analyses(sets,reference,alat_ang):
    if not len(reference.symbols) or abs(np.linalg.det(reference.cell))<1.e-10:raise ValueError('QE phonons require a reference structure with a cell')
    if any(np.linalg.norm(s.qpoint)>1.e-10 for s in sets) and (alat_ang is None or not np.isfinite(alat_ang) or alat_ang<=0):
        raise ValueError('Enter the positive alat (Å) used to write these Cartesian q points')
    result=[]
    for index,source in enumerate(sets):
        if source.atom_count is not None and source.atom_count!=len(reference.symbols):raise ValueError('QE mode atom count differs from the selected reference')
        modes=deepcopy(source.modes)
        for mode in modes:mode.q_fractional=tuple(np.asarray(source.qpoint)@reference.cell.T/alat_ang) if alat_ang else (0.,0.,0.)
        result.append(VibrationalAnalysis(reference.clone(),modes,source_line=source.source_line,
            purpose=f'q {index+1}: {source.label}',note='Printed normalized complex displacements; visual amplitude only. No additional mass weighting.'))
    return result


def bind_qe_phonons(document,reference,alat_ang,reference_name='selected structure'):
    source=document.calculation_results
    if not isinstance(source,QeResults) or not source.phonon_sets:raise ValueError('This file has no QE phonon data')
    analyses=make_analyses(source.phonon_sets,reference,alat_ang)
    results=deepcopy(source)
    note=(f'Explicit reference: {reference_name}; atom order supplied by the user. '
          f'Cartesian q scale alat = {alat_ang:g} Å. Frequencies and vectors remain from {document.path.name}.')
    return Document(document.path,'QE phonons (reference assigned)',[reference.clone()],
                    vibrations=analyses,calculation_results=results,note=note)


def phonon_offsets(state,shifts):
    """Bloch displacement of each supplied source-atom lattice translation."""
    theta=state['phase']-2*pi*(np.asarray(shifts)@np.asarray(state['q_fractional']))
    return (state['real']*np.sin(theta)[...,None]-state['imaginary']*np.cos(theta)[...,None])*state['scale']
