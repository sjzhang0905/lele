"""Gaussian formatted-checkpoint geometry, energies, orbitals and basis input."""
from pathlib import Path
import re
import numpy as np
from ase.data import chemical_symbols
from ase.units import Bohr,Hartree
from .core import Document,Frame
from .calculation_results import CalculationResults,CalculationJob,CalculationStep,CalculationStage,Orbital,OrbitalSet
from .gaussian_basis import GaussianShell,GaussianWavefunction,shell_polynomials
from .output_text import open_output_text,check_load_cancelled

HEADER=re.compile(r'^(.+?)\s+([IRCLH])\s+(?:N=\s*(\d+)\s*$|(.+?)\s*$)')
REAL=re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[DEde][-+]?\d+)?')
ARRAYS={'Coordinates of each shell','Atomic numbers','Current cartesian coordinates','Shell types','Number of primitives per shell','Shell to atom map','Primitive exponents','Contraction coefficients','P(S=P) Contraction coefficients','Alpha Orbital Energies','Beta Orbital Energies','Alpha MO coefficients','Beta MO coefficients'}


def _real(value):
    value=float(value.replace('D','E').replace('d','e'))
    if not np.isfinite(value):raise ValueError('Non-finite FCHK numeric value.')
    return value


def read_fchk_fields(path):
    fields={}
    with open_output_text(path) as stream:
        title=stream.readline().strip();method=stream.readline().strip()
        pending=None
        while True:
            line=pending if pending is not None else stream.readline();pending=None
            if not line:break
            check_load_cancelled();match=HEADER.match(line)
            if not match:continue
            name,kind,count,value=match.groups();name=name.strip()
            if count is None:
                if kind=='I':fields[name]=int(value)
                elif kind=='R':fields[name]=_real(value)
                continue
            if kind not in ('I','R'):
                # Character/logical fields have different fixed-width layouts;
                # none are required here. Resume at the next typed field.
                for line in stream:
                    check_load_cancelled()
                    if HEADER.match(line):pending=line;break
                continue
            count=int(count);keep=name in ARRAYS;values=[];seen=0
            while seen<count:
                check_load_cancelled();line=stream.readline()
                if not line or HEADER.match(line):raise ValueError(f'Truncated FCHK array: {name}.')
                tokens=REAL.findall(line)
                seen+=len(tokens)
                if seen>count:raise ValueError(f'FCHK array length mismatch: {name}.')
                if keep:values.extend(int(x) if kind=='I' else _real(x) for x in tokens)
            if keep:fields[name]=np.asarray(values,dtype=int if kind=='I' else float)
    return fields,title,method


def _basis(fields,positions):
    required=['Shell types','Number of primitives per shell','Shell to atom map','Primitive exponents','Contraction coefficients']
    if not all(k in fields for k in required):return [],'FCHK basis data are incomplete; orbital surfaces are unavailable.'
    types,counts,atoms,exponents,contractions=[fields[k] for k in required]
    if not len(types)==len(counts)==len(atoms) or np.any(counts<=0):raise ValueError('FCHK shell tables have inconsistent lengths.')
    if sum(counts)!=len(exponents) or len(exponents)!=len(contractions) or np.any(exponents<=0):raise ValueError('Invalid FCHK primitive table.')
    p=fields.get('P(S=P) Contraction coefficients',np.zeros(len(exponents)))
    if -1 in types and ('P(S=P) Contraction coefficients' not in fields or len(p)!=len(exponents)):
        raise ValueError('FCHK SP shells require P contraction coefficients.')
    centers=fields.get('Coordinates of each shell')
    if centers is not None:
        if len(centers)!=3*len(types):raise ValueError('FCHK shell coordinate count mismatch.')
        centers=centers.reshape(-1,3)
    shells=[];offset=0;reason=''
    for shell_index,(kind,count,atom) in enumerate(zip(types,counts,atoms)):
        if not 1<=atom<=len(positions):raise ValueError('FCHK shell-to-atom index is out of range.')
        sl=slice(offset,offset+count);offset+=count
        orders=[(0,False,contractions[sl]),(1,False,p[sl])] if kind==-1 else [(abs(int(kind)),kind<0,contractions[sl])]
        for l,pure,coefs in orders:
            shells.append(GaussianShell((positions[atom-1]/Bohr if centers is None else centers[shell_index].copy()),l,exponents[sl].copy(),coefs.copy(),pure))
            try:shell_polynomials(l,pure)
            except ValueError as exc:reason=str(exc)
    return shells,reason


