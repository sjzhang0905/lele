"""Surgical Cartesian replacements in self-contained calculation inputs.

Non-structural text is never regenerated. Ambiguous multi-job, external and
internal-coordinate inputs are rejected instead of guessed.
"""
from dataclasses import dataclass
import re
import numpy as np

BOHR_ANG = 0.529177210903
_NUMBER = re.compile(r'^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?$')


@dataclass
class _Row:
    line: int
    symbol: str
    tokens: list
    xyz: tuple
    special: bool = False


def _error(message):
    raise ValueError(message + ' Please provide this input as a sample before enabling automatic replacement.')


def _tokens(line, comment, comma=False):
    body = line.split(comment, 1)[0]
    return list(re.finditer(r'[^\s,]+' if comma else r'\S+', body))


def _symbol(token, numeric=False):
    from .chemical_analysis import ATOMIC_NUMBERS
    if numeric and token.isdigit():
        return next((s for s, n in ATOMIC_NUMBERS.items() if n == int(token)), None)
    match = re.fullmatch(r'([A-Za-z]{1,2})(\d*)', token)
    if match:
        value = match[1].capitalize()
        if value in ATOMIC_NUMBERS:
            return value
    return None


def _row(lines, index, kind):
    tokens = _tokens(lines[index], '!' if kind == 'gaussian_in' else '#', kind == 'gaussian_in')
    if not tokens:
        return None
    label = tokens[0][0]
    symbol = 'Tv' if kind == 'gaussian_in' and label.lower() == 'tv' else _symbol(label, kind == 'gaussian_in')
    if symbol is None:
        _error('Unsupported atom label or non-Cartesian coordinate record: ' + label)
    xyz = (1, 2, 3)
    special = label.lower() != symbol.lower() and not (kind == 'gaussian_in' and label.isdigit())
    if kind == 'gaussian_in':
        if len(tokens) == 5 and re.fullmatch(r'[+-]?\d+', tokens[1][0]):
            xyz = (2, 3, 4)
            special = True
        elif len(tokens) != 4:
            _error('Gaussian Z-matrix, layered or extended atom records are not yet supported.')
    elif kind == 'orca_in' and len(tokens) != 4:
        _error('ORCA extended atom records are not yet supported.')
    elif kind == 'nwchem_in':
        if len(tokens) < 4:
            _error('NWChem geometry must contain explicit Cartesian coordinates.')
        special = special or len(tokens) > 4
    if any(not _NUMBER.fullmatch(tokens[i][0]) for i in xyz):
        _error('Coordinate expressions and Z-matrices are not replaced automatically.')
    return _Row(index, symbol, tokens, xyz, special)


def _substitute(line, replacements):
    for start, end, value in sorted(replacements, reverse=True):
        line = line[:start] + value + line[end:]
    return line


def _number(value):
    number = format(float(value), '.15g')
    # Gaussian readers distinguish Cartesian 0.0 from an internal-coordinate
    # reference index 0. Always retain an explicit floating-point spelling.
    return number if '.' in number or 'e' in number.lower() else number + '.0'


def _set_row(lines, row, position, symbol=None):
    replacements = [(row.tokens[i].start(), row.tokens[i].end(), _number(value))
                    for i, value in zip(row.xyz, position)]
    if symbol is not None:
        replacements.append((row.tokens[0].start(), row.tokens[0].end(), symbol))
    lines[row.line] = _substitute(lines[row.line], replacements)


def _apply_atoms(lines, rows, frame, factor, guarded):
    if not rows:
        _error('No explicit atom coordinates found.')
    matching = [r.symbol for r in rows] == list(frame.symbols)
    if guarded and (not matching or frame.info.get('atom_order_edited')):
        raise ValueError('This template contains atom-specific settings. Its atom count, element order '
                         'and atom identities must remain unchanged; reordering would attach those '
                         'settings to different atoms.')
    positions = frame.positions / factor
    if len(rows) == len(frame.symbols):
        for row, symbol, position in zip(rows, frame.symbols, positions):
            _set_row(lines, row, position, symbol if row.symbol != symbol else None)
        return
    if guarded:
        raise ValueError('Atom-specific template settings prevent changing the atom count.')
    # Keep every comment/blank line and all text outside the atom records.
    # Insert the new records at the first old atom; remove only old atom rows.
    newline = '\r\n' if lines[rows[0].line].endswith('\r\n') else '\n'
    indent = re.match(r'\s*', lines[rows[0].line])[0]
    generated = [indent + symbol + '  ' + '  '.join(map(_number, xyz)) + newline
                 for symbol, xyz in zip(frame.symbols, positions)]
    for row in rows:
        if '#' in lines[row.line] or '!' in lines[row.line]:
            raise ValueError('Changing the atom count would detach inline atom comments. '
                             'Use a template with the same atom count or remove those comments first.')
    for row in rows:
        lines[row.line] = ''
    lines[rows[0].line] = ''.join(generated)


