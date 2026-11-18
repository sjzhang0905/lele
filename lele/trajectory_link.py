"""Manually pair a position trajectory with the ionic records from one output."""
from bisect import bisect_left, bisect_right
from collections import defaultdict
from pathlib import Path
import re

import numpy as np
from ase.units import Hartree

from .core import Document
from .cp2k_results import Cp2kStep, read_cp2k_output, read_cp2k_xyz
from .legacy_converter import detect_format, ConversionError
from .output_text import check_load_cancelled, open_output_text
from .xtb_results import read_xtb_results, read_xtb_xyz


def association_role(document):
    results = document.calculation_results
    if results is not None and results.program in ('CP2K', 'xTB'):
        if document.format_name in ('CP2K output', 'xTB output'):
            if any(s.kind in ('optimization', 'md') for s in results.stages):
                return 'output'
        if document.format_name in ('CP2K XYZ trajectory', 'xTB optimization trajectory'):
            return 'trajectory'
    if document.frames and document.path.suffix.lower() in ('.xyz', '.extxyz'):
        return 'trajectory'
    return None


def _read_positions(path, program):
    # CP2K writes the same i/time/E header for position, velocity and force XYZ.
    if re.search(r'(?:^|[-_.])(?:frc|forces?|vel|velocities)(?:[-_.]|$)', path.name, re.I):
        raise ValueError('Select the position trajectory, such as *-pos-1.xyz.')
    with open_output_text(path) as stream:
        first = next((line for line in stream if line.strip()), '')
        if not first.strip().isdigit():
            raise ValueError('Select a Cartesian XYZ position trajectory or an xTB optimization log.')
        comment = stream.readline()
    if program == 'CP2K':
        if re.search(r'\bxtb\s*:', comment, re.I):
            raise ValueError('This is an xTB trajectory. Select the CP2K position trajectory.')
        prop = re.search(r'\bProperties=([^\s]+)', comment, re.I)
        if prop and not prop[1].lower().startswith('species:s:1:pos:r:3'):
            raise ValueError('The extended XYZ must contain element symbols followed by Cartesian positions.')
        data = read_cp2k_xyz(path, strict=True)
        frames = [s.geometry for s in data.steps]
        truncated = 'Incomplete trailing' in data.note
    else:
        if re.search(r'\bi\s*=\s*\d+\s*,|\bLattice=', comment, re.I):
            raise ValueError('Select the xTB optimization XYZ trajectory.')
        frames, warning = read_xtb_xyz(path)
        if warning.startswith('Invalid'):
            raise ValueError(warning)
        truncated = bool(warning)
    if not frames:
        raise ValueError('No complete coordinate frames were found.')
    if any(f.symbols != frames[0].symbols for f in frames):
        raise ValueError('The element sequence changes within the trajectory.')
    return frames, truncated


def _energy(step, program):
    if program == 'xTB' and step.geometry is not None:
        return step.geometry.info.get('xtb_cycle_energy_ev', step.energy_ev)
    return step.energy_ev


