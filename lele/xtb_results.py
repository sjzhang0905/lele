"""xTB/g-xTB optimization, Hartree energies and printed frontier orbitals.

Only same-directory, verified trajectory companions are associated with stdout.
Missing per-cycle geometries remain missing; neither SCF rows nor ANC norms are
treated as geometry records or Cartesian maximum/RMS forces.
"""
from pathlib import Path
import re
import numpy as np
from ase.data import atomic_numbers
from ase.units import Hartree, Bohr
from .core import Frame
from .output_text import read_output_lines
from .calculation_results import (NUMBER, CalculationResults, CalculationJob,
    CalculationStep, CalculationStage, Orbital, OrbitalSet)

VERSION=re.compile(r'^\s*\*?\s*xtb version\s+\d',re.I)
CYCLE=re.compile(r'^\s*\.+\s*CYCLE\s+(\d+)\s*\.+',re.I)
CYCLE_ENERGY=re.compile(rf'^\s*\*\s*total energy\s*:\s*({NUMBER})\s+Eh\b',re.I)
SUMMARY_ENERGY=re.compile(rf'^\s*(?:::|\|)\s*TOTAL ENERGY\s+({NUMBER})\s+Eh\b',re.I)
GAP=re.compile(rf'HOMO-LUMO\s+GAP\s+({NUMBER})\s+eV\b',re.I)
HEADER=re.compile(r'^\s*(alpha|beta)?\s*#\s+Occupation\s+Energy/Eh\s+Energy/eV',re.I)


def number(text):
    value=float(text.replace('D','E').replace('d','e'))
    if not np.isfinite(value):raise ValueError('Non-finite xTB result')
    return value


def xyz_block(lines,start):
    """One complete XYZ frame; positions are Angstrom, comment energy is Eh."""
    if start>=len(lines) or not lines[start].strip().isdigit():return None,start
    n=int(lines[start].strip())
    if not 0<n<=200000 or start+n+2>len(lines):return None,start
    symbols=[];positions=[]
    try:
        for line in lines[start+2:start+2+n]:
            fields=line.split()
            if len(fields)<4: return None,start
            symbol=fields[0].capitalize()
            if symbol not in atomic_numbers:return None,start
            symbols.append(symbol);positions.append([number(v) for v in fields[1:4]])
        comment=lines[start+1]
        match=re.search(rf'\benergy\s*:\s*({NUMBER})',comment,re.I)
        if match is None:match=re.search(rf'\bSCF\s+done\s+({NUMBER})',comment,re.I)
        energy=None if match is None else number(match[1])*Hartree
        return Frame(symbols,positions,energy_ev=energy,info={'source_line':start+1,'xtb_comment':comment.strip()}),start+n+2
    except (ValueError,OverflowError):return None,start


def read_xtb_xyz(path):
    lines=read_output_lines(path);frames=[];i=0;atoms=0;note=''
    while i<len(lines):
        if not lines[i].strip():i+=1;continue
        frame,end=xyz_block(lines,i)
        if frame is None:
            note=f'Incomplete or invalid XYZ record at line {i+1}; only earlier complete records are available.';break
        atoms+=len(frame.symbols)
        if atoms>2000000:raise ValueError('xTB trajectory exceeds 2,000,000 atom records')
        frames.append(frame);i=end
    return frames,note


def final_geometry(lines,index):
    for start in range(index+1,min(len(lines),index+9)):
        frame,end=xyz_block(lines,start)
        if frame is not None:return frame,end
        if lines[start].strip().lower().startswith('$coord'):
            factor=1. if re.search(r'angs|angstrom',lines[start],re.I) else Bohr
            symbols=[];positions=[];j=start+1
            try:
                while j<len(lines) and not lines[j].strip().startswith('$'):
                    fields=lines[j].split();j+=1
                    if not fields:continue
                    if len(fields)<4 or fields[3].capitalize() not in atomic_numbers:return None,index+1
                    symbols.append(fields[3].capitalize());positions.append([number(v)*factor for v in fields[:3]])
                if symbols:return Frame(symbols,positions),j
            except (ValueError,OverflowError):return None,index+1
    return None,index+1


def parse_orbital_table(lines,start):
    rows=[];labels={};gap=None;i=start+1
    while i<len(lines):
        line=lines[i];stripped=line.strip()
        if HEADER.match(line):break
        match=re.search(rf'HL-Gap\s+({NUMBER})\s+Eh\s+({NUMBER})\s+eV',line,re.I)
        if match:gap=number(match[2]);break
        if not stripped or set(stripped)<=set('-=') or '...' in stripped:i+=1;continue
        fields=stripped.split()
        if not fields or not fields[0].isdigit():break
        values=re.findall(NUMBER,' '.join(fields[1:]).split('(')[0])
        if len(values) not in (2,3):break
        try:
            occupation=number(values[0]) if len(values)==3 else 0.
            energy=number(values[-1]);index=int(fields[0])
            rows.append(Orbital(index,occupation,energy))
            for role in ('homo','lumo'):
                if re.search(r'\('+role+r'\)',line,re.I):labels[role]=index
        except (ValueError,OverflowError):break
        i+=1
    return rows,labels,gap,i


