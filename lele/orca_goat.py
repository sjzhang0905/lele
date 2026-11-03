"""Printed GOAT ensembles and optional associated conformer coordinates."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import numpy as np
from ase.units import Hartree
from .calculation_results import NUMBER
from .gaussian_vibrations import _number
from .orca_neb import read_xyz_records, companion_prefix
from .output_text import read_output_lines, load_progress

KCAL_PER_EV=23.0605478306


@dataclass
class Conformer:
    number: int
    relative_kcal: float | None
    degeneracy: float | None = None
    printed_percent: float | None = None
    cumulative_percent: float | None = None
    reference: object = None
    frame_index: int | None = None


@dataclass
class ConformerEnsemble:
    source_line: int
    source: str
    conformers: list = field(default_factory=list)
    temperature: float | None = None
    note: str = ''

    def populations(self, temperature):
        if temperature<=0:raise ValueError('Temperature must be positive')
        if any(c.relative_kcal is None for c in self.conformers):return None
        energies=np.asarray([c.relative_kcal for c in self.conformers])
        degeneracy=np.asarray([1. if c.degeneracy is None else c.degeneracy for c in self.conformers])
        if np.any(degeneracy<=0):return None
        weights=degeneracy*np.exp(-(energies-energies.min())/(.00198720425864*temperature))
        return weights/weights.sum()*100.


def read_goat_ensembles(path):
    path=Path(path);lines=read_output_lines(path);ensembles=[];temperature=None
    if not path.name.endswith('.finalensemble.xyz') and not any('Final ensemble info' in s for s in lines):return []
    progress=load_progress('ORCA: GOAT ensembles',len(lines))
    prefix=companion_prefix(path,lines)
    if path.name.endswith('.finalensemble.xyz'):
        records=read_xyz_records(path,bare_energy=True)
        known=[f.energy_ev for f in records if f.energy_ev is not None]
        baseline=min(known) if known else None
        e=ConformerEnsemble(1,str(path),note='XYZ-only ensemble; degeneracy and printed populations are unavailable.')
        e.conformers=[Conformer(i,None if f.energy_ev is None or baseline is None else (f.energy_ev-baseline)*KCAL_PER_EV,reference=f) for i,f in enumerate(records)]
        return [e] if records else []
    i=0
    while i<len(lines):
        progress(i)
        line=lines[i]
        temp=re.search(rf'Ensemble temperature\s*\.+\s*({NUMBER})',line,re.I)
        if temp:temperature=_number(temp[1])
        if 'Final ensemble info' in line:
            ensemble=ConformerEnsemble(i+1,str(path),temperature=temperature)
            j=i+1;filename=Path(str(prefix)+'.finalensemble.xyz')
            while j<len(lines):
                m=re.match(rf'^\s*(\d+)\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*$',lines[j])
                if m:ensemble.conformers.append(Conformer(int(m[1]),_number(m[2]),_number(m[3]),_number(m[4]),_number(m[5])))
                written=re.search(r'Writing final ensemble to\s+(\S+)',lines[j],re.I)
                if written:filename=path.parent/Path(written[1]).name;break
                if j>i+8 and not m and ensemble.conformers and not lines[j].strip():break
                j+=1
            # The final filename can appear several summary lines after the table.
            for following in lines[j:min(j+12,len(lines))]:
                written=re.search(r'Writing final ensemble to\s+(\S+)',following,re.I)
                if written:filename=path.parent/Path(written[1]).name;break
            if filename.exists():
                records=read_xyz_records(filename,bare_energy=True)
                sequential=[c.number for c in ensemble.conformers] in [list(range(len(records))),list(range(1,len(records)+1))]
                valid=len(records)==len(ensemble.conformers) and sequential
                if valid and records and all(f.energy_ev is not None for f in records):
                    energy=np.asarray([f.energy_ev for f in records]);energy=(energy-energy.min())*KCAL_PER_EV
                    valid=np.allclose(energy,[c.relative_kcal for c in ensemble.conformers],atol=.005,rtol=0)
                if valid:
                    for c,f in zip(ensemble.conformers,records):c.reference=f
                else:ensemble.note='Companion XYZ does not match the printed conformer count/energies; coordinates were not assigned.'
            else:ensemble.note='Companion .finalensemble.xyz not found; printed energies/populations remain available.'
            if ensemble.conformers:ensembles.append(ensemble)
            i=j
        i+=1
    progress(len(lines))
    return ensembles


def attach_goat(document):
    ensembles=read_goat_ensembles(document.path)
    for ei,ensemble in enumerate(ensembles):
        for c in ensemble.conformers:
            if c.reference is None:continue
            existing=next((i for i,f in enumerate(document.frames) if f.info.get('goat_conformer')==c.number and f.info.get('goat_ensemble')==ei),None)
            if existing is not None:c.frame_index=existing;continue
            f=c.reference
            f.info.update(goat_conformer=c.number,goat_ensemble=ei,series_key=f'goat:{ei}',series_label=f'GOAT ensemble {ei+1}',source_kind='orca_out')
            if document.frames:
                for key in ('converter_charge','converter_mult'):
                    if key in document.frames[0].info:f.info[key]=document.frames[0].info[key]
            c.frame_index=len(document.frames);document.frames.append(f)
    document.conformer_ensembles=ensembles


def aligned_rmsd(reference, frame, heavy=False):
    if reference.symbols!=frame.symbols:return None
    indices=[i for i,s in enumerate(reference.symbols) if not heavy or s!='H']
    if not indices:return None
    a=reference.positions[indices];b=frame.positions[indices]
    a=a-a.mean(axis=0);b=b-b.mean(axis=0)
    u,_,vt=np.linalg.svd(a.T@b);sign=np.eye(3);sign[-1,-1]=np.linalg.det(u@vt)
    return float(np.sqrt(np.mean(np.sum((a@(u@sign@vt)-b)**2,axis=1))))
