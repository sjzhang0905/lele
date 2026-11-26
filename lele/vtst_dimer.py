"""VTST dimer translation centres and rotation diagnostics."""
from pathlib import Path
import re

import numpy as np

from .calculation_results import CalculationJob, CalculationStage, NUMBER
from .output_text import check_load_cancelled, read_output_lines
from .vasp_results import ENERGY_KEY, SIGMA, TOTEN, NO_ENTROPY, VaspResults, VaspStep, number

HEADER = ('step', 'force', 'torque', 'energy', 'curvature', 'angle')
ITERATION = re.compile(r'\bIteration\s+(\d+)\(\s*(\d+)\s*\)', re.I)
ROTATION = re.compile(r'Itr\s+(\d+)\s+Rot\s+(\d+)', re.I)
METRIC = re.compile(r'(F0|FN|CN|Th)\s*(?:=\s*)?(' + NUMBER + r')\s*$', re.I)
METRIC_KEYS = {'f0': 'force', 'fn': 'torque', 'cn': 'curvature', 'th': 'angle'}


def _stage(results, line):
    i = len(results.jobs)
    job = CalculationJob(i, line, tasks={'VTST dimer saddle search'})
    stage = CalculationStage(len(results.stages), i, 'VTST dimer', 'vtst_dimer', line)
    results.jobs.append(job)
    results.stages.append(stage)
    return job, stage


def _step(results, stage, cycle, line):
    step = VaspStep(stage.job_index, line, cycle=cycle, stage_index=stage.index,
                    info={'vtst_rotations': [], 'structure_label': f'Dimer centre · step {cycle}'})
    results.steps.append(step)
    return step


def read_dimcar(path):
    results = VaspResults()
    step = stage = None
    pending_error = None
    for i, raw in enumerate(read_output_lines(path), 1):
        check_load_cancelled()
        fields = raw.split()
        if not fields or raw.lstrip().startswith(('#', '!')):
            continue
        if tuple(f.lower() for f in fields) == HEADER:
            stage = step = None
            continue
        if pending_error:
            raise ValueError(f'Invalid DIMCAR record at line {pending_error}.')
        if len(fields) < 6:
            pending_error = i
            continue
        try:
            if len(fields) != 6:
                raise ValueError
            cycle = int(fields[0])
            force, energy = number(fields[1]), number(fields[3])
            final_centre = fields[2] == fields[4] == fields[5] == '---'
            if not final_centre:
                torque, curvature, angle = (number(fields[k]) for k in (2, 4, 5))
        except ValueError:
            raise ValueError(f'Invalid DIMCAR record at line {i}.') from None
        if stage is None or (step is not None and cycle < step.cycle):
            _, stage = _stage(results, i)
            step = None
        if step is None or step.cycle != cycle:
            step = _step(results, stage, cycle, i)
        entry = dict(line=i, force=force, centre_energy=energy)
        if final_centre:
            step.info['vtst_final_centre'] = entry
        else:
            rows = step.info['vtst_rotations']
            rows.append(dict(entry, rotation=len(rows)+1, torque=torque, curvature=curvature, angle=angle))
        stage.end_line = i
    if not results.steps:
        raise ValueError('No complete VTST DIMCAR records.')
    results.note = 'DIMCAR records contain the centre energy and rotation diagnostics. Coordinates, E0 and termination status are supplied by separate outputs.'
    if pending_error:
        results.note += f' Incomplete trailing record at line {pending_error} omitted.'
    return results


def _evaluations(run):
    """Group sparse records by VASP ionic evaluation in both energy/force print orders."""
    cell_line = ionic = None
    record = {}
    ionic_summary = False
    for i in run.numbers:
        check_load_cancelled()
        line = run.records[i][1].strip()
        lower = line.lower()
        it = ITERATION.search(line) if 'iteration' in lower else None
        if it:
            if ionic != int(it[1]) or int(it[2]) == 1:
                if record:
                    yield record
                record = {}
                ionic = int(it[1])
            ionic_summary = False
        elif 'direct lattice vectors' in lower:
            cell_line = i
        elif lower.startswith('position') and re.match(r'position\s+total-force', lower):
            if 'position' in record:
                yield record
                record = {}
            record.update(position=i, cell_line=cell_line)
            ionic_summary = True
        elif 'free energie of the ion-electron system' in lower:
            if 'position' in record and ENERGY_KEY in record:
                yield record
                record = {}
            ionic_summary = True
        elif ionic_summary and ('entropy' in lower or 'toten' in lower):
            for pattern, key in ((SIGMA, ENERGY_KEY), (TOTEN, 'vasp_free_energy_ev'),
                                 (NO_ENTROPY, 'vasp_energy_without_entropy_ev')):
                match = pattern.search(line)
                if match:
                    record[key] = number(match[1])
        elif lower.startswith('dimer:'):
            detail = line.split(':', 1)[1].strip()
            rotation = ROTATION.match(detail)
            if rotation:
                record.update(cycle=int(rotation[1]), rotation=int(rotation[2]), line=i)
            elif detail.lower().startswith('central point'):
                record['central'] = True
            else:
                metric = METRIC.fullmatch(detail)
                if metric:
                    record[METRIC_KEYS[metric[1].lower()]] = number(metric[2])
        elif 'reached required accuracy' in lower:
            record['converged'] = True
        elif 'general timing and accounting' in lower:
            record['finished'] = True
    if record:
        yield record


