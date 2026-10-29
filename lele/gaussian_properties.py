"""Printed Gaussian permanent and transition moments, grouped by TD block."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import numpy as np
from ase.units import Hartree, Bohr, Debye
from .gaussian_vibrations import _orientation, _ORIENTATION, _CHARGE, _SCF, _job_boundary, _number

N=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[DEde][-+]?\d+)?'
DIPOLE=re.compile(rf'X=\s*({N})\s+Y=\s*({N})\s+Z=\s*({N})\s+Tot=\s*({N})')
EXCITED=re.compile(rf'Excited State\s+(\d+):\s*(.*?)\s+({N})\s+eV\s+({N})\s+nm\s+f\s*=\s*({N})')
AU_TO_DEBYE=Bohr/Debye


def transition_state_label(state):
    """Hide Gaussian's unknown-symmetry placeholder in user-facing lists."""
    return re.sub(r'-\s*\?Sym\s*$', '', state.strip(), flags=re.I).strip() or 'Unknown'

@dataclass
class DipoleRecord:
    reference: object
    vector: np.ndarray
    printed_total: float
    source_line: int
    density: str=''
    state_number: int|None=None
    kind: str='permanent'

@dataclass
class TransitionContribution:
    from_orbital: int
    to_orbital: int
    coefficient: float|None
    from_spin: str=''
    to_spin: str=''
    direction: str='->'
    printed_weight: float|None=None

@dataclass
class Transition:
    number: int
    state: str
    energy_ev: float
    wavelength_nm: float
    oscillator_strength: float|None
    electric_dipole_au: object=None
    dipole_strength_au2: float|None=None
    oscillator_strength_length: float|None=None
    velocity_dipole_au: object=None
    oscillator_strength_velocity: float|None=None
    magnetic_dipole_au: object=None
    contributions: list=field(default_factory=list)
    source_line: int|None=None
    source_label: str=''

@dataclass
class ElectronicSpectrum:
    reference: object=None
    transitions: list=field(default_factory=list)
    source_line: int=0
    label: str=''


def read_gaussian_properties(path):
    lines=Path(path).read_text(errors='replace').splitlines()
    dipoles=[];spectra=[];current=spectrum=None;info={};data={};density='';selected=last=None;i=0
    last_transition=None
    while i<len(lines):
        line=lines[i]
        if _job_boundary(line):
            current=spectrum=None;info={};data={};density='';selected=last=None
            last_transition=None
        charge=_CHARGE.search(line)
        if charge:info.update(converter_charge=int(charge[1]),converter_mult=int(charge[2]))
        if _ORIENTATION.match(line):
            current,i=_orientation(lines,i,info);spectrum=None;data={};density='';selected=last=None;last_transition=None;continue
        scf=_SCF.search(line)
        if scf and current is not None:current[0].energy_ev=_number(scf[1])*Hartree
        if 'Population analysis using' in line:
            m=re.search(r'Population analysis using (?:the )?(.+?) Density',line,re.I)
            density=m[1].strip() if m else 'unspecified'
        if 'This state for optimization' in line:selected=last
        table=None
        for name,key in [('electric','electric'),('velocity','velocity'),('magnetic','magnetic')]:
            if f'Ground to excited state transition {name} dipole moments' in line:table=key;break
        if table is not None:
            if table=='electric':
                if spectrum is not None and spectrum.transitions:spectrum=None
                data={}
            j=i+1
            while j<len(lines) and j<=i+4 and not re.match(r'^\s*\d+\s+',lines[j]):j+=1
            while j<len(lines):
                f=lines[j].split()
                if len(f)<4 or not f[0].isdigit():break
                try:values=[_number(v) for v in f[1:]]
                except ValueError:break
                row=data.setdefault(int(f[0]),{});row[table]=np.array(values[:3])
                if table in ('electric','velocity') and len(values)>=5:
                    row[table+'_strength']=values[3];row[table+'_oscillator']=values[4]
                j+=1
            i=max(i+1,j);continue
        if 'Dipole moment (' in line and i+1<len(lines):
            m=DIPOLE.search(lines[i+1])
            if m:
                values=[_number(v) for v in m.groups()]
                excited=bool(density and density.upper()!='SCF' and
                    (re.search(r'TD|excited',density,re.I) or
                     ((selected is not None or (spectrum is not None and spectrum.transitions)) and re.search(r'CI|RhoCI',density,re.I))))
                dipoles.append(DipoleRecord(None if current is None else current[0].clone(),np.array(values[:3]),
                    values[3],i+1,density,selected if excited else None,'excited permanent' if excited else 'permanent'))
        m=EXCITED.search(line)
        if m:
            number=int(m[1]);last=number;energy,wavelength,strength=[_number(m[k]) for k in (3,4,5)]
            if energy>0 and wavelength>0 and strength>=0:
                if spectrum is None or (spectrum.transitions and number<=spectrum.transitions[-1].number):
                    if spectrum is not None:data={}
                    spectrum=ElectronicSpectrum(None if current is None else current[0].clone(),source_line=i+1);spectra.append(spectrum)
                row=data.get(number,{})
                spectrum.transitions.append(Transition(number,m[2],energy,wavelength,strength,
                    row.get('electric'),row.get('electric_strength'),row.get('electric_oscillator'),
                    row.get('velocity'),row.get('velocity_oscillator'),row.get('magnetic')))
                last_transition=spectrum.transitions[-1];last_transition.source_line=i+1
        contribution=re.match(rf'^\s*(\d+)([ABab]?)\s*(->|<-)\s*(\d+)([ABab]?)\s+({N})\s*$',line)
        if contribution and last_transition is not None:
            last_transition.contributions.append(TransitionContribution(int(contribution[1]),int(contribution[4]),
                _number(contribution[6]),contribution[2].upper(),contribution[5].upper(),contribution[3]))
        i+=1
    return dipoles,spectra


