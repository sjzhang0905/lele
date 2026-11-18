"""Preserve POSCAR text, species/POTCAR order and nonstructural records."""
import re
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


def replace_poscar_coordinates(text, frame):
    lines = text.splitlines(keepends=True)
    if len(lines) < 9:
        raise ValueError('Incomplete POSCAR input.')
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
    names = lines[5].split()
    if not names or all(re.fullmatch(r'\d+', name) for name in names):
        raise ValueError('VASP 4 inputs require external species information. Provide an explicit VASP 5 POSCAR as a sample.')
    # POTCAR determines these species; never reorder groups merely by changing
    # the helpful names line. A safe coordinate update keeps group semantics.
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
    expected = [symbol for symbol, count in zip(elements, counts) for _ in range(count)]
    if frame.symbols != expected:
        raise ValueError('Changing POSCAR species blocks also requires a matching POTCAR. Keep the existing atom count and species-block order, or export a new POSCAR explicitly.')
    index = 7
    selective = lines[index].lstrip().lower().startswith('s')
    if selective:
        index += 1
    mode = lines[index].strip().lower()
    if not mode or mode[0] not in 'dck':
        raise ValueError('Unsupported POSCAR coordinate mode.')
    direct = mode[0] == 'd'
    start = index + 1
    count = len(expected)
    if len(lines) < start + count:
        raise ValueError('Incomplete POSCAR atom table.')
    for line in lines[start:start + count]:
        fields = _fields(line)
        if len(fields) < 3:
            raise ValueError('Incomplete POSCAR coordinate row.')
        for token in fields[:3]:
            _value(token[0])
        if selective and (len(fields) < 6 or any(token[0].upper() not in ('T', 'F') for token in fields[3:6])):
            raise ValueError('Missing POSCAR selective-dynamics T/F flags.')
    tail = [line.strip() for line in lines[start + count:] if line.strip()]
    reordered = bool(frame.info.get('atom_order_edited'))
    if reordered and (selective or tail):
        raise ValueError('Reordered atoms cannot safely inherit row-specific POSCAR constraints or velocities unchanged.')
    target_cell = np.asarray(frame.cell, float) if any(frame.pbc) else np.eye(3) * 30.
    if tail:
        # Cartesian velocities do not use the POSCAR coordinate scaling. Keep
        # their exact bytes. More complex MD restart blocks need a sample.
        velocity_mode = 'c'
        velocity_lines = tail
        if tail[0][:1].lower() in 'dck':
            velocity_mode = tail[0][:1].lower()
            velocity_lines = tail[1:]
        if len(velocity_lines) != count or any(len(line.split()) != 3 for line in velocity_lines):
            raise ValueError('POSCAR contains lattice velocities or predictor/corrector data. Provide this restart input as a sample.')
        try:
            for line in velocity_lines:
                for token in line.split():
                    _value(token)
        except ValueError:
            raise ValueError('Unrecognized POSCAR trailing records; provide this input as a sample.') from None
        if velocity_mode == 'd' and not np.allclose(target_cell, old_cell, rtol=1.e-12, atol=1.e-12):
            raise ValueError('Changing the cell would change Direct-mode velocities. Provide this restart input as a sample.')
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
    for i, position in enumerate(positions):
        lines[start + i] = _replace_values(lines[start + i], position)
    return ''.join(lines)