def _cell(frame):
    if any(frame.pbc):
        cell = np.asarray(frame.cell, dtype=float)
        if not np.isfinite(cell).all() or abs(np.linalg.det(cell)) < 1.e-12:
            raise ValueError('The periodic structure needs an invertible three-dimensional cell.')
        return cell
    return np.eye(3) * 30.


def _gaussian(text, frame):
    lines = text.splitlines(keepends=True)
    if re.search(r'(?im)^\s*--link1--\s*$', text):
        _error('Gaussian Link1 inputs require an explicit target job selection.')
    route_start = next((i for i, line in enumerate(lines) if line.lstrip('\ufeff \t').startswith('#')), None)
    if route_start is None:
        _error('Gaussian route section was not found.')
    end_route = route_start
    while end_route < len(lines) and lines[end_route].strip():
        end_route += 1
    route = ' '.join(lines[route_start:end_route])
    if re.search(r'\b(?:oniom|counterpoise|qst[23])\b|\bgeom\s*=\s*(?:\([^)]*)?(?:allcheck|check|checkpoint)', route, re.I):
        _error('Gaussian ONIOM, counterpoise, QST and checkpoint geometry require a sample-specific handler.')
    start_title = end_route
    while start_title < len(lines) and not lines[start_title].strip():
        start_title += 1
    end_title = start_title
    while end_title < len(lines) and lines[end_title].strip():
        end_title += 1
    charge = end_title
    while charge < len(lines) and not lines[charge].strip():
        charge += 1
    if charge >= len(lines) or not re.fullmatch(r'\s*[+-]?\d+\s*[, ]\s*\d+\s*(?:!.*)?', lines[charge].strip()):
        _error('Gaussian needs one charge/multiplicity pair and an inline Cartesian geometry.')
    end = charge + 1
    while end < len(lines) and lines[end].strip():
        end += 1
    parsed = [_row(lines, i, 'gaussian_in') for i in range(charge + 1, end)]
    rows = [r for r in parsed if r is not None and r.symbol != 'Tv']
    tv = [r for r in parsed if r is not None and r.symbol == 'Tv']
    if tv and len(tv) != 3:
        _error('Gaussian one- or two-dimensional Tv cells require a sample-specific handler.')
    factor = 1.
    units = re.search(r'\bunits\s*(?:=\s*)?(\([^)]*\)|[^\s]+)', route, re.I)
    if units:
        values = set(re.findall(r'[a-z]+', units[1].lower()))
        if values - {'au', 'bohr', 'ang', 'angstrom', 'deg', 'degree', 'rad', 'radian'}:
            _error('Unsupported Gaussian Units option.')
        if values & {'au', 'bohr'}:
            if values & {'ang', 'angstrom'}:
                _error('Conflicting Gaussian coordinate units.')
            factor = BOHR_ANG
    guarded = (any(r.special for r in rows) or bool(''.join(lines[end:]).strip())
               or bool(re.search(r'\b(?:modredundant|gic|connectivity|readopt|readfreeze|addgic|genecp|gen|pseudo)\b', route, re.I)))
    for row, vector in zip(tv, _cell(frame) / factor if tv else []):
        _set_row(lines, row, vector)
    _apply_atoms(lines, rows, frame, factor, guarded)
    return ''.join(lines)


