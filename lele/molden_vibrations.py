"""Read CP2K-compatible Molden vibrations independently of other output files.

FR-COORD and FR-NORM-COORD are in Bohr by the Molden specification. Relative
Cartesian vectors are converted uniformly, without a second mass weighting.
Frozen-atom zero rows and a partial list of modes are retained as printed.
"""
import re
import numpy as np
from ase.data import atomic_numbers,chemical_symbols
from ase.units import Bohr
from .core import Frame,NormalMode,VibrationalAnalysis
from .calculation_results import CalculationResults,CalculationJob,CalculationStep,CalculationStage
from .output_text import read_output_lines,scan_lines,load_progress,check_load_cancelled

SECTION=re.compile(r'^\s*\[([^]]+)\]\s*(.*?)\s*$')
MODE=re.compile(r'^\s*vibration\s+(\d+)\s*$',re.I)


def real(value):
    result=float(value.replace('D','E').replace('d','e'))
    if not np.isfinite(result):raise ValueError('Non-finite Molden value')
    return result


def unit_scale(unit,default='au'):
    unit=unit.strip().strip('()').lower() or default
    if unit in ('au','a.u.','bohr'):return Bohr
    if unit in ('angs','angstrom','angstroms'):return 1.
    raise ValueError('Unsupported Molden coordinate unit: '+unit)


