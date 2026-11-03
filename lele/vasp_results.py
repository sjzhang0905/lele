"""Independent, printed-only VASP OUTCAR, OSZICAR and XDATCAR records.

Never open a neighbouring POSCAR, CONTCAR, POTCAR or results file. Ionic
energies, coordinates and normal-mode references keep their own source lines.
"""
from dataclasses import dataclass, field
import re

import numpy as np
from ase.data import atomic_masses, atomic_numbers

from .calculation_results import (CalculationJob, CalculationResults,
                                  CalculationStage, CalculationStep, NUMBER)
from .core import Frame, NormalMode, VibrationalAnalysis
from .output_text import read_output_lines, check_load_cancelled, load_progress, scan_lines

VERSION = re.compile(r'^\s*vasp\.\d', re.I)
CONFIG = re.compile(r'^\s*(Direct|Cartesian)\s+configuration\s*=\s*(\d+)', re.I)
TOTEN = re.compile(rf'^\s*free\s+energy\s+TOTEN\s*=\s*({NUMBER})', re.I)
SIGMA = re.compile(rf'energy\s*\(sigma\s*->\s*0\)\s*=\s*({NUMBER})', re.I)
NO_ENTROPY = re.compile(rf'^\s*energy\s+without\s+entropy\s*=\s*({NUMBER})', re.I)
FREQUENCY = re.compile(rf'^\s*(\d+)\s+f\s*(/i)?\s*=.*?({NUMBER})\s+cm-1', re.I)
ENERGY_KEY = 'vasp_energy_sigma0_ev'
ENERGY_LABEL = 'E0 (σ→0)'
ENERGIES = ((ENERGY_KEY, ENERGY_LABEL),)
ENERGY_NOTE = 'Energy: E0 (σ→0) only, in eV. Missing E0 values remain unavailable.'


def number(value):
    result = float(value.replace('D', 'E').replace('d', 'e'))
    if not np.isfinite(result):
        raise ValueError('Non-finite VASP value')
    return result


@dataclass
class VaspStep(CalculationStep):
    info: dict = field(default_factory=dict)


class VaspResults(CalculationResults):
    def __init__(self):
        super().__init__('VASP', force_unit='eV/Å (Cartesian components)',
                         displacement_unit='Å')
        self.vibrations = []
        self.frequency_records = []

    def frames(self, max_frames=None):
        # Equal positions can still represent different times or unit cells.
        frames = []
        for _,step in scan_lines(self.steps,'VASP: collecting structure frames'):
            check_load_cancelled()
            step.frame_index = None
            if step.geometry is None:
                continue
            if max_frames is not None and len(frames) >= max_frames:
                raise ValueError(f'Trajectory exceeds {max_frames} frames')
            frame = step.geometry.clone()
            frame.energy_ev = step.energy_ev
            frame.info.update(step.info, calculation_index=step.job_index,
                              source_line=step.source_line,
                              stage_index=step.stage_index,
                              optimization_cycle=step.cycle)
            step.frame_index = len(frames)
            if step.converged:frame.info['optimization_converged']=True
            frames.append(frame)
        return frames


def energy_lines(info):
    return [f'{label}: {info[key]:.9f} eV' for key, label in ENERGIES if key in info]


def normalize_document_e0(document, extra_frames=()):
    """Apply the current energy policy to legacy project snapshots as well.

    Raw printed fields stay available as source metadata. An energy cleared
    by a structural edit stays cleared, even if its old E0 metadata remains.
    """
    results = document.calculation_results
    if results is None or results.program != 'VASP':return
    for step in results.steps:
        step.energy_ev = getattr(step, 'info', {}).get(ENERGY_KEY)
    frames = list(document.frames)+list(extra_frames)
    frames += [a.reference for a in document.vibrations]
    frames += [a.reference for a in getattr(results, 'vibrations', [])]
    for frame in frames:
        if frame.energy_ev is not None:frame.energy_ev = frame.info.get(ENERGY_KEY)
        if frame.energy_ev is None:frame.info.pop('energy_source', None)
        else:frame.info['energy_source'] = ENERGY_LABEL
    for job in results.jobs:
        job.energy_ev = next((s.energy_ev for s in reversed(results.steps)
                              if s.job_index == job.index and s.energy_ev is not None), None)
        for analysis in document.vibrations:
            stage = next((s for s in results.stages if s.index == analysis.stage_index), None)
            if stage is not None and stage.job_index == job.index and stage.kind == 'frequency':
                job.energy_ev = analysis.reference.energy_ev
    legacy_notes = (
        'Default energy: σ→0, then TOTEN, then energy without entropy, in eV.',
        'E0 is preferred, then F (eV).')
    for obj in (document, results):
        for old in legacy_notes:obj.note = obj.note.replace(old, ENERGY_NOTE)