def _orca_geometry(lines):
    text = ''.join(lines)
    if re.search(r'(?im)^\s*\$new_job\b|^\s*%compound\b', text):
        _error('ORCA multiple-job or Compound inputs require an explicit target job selection.')
    starts = [i for i, line in enumerate(lines) if re.match(r'^\s*\*\s*\w+', line)]
    percent = [i for i, line in enumerate(lines) if re.match(r'^\s*%coords\b', line, re.I)]
    if len(starts) > 1 or len(percent) > 1:
        _error('Multiple ORCA coordinate definitions are ambiguous.')
    unit_values = []
    for line in lines:
        if line.lstrip().startswith('!'):
            unit_values.extend(re.findall(r'\b(angs|bohrs)\b', line.split('#', 1)[0], re.I))
    block_start = block_end = None
    coord_start = coord_end = None
    if percent:
        block_start = percent[0]
        if not re.fullmatch(r'\s*%coords\s*(?:#.*)?', lines[block_start].rstrip('\r\n'), re.I):
            _error('Inline ORCA %coords directives require a sample-specific handler.')
        level = 1
        for i in range(block_start + 1, len(lines)):
            content = lines[i].split('#', 1)[0].strip()
            if re.fullmatch('coords', content, re.I):
                if coord_start is not None:
                    _error('Multiple ORCA coords subblocks are ambiguous.')
                coord_start = i
                level += 1
            elif re.fullmatch('end', content, re.I):
                level -= 1
                if level == 1:
                    coord_end = i
                if level == 0:
                    block_end = i
                    break
            elif level == 1:
                unit = re.fullmatch(r'units\s+(\w+)', content, re.I)
                if unit:
                    unit_values.append(unit[1])
                ctyp = re.fullmatch(r'ctyp\s+(\w+)', content, re.I)
                if ctyp and ctyp[1].lower() != 'xyz':
                    _error('ORCA internal-coordinate %coords blocks are not replaced automatically.')
        if block_end is None:
            _error('Unclosed ORCA %coords block.')
    factors = []
    for unit in unit_values:
        if unit.lower() not in ('angs', 'bohrs'):
            _error('Unsupported ORCA coordinate unit: ' + unit)
        factors.append(BOHR_ANG if unit.lower() == 'bohrs' else 1.)
    if len(set(factors)) > 1:
        _error('Conflicting ORCA coordinate unit declarations.')
    factor = factors[0] if factors else 1.
    if starts:
        if coord_start is not None:
            _error('Both ORCA star and %coords geometries are present.')
        start = starts[0]
        if not re.fullmatch(r'\s*\*\s*xyz\s+[+-]?\d+\s+\d+\s*(?:#.*)?', lines[start].rstrip('\r\n'), re.I):
            _error('Only an inline ORCA * xyz geometry is supported; external and internal geometries need samples.')
        end = next((i for i in range(start + 1, len(lines))
                    if re.fullmatch(r'\s*\*\s*(?:#.*)?', lines[i].rstrip('\r\n'))), None)
        if end is None:
            _error('Unclosed ORCA * xyz block.')
        return start, end, factor
    if coord_start is None or coord_end is None:
        _error('No inline ORCA Cartesian coordinate block found.')
    return coord_start, coord_end, factor


def _orca(text, frame):
    lines = text.splitlines(keepends=True)
    start, end, factor = _orca_geometry(lines)
    rows = [r for i in range(start + 1, end) if (r := _row(lines, i, 'orca_in')) is not None]
    outside = ''.join(lines[:start] + lines[end + 1:])
    # These blocks can bind settings to atom indices. Preserving their bytes
    # requires keeping the original identities and numbering as well.
    guarded = any(r.special for r in rows) or bool(re.search(
        r'(?i)\b(?:constraints|scan|modify_internal|newgto|newauxgto|newecp|fragment|fragments|'
        r'atomlist|atoms|nuclei|pointcharges|inhess|readhess|activeatoms|qmatoms|flipspin|brokensym)\b', outside))
    guarded = guarded or any(name.lower() not in ('pal', 'maxcore', 'coords', 'base')
                             for name in re.findall(r'(?im)^\s*%(\w+)', outside))
    _apply_atoms(lines, rows, frame, factor, guarded)
    return ''.join(lines)