def _compatible_trajectory(frames,steps,reference):
    if not frames or reference is None or len(frames)!=len(steps):return False
    if any(f.symbols!=reference.symbols for f in frames):return False
    if not np.allclose(frames[-1].positions,reference.positions,atol=2e-6,rtol=0):return False
    return all(f.energy_ev is not None and s.energy_ev is not None and
               abs(f.energy_ev-s.energy_ev)/Hartree<=5.1e-8 for f,s in zip(frames,steps))


def _associate_trajectory(path,steps,reference):
    if reference is None:return None,[]
    candidates=[path.with_name(path.stem+'.xtbopt.log'),path.with_name(path.stem+'_xtbopt.log'),path.with_name('xtbopt.log')]
    matched=[];seen=set();notes=[]
    for candidate in candidates:
        if candidate==path or candidate in seen or not candidate.is_file():continue
        seen.add(candidate)
        try:frames,note=read_xtb_xyz(candidate)
        except (ValueError,OSError):frames=[];note='Could not read a complete trajectory.'
        if not note and _compatible_trajectory(frames,steps,reference):matched.append((candidate,frames))
        else:notes.append(candidate.name+' does not match this optimization; it was not attached.')
    if not matched:return None,notes
    first=matched[0]
    if any(any(not np.allclose(a.positions,b.positions,atol=1e-7,rtol=0) for a,b in zip(first[1],item[1])) for item in matched[1:]):
        return None,notes+['More than one different trajectory matches the printed energies; no trajectory was attached.']
    return first,notes


def _metadata(job,text):
    call=re.search(r'(?mi)^\s*program call\s*:\s*(.*)',text)
    job.route=call[1].strip() if call else ''
    method=re.search(r'(?mi)Hamiltonian\s+(GFN[012]-xTB|GFN-FF)',text)
    if re.search(r'--gxtb\b',job.route,re.I):job.method='g-xTB'
    elif method:job.method=method[1]
    else:
        gfn=re.search(r'--gfn\s*=?\s*([012])\b',job.route)
        if gfn:job.method='GFN'+gfn[1]+'-xTB'
        elif '--gfnff' in job.route:job.method='GFN-FF'
    charge=re.findall(rf'(?mi)(?:molecular charge|::\s*total charge)\s+({NUMBER})\s+e\b',text)
    cli=re.search(r'--chrg(?:\s+|=)([-+]?\d+)',job.route)
    if charge and abs(number(charge[-1])-round(number(charge[-1])))<1e-5:job.charge=round(number(charge[-1]))
    elif cli:job.charge=int(cli[1])
    unpaired=re.findall(rf'number of unpaired electrons\s+({NUMBER})',text,re.I)
    uhf=re.search(r'--uhf(?:\s+|=)(\d+)',job.route)
    if unpaired:job.multiplicity=int(round(abs(number(unpaired[-1]))))+1
    elif uhf:job.multiplicity=int(uhf[1])+1