def _match_frames(results, frames, eligible):
    program = results.program
    cp2k = program == 'CP2K'
    # Native CP2K XYZ prints ten decimal places in Eh. Standard xTB stdout
    # rounds each optimization cycle to seven. Keep the final single point separate.
    tolerance = (5.1e-9 if cp2k else 5.1e-8) * Hartree
    records = results.steps
    by_cycle = defaultdict(list)
    reference = {}
    energies = []
    for i in eligible:
        s = records[i]
        by_cycle[s.cycle].append(i)
        if s.geometry is not None:
            reference.setdefault(s.job_index, s.geometry)
        energy = _energy(s, program)
        if energy is not None:
            energies.append((energy, i))
    energies.sort()
    jobs = {s.job_index for s in results.stages if s.kind in ('optimization', 'md')}
    printed = getattr(results, 'metadata', {}).get('jobs', {})
    atoms = frames[0].symbols
    valid_jobs = {j for j in jobs if
                  (j not in reference or reference[j].symbols == atoms) and
                  printed.get(str(j), {}).get('Atoms', results.jobs[j].atom_count or len(atoms)) == len(atoms)}
    if not valid_jobs:
        raise ValueError('The trajectory atom count or element order differs from the output.')
    eligible = [i for i in eligible if records[i].job_index in valid_jobs]

    def same_energy(frame, index):
        step = records[index]
        energy = _energy(step, program)
        if frame.energy_ev is None or energy is None:
            return True
        if abs(frame.energy_ev - energy) <= tolerance:
            return True
        potential = getattr(step, 'info', {}).get('cp2k_md_potential_hartree')
        return potential is not None and np.isclose(frame.energy_ev / Hartree, potential, atol=5.1e-9, rtol=5.1e-12)

    def by_energy(value):
        if value is None:
            return []
        lo = bisect_left(energies, (value-tolerance, -1))
        hi = bisect_right(energies, (value+tolerance, len(records)))
        return [index for _, index in energies[lo:hi]]

    def unnumbered_endpoint(i, xyz_step, frame_number):
        s = records[i]
        if s.cycle is None or s.info.get('cp2k_unnumbered'):
            return True
        if s.info.get('cp2k_final_reevaluation'):
            return xyz_step == s.cycle+1
        return (i == eligible[0] and frame_number == 0 and
                ((not s.info.get('cp2k_opt_summary') and
                  results.stages[s.stage_index].kind == 'optimization' and xyz_step == s.cycle-1) or
                 (s.info.get('cp2k_md_initial') and 'cp2k_md_step' not in s.info)))

    def ordinary(i):
        s = records[i]
        return (s.cycle is None or getattr(s, 'info', {}).get('cp2k_unnumbered') or len(by_cycle[s.cycle]) == 1 or
                getattr(s, 'info', {}).get('cp2k_opt_summary') or
                getattr(s, 'info', {}).get('cp2k_final_reevaluation'))

    ordered = [i for i in eligible if ordinary(i)] if cp2k else eligible
    by_order = len(ordered) == len(frames) and len(valid_jobs) == 1
    groups = []
    for n, f in enumerate(frames):
        check_load_cancelled()
        step = f.info.get('trajectory_step')
        if step is not None:
            candidates = [i for i in by_cycle[step] if records[i].job_index in valid_jobs]
            if cp2k and not candidates:
                # CP2K can write the initial line-search evaluation as i=0
                # and a separate, unnumbered reevaluation at the minimum.
                candidates = [i for i in by_energy(f.energy_ev) if
                              unnumbered_endpoint(i, step, n)] if eligible else []
                if not candidates and len(valid_jobs) == 1:
                    groups.append([])  # Printed trajectory step without an output record.
                    continue
        elif by_order:
            candidates = [ordered[n]]
        else:
            candidates = by_energy(f.energy_ev)
        candidates = [i for i in candidates if records[i].job_index in valid_jobs and same_energy(f, i)]
        time = f.info.get('time_fs')
        if time is not None:
            candidates = [i for i in candidates if
                          'time_fs' not in records[i].info or abs(time-records[i].info['time_fs']) < 5.1e-5]
        if len(candidates) > 1 and cp2k:
            accepted = [i for i in candidates if records[i].info.get('cp2k_opt_summary')]
            if accepted:
                candidates = accepted
        if not candidates:
            raise ValueError(f'Trajectory frame {n+1} has no compatible output record. Check the step, time and energy.')
        groups.append(sorted(candidates))
    if not any(groups) and eligible:
        raise ValueError('The trajectory and the output have no matching steps.')
    if not any(groups) and not eligible and not all(f.info.get('trajectory_step') is not None for f in frames):
        raise ValueError('The output contains no numbered records for matching this trajectory.')

    # Forward/backward bounds allow repeated energies and restarted counters
    # only when the ordering of all frames has a unique solution.
    def bounds(reverse):
        edge = len(records) if reverse else -1
        chosen = {}
        for n in (reversed(range(len(groups))) if reverse else range(len(groups))):
            group = groups[n]
            if not group:
                continue
            k = bisect_left(group, edge)-1 if reverse else bisect_right(group, edge)
            if not 0 <= k < len(group):
                raise ValueError(f'Inconsistent trajectory ordering at frame {n+1}.')
            edge = chosen[n] = group[k]
        return chosen
    matches = bounds(False)
    if matches != bounds(True):
        raise ValueError('Several output steps fit the trajectory. Select the matching run or include step numbers.')
    for n, i in matches.items():
        s, f = records[i], frames[n]
        if s.geometry is None or getattr(s, 'info', {}).get('cp2k_reftraj_input_geometry'):
            continue
        delta = f.positions - s.geometry.positions
        if any(s.geometry.pbc) and abs(np.linalg.det(s.geometry.cell)) > 1e-10:
            fractional = np.linalg.solve(s.geometry.cell.T, delta.T).T
            lattice_shift = np.rint(fractional) * np.asarray(s.geometry.pbc)
            delta -= lattice_shift @ s.geometry.cell
        if not np.allclose(delta, 0, atol=2e-5, rtol=0):
            raise ValueError(f'Trajectory frame {n+1} disagrees with the coordinates printed for this output step.')
    order_only = by_order and any(f.energy_ev is None and 'trajectory_step' not in f.info for f in frames)
    return matches, valid_jobs, order_only