def _nwchem_geometry(text):
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if re.match(r'^\s*geometry\b', line, re.I)]
    if len(starts) != 1:
        _error('NWChem requires one explicit geometry block.')
    start = starts[0]
    header = lines[start].split('#', 1)[0]
    if header.rstrip().endswith('\\'):
        _error('Continued NWChem geometry directives require a sample-specific handler.')
    end = next((i for i in range(start + 1, len(lines))
                if re.fullmatch(r'\s*end\s*(?:#.*)?', lines[i].rstrip('\r\n'), re.I)), None)
    if end is None:
        _error('Unclosed NWChem geometry block.')
    rows = []
    for i in range(start + 1, end):
        content = lines[i].split('#', 1)[0].strip()
        if not content:
            continue
        if re.match(r'^(?:system|zmatrix|zmt|zmat|zcoord|load)\b', content, re.I):
            _error('NWChem periodic SYSTEM, Z-matrix or external geometry requires a sample-specific handler.')
        if re.match(r'^symmetry\b', content, re.I):
            if not re.fullmatch(r'symmetry\s+(?:group\s+)?c1', content, re.I):
                _error('NWChem geometry symmetry expansion is ambiguous for coordinate replacement.')
            continue
        rows.append(_row(lines, i, 'nwchem_in'))
    units = re.search(r'\bunits\s+(\w+)', header, re.I)
    unit = units[1].lower() if units else 'angstroms'
    factors = {'angstrom': 1., 'angstroms': 1., 'an': 1., 'nm': 10., 'nanometers': 10.,
               'pm': .01, 'picometers': .01, 'au': 1 / 1.8897265,
               'atomic': 1 / 1.8897265, 'bohr': 1 / 1.8897265}
    if unit not in factors:
        _error('Unsupported NWChem geometry units: ' + unit)
    factor = factors[unit]
    conversion = re.search(r'\b(?:angstrom_to_au|ang2au)\s+(\S+)', header, re.I)
    if conversion and unit in ('au', 'atomic', 'bohr'):
        try:
            factor = 1. / float(conversion[1].replace('D', 'E').replace('d', 'e'))
        except (ValueError, ZeroDivisionError):
            _error('Invalid NWChem angstrom-to-au factor.')
        if not np.isfinite(factor) or factor <= 0:
            _error('Invalid NWChem angstrom-to-au factor.')
    return lines, start, end, rows, factor


def read_nwchem_cartesian(text):
    """Read the same single molecular grammar used by the replacement path.

    ASE's current NWChem input reader ignores length units and requires an
    extra blank line after END. Keep the fallback for other NWChem grammars.
    """
    _, _, _, rows, factor = _nwchem_geometry(text)
    if not rows:
        _error('No explicit NWChem Cartesian geometry found.')
    positions = [[float(row.tokens[i][0].replace('D', 'E').replace('d', 'e')) * factor
                  for i in row.xyz] for row in rows]
    return [row.symbol for row in rows], np.asarray(positions, float)


def _nwchem(text, frame):
    lines, start, end, rows, factor = _nwchem_geometry(text)
    outside = ''.join(lines[:start] + lines[end + 1:])
    guarded = (any(r.special for r in rows) or bool(re.search(
        r'\b(?:constraints|fix|freeze|frozen|spring|zcoord|qmmm|cosmo|bq|odft|bsse|actlist|shake_constraint)\b', outside, re.I))
        or bool(re.search(r'(?im)^\s*(?:set\b|nwpw\b)', outside)))
    # Element/tag-specific basis and ECP records cannot cover new species.
    if set(frame.symbols) - {r.symbol for r in rows}:
        if re.search(r'(?im)^\s*(?:basis|ecp)\b', outside) and not re.search(r'(?im)^\s*\*\s+library\b', outside):
            raise ValueError('The NWChem template has explicit basis/ECP settings and does not cover the new elements.')
    _apply_atoms(lines, rows, frame, factor, guarded)
    return ''.join(lines)


def replace_molecular_coordinates(text, kind, frame):
    """Return a new input string; never mutate a file or the supplied Frame."""
    if not isinstance(text, str):
        raise TypeError('Input template must be text.')
    if not frame.symbols or not np.isfinite(frame.positions).all():
        raise ValueError('A finite, nonempty current structure is required.')
    from .site_occupancy import is_disordered
    if is_disordered(frame):
        raise ValueError('Fractional occupancies need an explicit ordered structure before applying coordinates.')
    handlers = {'gaussian_in': _gaussian, 'orca_in': _orca, 'nwchem_in': _nwchem}
    if kind not in handlers:
        raise ValueError('Unsupported molecular input kind: ' + str(kind))
    bom = '\ufeff' if text.startswith('\ufeff') else ''
    return bom + handlers[kind](text[len(bom):], frame)