def _rows(lines, start, columns, count=None):
    """Convert normal numeric blocks together; retain the legacy odd-layout reader."""
    from .trajectory_io import numeric_array
    rows=[];i=start
    while i<len(lines) and (count is None or len(rows)<count):
        text=lines[i].strip()
        if not rows and (not text or set(text)=={'-'}):i+=1;continue
        if not text or text[0] not in '+-.0123456789':break
        fields=text.split()
        if len(fields)<columns:return _rows_legacy(lines,start,columns,count)
        rows.append(fields);i+=1
    try:
        array=numeric_array(rows).reshape(len(rows),-1) if rows else np.empty((0,columns))
        if np.isfinite(array).all():return array[:,:columns],i
    except (ValueError,TypeError):pass
    return _rows_legacy(lines,start,columns,count)


def _rows_legacy(lines, start, columns, count=None):
    """Consume one contiguous complete numeric table, never a later table."""
    rows = []
    i = start
    while i < len(lines) and (count is None or len(rows) < count):
        fields = re.findall(NUMBER, lines[i])
        if not rows and (not lines[i].strip() or set(lines[i].strip()) == {'-'}):
            i += 1
            continue
        try:
            if len(fields) < columns or re.sub(NUMBER, '', lines[i]).strip():
                break
            row = [number(x) for x in fields[:columns]]
        except ValueError:
            break
        rows.append(row)
        i += 1
    return np.asarray(rows, float).reshape(-1, columns), i


def _species(lines, marker):
    found = []
    for _,line in scan_lines(lines,'VASP: identifying metadata'):
        match = re.match(r'^\s*'+marker, line)
        if match:
            for token in line[match.end():].split():
                symbol = token.split('_')[0].strip(':')
                if symbol in atomic_numbers:
                    found.append(symbol)
                    break
    return found


def _tag(lines, key):
    pattern = re.compile(r'\b'+key+rf'\s*=\s*({NUMBER})')
    values = [number(m[1]) for line in lines if (m := pattern.search(line))]
    return values[-1] if values else None


def _metadata(lines):
    # Scan headers/tags together once, rather than re-scanning a long OUTCAR
    # separately for every INCAR tag and species-label convention.
    counts=None;labels={key:[] for key in ('TITEL','POTCAR','VRHFIN')};masses=[];tags={}
    tag=re.compile(r'\b(NIONS|IBRION|ISIF|ENCUT|EDIFF|EDIFFG|ISPIN|NELECT)\s*=\s*('+NUMBER+r')')
    for _,line in scan_lines(lines,'VASP: reading metadata'):
        stripped=line.lstrip()
        if counts is None and 'ions per type' in line:
            counts=[int(x) for x in re.findall(r'\d+',line.split('=',1)[1])]
        for key,separator in (('TITEL','='),('POTCAR',':'),('VRHFIN','=')):
            if stripped.startswith(key) and re.match(r'^'+key+r'\s*'+separator,stripped):
                for token in stripped.split(separator,1)[1].split():
                    symbol=token.split('_')[0].strip(':')
                    if symbol in atomic_numbers:labels[key].append(symbol);break
        if stripped.startswith('POMASS') and '=' in line:
            candidate=re.findall(NUMBER,line.split('=',1)[1].split(';',1)[0])
            if candidate:masses.append([number(x) for x in candidate])
        if '=' in line:
            for match in tag.finditer(line):tags[match[1]]=number(match[2])
    counts=counts or []
    species=next((candidate[:len(counts)] for candidate in labels.values() if counts and len(candidate)>=len(counts)),[])
    symbols=[s for s,n in zip(species,counts) for _ in range(n)]
    by_type=next((x for x in reversed(masses) if len(x)==len(counts)),None)
    if by_type is None and len(masses)>=len(counts) and counts:by_type=[x[0] for x in masses[:len(counts)]]
    expanded=([m for m,n in zip(by_type,counts) for _ in range(n)] if by_type else
              [atomic_masses[atomic_numbers[s]] for s in symbols])
    return counts,species,symbols,np.asarray(expanded),bool(by_type),tags


