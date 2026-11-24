"""Recover explicit per-atom constraints from the printed input of each calculation job."""
import re

from .atom_constraints import _gaussian_tokens, read_input_constraints
from .output_text import check_load_cancelled, read_output_lines


def _gaussian_records(lines, start, end, frame, route):
    from .coordinate_templates_molecular import _symbol
    count = len(frame.symbols)
    atoms, directives = [], []
    for i in range(start, end):
        if i % 2048 == 0:
            check_load_cancelled()
        line = lines[i]
        if 'Symbolic Z-matrix:' in line:
            if atoms:  # A single mask cannot describe multiple input geometries.
                return {}
            j = i + 1
            while j < end and (not lines[j].strip() or lines[j].lstrip().startswith('Charge =')):
                j += 1
            candidate = []
            for symbol in frame.symbols:
                if j >= end:
                    break
                words = _gaussian_tokens(lines[j])
                if len(words) not in (4, 5) or _symbol(words[0].split('(')[0], True) != symbol:
                    break
                if len(words) == 5 and not re.fullmatch(r'[+-]?\d+', words[1]):
                    break
                try:
                    [float(v.replace('D','E').replace('d','e')) for v in words[-3:]]
                except ValueError:
                    break
                candidate.append(lines[j])
                j += 1
            if len(candidate) == count:
                atoms = candidate
        elif 'ModRedundant input section has been read' in line:
            j = i + 1
            while j < end and lines[j].strip():
                if not re.match(r'^\s*(?:[XBALDTO]\s+)?(?:\d+|\*)\s+', lines[j], re.I):
                    break
                directives.append(lines[j])
                j += 1
    if not (atoms or directives):
        return {}
    # The input grammar already handles freeze codes, atom-only ModRedundant
    # directives, NoFreeze and unsupported ReadOpt/GIC cases. If only atom
    # indices were echoed, no geometry is inferred from the placeholder rows.
    if not atoms:
        atoms = [symbol+' 0.0 0.0 0.0' for symbol in frame.symbols]
    route = route.lstrip('# ') or 'p'
    if directives and 'modredundant' not in route.lower():
        route += ' opt=modredundant'
    record = ['# '+route, '', 'Printed atom constraints', '', '0 1', *atoms, '', *directives]
    return read_input_constraints('gaussian_in', record, frame)


def _echoed_input(lines, start, end, kind):
    record = []
    active = False
    complete = False
    depth = 0
    force_evals = 0
    for i in range(start, end):
        if i % 2048 == 0:
            check_load_cancelled()
        line = lines[i]
        if kind == 'orca_out':
            if '>' not in line:
                continue
            match = re.match(r'^\s*\|\s*\d+\s*>\s?(.*)', line)
            if match:
                record.append(match[1])
        elif kind == 'cp2k_out':
            if not active and '&' not in line:
                continue
            text = line.strip()
            if text.startswith('INPUT|'):
                text = text[6:].strip()
            key = text.split(None, 1)[0].upper() if text else ''
            if key == '&FORCE_EVAL':
                force_evals += 1
            if key == '&MOTION' and not active:
                if complete:
                    return []
                active = True
            if active:
                record.append(text)
                if key.startswith('&'):
                    depth += -1 if key == '&END' else 1
                    if depth == 0:
                        active = False
                        complete = True
        else:
            if kind == 'siesta_out':
                begins = 'Dump of input data file' in line
                ends = 'End of input data file' in line
            else:
                begins = 'echo of input deck' in line.lower()
                ends = active and len(line.strip()) > 10 and set(line.strip()) == {'='}
            if begins:
                if active or complete:
                    return []
                active = True
            elif active and ends:
                active = False
                complete = True
            elif active:
                record.append(line)
    if kind == 'orca_out':
        return record
    return record if complete and not active and force_evals <= 1 else []


def _attach_records(kind, lines, jobs, groups):
    bounds = [max(0, job.start_line - 1) for job in jobs] or [0]
    for job, frames in groups.items():
        if not 0 <= job < len(bounds) or not frames:
            continue
        start, end = bounds[job], bounds[job+1] if job+1 < len(bounds) else len(lines)
        first = frames[0]
        if kind == 'gaussian_out':
            info = _gaussian_records(lines, start, end, first, jobs[job].route if jobs else '')
        else:
            record = _echoed_input(lines, start, end, kind)
            if not record:
                continue
            info = read_input_constraints(kind.replace('_out','_in'), record, first)
        if 'fixed_axes' not in info:
            continue
        info['fixed_axes_source'] += ' (printed in output)'
        for frame in frames:
            if frame.symbols == first.symbols and 'fixed_axes' not in frame.info:
                frame.info.update(info)


def attach_step_constraints(results, kind, lines):
    """Attach before frame deduplication so equal geometries can differ in constraints."""
    groups = {}
    for step in results.steps:
        if step.geometry is not None:
            groups.setdefault(step.job_index, []).append(step.geometry)
    _attach_records(kind, lines, results.jobs, groups)


def attach_printed_constraints(document, kind):
    groups = {}
    for frame in document.frames:
        groups.setdefault(frame.info.get('calculation_index', 0), []).append(frame)
    results = document.calculation_results
    _attach_records(kind, read_output_lines(document.path), results.jobs if results else [], groups)