def read_fchk(path):
    path=Path(path);fields,title,method=read_fchk_fields(path)
    if 'Atomic numbers' not in fields or 'Current cartesian coordinates' not in fields:
        raise ValueError('FCHK requires Atomic numbers and Current cartesian coordinates.')
    numbers=fields['Atomic numbers'];natoms=int(fields.get('Number of atoms',len(numbers)))
    coordinates=fields['Current cartesian coordinates']
    if natoms<=0 or len(numbers)!=natoms or len(coordinates)!=3*natoms:raise ValueError('FCHK atom/coordinate count mismatch.')
    if np.any(numbers<0) or np.any(numbers>=len(chemical_symbols)):raise ValueError('Invalid FCHK atomic number.')
    info={'title':title,'source_line':1,'calculation_index':0,'stage_index':0}
    if 'Charge' in fields:info['converter_charge']=int(fields['Charge'])
    if 'Multiplicity' in fields:info['converter_mult']=int(fields['Multiplicity'])
    energy=fields.get('Total Energy',fields.get('SCF Energy'))
    frame=Frame([chemical_symbols[z] for z in numbers],coordinates.reshape(-1,3)*Bohr,np.zeros((3,3)),energy_ev=None if energy is None else energy*Hartree,info=info)
    results=CalculationResults('Gaussian FCHK')
    results.jobs=[CalculationJob(0,1,method=method,charge=fields.get('Charge'),multiplicity=fields.get('Multiplicity'),energy_ev=frame.energy_ev,termination='Checkpoint snapshot; termination not recorded')]
    results.stages=[CalculationStage(0,0,'FCHK snapshot','snapshot',1,status='Convergence not recorded')]
    results.steps=[CalculationStep(0,1,frame,frame.energy_ev,frame_index=0,stage_index=0)]
    channels={};coefficients={};orbital_rows=[];warnings=[]
    unrestricted='Beta Orbital Energies' in fields
    nalpha=fields.get('Number of alpha electrons');nbeta=fields.get('Number of beta electrons')
    nao=int(fields.get('Number of basis functions',0))
    for spin in ('Alpha','Beta'):
        energies=fields.get(spin+' Orbital Energies')
        if energies is None:continue
        channel=spin.lower() if unrestricted else 'restricted'
        if nalpha is None or nbeta is None:
            raise ValueError('FCHK orbital energies require alpha and beta electron counts to identify occupations.')
        elif unrestricted:
            n=nalpha if spin=='Alpha' else nbeta
            if not 0<=n<=len(energies):raise ValueError('FCHK electron count exceeds orbital count.')
            occupations=(np.arange(len(energies))<n).astype(float)
        else:
            if not 0<=nbeta<=nalpha<=len(energies):raise ValueError('Invalid FCHK alpha/beta electron counts.')
            occupations=(np.arange(len(energies))<nalpha).astype(float)+(np.arange(len(energies))<nbeta).astype(float)
        channels[channel]=[Orbital(i+1,float(occ),float(e*Hartree)) for i,(occ,e) in enumerate(zip(occupations,energies))]
        orbital_rows.extend((channel,o.number,o.occupation,o.energy_ev) for o in channels[channel])
        coefs=fields.get(spin+' MO coefficients')
        if coefs is not None:
            if nao<=0 or len(coefs)!=len(energies)*nao:raise ValueError('FCHK MO coefficient dimensions do not match energies/basis.')
            coefficients[channel]=coefs.reshape(len(energies),nao)
    if channels:results.orbitals=[OrbitalSet(0,1,channels,step_index=0,frame_index=0,numbering='1-based FCHK orbital numbers; occupations from alpha/beta electron counts')]
    shells,reason=_basis(fields,frame.positions)
    if shells and nao and sum(s.size for s in shells)!=nao:raise ValueError('FCHK shell count does not match number of basis functions.')
    if not coefficients:reason=reason or 'No MO coefficient arrays were supplied; orbital surfaces are unavailable.'
    wf=GaussianWavefunction(frame.positions.copy(),shells,coefficients,orbital_rows,'Gaussian FCHK',reason,{'title':title,'method':method})
    note='Gaussian formatted-checkpoint snapshot. Orbital amplitudes use Bohr^-3/2; geometry uses Angstrom.'
    if reason:note+=' '+reason
    if warnings:note+=' '+' '.join(sorted(set(warnings)))
    document=Document(path,'Gaussian FCHK',[frame],calculation_results=results,note=note)
    document.wavefunction=wf
    return document
