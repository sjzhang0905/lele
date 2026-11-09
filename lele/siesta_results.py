"""Printed SIESTA ionic records, with independent geometry/energy provenance."""
from dataclasses import dataclass, field
import re

import numpy as np

from .calculation_results import CalculationJob, CalculationResults, CalculationStage, CalculationStep
from .core import Frame
from .output_text import read_output_lines, check_load_cancelled, load_progress
from .siesta_trajectory import (NUMBER, ENERGY, SPECIES, CELL_HEADER, COORD_HEADER,
    BOHR, SPIN_FLAG, _symbol, _number, _extract_coordinates, _frame_energy_map)

MOVE = re.compile(r'^\s*(?:siesta:\s*)?Begin\s+(FIRE|CG|Broyden|MD|Verlet|Nose)[\w .-]*?\s+(?:move|step)\s*=\s*(\d+)', re.I)
TOTAL = re.compile(r'^\s*siesta:\s*Total\s*=\s*(' + NUMBER.pattern + r')', re.I)
FREE = re.compile(r'^\s*siesta:\s*FreeEng\s*=\s*(' + NUMBER.pattern + r')', re.I)
ATOMS = re.compile(r'^\s*(?:redata:\s*)?Number\s*Of\s*Atoms\s*(?:=|:)?\s*(\d+)\b', re.I)
SCF_DONE = re.compile(r'SCF cycle converged after\s+(\d+)\s+iterations', re.I)
RUN = re.compile(r'^\s*(?:Executable\s*:\s*siesta\b|Siesta\s+Version\s*:)', re.I)


@dataclass
class SiestaStep(CalculationStep):
    info: dict = field(default_factory=dict)


def results_from_frames(frames, note=''):
    """Retain an ANI/MDE association already verified by the history reader."""
    result = CalculationResults('SIESTA', note=note)
    result.jobs.append(CalculationJob(0, 1, tasks={'Trajectory'}))
    for i, frame in enumerate(frames):
        result.steps.append(SiestaStep(0, int(frame.info.get('source_line', 1)),
            geometry=frame.clone(), energy_ev=frame.energy_ev, frame_index=i,
            cycle=frame.info.get('optimization_cycle', i+1),
            info={'energy_source': frame.info.get('energy_source', 'SIESTA trajectory')}))
    result.jobs[0].energy_ev = next((f.energy_ev for f in reversed(frames) if f.energy_ev is not None), None)
    result.periodic_geometry_seen = any(any(f.pbc) for f in frames)
    return result


