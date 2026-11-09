"""Molden geometry, Gaussian basis, orbitals, and optional vibrations.

[Atoms] units are mandatory by the format; [GTO] exponents are in Bohr^-2.
MO energies are Hartree. Spherical d/f flags and explicit occupations are kept.
"""
from pathlib import Path
import re
import numpy as np
from ase.data import chemical_symbols
from ase.units import Bohr,Hartree
from .core import Document,Frame
from .calculation_results import CalculationResults,CalculationJob,CalculationStep,CalculationStage,Orbital,OrbitalSet
from .gaussian_basis import GaussianShell,GaussianWavefunction,shell_polynomials
from .molden_vibrations import SECTION,real,unit_scale
from .output_text import read_output_lines,check_load_cancelled


def _sections(lines):
    sections={};current=None;seen=False;flags=set()
    for i,line in enumerate(lines):
        check_load_cancelled();m=SECTION.match(line)
        if not m:continue
        key=re.sub(r'\s+','',m[1].upper())
        if current is not None:sections[current][2]=i
        if key=='MOLDENFORMAT':
            if seen:raise ValueError('Open separate Molden calculations as separate files.')
            seen=True;current=None;continue
        if re.fullmatch(r'(?:[5679](?:D|F)|10F|(?:15|9)G)+',key):
            flags.update(re.findall(r'\d+[DFG]',key));current=None;continue
        if key in sections:raise ValueError('Repeated Molden section: '+key)
        sections[key]=[m[2],i+1,len(lines)];current=key
    if not seen:raise ValueError('Missing [Molden Format] header.')
    return sections,flags


def _basis(lines,section,positions,flags,atom_ids):
    if section is None:return [],'No [GTO] basis was supplied; orbital surfaces are unavailable.'
    _,start,end=section;rows=[line.split() for line in lines[start:end] if line.strip() and not line.lstrip().startswith((';','#'))]
    i=0;atom=None;shells=[];reason=''
    while i<len(rows):
        check_load_cancelled();row=rows[i];i+=1
        if len(row) in (1,2) and row[0].isdigit():
            atom=int(row[0])
            if atom not in atom_ids:raise ValueError('Molden basis atom index has no matching [Atoms] record.')
            continue
        if atom is None or len(row)<2:raise ValueError('Invalid Molden [GTO] shell header.')
        kind=row[0].lower()
        if kind not in ('s','p','d','f','g','h','i','sp'):raise ValueError('Unsupported Molden shell type: '+kind)
        count=int(row[1])
        # The optional third shell field is obsolete in the Molden spec.
        if count<1 or i+count>len(rows):raise ValueError('Incomplete Molden Gaussian shell.')
        primitives=rows[i:i+count];i+=count
        expected=3 if kind=='sp' else 2
        if any(len(r)!=expected for r in primitives):raise ValueError('Invalid Molden primitive row.')
        exponents=np.array([real(r[0]) for r in primitives])
        if np.any(exponents<=0):raise ValueError('Molden Gaussian exponents must be positive.')
        for col,letter in enumerate(('s','p') if kind=='sp' else (kind,),1):
            l='spdfghi'.index(letter)
            pure=(l==2 and '5D' in flags) or (l==3 and ('7F' in flags or ('5D' in flags and '10F' not in flags))) or (l==4 and '9G' in flags)
            shells.append(GaussianShell(positions[atom_ids[atom]]/Bohr,l,exponents.copy(),np.array([real(r[col]) for r in primitives]),pure))
            try:shell_polynomials(l,pure)
            except ValueError as exc:reason=str(exc)
    return shells,reason


def _orbitals(lines,section,nao):
    if section is None:return {},{},[]
    records=[];record={};coefs={}
    def finish():
        nonlocal record,coefs
        if not record and not coefs:return
        if not all(k in record for k in ('ene','spin','occup')):raise ValueError('Molden MO lacks Ene, Spin, or Occup.')
        spin=record['spin'].lower()
        if spin not in ('alpha','beta'):raise ValueError('Unsupported Molden orbital spin: '+spin)
        if record['occup']<0 or record['occup']>2+1e-7:raise ValueError('Invalid Molden orbital occupation.')
        if coefs and (min(coefs)<1 or (nao and max(coefs)>nao)):raise ValueError('Molden AO coefficient index out of range.')
        records.append((record,coefs));record={};coefs={}
    _,start,end=section
    for line in lines[start:end]:
        check_load_cancelled();line=line.strip()
        if not line or line.startswith((';','#')):continue
        if '=' in line:
            key,value=[x.strip() for x in line.split('=',1)];key=key.lower()
            if key=='sym' and record or (key=='ene' and 'ene' in record):finish()
            if coefs:finish()
            if key in record:raise ValueError('Repeated Molden MO field: '+key)
            record[key]=real(value) if key in ('ene','occup') else value
        else:
            row=line.split()
            if len(row)!=2:raise ValueError('Invalid Molden MO coefficient row.')
            index=int(row[0])
            if index in coefs:raise ValueError('Duplicate Molden AO coefficient index.')
            coefs[index]=real(row[1])
    finish();channels={};matrices={};orbital_rows=[]
    for record,coefs in records:
        channel=record['spin'].lower();number=len(channels.setdefault(channel,[]))+1
        orbital=Orbital(number,record['occup'],record['ene']*Hartree)
        channels[channel].append(orbital);orbital_rows.append((channel,number,orbital.occupation,orbital.energy_ev))
        if nao:
            # Molden MO records may omit zero coefficients. Missing entries
            # are zero, but a wholly absent coefficient table is not a wavefunction.
            if not coefs:raise ValueError('Molden MO has no AO coefficients.')
            array=np.zeros(nao)
            for index,value in coefs.items():array[index-1]=value
            matrices.setdefault(channel,[]).append(array)
    return channels,{k:np.asarray(v) for k,v in matrices.items()},orbital_rows