def _frame(symbols, positions, cell, info):
    if len(symbols) != len(positions) or not symbols:
        return None
    periodic = abs(np.linalg.det(cell)) > 1.e-12
    return Frame(list(symbols), positions, cell.copy(), (periodic,)*3, info=dict(info))


def _read_outcar_segment(lines, offset, results):
    counts, species, symbols, masses, printed_masses, tags = _metadata(lines)
    natoms = sum(counts) or int(tags.get('NIONS') or 0)
    ibrion = tags.get('IBRION')
    frequency = ibrion in (5, 6, 7, 8)
    kind, name = ('frequency', 'Finite-displacement structures' if ibrion in (5, 6)
                  else 'Frequency calculation structures') if frequency else (
        ('md', 'Molecular dynamics') if ibrion == 0 else
        ('optimization', 'Geometry optimization') if ibrion in (1, 2, 3, 44) else
        ('single_point', 'Printed ionic records'))
    ji, si = len(results.jobs), len(results.stages)
    task = {
        'frequency': 'Frequency', 'md': 'Molecular dynamics',
        'optimization': 'Optimization', 'single_point': 'Single point / properties'}[kind]
    job = CalculationJob(ji, offset+1, tasks={task})
    job.route = ', '.join(f'{key}={value:g}' for key in ('IBRION', 'ISIF', 'ENCUT', 'EDIFF', 'EDIFFG', 'ISPIN')
                          if (value := tags.get(key)) is not None)
    results.jobs.append(job)
    stage = CalculationStage(si, ji, name, kind, offset+1, offset+len(lines))
    results.stages.append(stage)
    info = {'poscar_groups': list(zip(species, counts))} if species else {}
    nelect = tags.get('NELECT')
    if nelect is not None:
        info['vasp_nelect'] = nelect
    cell = np.zeros((3, 3))
    current = None
    initial = None
    cycle = 0
    first_step = len(results.steps)
    raw_modes, modes_divided, mode_reference = {}, {}, None
    divided = False
    in_modes = False
    in_scf = False
    i = 0
    progress=load_progress('VASP: ionic structures, energies and modes',len(lines))
    while i < len(lines):
        check_load_cancelled()
        progress(i)
        line = lines[i]
        source = offset+i+1
        iteration = re.search(r'Iteration\s+\d+\(\s*(\d+)\)', line)
        if iteration:
            in_scf = True
            current = None
            job.scf_cycles = int(iteration[1])
        if 'FREE ENERGIE OF THE ION-ELECTRON SYSTEM' in line.upper():
            in_scf = False
        if 'direct lattice vectors' in line.lower():
            rows, end = _rows(lines, i+1, 3, 3)
            if len(rows) == 3:
                cell = rows
                results.periodic_geometry_seen = True
                i = end
                continue
        if 'position of ions in cartesian coordinates' in line.lower() and natoms:
            rows, end = _rows(lines, i+1, 3, natoms)
            if len(rows) == natoms:
                initial = (_frame(symbols, rows, cell, info), source)
                i = end
                continue
        if re.match(r'^\s*POSITION\s+TOTAL-FORCE', line, re.I):
            in_scf = False
            rows, end = _rows(lines, i+1, 6, natoms or None)
            cycle += 1
            frame = _frame(symbols, rows[:, :3], cell, info) if len(rows) == natoms else None
            current = VaspStep(ji, source, frame, stage_index=si, cycle=cycle)
            if frame is not None:
                force = rows[:, 3:]
                values = {'max_force': float(np.abs(force).max()),
                          'rms_force': float(np.sqrt(np.mean(force**2)))}
                current.convergence = {key: (value, None) for key, value in values.items()}
                frame.info.update({'cartesian_'+key+'_ev_ang': value for key, value in values.items()})
            else:
                results.note += f' Incomplete coordinates or missing species at line {source}; no geometry assigned.'
            results.steps.append(current)
            i = end
            continue
        energy = TOTEN.match(line)
        no_entropy, sigma = NO_ENTROPY.search(line), SIGMA.search(line)
        if (energy or no_entropy or sigma) and not in_scf:
            # Initial electronic iterations can also print TOTEN. Only the
            # ionic summary (or a standalone summary excerpt) belongs here.
            repeated = current is not None and any(match and key in current.info for match, key in (
                (energy, 'vasp_free_energy_ev'), (no_entropy, 'vasp_energy_without_entropy_ev'),
                (sigma, 'vasp_energy_sigma0_ev')))
            if current is None or repeated:
                cycle += 1
                current = VaspStep(ji, source, stage_index=si, cycle=cycle)
                results.steps.append(current)
            for match, key in ((energy, 'vasp_free_energy_ev'), (no_entropy, 'vasp_energy_without_entropy_ev'),
                               (sigma, 'vasp_energy_sigma0_ev')):
                if match:
                    current.info[key] = number(match[1])
            current.energy_ev = current.info.get(ENERGY_KEY)
            if current.energy_ev is not None:current.info['energy_source'] = ENERGY_LABEL
        if 'reached required accuracy' in line:
            stage.status = 'Converged (printed)'
            if current is not None:
                current.converged = True
        if 'General timing and accounting' in line:
            job.termination = 'Normal completion (timing summary printed)'
        if 'Eigenvectors and eigenvalues of the dynamical matrix' in line:
            in_modes, divided = True, False
            current = None
        if 'Eigenvectors after division by SQRT(mass)' in line:
            in_modes, divided = True, True
        match = FREQUENCY.match(line) if in_modes else None
        if match:
            value = number(match[3]) * (-1 if match[2] else 1)
            key = int(match[1])
            j = i+1
            while j < min(len(lines), i+5) and not re.search(r'\bdx\s+dy\s+dz\b', lines[j], re.I):
                j += 1
            rows, end = _rows(lines, j+1, 6, natoms or None) if j < min(len(lines), i+5) else (np.empty((0, 6)), i+1)
            vectors = None
            if natoms and len(rows) == natoms and len(symbols) == natoms:
                reference = _frame(symbols, rows[:, :3], cell, info)
                if mode_reference is None:
                    mode_reference = reference
                if np.allclose(reference.positions, mode_reference.positions, atol=1.e-6, rtol=0):
                    if divided:
                        vectors = rows[:, 3:]
                    elif len(masses) == natoms and np.all(masses > 0):
                        vectors = rows[:, 3:] / np.sqrt(masses[:, None])
            mode = NormalMode(key, value, vectors)
            (modes_divided if divided else raw_modes)[key] = (mode, source)
            i = max(i+1, end)
            continue
        i += 1
    progress(len(lines))
    modes = dict(raw_modes)
    for key, pair in modes_divided.items():
        if pair[0].can_animate or key not in modes or not modes[key][0].can_animate:
            modes[key] = pair
    if modes:
        ordered = [pair[0] for pair in modes.values()]
        job.frequency_count = len(ordered)
        job.imaginary_modes = sum(m.imaginary for m in ordered)
        job.tasks.add('Frequency')
        for mode, source in modes.values():
            results.frequency_records.append(dict(job_index=ji, number=mode.number,
                frequency_cm1=mode.frequency_cm1, source_line=source))
        if mode_reference is not None:
            matched = next((s for s in results.steps[first_step:] if s.geometry is not None
                            and s.geometry.symbols == mode_reference.symbols
                            and np.allclose(s.geometry.positions, mode_reference.positions, atol=1.e-5, rtol=0)), None)
            if matched is not None:
                mode_reference.energy_ev = matched.energy_ev
                mode_reference.info.update(matched.info)
                mode_reference.info['vasp_reference_source_line'] = matched.source_line
            note = ('VASP f/i modes are negative. Cartesian animation vectors use the printed '
                    'SQRT(mass)-divided table when available, otherwise the dynamical-matrix '
                    'eigenvectors divided by SQRT(POMASS). Intensities are not supplied by this reader.')
            if not printed_masses:
                note += ' POMASS absent: standard elemental masses used.'
            results.vibrations.append(VibrationalAnalysis(mode_reference, ordered,
                min(pair[1] for pair in modes.values()), note,
                purpose='VASP normal modes', stage_index=si))
    own = results.steps[first_step:]
    if not any(s.geometry is not None for s in own):
        # An initial orientation is real structure, but its energy is not
        # assumed to match any coordinate-free energy record.
        if initial is not None and initial[0] is not None:
            results.steps.insert(first_step, VaspStep(ji, initial[1], initial[0], stage_index=si, cycle=0))
        elif mode_reference is not None:
            results.steps.insert(first_step, VaspStep(ji, results.vibrations[-1].source_line,
                mode_reference.clone(), stage_index=si, cycle=0))
    energies = [s.energy_ev for s in results.steps[first_step:] if s.energy_ev is not None]
    job.energy_ev = energies[-1] if energies else None
    if frequency and mode_reference is not None:
        job.energy_ev = mode_reference.energy_ev
    if any(s.geometry is not None and not any(s.geometry.pbc) for s in results.steps[first_step:]):
        results.note += ' Cell not printed for some structures; only their Cartesian coordinates are available, without periodic images.'
    if stage.status == 'Not confirmed' and job.termination.startswith('Normal'):
        stage.status = 'Finished (convergence not assumed)'
    results.note += (' '+ENERGY_NOTE+' '
                     'Force curves use Cartesian maximum/RMS components; no unprinted thresholds are assumed.')


