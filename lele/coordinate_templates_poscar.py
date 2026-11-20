"""Preserve POSCAR text, species/POTCAR order and nonstructural records."""
import re
from collections import defaultdict, deque
from itertools import groupby
import numpy as np

_REAL = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?\Z')


def _value(token):
    if not _REAL.fullmatch(token):
        raise ValueError('Unsupported POSCAR numeric expression; provide this file as a sample.')
    value = float(token.replace('D', 'E').replace('d', 'e'))
    if not np.isfinite(value):
        raise ValueError('Non-finite POSCAR value.')
    return value


def _fields(line):
    return list(re.finditer(r'\S+', line))


def _replace_values(line, values):
    fields = _fields(line)
    if len(fields) < len(values):
        raise ValueError('Incomplete POSCAR structure record.')
    for match, value in reversed(list(zip(fields, values))):
        line = line[:match.start()] + format(float(value), '.16g') + line[match.end():]
    return line


def _species_blocks(frame, elements, counts, names):
    """Retain POTCAR slots (including repeated species) wherever row order permits."""
    expected = [symbol for symbol, count in zip(elements, counts) for _ in range(count)]
    if frame.symbols == expected:
        return names, counts
    groups = frame.info.get('poscar_groups', [])
    if ([s for s, _ in groups] == elements and
            [s for s, n in groups for _ in range(n)] == frame.symbols):
        return names, [n for _, n in groups]
    runs = [(symbol, sum(1 for _ in rows)) for symbol, rows in groupby(frame.symbols)]
    old_runs = [(symbol, [(names[i], counts[i]) for i, _ in slots])
                for symbol, slots in groupby(enumerate(elements), key=lambda pair: pair[1])]
    old_symbols = [symbol for symbol, _ in old_runs]
    # Match each incoming run to the next original occurrence of its species.
    # This keeps distinct same-element potentials together even when another
    # species is added. Repeated labels can have different POTCARs.
    slots = defaultdict(deque)
    for index, symbol in enumerate(old_symbols):
        slots[symbol].append(index)
    matches = [slots[s].popleft() if slots[s] else None for s, _ in runs]
    keep_slots = all(i is not None for i in matches) and matches == sorted(matches)
    result = []
    cursor = 0
    for (symbol, length), match in zip(runs, matches):
        if match is None:
            labels = {name for name, element in zip(names, elements) if element == symbol}
            result.append((labels.pop() if len(labels) == 1 else symbol, length))
            continue
        if keep_slots:
            for _, skipped in old_runs[cursor:match]:
                result.extend((name, 0) for name, _ in skipped)
        block = old_runs[match][1]
        for name, old_count in block[:-1]:
            used = min(length, old_count)
            result.append((name, used))
            length -= used
        result.append((block[-1][0], length))
        cursor = match + 1
    if keep_slots:
        for _, skipped in old_runs[cursor:]:
            result.extend((name, 0) for name, _ in skipped)
    return [name for name, _ in result], [n for _, n in result]


def _header_tokens(line, old_count, values):
    fields = _fields(line)
    if len(values) == old_count:
        for match, value in reversed(list(zip(fields, values))):
            line = line[:match.start()] + str(value) + line[match.end():]
        return line
    return line[:fields[0].start()] + '  '.join(map(str, values)) + line[fields[old_count - 1].end():]


def _resize_rows(rows, new_count, extra, newline):
    """Resize a per-ion table and retain the final line ending, even at EOF."""
    if new_count == len(rows):
        return rows
    ending = rows[-1][len(rows[-1].rstrip('\r\n')):]
    result = list(rows[:new_count])
    if new_count > len(rows):
        result[-1] = result[-1].rstrip('\r\n') + newline
        result.extend(extra + newline for _ in range(new_count - len(rows)))
    result[-1] = result[-1].rstrip('\r\n') + ending
    return result