def read_molden(path):
    path=Path(path);lines=read_output_lines(path);sections,flags=_sections(lines)
    if ('5D' in flags and '6D' in flags) or ('7F' in flags and '10F' in flags):raise ValueError('Conflicting Molden spherical/Cartesian flags.')
    vibrations=[];note='';results=None
    if 'FREQ' in sections:
        from .molden_vibrations import read_molden_vibrations
        frame,vibrations,results,note=read_molden_vibrations(path)
    if 'ATOMS' in sections:
        units,start,end=sections['ATOMS']
        if not units.strip():raise ValueError('Molden [Atoms] must specify AU or Angs.')
        positions=[];symbols=[];atom_ids={}
        for line in lines[start:end]:
            if not line.strip():continue
            row=line.split()
            if len(row)!=6:raise ValueError('Invalid Molden [Atoms] row.')
            index=int(row[1]);z=int(row[2])
            if index<1 or index in atom_ids or not 0<=z<len(chemical_symbols):raise ValueError('Invalid Molden atom index/atomic number.')
            atom_ids[index]=len(symbols);symbols.append(chemical_symbols[z]);positions.append([real(x) for x in row[3:]])
        if not symbols:raise ValueError('Empty Molden atom table.')
        positions=np.asarray(positions)*unit_scale(units)
        frame=Frame(symbols,positions,np.zeros((3,3)),info={'source_line':start+1,'calculation_index':0,'stage_index':0})
    elif 'FREQ' in sections:
        positions=frame.positions;atom_ids={i+1:i for i in range(len(frame.symbols))}
    elif 'FR-COORD' in sections:
        units,start,end=sections['FR-COORD'];symbols=[];positions=[]
        for line in lines[start:end]:
            if not line.strip():continue
            row=line.split()
            if len(row)!=4:raise ValueError('Invalid Molden [FR-COORD] row.')
            symbols.append(row[0].capitalize());positions.append([real(x) for x in row[1:]])
        positions=np.asarray(positions)*unit_scale(units)
        frame=Frame(symbols,positions,np.zeros((3,3)));atom_ids={i+1:i for i in range(len(symbols))}
    else:raise ValueError('Molden file has no [Atoms] or [FR-COORD] geometry.')
    if 'CELL' in sections:
        units,start,end=sections['CELL'];rows=[line.split() for line in lines[start:end] if line.strip()]
        if len(rows)!=3 or any(len(row)!=3 for row in rows):raise ValueError('Invalid Molden cell vectors.')
        frame.cell=np.array([[real(x) for x in row] for row in rows])*unit_scale(units)
        note+=' Printed cell retained; periodic flags are not specified and are not assumed.'
    shells,reason=_basis(lines,sections.get('GTO'),positions,flags,atom_ids)
    channels,coefficients,orbital_rows=_orbitals(lines,sections.get('MO'),sum(s.size for s in shells))
    if results is None:
        results=CalculationResults('Molden')
        results.jobs=[CalculationJob(0,1,termination='Molden snapshot; termination not recorded')]
        results.stages=[CalculationStage(0,0,'Molden snapshot','snapshot',1,status='Convergence not recorded')]
        frame.info['stage_index']=0
        results.steps=[CalculationStep(0,1,frame,frame_index=0,stage_index=0)]
    if channels:results.orbitals=[OrbitalSet(0,1,channels,step_index=0,frame_index=0,numbering='1-based Molden MO order within each spin channel')]
    if not coefficients:reason=reason or 'No MO coefficients were supplied; orbital surfaces are unavailable.'
    wf=GaussianWavefunction(positions.copy(),shells,coefficients,orbital_rows,'Molden',reason,{'spherical_flags':sorted(flags)})
    note+=' Molden geometry, printed MO energies and occupations. Orbital amplitudes use Bohr^-3/2.'
    if reason:note+=' '+reason
    document=Document(path,'Molden',[frame],note=note.strip(),vibrations=vibrations,calculation_results=results)
    document.wavefunction=wf
    return document