def read_vasp_results(path):
    lines = read_output_lines(path)
    results = VaspResults()
    boundaries = [i for i, line in scan_lines(lines,'VASP: identifying runs') if VERSION.match(line)]
    starts = [0] + boundaries[1:]
    for start, end in zip(starts, starts[1:]+[len(lines)]):
        _read_outcar_segment(lines[start:end], start, results)
    results.note = ' '.join(dict.fromkeys(results.note.split('  '))).strip()
    return results


def read_oszicar(path):
    results = VaspResults()
    job = CalculationJob(0, 1, tasks={'Ionic energy records'})
    results.jobs.append(job)
    results.stages.append(CalculationStage(0, 0, 'Ionic energies (no coordinates)', 'energy', 1))
    for i, line in scan_lines(read_output_lines(path),'VASP: ionic energy records'):
        match = re.match(r'^\s*(\d+)\s+(?:F\s*=|T\s*=)', line)
        if not match:
            continue
        info = {}
        for name, key in (('F', 'vasp_free_energy_ev'), ('E0', 'vasp_energy_sigma0_ev')):
            value = re.search(r'\b'+name+rf'\s*=\s*({NUMBER})', line)
            if value:
                info[key] = number(value[1])
        if info:
            value = info.get(ENERGY_KEY)
            if value is not None:info['energy_source'] = ENERGY_LABEL
            results.steps.append(VaspStep(0, i+1, energy_ev=value,
                stage_index=0, cycle=int(match[1]), info=info))
            if value is not None:job.energy_ev = value
    results.note = 'OSZICAR ionic summaries only; electronic iterations are excluded. '+ENERGY_NOTE+' No companion files are read.'
    return results