def read_molden_vibrations(path):
    lines=read_output_lines(path);sections={};current=None;seen_header=False
    for i,line in scan_lines(lines,'Molden: indexing sections'):
        match=SECTION.match(line)
        if match is None:continue
        key=re.sub(r'\s+',' ',match[1].strip().upper())
        if current is not None:sections[current][2]=i
        if key=='MOLDEN FORMAT':
            if seen_header:raise ValueError('Open separate Molden calculations as separate files')
            seen_header=True;current=None;continue
        if key in sections:raise ValueError('Repeated Molden section: '+key)
        sections[key]=[match[2],i+1,len(lines)];current=key
    if not seen_header:raise ValueError('Missing [Molden Format] header')
    if 'FREQ' not in sections:raise ValueError('No [FREQ] vibration data in this Molden file')
    def rows(key):
        if key not in sections:return []
        _,start,end=sections[key]
        return [(i,lines[i].split()) for i in range(start,end) if lines[i].strip()]
    notices=[];atoms=None
    if 'ATOMS' in sections:
        symbols=[];positions=[];ids=set()
        for source,fields in rows('ATOMS'):
            if len(fields)!=6:raise ValueError(f'Incomplete Molden [Atoms] row at line {source+1}')
            index=int(fields[1]);z=int(fields[2])
            if index<1 or index in ids or not 0<z<len(chemical_symbols):raise ValueError('Invalid Molden atom index/atomic number')
            symbol=chemical_symbols[z]
            if fields[0].capitalize()!=symbol:raise ValueError('Molden element and atomic number disagree')
            ids.add(index);symbols.append(symbol);positions.append([real(x) for x in fields[3:]])
        if symbols:atoms=(symbols,np.asarray(positions)*unit_scale(sections['ATOMS'][0]))
    if 'FR-COORD' in sections:
        symbols=[];positions=[]
        for source,fields in rows('FR-COORD'):
            if len(fields)!=4 or fields[0].capitalize() not in atomic_numbers:
                raise ValueError(f'Incomplete Molden [FR-COORD] row at line {source+1}')
            symbols.append(fields[0].capitalize());positions.append([real(x) for x in fields[1:]])
        positions=np.asarray(positions).reshape(-1,3)*unit_scale(sections['FR-COORD'][0])
        if atoms is not None and atoms[0]!=symbols:raise ValueError('[Atoms] and [FR-COORD] atom sequences differ')
        if atoms is not None and not np.allclose(atoms[1],positions,atol=2e-6,rtol=0):
            notices.append('Vibration reference uses [FR-COORD], which differs from [Atoms].')
        coordinate_section='FR-COORD'
    elif atoms is not None:
        symbols,positions=atoms;coordinate_section='Atoms'
        notices.append('[FR-COORD] absent; using the explicitly unit-labelled [Atoms] reference.')
    else:raise ValueError('No complete reference coordinates in this Molden file')
    if not symbols:raise ValueError('Empty Molden reference geometry')
    cell=np.zeros((3,3))
    if 'CELL' in sections:
        data=rows('CELL')
        if len(data)!=3 or any(len(v)!=3 for _,v in data):raise ValueError('Incomplete Molden [Cell] vectors')
        cell=np.asarray([[real(x) for x in row] for _,row in data])*unit_scale(sections['CELL'][0])
        notices.append('Printed cell retained; periodic flags are not specified in Molden and are not assumed.')
    info={'molden_reference_section':coordinate_section,'source_line':sections[coordinate_section.upper()][1],
          'calculation_index':0,'stage_index':0}
    reference=Frame(symbols,positions,cell,info=info)
    frequencies=[real(value) for _,fields in rows('FREQ') for value in fields]
    if not frequencies:raise ValueError('No numeric Molden frequencies')
    modes=[NormalMode(i+1,value,ir_intensity_unit='source units') for i,value in enumerate(frequencies)]
    if 'FR-NORM-COORD' in sections:
        _,i,end=sections['FR-NORM-COORD'];seen=set()
        report=load_progress('Molden: Cartesian vibration vectors',end-i);start=i
        while i<end:
            check_load_cancelled();report(i-start);match=MODE.match(lines[i])
            if match is None:i+=1;continue
            number=int(match[1]);i+=1
            if not 1<=number<=len(modes) or number in seen:raise ValueError('Molden vibration number is duplicated or has no frequency')
            seen.add(number);vectors=[];invalid=False
            while i<end and MODE.match(lines[i]) is None:
                if lines[i].strip():
                    fields=lines[i].split()
                    try:
                        if len(fields)!=3:raise ValueError()
                        vectors.append([real(x) for x in fields])
                    except ValueError:invalid=True
                i+=1
                if i%512==0:check_load_cancelled();report(i-start)
            if not invalid and len(vectors)==len(symbols):modes[number-1].displacements=np.asarray(vectors)*Bohr
            else:notices.append(f'Mode {number}: incomplete displacement rows; animation unavailable for this mode.')
        report(end-start)
    if 'INT' in sections:
        values=rows('INT');raw=[]
        for _,fields in values:raw.append([real(x) for x in fields])
        reference.info['molden_intensity_columns']=raw
        for mode,row in zip(modes,raw):
            if row:mode.ir_intensity=row[0]
        if len(raw)!=len(modes):notices.append('[INT] count differs from [FREQ]; only existing corresponding intensities are available.')
        notices.append('[INT] values retain source units. CP2K writes a.u./amu; no km/mol or Raman-activity conversion is assumed.')
    missing=sum(m.displacements is None for m in modes)
    if missing:notices.append(f'{missing} mode(s) have no complete Cartesian displacement data.')
    note=('Molden frequencies are cm⁻¹. Coordinates/vectors are converted from their printed units to Å; '
          'no additional mass weighting is applied. Zero rows remain zero. No energy, charge, periodicity or '
          'optimization status is borrowed from other files. '+' '.join(notices)).strip()
    analysis=VibrationalAnalysis(reference,modes,sections['FREQ'][1],note,purpose='Molden normal modes',stage_index=0)
    results=CalculationResults('Molden',jobs=[CalculationJob(0,1,tasks={'Frequency'},
        frequency_count=len(modes),imaginary_modes=sum(m.imaginary for m in modes),termination='Not recorded in Molden')],
        stages=[CalculationStage(0,0,'Molden vibration reference','frequency',1,status='Printed modes')],
        steps=[CalculationStep(0,info['source_line'],reference.clone(),frame_index=0,stage_index=0)],note=note)
    return reference,[analysis],results,note