def read_dimer_segment(run, results, counts, species, symbols, tags, *, last_only=False):
    from .vasp_results import _frame
    job, stage = _stage(results, run.start+1)
    stage.end_line = run.start + len(run)
    job.route = ', '.join(f'{k}={tags[k]:g}' for k in ('IBRION','EDIFFG','ENCUT') if k in tags)
    centres = {}
    structures = []
    for record in _evaluations(run):
        if record.get('finished'):
            job.termination = 'Normal completion (timing summary printed)'
        if record.get('converged'):
            stage.status = 'Converged (printed)'
        if 'cycle' not in record:
            continue
        cycle = record['cycle']
        rotation = record['rotation']
        step = centres.get(cycle)
        if step is None:
            step = centres[cycle] = _step(results, stage, cycle, run.start + record['line'] + 1)
        if rotation == 0 or record.get('central'):
            if 'position' in record:
                structures.append((step, record['position'], record['cell_line']))
            for key in (ENERGY_KEY, 'vasp_free_energy_ev', 'vasp_energy_without_entropy_ev'):
                if key in record:
                    step.info[key] = record[key]
            step.energy_ev = step.info.get(ENERGY_KEY)
            if step.energy_ev is not None:
                job.energy_ev = step.energy_ev
            if 'force' in record:
                step.info['vtst_force'] = record['force']
            step.converged = bool(record.get('converged'))
        else:
            rows = step.info['vtst_rotations']
            if not rows or rows[-1]['rotation'] != rotation:
                rows.append(dict(rotation=rotation, line=run.start+record['line']+1))
            for key in ('force','torque','curvature','angle'):
                if key in record:
                    rows[-1][key] = record[key]
    # Displaced force evaluations never supply geometry or E0 for a centre.
    for step, pos_line, lattice_line in (reversed(structures) if last_only else structures):
        check_load_cancelled()
        if not symbols:
            continue
        rows, _ = run.rows(pos_line+1, 6, len(symbols))
        if len(rows) != len(symbols):
            continue
        cell = np.zeros((3,3))
        if lattice_line is not None:
            vectors, _ = run.rows(lattice_line+1, 3, 3)
            if len(vectors) == 3:
                cell = vectors
        info = {'poscar_groups': list(zip(species, counts)), 'vtst_position_line': run.start+pos_line+1}
        if 'NELECT' in tags:
            info['vasp_nelect'] = tags['NELECT']
        step.geometry = _frame(symbols, rows[:,:3].copy(), cell, info)
        if step.energy_ev is not None:
            step.info['energy_source'] = 'E0 (σ→0)'
        if last_only:
            break
    results.note += ' VTST dimer frames are translation centres. E0 and centre free energy come from the ionic evaluation of each centre.'


def records(results):
    for step in results.steps:
        if 'vtst_rotations' not in step.info:
            continue
        base = dict(job=step.job_index+1, step=step.cycle, frame=step.frame_index, line=step.source_line,
                    e0=step.energy_ev, centre_energy=step.info.get('vasp_free_energy_ev'),
                    force=step.info.get('vtst_force'))
        rotations = step.info['vtst_rotations']
        for row in rotations:
            yield {**base, **row}
        final_centre = step.info.get('vtst_final_centre')
        if final_centre or not rotations:
            yield {**base, **(final_centre or {})}


def read_mode(path):
    from .formats import load_document
    from .core import Document
    stem = re.match(r'(NEWMODECAR|MODECAR)', path.name, re.I)
    target = 'CENTCAR' if stem[1].upper() == 'NEWMODECAR' else 'POSCAR'
    reference = path.with_name(target + path.name[stem.end():])
    if not reference.is_file():
        raise ValueError(f'Open {path.name} alongside its corresponding {reference.name} for atom identities and positions.')
    source = load_document(reference)
    frame = source.frames[0]
    rows = [line.split() for line in read_output_lines(path) if line.strip()]
    if len(rows) != len(frame.symbols) or any(len(row) != 3 for row in rows):
        raise ValueError('The direction file must contain one Cartesian three-vector per reference atom.')
    vectors = np.asarray([[number(v) for v in row] for row in rows])
    if not np.any(vectors):
        raise ValueError('The dimer direction is zero.')
    frame.info['vtst_dimer_mode'] = vectors
    return Document(Path(path), 'VTST dimer direction', [frame],
                    note=f'Geometry from {reference.name}. Arrows show the Cartesian dimer direction from {path.name}.')