def _xdat_header(lines, start):
    title = lines[start].split()
    scale = np.asarray([number(x) for x in lines[start+1].split()])
    cell = np.asarray([[number(x) for x in line.split()[:3]] for line in lines[start+2:start+5]])
    if cell.shape != (3, 3) or len(scale) not in (1, 3):
        raise ValueError('Incomplete XDATCAR lattice header')
    if len(scale) == 1 and scale[0] < 0:
        scale = np.array([(abs(scale[0]) / abs(np.linalg.det(cell)))**(1/3)])
    if np.any(scale <= 0):
        raise ValueError('Invalid XDATCAR scale')
    cell = cell * scale
    if abs(np.linalg.det(cell)) < 1.e-12:
        raise ValueError('Singular XDATCAR cell')
    tokens = lines[start+5].split()
    if all(t.isdigit() for t in tokens):
        counts, species, end = [int(x) for x in tokens], title, start+6
    else:
        species, counts, end = tokens, [int(x) for x in lines[start+6].split()], start+7
    if not counts or len(species) != len(counts) or not all(s in atomic_numbers for s in species) or sum(counts) <= 0:
        raise ValueError('XDATCAR needs printed element symbols and atom counts; no companion species are assumed')
    if end < len(lines) and lines[end].strip().lower().startswith('selective'):
        end += 1
    return cell, scale, species, counts, end