def _restart_tail(lines, count, new_count, old_cell, target_cell, reordered, geometry_changed, newline, notes):
    """Preserve VASP restart records and resize ordinary ion velocities by row."""
    records = [i for i, line in enumerate(lines) if line.strip()]
    if not records:
        return lines
    first = records[0]
    if lines[first].strip().lower().startswith('lattice velocities'):
        # State, three lattice velocities, three Cartesian lattice vectors.
        if len(records) < 8 or records[7] != first + 7:
            raise ValueError('Incomplete CONTCAR lattice velocities and vectors.')
        for i in records[2:8]:
            if len(lines[i].split()) != 3:
                raise ValueError('Malformed CONTCAR lattice velocity or vector.')
            for token in lines[i].split():
                _value(token)
        if not np.allclose(old_cell, target_cell, rtol=1.e-12, atol=1.e-12):
            for i, vector in zip(records[5:8], target_cell):
                lines[i] = _replace_values(lines[i], vector)
        records = records[8:]
        if not records:
            return lines
    velocity_mode = 'c'
    if lines[records[0]].strip().lower()[0] in 'dck':
        velocity_mode = lines[records[0]].strip().lower()[0]
        records = records[1:]
    if (len(records) < count or records[count-1] != records[0] + count - 1 or
            any(len(lines[i].split()) != 3 for i in records[:count])):
        raise ValueError('Unrecognized CONTCAR velocity or predictor-corrector records.')
    velocities = np.array([[_value(token) for token in lines[i].split()] for i in records[:count]])
    if reordered and count == new_count and np.any(velocities):
        raise ValueError('Reordered atoms cannot inherit nonzero row-specific restart velocities.')
    if velocity_mode == 'd' and not np.allclose(target_cell, old_cell, rtol=1.e-12, atol=1.e-12):
        # Retain the physical velocities when the Direct-coordinate basis changes.
        conversion = old_cell @ np.linalg.inv(target_cell)
        for i, vector in zip(records, velocities @ conversion):
            lines[i] = _replace_values(lines[i], vector)
    history = records[count:]
    if history:
        if (len(history) != 3 + 3 * count or
                any(len(lines[i].split()) != 3 for i in history[3:])):
            raise ValueError('Unrecognized CONTCAR predictor-corrector history.')
        if geometry_changed:
            # Integrator history belongs to the old coordinates and cell.
            del lines[records[count - 1] + 1:]
            notes.append('The geometry changed. The updated file omits the old MD predictor-corrector history. '
                         'The backup retains the complete restart.')
    start = records[0]
    lines[start:start + count] = _resize_rows(lines[start:start + count], new_count, '  0  0  0', newline)
    if new_count > count:
        notes.append('New atoms receive zero initial velocity.')
    return lines