def _attach_frame(step, frame, number, job, program):
    existing = step.geometry
    if existing is not None:
        frame.info = {**existing.info, **frame.info}
    frame.info['trajectory_frame'] = number
    frame.info['trajectory_source_line'] = frame.info['source_line']
    if program == 'CP2K':
        meta = step.info
        if 'trajectory_cell' not in frame.info and 'cp2k_output_cell' in meta:
            frame.cell = np.array(meta['cp2k_output_cell'])
        if 'trajectory_pbc' not in frame.info and 'cp2k_periodicity' in meta and frame.cell.any():
            frame.pbc = tuple(meta['cp2k_periodicity'])
        if frame.info.get('trajectory_step') is not None and (step.cycle is None or meta.get('cp2k_unnumbered')
                or meta.get('cp2k_final_reevaluation') or number == 1):
            step.cycle = frame.info['trajectory_step']
        if 'time_fs' in frame.info:
            meta.setdefault('time_fs', frame.info['time_fs'])
        if 'MD' in job.tasks and step.cycle is not None:
            meta.setdefault('cp2k_md_step', step.cycle)
        frame.info.update(meta)
        if step.cycle is not None:
            frame.info['linked_step'] = step.cycle
    else:
        frame.info['linked_step'] = step.cycle
        if job.xtb_fixed_atoms is not None:
            from .atom_constraints import xtb_fixed_constraints
            frame.info.update(xtb_fixed_constraints(job.xtb_fixed_atoms, frame))
        frame.info['xtb_cycle_energy_ev'] = _energy(step, program)
        if frame.energy_ev is not None:
            frame.info['xtb_trajectory_energy_ev'] = frame.energy_ev
            if existing is None or 'xtb_cycle_energy_ev' not in existing.info:
                step.energy_ev = frame.energy_ev
    if step.energy_ev is None:
        step.energy_ev = frame.energy_ev
    if job.charge is not None:
        frame.info['converter_charge'] = job.charge
    if job.multiplicity is not None:
        frame.info['converter_mult'] = job.multiplicity
    step.geometry = frame