def read_siesta_records(path, max_frames=None):
    """Keep every printed structure; match energies by explicit ionic move.

    SCF table rows never become ionic steps. Initial coordinates and final
    '(unrelaxed)' coordinates stay separate from evaluated ionic geometries.
    Unmarked old outputs retain the conservative complete-count association.
    """
    lines = read_output_lines(path)
    result = CalculationResults('SIESTA', force_unit='eV/Å')
    frames, records, groups, warnings = [], [], [], []
    geometry_contexts, first_cells = [], {}
    species, cell, atom_count, spin = {}, None, None, None
    current = None
    final_energy_block = False
    job = CalculationJob(0, 1)
    result.jobs.append(job)
    stage = None
    j = 0
    progress = load_progress('SIESTA: ionic steps and printed energies', len(lines))

    def start_stage(solver, line):
        item = CalculationStage(len(result.stages), job.index,
            solver+' trajectory' if solver.lower() in ('md', 'verlet', 'nose') else solver+' optimization',
            'molecular_dynamics' if solver.lower() in ('md', 'verlet', 'nose') else 'optimization', line)
        result.stages.append(item)
        job.tasks.add('Molecular dynamics' if item.kind == 'molecular_dynamics' else 'Geometry optimization')
        return item

    while j < len(lines):
        check_load_cancelled(); progress(j)
        raw = lines[j]
        if RUN.match(raw) and (any(f.info['calculation_index'] == job.index for f in frames)
                              or any(r[3] == job.index for r in records)):
            if stage is not None: stage.end_line = j
            job = CalculationJob(len(result.jobs), j+1)
            result.jobs.append(job)
            current, stage, cell, species, atom_count, spin = None, None, None, {}, None, None
            final_energy_block = False
        sm = SPECIES.search(raw)
        if sm:
            z = abs(int(sm.group(2)))
            name = _symbol(sm.group(3), {}) or _symbol(str(z), {})
            if name: species[int(sm.group(1))] = name
        count = ATOMS.search(raw)
        if count: atom_count = int(count.group(1))
        spin_match = SPIN_FLAG.search(raw)
        if spin_match: spin = spin_match.group(1).lower() in ('.true.', 'true', 'yes', 't')
        if re.match(r'^\s*Spin\s+polarized\b', raw, re.I): spin = True
        move = MOVE.search(raw)
        if move:
            solver, cycle = move.group(1), int(move.group(2))
            if stage is None or (current is not None and cycle <= current['cycle']):
                if stage is not None: stage.end_line = j
                stage = start_stage(solver, j+1)
            current = {'job': job.index, 'stage': stage.index, 'cycle': cycle,
                       'source_line': j+1, 'frames': [], 'records': []}
            groups.append(current)
            final_energy_block = False
        if re.search(r'siesta:\s*Final energy', raw, re.I): final_energy_block = True
        elif re.search(r"siesta:\s*Program.s energy decomposition", raw, re.I): final_energy_block = False
        em = ENERGY.search(raw)
        tm = TOTAL.search(raw)
        fm = FREE.search(raw)
        record = None
        if em:
            kind = 'etot' if em.group(1).lower().replace('_','').replace('-','') == 'etot' else 'e_ks'
            record = (j, kind, _number(em.group(2)), job.index)
        elif tm:
            record = (j, 'final_total' if final_energy_block else 'total', _number(tm.group(1)), job.index)
        if record is not None and np.isfinite(record[2]):
            records.append(record)
            if current is not None: current['records'].append(record)
        if fm and current is not None:
            value = _number(fm.group(1))
            if np.isfinite(value): current['free_energy_ev'] = value
        scf = SCF_DONE.search(raw)
        if scf:
            job.scf_cycles = int(scf.group(1))
            if current is not None: current['scf_cycles'] = job.scf_cycles
        if re.search(r'^(?:\s*Job completed|\s*>>\s*End of run)', raw, re.I):
            job.termination = 'Normal termination'
        if (stage is not None and re.search(r'(?:geometry|optimization|FIRE|Broyden|CG).*\bconverged\b', raw, re.I)
                and not re.search(r'SCF|population|\bnot\b|\bno\b', raw, re.I)):
            stage.status = 'Converged'
        if CELL_HEADER.search(raw):
            rows = []
            for line in lines[j+1:j+5]:
                line = line.split(':', 1)[1] if line.strip().lower().startswith(('outcell:', 'siesta:')) else line
                values = NUMBER.findall(line)
                if len(values) >= 3: rows.append([_number(x) for x in values[:3]])
                if len(rows) == 3: break
            if len(rows) == 3:
                cell = np.asarray(rows) * (BOHR if 'bohr' in raw.lower() else 1.)
                first_cells.setdefault(job.index, cell.copy())
                if current is not None: current['cell'] = cell.copy()
        if COORD_HEADER.search(raw):
            names, positions, end = _extract_coordinates(lines, j, species)
            if names and (atom_count is None or len(names) == atom_count):
                lower = raw.lower()
                # SIESTA prints outcell *after* outcoor, including in
                # variable-cell runs. Resolve that move's lattice later.
                if 'bohr' in lower: positions *= BOHR
                info = {'source': 'SIESTA .out', 'source_kind': 'siesta_out',
                        'source_line': j+1, 'calculation_index': job.index}
                if spin is not None: info['spin_polarized'] = spin
                unrelaxed = 'unrelaxed' in lower
                if unrelaxed:
                    info.update(structure_label='Final unrelaxed coordinates', siesta_unrelaxed=True)
                elif current is not None:
                    info.update(stage_index=current['stage'], optimization_cycle=current['cycle'])
                else:
                    info['structure_label'] = 'Initial coordinates'
                frame = Frame(names, positions, cell.copy() if cell is not None else np.zeros((3,3)),
                              (cell is not None,)*3, info=info)
                frames.append(frame)
                geometry_contexts.append((current, 'fractional' in lower, cell))
                if current is not None and not unrelaxed: current['frames'].append(len(frames)-1)
                if max_frames is not None and len(frames) > max_frames:
                    raise ValueError(f'SIESTA output exceeds frame limit ({max_frames})')
            elif names:
                warnings.append(f'Incomplete coordinates at line {j+1}: {len(names)} of {atom_count} atoms.')
            j = max(j, end-1)
        j += 1
    progress(len(lines))
    if stage is not None: stage.end_line = len(lines)
    retained, old_to_new = [], {}
    for index, (frame, (context, fractional, previous_cell)) in enumerate(zip(frames, geometry_contexts)):
        lattice = context.get('cell', previous_cell) if context is not None else previous_cell
        if lattice is None: lattice = first_cells.get(frame.info['calculation_index'])
        if fractional and lattice is None:
            warnings.append(f'Fractional coordinates at line {frame.info["source_line"]} have no printed cell.')
            continue
        if lattice is not None:
            frame.cell = lattice.copy()
            frame.pbc = (True,)*3
            if fractional: frame.positions = frame.positions @ lattice
        old_to_new[index] = len(retained)
        retained.append(frame)
    frames = retained
    for group in groups:
        group['frames'] = [old_to_new[i] for i in group['frames'] if i in old_to_new]
    result.periodic_geometry_seen = any(any(f.pbc) for f in frames)

    if groups:
        priority = {'e_ks': 4, 'final_total': 3, 'total': 2, 'etot': 1}
        last_by_stage = {group['stage']:group for group in groups}
        for group in groups:
            chosen = max(group['records'], key=lambda x:(priority[x[1]], x[0]), default=None)
            candidates = group['frames']
            reference = frames[candidates[0]] if candidates else None
            compatible = reference is not None and all(
                f.symbols == reference.symbols and np.allclose(f.cell, reference.cell, atol=1.e-7, rtol=0)
                and np.allclose(f.positions, reference.positions, atol=1.e-7, rtol=0)
                for f in (frames[k] for k in candidates))
            info = {'energy_source': 'SIESTA '+({'e_ks':'E_KS', 'etot':'Etot', 'total':'Total', 'final_total':'Final total'}[chosen[1]] if chosen else 'not printed')}
            info['printed_energies_ev'] = {kind:value for _,kind,value,_ in group['records']}
            if 'free_energy_ev' in group: info['free_energy_ev'] = group['free_energy_ev']
            if 'scf_cycles' in group: info['scf_cycles'] = group['scf_cycles']
            value = None if chosen is None else chosen[2]
            frame_index = candidates[0] if compatible else None
            step = SiestaStep(group['job'], chosen[0]+1 if chosen else group['source_line'],
                geometry=reference.clone() if compatible else None, energy_ev=value,
                frame_index=frame_index, stage_index=group['stage'], cycle=group['cycle'], info=info)
            if compatible:
                for index in candidates:
                    frames[index].energy_ev = value
                    if chosen:
                        frames[index].info.update(energy_source=info['energy_source'], energy_source_line=chosen[0]+1)
                step.geometry = frames[frame_index].clone()
                if (result.stages[group['stage']].status == 'Converged'
                        and last_by_stage[group['stage']] is group):
                    step.converged = True
                    for index in candidates: frames[index].info['optimization_converged'] = True
            result.steps.append(step)
        count = sum(s.energy_ev is not None for s in result.steps)
        matched = sum(s.energy_ev is not None and s.frame_index is not None for s in result.steps)
        note = f'{len(groups)} SIESTA ionic moves; {count} energy records, {matched} paired to structures by move boundaries.'
        unmatched = sum(f.energy_ev is None for f in frames)
        if unmatched: note += f' {unmatched} printed geometries have no assigned energy (initial/reference, unrelaxed or unmatched).'
    else:
        legacy_records = [(line,kind,value) for line,kind,value,_ in records]
        note = _frame_energy_map(frames, legacy_records) if frames else 'No per-step coordinate blocks in SIESTA .out.'
        for index, frame in enumerate(frames):
            frame.info.pop('structure_label', None)
            if frame.energy_ev is not None:
                result.steps.append(SiestaStep(frame.info['calculation_index'], frame.info['source_line'],
                    geometry=frame.clone(), energy_ev=frame.energy_ev, frame_index=index, cycle=index+1,
                    info={'energy_source':frame.info.get('energy_source','SIESTA output')}))
        if not result.steps and records:
            family = next(kind for kind in ('e_ks','final_total','etot','total') if any(r[1]==kind for r in records))
            for line,kind,value,job_index in records:
                if kind == family:
                    result.steps.append(SiestaStep(job_index,line+1,energy_ev=value,
                        cycle=len(result.steps)+1,info={'energy_source':'SIESTA '+kind}))
    for item in result.jobs:
        totals = [r for r in records if r[3]==item.index and r[1]=='final_total']
        known = [s.energy_ev for s in result.steps if s.job_index==item.index and s.energy_ev is not None]
        item.energy_ev = totals[-1][2] if totals else known[-1] if known else None
        if not item.tasks: item.tasks.add('Single point' if len(known)<=1 else 'Ionic records')
    last = next((s for s in reversed(result.steps) if s.energy_ev is not None), None)
    if any(f.info.get('siesta_unrelaxed') for f in frames) and last is not None:
        note += f' Final unrelaxed coordinates were not paired to an energy; last calculated {last.info["energy_source"]} (move {last.cycle}) = {last.energy_ev:.9f} eV.'
    totals = [r for r in records if r[1]=='final_total']
    if totals: note += f' Final reported total energy = {totals[-1][2]:.9f} eV.'
    if warnings: note += ' '+' '.join(warnings)
    result.note = note
    return frames, note, result