def read_xdatcar(path, max_frames=None):
    from .output_text import open_output_text
    from .trajectory_io import numeric_array
    results=VaspResults()
    results.jobs.append(CalculationJob(0,1,tasks={'Structure trajectory'}))
    results.stages.append(CalculationStage(0,0,'XDATCAR trajectory','trajectory',1))
    results.periodic_geometry_seen=True
    from pathlib import Path
    size=Path(path).stat().st_size
    progress=load_progress('VASP: XDATCAR coordinate frames',size)
    with open_output_text(path) as stream:
        line_number=0;pending=None
        def take():
            nonlocal line_number,pending
            if pending is not None:
                item=pending;pending=None;return item
            raw=stream.readline()
            if not raw:return None
            line_number+=1
            return line_number,raw.rstrip('\r\n')
        def header(first):
            nonlocal pending
            rows=[first[1]]
            for _ in range(5):
                item=take()
                if item is None:raise ValueError('Incomplete XDATCAR header')
                rows.append(item[1])
            # VASP4 count-only headers have six lines; identified species need
            # a seventh counts line. _xdat_header retains the existing policy
            # for missing element labels and all cell/scale conventions.
            if not all(x.isdigit() for x in rows[5].split()):
                item=take()
                if item is None:raise ValueError('Incomplete XDATCAR counts')
                rows.append(item[1])
            item=take()
            if item is not None:
                if item[1].strip().lower().startswith('selective'):rows.append(item[1])
                else:pending=item
            return _xdat_header(rows,0)[:4]
        first=take()
        while first is not None and not first[1].strip():first=take()
        if first is None:raise ValueError('Empty XDATCAR')
        cell,scale,species,counts=header(first)
        while True:
            check_load_cancelled()
            progress(min(max(0,size-1),stream.buffer.tell()))
            item=take()
            if item is None:break
            source,text=item
            if not text.strip():continue
            match=CONFIG.match(text)
            if match is None:
                try:cell,scale,species,counts=header(item);continue
                except (ValueError,IndexError):
                    results.note=f'Incomplete trailing XDATCAR header at line {source}; complete frames retained.';break
            rows=[]
            for _ in range(sum(counts)):
                item=take()
                if item is None:break
                fields=item[1].split()
                if len(fields)<3:break
                rows.append(fields)
            try:
                numeric=numeric_array(rows)
                complete=(len(rows)==sum(counts) and numeric.ndim==2 and numeric.shape[1]>=3
                          and np.isfinite(numeric).all())
            except (ValueError,TypeError):complete=False
            if not complete:
                results.note=f'Incomplete XDATCAR configuration at line {source}; complete frames retained.';break
            if max_frames is not None and len(results.steps)>=max_frames:
                raise ValueError(f'Trajectory exceeds {max_frames} frames')
            positions=numeric[:,:3]@cell if match[1].lower()=='direct' else numeric[:,:3]*scale
            symbols=[s for s,n in zip(species,counts) for _ in range(n)]
            frame=_frame(symbols,positions,cell,{'poscar_groups':list(zip(species,counts))})
            results.steps.append(VaspStep(0,source,frame,stage_index=0,cycle=int(match[2])))
    progress(size)
    results.note=('XDATCAR contains structure records only; no energies or times are assumed. '+results.note).strip()
    return results