def link_trajectory(output_path, trajectory_path):
    """Return a new self-contained document. The source files are read only."""
    output_path = Path(output_path).expanduser().resolve()
    trajectory_path = Path(trajectory_path).expanduser().resolve()
    if output_path == trajectory_path:
        raise ValueError('Select the other file in the pair.')
    try:
        kind = detect_format(output_path).kind
    except ConversionError as error:
        raise ValueError('Select a CP2K or xTB calculation output.') from error
    if kind == 'cp2k_out':
        results = read_cp2k_output(output_path)
    elif kind == 'xtb_out':
        results = read_xtb_results(output_path, allow_companions=False)
    else:
        raise ValueError('Select a CP2K optimization / MD output or an xTB optimization output.')
    stages = {s.index: s for s in results.stages if s.kind in ('optimization', 'md')}
    if not stages:
        raise ValueError('The selected output contains no optimization or MD run.')
    program = results.program
    frames, truncated = _read_positions(trajectory_path, program)
    eligible = [i for i, s in enumerate(results.steps) if s.stage_index in stages]
    matches, jobs, order_only = _match_frames(results, frames, eligible)
    if len(matches) < len(frames):
        # Extra XYZ-only records require explicit monotone steps from a single run.
        cycles = [f.info.get('trajectory_step') for f in frames]
        if len(jobs) != 1 or any(c is None for c in cycles) or any(a >= b for a, b in zip(cycles, cycles[1:])):
            raise ValueError('Unmatched trajectory steps cannot be assigned uniquely across restarts.')
    old = list(results.steps)
    inserts = defaultdict(list)
    if len(matches) < len(frames):
        stage = next(s for s in stages.values() if s.job_index in jobs)
        constant_cell = {}
        ensemble = results.metadata['jobs'][str(stage.job_index)].get('MD ensemble', '').upper()
        if 'GEO_OPT' in results.jobs[stage.job_index].tasks or ensemble in ('NVE', 'NVT', 'LANGEVIN'):
            cell_info = next((s.info for s in old if s.stage_index == stage.index and 'cp2k_output_cell' in s.info), {})
            constant_cell = {k: cell_info[k] for k in ('cp2k_output_cell', 'cp2k_periodicity') if k in cell_info}
        ordered = [(s.cycle, i) for i, s in enumerate(old) if s.stage_index == stage.index and s.cycle is not None]
        if any(a[0] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Unmatched trajectory steps cannot be assigned across a restarted output.')
    for n, frame in enumerate(frames):
        check_load_cancelled()
        if n in matches:
            step = old[matches[n]]
        else:
            cycle = frame.info['trajectory_step']
            position = bisect_right(ordered, (cycle, len(old)))
            at = ordered[position][1] if position < len(ordered) else (eligible[-1]+1 if eligible else len(old))
            step = Cp2kStep(stage.job_index, frame.info['source_line'], energy_ev=frame.energy_ev,
                            stage_index=stage.index, cycle=cycle, info={**constant_cell, 'trajectory_only': True})
            if stage.kind == 'md':
                step.info['cp2k_md_step'] = cycle
            inserts[at].append(step)
        _attach_frame(step, frame, n+1, results.jobs[step.job_index], program)
    if inserts:
        results.steps = []
        shifted = {}
        for i, s in enumerate(old):
            results.steps.extend(inserts.get(i, ()))
            shifted[i] = len(results.steps)
            results.steps.append(s)
        results.steps.extend(inserts.get(len(old), ()))
        for orbital in results.orbitals:
            if orbital.step_index is not None:
                orbital.step_index = shifted[orbital.step_index]
    if program == 'xTB':
        first = {}
        for i in eligible:
            first.setdefault(old[i].job_index, i)
        for orbital in results.orbitals:
            i = first.get(orbital.job_index)
            if (orbital.step_index is None and i is not None and old[i].geometry is not None
                    and orbital.source_line < old[i].source_line):
                orbital.step_index = i
    link = dict(path=str(trajectory_path), matched=len(matches), trajectory_frames=len(frames),
                trajectory_only=len(frames)-len(matches), by_order=order_only)
    note = (f'Associated trajectory: {trajectory_path.name}. {len(matches)} of {len(frames)} '
            'trajectory frames matched output records.')
    if link['trajectory_only']:
        note += f' {link["trajectory_only"]} additional numbered frames come from the trajectory.'
    if order_only:
        note += ' Frames without a printed step or energy were paired by record order.'
    if truncated:
        note += ' Incomplete trailing trajectory data were omitted.'
    results.note = (note + ' ' + results.note).strip() if program == 'CP2K' else note
    label = program + ' output'
    geometries = results.frames()
    for frame in geometries:
        frame.info.update(source_kind=kind, source_format=label)
    document = Document(output_path, label, geometries, note=results.note, calculation_results=results,
                        trajectory_link=link, electronic_spectra=getattr(results, 'spectra', []),
                        dipoles=getattr(results, 'dipoles', []))
    from .atom_constraints import attach_document_constraints
    attach_document_constraints(document, kind)
    return document
