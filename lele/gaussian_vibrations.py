"""Read Gaussian harmonic Cartesian modes independently of the ASE trajectory.

The reference is the geometry printed for that frequency calculation, in its
own orientation. It must not be replaced with an arbitrary optimization frame.
High precision supplementary tables (three dashes) are deliberately ignored:
Gaussian also prints the ordinary atom/XYZ table, which is read exactly once.
"""
from __future__ import annotations

from pathlib import Path
from .output_text import read_output_lines, check_load_cancelled
import re

import numpy as np
from ase.data import chemical_symbols
from ase.units import Hartree

from .core import Frame, NormalMode, VibrationalAnalysis

_FREQUENCIES = re.compile(r'^\s*Frequencies\s+--\s+(.+)$')
_ORIENTATION = re.compile(r'^\s*(Input|Standard|Z-Matrix) orientation:')
_CHARGE = re.compile(r'Charge\s*=\s*(-?\d+)\s+Multiplicity\s*=\s*(\d+)')
_SCF = re.compile(r'SCF Done:.*?=\s*([-+\d.DEde]+)')


def _job_boundary(line):
    return ('Normal termination of Gaussian' in line or '--Link1--' in line
            or re.search(r'Link1:\s+Proceeding to internal job step', line) is not None)


def _number(text):
    value = float(text.replace('D', 'E').replace('d', 'e'))
    if not np.isfinite(value):
        raise ValueError('Non-finite printed number')
    return value


def _orientation(lines, start, info):
    separators = 0
    rows = []
    for i in range(start + 1, len(lines)):
        line = lines[i].strip()
        if line and set(line) == {'-'}:
            separators += 1
            if separators == 3:
                if not rows:
                    return None, i + 1
                numbers = [row[0] for row in rows]
                frame = Frame([chemical_symbols[n] if n > 0 else 'X' for n in numbers],
                              [row[1] for row in rows], info=dict(info))
                return (frame, numbers), i + 1
            continue
        if separators == 2:
            fields = line.split()
            try:
                if len(fields) != 6 or int(fields[0]) != len(rows) + 1:
                    return None, i + 1
                atomic_number = int(fields[1])
                if atomic_number >= len(chemical_symbols):
                    return None, i + 1
                rows.append((atomic_number, [_number(x) for x in fields[3:]]))
            except ValueError:
                return None, i + 1
        elif i - start > 8:
            return None, i + 1
    return None, len(lines)


def read_gaussian_vibrations(path: str | Path):
    """Return analyses and reader notices, keeping complete modes in partial logs."""
    lines = read_output_lines(path)
    if not any('Frequencies' in line for line in lines):return [], ''
    from .output_text import load_progress
    progress=load_progress('Gaussian: vibrational modes',len(lines))
    analyses, notices = [], []
    current = None
    analysis = None
    info = {}
    i = 0
    while i < len(lines):
        check_load_cancelled()
        progress(i)
        line = lines[i]
        # A combined Opt+Freq file can contain independently terminated jobs.
        # Never reuse an earlier job's orientation if a later one omits it.
        if _job_boundary(line):
            current = analysis = None
            info = {}
        charge = _CHARGE.search(line)
        if charge:
            info.update(converter_charge=int(charge[1]), converter_mult=int(charge[2]))
        orientation = _ORIENTATION.match(line)
        if orientation:
            analysis = None
            current, i = _orientation(lines, i, info)
            if current is None:
                notices.append('Incomplete Gaussian reference orientation; affected modes cannot be animated.')
            continue
        scf = _SCF.search(line)
        if scf and current is not None:
            current[0].energy_ev = _number(scf[1]) * Hartree
        if 'Harmonic frequencies (' in line:
            analysis = None
        frequencies = _FREQUENCIES.match(line)
        if not frequencies:
            i += 1
            continue
        try:
            values = [_number(x) for x in frequencies[1].split()]
        except ValueError:
            notices.append(f'Unreadable Gaussian frequency at line {i + 1}.')
            i += 1
            continue
        count = len(values)
        numbers, symmetry = [], [''] * count
        for j in range(i - 1, max(-1, i - 5), -1):
            fields = lines[j].split()
            if len(fields) == count and all(x.isdigit() and int(x) > 0 for x in fields):
                numbers = [int(x) for x in fields]
                if j + 1 < i and len(lines[j + 1].split()) == count:
                    symmetry = lines[j + 1].split()
                break
        if current is None:
            notices.append('Gaussian frequencies found without a reference orientation; animation unavailable.')
            i += 1
            continue
        if (analysis is None or (numbers and analysis.modes
                                and numbers[0] <= analysis.modes[-1].number)):
            analysis = VibrationalAnalysis(current[0].clone(), source_line=i + 1)
            analyses.append(analysis)
        if not numbers:
            first = analysis.modes[-1].number + 1 if analysis.modes else 1
            numbers = list(range(first, first + count))
        properties = {}
        j = i + 1
        found_table = False
        while j < min(i + 18, len(lines)):
            fields = lines[j].split()
            if fields[:2] == ['Atom', 'AN']:
                found_table = True
                j += 1
                break
            if (_FREQUENCIES.match(lines[j]) or _ORIENTATION.match(lines[j])
                    or _job_boundary(lines[j]) or 'Harmonic frequencies (' in lines[j]):
                break
            if '--' in lines[j]:
                label, raw = lines[j].split('--', 1)
                key = {'IR Inten': 'ir_intensity', 'Red. masses': 'reduced_mass',
                       'Frc consts': 'force_constant', 'Raman Activ': 'raman_activity'}.get(label.strip())
                if key:
                    try:
                        prop = [_number(x) for x in raw.split()]
                        if len(prop) == count:
                            properties[key] = prop
                    except ValueError:
                        pass
            j += 1
        vectors = []
        if found_table:
            for atom, expected_number in enumerate(current[1], 1):
                if j >= len(lines):
                    break
                fields = lines[j].split()
                try:
                    if (len(fields) != 2 + 3 * count or int(fields[0]) != atom
                            or int(fields[1]) != expected_number):
                        break
                    vectors.append([_number(x) for x in fields[2:]])
                except ValueError:
                    break
                j += 1
        complete = len(vectors) == len(analysis.reference.symbols)
        data = np.asarray(vectors).reshape(-1, count, 3) if complete else None
        if not complete:
            message = f'Modes {numbers[0]}–{numbers[-1]}: missing or incomplete Cartesian displacements.'
            analysis.note = '\n'.join(filter(None, (analysis.note, message)))
        for column, value in enumerate(values):
            analysis.modes.append(NormalMode(
                numbers[column], value, None if data is None else data[:, column, :],
                symmetry=symmetry[column],
                **{key: prop[column] for key, prop in properties.items()}))
        i = max(i + 1, j)
    progress(len(lines))
    return [a for a in analyses if a.modes], ' '.join(dict.fromkeys(notices))