def contribution_text(transition, limit=4):
    rows=sorted(transition.contributions,key=lambda c:abs(c.coefficient) if c.coefficient is not None else (c.printed_weight or 0),reverse=True)
    parts=[]
    for row in rows[:limit]:
        value=('coefficient not printed'+('' if row.printed_weight is None else f', weight={row.printed_weight:g}')) if row.coefficient is None else f'c={row.coefficient:+.6f}'
        parts.append(f'{row.from_orbital}{row.from_spin} {row.direction} {row.to_orbital}{row.to_spin} ({value})')
    if len(rows)>limit:parts.append(f'+{len(rows)-limit} more')
    return '; '.join(parts) if parts else 'Not printed'


def read_orca_properties(path, results):
    from .orca_properties import read_orca_properties as reader
    return reader(path, results)


def vector_for_geometry(reference,vector,frame):
    if reference is None or reference.symbols!=frame.symbols or not frame.symbols:return None
    a=reference.positions-reference.positions.mean(axis=0);b=frame.positions-frame.positions.mean(axis=0)
    if np.allclose(a,b,atol=2e-5,rtol=0):return np.asarray(vector).copy()
    u,_,vt=np.linalg.svd(a.T@b);d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);r=u@d@vt
    return np.asarray(vector)@r if np.allclose(a@r,b,atol=2e-4,rtol=0) else None


def selected_dipole(document,frame,source='permanent'):
    if source.startswith('transition:'):
        try:
            _,calc,state=source.split(':');spectrum=document.electronic_spectra[int(calc)]
            t=next(t for t in spectrum.transitions if t.number==int(state))
        except (ValueError,IndexError,StopIteration):return None
        return None if t.electric_dipole_au is None else vector_for_geometry(spectrum.reference,t.electric_dipole_au*AU_TO_DEBYE,frame)
    if source.startswith('permanent:'):
        try:record=document.dipoles[int(source.split(':')[1])]
        except (ValueError,IndexError):return None
        return vector_for_geometry(record.reference,record.vector,frame)
    matches=[]
    for record in document.dipoles:
        if record.kind=='excited permanent':continue
        v=vector_for_geometry(record.reference,record.vector,frame)
        if v is not None:
            score=abs(record.reference.energy_ev-frame.energy_ev) if record.reference.energy_ev is not None and frame.energy_ev is not None else 0.
            matches.append((score,v))
    return min(matches,key=lambda x:x[0])[1] if matches else None


def dipole_label(document,source='permanent'):
    if source.startswith('transition:'):return 'μ(0->'+source.split(':')[-1]+')'
    if source.startswith('permanent:'):
        try:r=document.dipoles[int(source.split(':')[1])]
        except (ValueError,IndexError):return 'μ'
        if r.kind=='excited permanent':return f'μ(state {r.state_number or "?"})'
    return 'μ'