def read_xtb_results(path,trajectory=False):
    path=Path(path);result=CalculationResults('xTB');notes=[]
    if trajectory:
        frames,note=read_xtb_xyz(path)
        if not frames:raise ValueError('No complete xTB XYZ geometry found')
        job=CalculationJob(0,1,method='xTB',tasks={'Optimization trajectory'},energy_ev=frames[-1].energy_ev)
        result.jobs=[job];result.stages=[CalculationStage(0,0,'xTB optimization trajectory','optimization',1,status='Not available in trajectory')]
        for i,frame in enumerate(frames):
            result.steps.append(CalculationStep(0,frame.info['source_line'],frame,frame.energy_ev,stage_index=0,cycle=i+1))
        count=sum(f.energy_ev is not None for f in frames)
        result.note=f'{len(frames)} coordinate records; {count} printed energies. Convergence and orbital results are not present in this trajectory.'
        if note:result.note+=' '+note
        return result
    lines=read_output_lines(path)
    starts=[i for i,line in enumerate(lines) if VERSION.match(line)] or [0]
    for ji,(start,end) in enumerate(zip(starts,starts[1:]+[len(lines)])):
        block=lines[start:end];job=CalculationJob(ji,start+1);result.jobs.append(job)
        _metadata(job,'\n'.join(block));steps=[];snapshots={};phase='initial';current=None;reference=None
        stage=CalculationStage(len(result.stages),ji,'xTB geometry optimization','optimization',start+1,end)
        i=0;final_energy=None;converged=False;matched=None
        def snapshot(key,line):
            if key not in snapshots:snapshots[key]=OrbitalSet(ji,line,numbering='1-based xTB orbital numbers; printed frontier labels take precedence')
            return snapshots[key]
        while i<len(block):
            line=block[i];source_line=start+i+1
            cycle=CYCLE.match(line)
            if cycle:
                current=CalculationStep(ji,source_line,stage_index=stage.index,cycle=int(cycle[1]))
                steps.append(current);phase=('cycle',source_line)
            match=CYCLE_ENERGY.match(line)
            if match and current is not None:current.energy_ev=number(match[1])*Hartree
            match=SUMMARY_ENERGY.match(line)
            if match:
                job.energy_ev=number(match[1])*Hartree
                if phase=='final':final_energy=job.energy_ev
            if re.search(r'GEOMETRY OPTIMIZATION CONVERGED AFTER\s+\d+\s+ITERATIONS',line,re.I):
                converged=True;stage.status='Converged';phase='final';current=None
            if re.search(r'(?:GEOMETRY OPTIMIZATION.*(?:FAILED|NOT CONVERGED)|FAILED TO CONVERGE.*(?:ITERATIONS|CYCLES))',line,re.I):
                stage.status='Not converged';phase='final';current=None
            if line.strip().lower()=='final structure:':
                frame,j=final_geometry(block,i)
                if frame is not None:reference=frame;phase='final';current=None;i=j;continue
            header=HEADER.match(line)
            if header:
                channel=(header[1] or 'Restricted').capitalize()
                rows,labels,gap,j=parse_orbital_table(block,i)
                if rows:
                    s=snapshot(phase,source_line);existing={r.number:r for r in s.channels.get(channel,[])}
                    existing.update({r.number:r for r in rows});s.channels[channel]=[existing[n] for n in sorted(existing)]
                    s.frontier_numbers.setdefault(channel,{}).update(labels)
                    if gap is not None:s.printed_gaps[channel]=gap
                i=max(i+1,j);continue
            gap=GAP.search(line)
            if gap:snapshot(phase,source_line).reported_gap_ev=number(gap[1])
            if re.search(r'^\s*\*\s*finished run on\b',line,re.I) and job.termination!='Normal termination':job.termination='Finished run'
            if re.search(r'normal termination of xtb',line,re.I):job.termination='Normal termination'
            i+=1
        steps=[s for s in steps if s.energy_ev is not None]
        if steps:
            job.tasks.add('Optimization');result.stages.append(stage)
            if converged:steps[-1].converged=True
            matched,more=_associate_trajectory(path,steps,reference);notes.extend(more)
            if matched:
                companion,frames=matched
                for step,frame in zip(steps,frames):
                    frame.info['xtb_cycle_energy_ev']=step.energy_ev
                    frame.info['xtb_trajectory_energy_ev']=frame.energy_ev
                    frame.info['xtb_trajectory_source']=companion.name
                    step.geometry=frame;step.energy_ev=frame.energy_ev
                notes.append(f'{companion.name}: {len(frames)} verified optimization geometries.')
            else:notes.append(f'Job {ji+1}: {len(steps)} energy records loaded independently of coordinates.')
            if reference is not None:
                last=steps[-1]
                if last.geometry is None:last.geometry=reference
                last.geometry.info.setdefault('xtb_cycle_energy_ev',last.energy_ev)
                # The explicit final geometry and its final single point are the same
                # geometry; retain the trajectory energy separately in Frame.info.
                if final_energy is not None:last.energy_ev=final_energy
            if final_energy is None:job.energy_ev=steps[-1].energy_ev
        else:
            job.tasks.add('Single point')
            steps=[CalculationStep(ji,start+1,reference,job.energy_ev)]
        for step in steps:
            if step.geometry is not None:
                if job.charge is not None:step.geometry.info['converter_charge']=job.charge
                if job.multiplicity is not None:step.geometry.info['converter_mult']=job.multiplicity
        offset=len(result.steps);result.steps.extend(steps)
        for key,s in snapshots.items():
            if key=='final':s.step_index=offset+len(steps)-1
            elif key=='initial' and steps[0].geometry is not None and (not job.tasks.intersection({'Optimization'}) or matched):s.step_index=offset
            elif isinstance(key,tuple):
                position=next((i for i,p in enumerate(steps) if p.source_line==key[1]),None)
                if position is not None:s.step_index=offset+position
            if len(s.channels)==1 and s.reported_gap_ev is not None:
                channel=next(iter(s.channels));h,l,g=s.frontier(channel)
                if h is not None and l is not None and abs((l.energy_ev-h.energy_ev)-s.reported_gap_ev)<2e-4:s.printed_gaps[channel]=s.reported_gap_ev
            result.orbitals.append(s)
    result.note=' '.join(dict.fromkeys(notes))
    return result