def replace_poscar_coordinates(text, frame, *, path=None, notes=None):
    lines = text.splitlines(keepends=True)
    if len(lines) < 8:
        raise ValueError('Incomplete POSCAR input.')
    notes = [] if notes is None else notes
    newline = re.search(r'\r\n|\n|\r', text)[0]
    scale_fields = _fields(lines[1])
    scale_tokens = []
    for token in scale_fields:
        if not _REAL.fullmatch(token[0]):
            break
        scale_tokens.append(token[0])
    if len(scale_tokens) not in (1, 3):
        raise ValueError('POSCAR must have one or three numeric scaling factors.')
    factors = np.asarray([_value(value) for value in scale_tokens])
    if np.any(factors == 0) or (len(factors) == 3 and np.any(factors < 0)):
        raise ValueError('Invalid POSCAR scaling factors.')
    original_raw = np.asarray([[_value(x[0]) for x in _fields(row)[:3]] for row in lines[2:5]])
    if original_raw.shape != (3, 3) or abs(np.linalg.det(original_raw)) < 1.e-12:
        raise ValueError('Invalid POSCAR lattice.')
    if len(factors) == 1 and factors[0] < 0:
        physical_scale = np.repeat((-factors[0] / abs(np.linalg.det(original_raw))) ** (1. / 3), 3)
    else:
        physical_scale = np.repeat(factors, 3) if len(factors) == 1 else factors
    old_cell = original_raw * physical_scale
    names = lines[5].split('!', 1)[0].split()
    if not names:
        raise ValueError('Missing POSCAR species or counts.')
    if all(re.fullmatch(r'\d+', name) for name in names):
        from io import StringIO
        from ase.io import ParseError
        from ase.io.vasp import read_vasp_configuration
        stream = StringIO(text)
        stream.name = str(path or 'POSCAR')
        old_counts = list(map(int, names))
        try:
            atoms = read_vasp_configuration(stream)
            if min(old_counts) <= 0:
                raise ValueError('Empty species block')
            names = [atoms[int(offset)].symbol for offset in np.cumsum([0, *old_counts[:-1]])]
        except (OSError, ValueError, IndexError, KeyError, RuntimeError, ParseError) as exc:
            raise ValueError('This VASP 4 target needs identifiable species in its title or an accompanying POTCAR/OUTCAR.') from exc
        lines.insert(5, '  '.join(names) + newline)
        notes.append('The updated VASP 4 file includes an explicit species header.')
    from .legacy_converter import normalize_element
    try:
        elements = [normalize_element(name) for name in names]
    except (ValueError, KeyError):
        raise ValueError('Unrecognized POSCAR species name.') from None
    count_fields = lines[6].split()
    try:
        counts = [int(value) for value in count_fields[:len(elements)]]
    except ValueError:
        raise ValueError('Invalid POSCAR species counts.') from None
    if len(counts) != len(elements) or any(value < 0 for value in counts):
        raise ValueError('Invalid POSCAR species counts.')
    new_names, new_counts = _species_blocks(frame, elements, counts, names)
    if new_names != names:
        lines[5] = _header_tokens(lines[5], len(names), new_names)
    if new_counts != counts:
        lines[6] = _header_tokens(lines[6], len(counts), new_counts)
    index = 7
    selective = lines[index].lstrip().lower().startswith('s')
    if selective:
        index += 1
    mode = lines[index].strip().lower()
    if not mode or mode[0] not in 'dck':
        raise ValueError('Unsupported POSCAR coordinate mode.')
    direct = mode[0] == 'd'
    start = index + 1
    count = sum(counts)
    if not count or not frame.symbols or len(lines) < start + count:
        raise ValueError('Incomplete POSCAR atom table.')
    original_positions = np.empty((count, 3))
    for i, line in enumerate(lines[start:start + count]):
        fields = _fields(line)
        if len(fields) < 3:
            raise ValueError('Incomplete POSCAR coordinate row.')
        original_positions[i] = [_value(token[0]) for token in fields[:3]]
        if selective and (len(fields) < 6 or any(token[0].upper() not in ('T', 'F') for token in fields[3:6])):
            raise ValueError('Missing POSCAR selective-dynamics T/F flags.')
    target_cell = np.asarray(frame.cell, float) if any(frame.pbc) else np.eye(3) * 30.
    original_positions = original_positions @ old_cell if direct else original_positions * physical_scale
    geometry_changed = (new_counts != counts or new_names != names or
                        not np.allclose(target_cell, old_cell, rtol=0., atol=1.e-10) or
                        not np.allclose(original_positions, frame.positions, rtol=0., atol=1.e-10))
    tail = _restart_tail(lines[start + count:], count, len(frame.symbols), old_cell, target_cell,
                         frame.info.get('atom_order_edited', False), geometry_changed, newline, notes)
    if len(factors) == 1 and factors[0] < 0:
        # Retain the negative-volume convention, with its new physical volume.
        lines[1] = _replace_values(lines[1], [-abs(np.linalg.det(target_cell))])
        new_factors = np.ones(3)
    else:
        new_factors = physical_scale
    for i, vector in enumerate(target_cell / new_factors):
        lines[2 + i] = _replace_values(lines[2 + i], vector)
    positions = (np.asarray(frame.positions) @ np.linalg.inv(target_cell) if direct
                 else np.asarray(frame.positions) / new_factors)
    template = '  0  0  0' + ('  T  T  T' if selective else '')
    rows = _resize_rows(lines[start:start + count], len(positions), template, newline)
    return ''.join(lines[:start] + [_replace_values(row, pos) for row, pos in zip(rows, positions)] + tail)
