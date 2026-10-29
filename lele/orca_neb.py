"""Separate NEB snapshots, image histories, interpolation and TS results."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import numpy as np
from ase.units import Hartree, Bohr
from .core import Frame
from .calculation_results import NUMBER
from .gaussian_vibrations import _number
from .output_text import read_output_lines


@dataclass
class NebProfile:
    label: str
    source: str
    iteration: int | None
    energies: list
    distances: list = field(default_factory=list)
    relative: bool = False
    ci: int | None = None
    frame_indices: list = field(default_factory=list)
    forces: dict = field(default_factory=dict)
    interpolation: list = field(default_factory=list)


@dataclass
class NebRun:
    label: str
    profiles: list = field(default_factory=list)
    convergence: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    nimages: int | None = None
    ts_frame: int | None = None
    stage_index: int | None = None


def read_xyz_records(path, bare_energy=False):
    lines = read_output_lines(path)
    records=[];i=0;atoms_read=0
    while i<len(lines):
        if not lines[i].strip():i+=1;continue
        try:n=int(lines[i].strip())
        except ValueError:break
        if n<1 or i+n+2>len(lines):break
        atoms_read+=n
        if atoms_read>2_000_000 or len(records)>=50000:raise ValueError('Result trajectory exceeds 2,000,000 atom records / 50,000 frames')
        comment=lines[i+1];symbols=[];positions=[]
        try:
            for line in lines[i+2:i+n+2]:
                f=line.split();symbols.append(f[0]);positions.append([_number(v) for v in f[1:4]])
            energy=re.search(rf'\bE\s+({NUMBER})',comment)
            if energy is None and bare_energy:energy=re.match(rf'^\s*({NUMBER})\s*$',comment)
            frame=Frame(symbols,positions,energy_ev=None if energy is None else _number(energy[1])*Hartree,
                        info={'result_comment':comment,'result_source':str(path)})
        except (ValueError,IndexError):break
        records.append(frame);i+=n+2
    return records


def companion_prefix(path, lines):
    for line in lines:
        m=re.match(r'\s*NAME\s*=\s*(.+?)\.inp\s*$',line)
        if m:return Path(path).parent/re.split(r'[/\\]',m[1])[-1]
    name=Path(path).name
    for suffix in ('.NEB.log','_MEP_ALL_trj.xyz','_MEP_trj.xyz','.interp.final','.interp','.finalensemble.xyz'):
        if name.endswith(suffix):return Path(path).with_name(name[:-len(suffix)])
    return Path(path).with_suffix('')


def _neb_log(path):
    profiles=[];current=None
    for line in read_output_lines(path):
        if ':' not in line:continue
        key,value=line.split(':',1);key=key.strip();value=value.strip()
        if key=='iteration':
            current=NebProfile(f'NEB.log · iteration {int(value)}',str(path),int(value),[])
            profiles.append(current)
        if current is None:continue
        if key=='energy':current.energies=[_number(v) for v in value.split()]
        elif key=='distance':current.distances=[_number(v)*Bohr for v in value.split()]
        elif key not in ('iteration','barrier','climbing','zoom on','nim'):
            try:current.forces[key]=[_number(v) for v in value.split()]
            except ValueError:pass
    return [p for p in profiles if p.energies]


def _interp(path):
    profiles=[];profile=None;section=''
    for line in read_output_lines(path):
        m=re.match(r'Iteration:\s*(\d+)',line.strip(),re.I)
        if m:
            profile=NebProfile(f'{Path(path).name} · iteration {m[1]}',str(path),int(m[1]),[],relative=True)
            profiles.append(profile);section='';continue
        if line.strip().startswith('Images:'):section='images';continue
        if line.strip().startswith('Interp.'):section='interp';continue
        if profile is None:continue
        fields=line.split()
        if len(fields) not in (2,3):continue
        try:
            values=[_number(v) for v in fields];x,e=values[-2:]
        except ValueError:continue
        if section=='images':profile.distances.append(x*Bohr);profile.energies.append(e)
        elif section=='interp':profile.interpolation.append((x*Bohr,e))
    return [p for p in profiles if p.energies]


def _main_profiles(lines):
    profiles=[];convergence=[];i=0;in_neb=False
    while i<len(lines):
        text=lines[i].strip()
        if text=='NEB OPTIMIZATION':in_neb=True
        if 'Next a TS optimization is performed' in text:in_neb=False
        if in_neb:
            m=re.match(r'^\s*(?:LBFGS|VPO|FIRE|SD)\s+(\d+)\s+(\d+)\s+(.+)$',lines[i])
            if m:
                try:v=[_number(x) for x in m[3].split()]
                except ValueError:v=[]
                if len(v)>=4:
                    convergence.append(dict(iteration=int(m[1]),image=int(m[2]),barrier=v[0],max_perp=v[1],rms_perp=v[2],
                        distance=v[3]*Bohr,max_ci=v[4] if len(v)>4 else None,rms_ci=v[5] if len(v)>5 else None))
        if text in ('PATH SUMMARY','PATH SUMMARY FOR NEB-TS'):
            p=NebProfile('Main output · '+text,'main output',None,[])
            j=i+1;distance=False
            while j<len(lines):
                row=lines[j].split()
                if row and row[0]=='Image':distance='Dist.' in lines[j]
                if row and row[0].isdigit():
                    try:
                        image=int(row[0]);values=[_number(v) for v in row[1:6 if distance else 5]]
                    except ValueError:j+=1;continue
                    if image!=len(p.energies):break
                    p.energies.append(values[1] if distance else values[0])
                    if distance:p.distances.append(values[0])
                    p.forces.setdefault('max(|Fr_perp|)',[]).append(values[-2])
                    p.forces.setdefault('RMS(Fp)',[]).append(values[-1])
                    if '<= CI' in lines[j]:p.ci=image
                elif row and row[0]=='TS':pass
                elif p.energies and text and lines[j].strip():break
                j+=1
            if p.energies:profiles.append(p)
            i=j;continue
        i+=1
    return profiles,convergence


def attach_neb(document):
    path=document.path;lines=read_output_lines(path)
    is_neb=any('Nudged Elastic Band Calculation' in s or re.search(r'\bNEB(?:-TS)?\b',s) and re.match(r'^\s*\|\s*\d+>\s*!',s) for s in lines)
    direct=path.name.endswith(('.NEB.log','.interp','.interp.final','_MEP_trj.xyz','_MEP_ALL_trj.xyz'))
    if not is_neb and not direct:return
    prefix=companion_prefix(path,lines);main,convergence=_main_profiles(lines)
    run=NebRun(prefix.name,list(main),convergence)
    match=next((re.search(r'Number of images \(incl\. end points\)\s*\.+\s*(\d+)',s) for s in lines if 'Number of images (incl.' in s),None)
    if match:run.nimages=int(match[1])
    neb_path=Path(str(prefix)+'.NEB.log');interp_path=Path(str(prefix)+'.interp')
    logged=_neb_log(neb_path) if neb_path.exists() else []
    interpolated=_interp(interp_path) if interp_path.exists() else []
    if logged and run.nimages is None:run.nimages=len(logged[0].energies)
    if main and run.nimages is None:run.nimages=len(main[0].energies)
    if interpolated and run.nimages is None:run.nimages=len(interpolated[0].energies)
    run.profiles += logged+interpolated
    results=document.calculation_results
    if results:
        stage=next((s for s in results.stages if s.kind=='neb'),None)
        run.stage_index=None if stage is None else stage.index
        candidates=[s.frame_index for s in results.steps if s.frame_index is not None and s.stage_index is not None and results.stages[s.stage_index].kind=='ts']
        if candidates:run.ts_frame=candidates[-1]
    all_path=Path(str(prefix)+'_MEP_ALL_trj.xyz')
    final_path=Path(str(prefix)+'_MEP_trj.xyz')
    records=read_xyz_records(all_path) if all_path.exists() else []
    finals=read_xyz_records(final_path) if final_path.exists() else []
    groups=[]
    n=run.nimages
    if n is None and finals:
        n=run.nimages=len(finals)
    if n:
        if len(records)%n:run.notes.append('Incomplete last XYZ snapshot is excluded.')
        groups=[records[i:i+n] for i in range(0,len(records)-n+1,n)]
        if len(finals)==n:groups.append(finals)
    assigned={}
    for group in groups:
        if document.frames and any(f.symbols!=document.frames[0].symbols for f in group):
            run.notes.append('XYZ atom sequence differs; snapshot was not linked.')
            continue
        energies=[None if f.energy_ev is None else f.energy_ev/Hartree for f in group]
        matching=[p for p in logged if len(p.energies)==len(group) and all(e is not None for e in energies)
                  and np.allclose(energies,p.energies,atol=1.e-7,rtol=0)]
        if matching:
            p=matching[0]
        else:
            p=NebProfile(f'XYZ snapshot {len(assigned)+1} · unmatched iteration',str(all_path),None,energies)
            if any(e is None for e in energies):continue
            run.profiles.append(p)
        if id(p) in assigned:continue
        indices=[]
        for image,f in enumerate(group):
            f.info.update(neb_profile=len(run.profiles) and run.profiles.index(p),neb_image=image,neb_iteration=p.iteration,
                          series_key=f'neb:{p.source}:{p.iteration}:{len(assigned)}',series_label=p.label)
            if document.frames:
                for key in ('converter_charge','converter_mult'):
                    if key in document.frames[0].info:f.info[key]=document.frames[0].info[key]
            indices.append(len(document.frames));document.frames.append(f)
        if indices:p.frame_indices=indices;assigned[id(p)]=indices
    for p in interpolated+main:
        p.frame_indices=[None]*len(p.energies)
        for other in logged:
            if not other.frame_indices or len(other.energies)!=len(p.energies):continue
            delta=np.asarray(p.energies)-p.energies[0] if p.relative else np.asarray(p.energies)
            expected=np.asarray(other.energies)-other.energies[0] if p.relative else np.asarray(other.energies)
            tolerance=5.1e-6 if p.source=='main output' else 1.e-7
            if np.allclose(delta,expected,atol=tolerance,rtol=0):p.frame_indices=other.frame_indices.copy();break
    # The main output prints a CI geometry even when other image geometries
    # are absent. Keep that reference separate from later TS evaluations.
    ci_reference=None;ci_energy=None
    for i,line in enumerate(lines):
        if line.strip()=='SADDLE POINT (ANGSTROEM)':
            from .orca_results import _coordinates
            block=list(lines[i:]);block[0]='CARTESIAN COORDINATES (ANGSTROEM)'
            ci_reference,_=_coordinates(block,0)
            for preceding in lines[max(0,i-12):i]:
                value=re.match(rf'\s*Energy\s*\.+\s*({NUMBER})\s*Eh',preceding)
                if value:ci_energy=_number(value[1])
    if ci_reference is not None:
        ci_reference.energy_ev=None if ci_energy is None else ci_energy*Hartree
        ci_reference.info.update(series_key='neb:main_ci:'+str(len(document.neb_runs)),series_label='Main-output CI reference',source_kind='orca_out')
        if document.frames:
            for key in ('converter_charge','converter_mult'):
                if key in document.frames[0].info:ci_reference.info[key]=document.frames[0].info[key]
        ci_index=None
        for p in main:
            if p.ci is not None and p.ci<len(p.frame_indices) and p.frame_indices[p.ci] is None:
                if ci_index is None:ci_index=len(document.frames);document.frames.append(ci_reference)
                p.frame_indices[p.ci]=ci_index
    if logged and interpolated and logged[-1].iteration!=interpolated[-1].iteration:
        run.notes.append(f'NEB.log ends at iteration {logged[-1].iteration}; interp ends at {interpolated[-1].iteration}. Sources remain separate.')
    if any(not any(i is not None for i in p.frame_indices) for p in main+interpolated):
        run.notes.append('Profiles without a matching XYZ energy snapshot remain energy-only; no structure is substituted.')
    if not records and not finals:run.notes.append('No companion MEP XYZ files found; only printed profiles are available.')
    document.neb_runs.append(run)
