#!/usr/bin/env python3
"""SIESTA relaxation history reader for .out and companion .ANI files.

Associate explicit ionic moves first; use complete-count matching otherwise.
Do not confuse electronic SCF iterations with ionic relaxation steps.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from .output_text import read_output_lines, check_load_cancelled, load_progress, open_output_text
import re
import numpy as np

from .core import Frame

ELEMENTS = ('X H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og').split()
SYMBOLS = set(ELEMENTS[1:])
NUMBER = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?')
ENERGY = re.compile(r'(?i)\b(?:siesta\s*:\s*)?(E[_-]?tot|Etot|E[_-]?KS(?:\([^)]*\))?)\s*=\s*(' + NUMBER.pattern + r')')
SPECIES = re.compile(r'(?i)Species\s+number\s*:\s*(\d+).*?Atomic\s+number\s*:\s*([+-]?\d+).*?Label\s*:\s*(\S+)')
CELL_HEADER = re.compile(r'(?i)(?:outcell:\s*unit\s+cell\s+vectors|siesta:\s*automatic\s+unit\s+cell\s+vectors)')
COORD_HEADER = re.compile(r'(?i)(?:outcoor:\s*.*coordinate|siesta:\s*atomic\s+coordinates)')
BOHR = 0.529177210903
SPIN_FLAG = re.compile(r'(?i)\bSpinPolarized\s*(?:=|:)?\s*(\.true\.|\.false\.|true|false|yes|no|[TF])(?=\s|$)')


def _number(text):
    return float(text.replace('d','e').replace('D','E'))


def _symbol(token, species):
    word = re.sub(r'[^A-Za-z]', '', token)
    if word:
        c = word[0].upper() + word[1:].lower()
        if c in SYMBOLS:
            return c
    try:
        num = int(token)
        if num in species:
            return species[num]
        if 1 <= num < len(ELEMENTS):
            return ELEMENTS[num]
    except (TypeError, ValueError):
        pass
    return None


def _coordinate_line(raw, species):
    line = raw.strip()
    if line.lower().startswith(('outcoor:', 'siesta:')):
        line = line.split(':', 1)[1].strip()
    parts = line.split()
    if len(parts) < 4:
        return None
    # Siesta outcoor prints x y z followed by species, Z or atomic label.
    try:
        coords = [_number(p) for p in parts[:3]]
    except ValueError:
        # Also accept atom-index, symbol, x, y, z in some printed formats.
        if len(parts) < 5 or not parts[0].isdigit():
            return None
        symbol = _symbol(parts[1], species)
        if symbol is None:
            return None
        try:
            return symbol, [_number(x) for x in parts[2:5]]
        except ValueError:
            return None
    symbol = next((_symbol(x, species) for x in reversed(parts[3:])
                   if re.search('[A-Za-z]', x) and _symbol(x, species)), None)
    if symbol is None:
        # Resolve species first: a species index is not an atomic number.
        for token in parts[3:]:
            if token.isdigit() and int(token) in species:
                symbol = species[int(token)]
                break
    if symbol is None:
        for token in parts[3:]:
            symbol = _symbol(token, species)
            if symbol:
                break
    if symbol is None:
        return None
    return symbol, coords


def _extract_coordinates(lines, header_idx, species):
    names, xyz = [], []
    j = header_idx + 1
    while j < len(lines):
        s = lines[j].strip()
        if not s and xyz:
            break
        if s.startswith('---') and xyz:
            break
        atom = _coordinate_line(s, species)
        if atom is None:
            if xyz:
                break
            # Some formats insert a short column heading.
            if j - header_idx > 6:
                break
        else:
            names.append(atom[0]); xyz.append(atom[1])
        j += 1
    return names, np.asarray(xyz, dtype=float).reshape(-1, 3),j


def _frame_energy_map(frames, energy_records):
    # Last choice is E_KS; replace with Etot when both exist per ionic step.
    # SIESTA may write several electronic energies for one ion step; only map
    # if a unique complete sequence can be established.
    if not energy_records:
        return 'No per-step energies found in SIESTA output.'
    for label in ('etot', 'e_ks', 'final_total', 'total'):
        records = [(i, e) for i, kind, e in energy_records if kind == label]
        if len(records) == len(frames):
            for frame, (idx, energy) in zip(frames, records):
                frame.energy_ev = energy
                frame.info['energy_source'] = 'SIESTA .out ' + label
                frame.info['energy_source_line'] = idx+1
            return ''
    return (f'SIESTA energy/geometry counts differ ({len(energy_records)} energy records, '
            f'{len(frames)} geometries); energies not paired to steps.')


def read_siesta_output(path: Path, max_frames: int | None = None):
    """Return (frames, note), reading all printed geometry snapshots."""
    from .siesta_results import read_siesta_records
    frames, note, _ = read_siesta_records(path, max_frames)
    return frames, note


def read_siesta_ani(path: Path, max_frames=None):
    """Read the conventional XYZ-like Siesta .ANI without an ASE dependency."""
    frames = []
    size=path.stat().st_size
    progress=load_progress('SIESTA: ANI coordinate frames',size)
    with open_output_text(path) as stream:
        while True:
            check_load_cancelled();progress(min(max(0,size-1),stream.buffer.tell()))
            count_line = stream.readline()
            if not count_line:
                break
            if not count_line.strip():
                continue
            try:
                n = int(count_line.strip())
            except ValueError as e:
                raise ValueError(f'Invalid ANI atom count after frame {len(frames)}') from e
            if n <= 0 or n > 1_000_000:
                raise ValueError('Invalid ANI atom count')
            comment = stream.readline()
            if not comment:
                raise ValueError('Truncated ANI comment')
            names, coords = [], []
            for _ in range(n):
                values = stream.readline().split()
                if len(values) < 4:
                    raise ValueError('Truncated ANI atomic coordinates')
                symbol = _symbol(values[0], {})
                if symbol is None:
                    raise ValueError('Unknown ANI element: ' + values[0])
                names.append(symbol)
                coords.append([_number(x) for x in values[1:4]])
            frames.append(Frame(names, np.asarray(coords), info={'source': 'SIESTA .ANI', 'comment': comment.strip()[:180]}))
            if max_frames is not None and len(frames) > max_frames:
                raise ValueError(f'ANI exceeds frame limit ({max_frames})')
    progress(size)
    return frames


def read_siesta_mde(path: Path):
    """Read only the documented MDE Step/T/E_KS/E_tot columns (eV).

    Arbitrary .MDE column layouts are intentionally not guessed.
    """
    lines = read_output_lines(path)
    header_found = any(re.match(r'(?i)^\s*#\s*Step\s+T\b', ln)
                       and re.search(r'(?i)E[_-]?KS', ln)
                       and re.search(r'(?i)E[_-]?tot', ln) for ln in lines)
    if not header_found:
        return []
    values = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        tokens = line.split()
        if len(tokens) < 4:
            continue
        try:
            step = int(tokens[0])
            energy = _number(tokens[3])
        except ValueError:
            continue
        if not np.isfinite(energy):
            continue
        values.append((step, energy))
    return values


def _same_name_sidecar(path, suffix):
    candidate = path.with_suffix(suffix)
    if candidate.is_file():
        return candidate
    return next((p for p in path.parent.iterdir()
                 if p.is_file() and p.suffix.lower() == suffix.lower()
                 and p.stem.lower() == path.stem.lower()), None)


def _add_mde_energies(path, frames):
    sidecar = _same_name_sidecar(path, '.MDE')
    if sidecar is None:
        return False
    try:
        energies = read_siesta_mde(sidecar)
    except (OSError, ValueError):
        return False
    if len(energies) != len(frames) or not frames:
        return False
    # Data must represent distinct ordered ionic steps.
    if any(b[0] <= a[0] for a, b in zip(energies, energies[1:])):
        return False
    for frame, (_, value) in zip(frames, energies):
        frame.energy_ev = value
        frame.info['energy_source'] = f'SIESTA {sidecar.name} E_tot'
    return True


def load_siesta_history(path: Path, max_frames=None, *, include_results=False):
    """Prefer .out snapshots; fall back to sibling .ANI when .out is sparse.

    A companion ANI has no unit cell; use per-step .out cells only with an
    unambiguous 1:1 match, otherwise refuse to invent a cell trajectory.
    """
    from .siesta_results import read_siesta_records, results_from_frames
    def finish(frames, note, results=None):
        if not include_results: return frames, note
        if results is None: results = results_from_frames(frames, note)
        results.note = note
        return frames, note, results

    if path.suffix.lower() == '.ani':
        ani_frames = read_siesta_ani(path, max_frames)
        matched = _add_mde_energies(path, ani_frames)
        return finish(ani_frames, ('ANI trajectory with matching MDE step energies.' if matched
                            else 'ANI coordinates only: energy and cell are not stored in ANI.'))

    output_frames, output_note, output_results = read_siesta_records(path, max_frames)
    ani = _same_name_sidecar(path, '.ANI')
    if ani is None:
        # Only an unambiguous sole .ANI is eligible when SystemLabel differs
        # from the shell-redirection output basename.
        all_ani = [q for q in path.parent.iterdir() if q.is_file() and q.suffix.lower() == '.ani']
        if len(all_ani) == 1:
            ani = all_ani[0]
    if ani is not None:
        try:
            ani_frames = read_siesta_ani(ani, max_frames)
        except (ValueError, OSError) as ex:
            return finish(output_frames, f'Companion ANI not readable: {ex}; {output_note}', output_results)
        if output_frames and ani_frames and ani_frames[-1].symbols != output_frames[-1].symbols:
            # A single unrelated ANI file in the directory must not replace
            # the currently opened calculation's geometry.
            return finish(output_frames, output_note, output_results)
        if ani.stem.lower() != path.stem.lower():
            if not output_frames:
                return finish(output_frames, output_note, output_results)
            # A distinct SystemLabel is common, but only pair an unmatched
            # basename when an actual output snapshot occurs in the ANI.
            source = output_frames[-1]
            if not any(f.symbols == source.symbols
                       and np.allclose(f.positions, source.positions, atol=0.05, rtol=0)
                       for f in ani_frames):
                return finish(output_frames, output_note, output_results)
        if len(ani_frames) > len(output_frames):
            # An ANI trajectory has no lattice. A unique unchanged lattice
            # reported by .out can be used, but variable cells cannot.
            cells = [f.cell for f in output_frames if any(f.pbc)]
            if cells and all(np.allclose(cells[0], other) for other in cells[1:]):
                for f in ani_frames:
                    f.cell = cells[0].copy()
                    f.pbc = (True, True, True)
            spin = output_frames[-1].info.get('spin_polarized') if output_frames else None
            if spin is not None:
                for f in ani_frames:
                    f.info['spin_polarized'] = spin
            matched = _add_mde_energies(ani, ani_frames)
            if not matched:
                # Etot records from .out can be associated by count only.
                records = []
                for raw in read_output_lines(path):
                    m = ENERGY.search(raw)
                    if m and m.group(1).lower().replace('_', '').replace('-', '') == 'etot':
                        records.append(_number(m.group(2)))
                if len(records) == len(ani_frames):
                    for frame, energy in zip(ani_frames, records):
                        frame.energy_ev = energy
                        frame.info['energy_source'] = 'SIESTA .out Etot (count-matched ANI)'
                    matched = True
            notes = f'{len(ani_frames)} geometries from {ani.name}'
            if cells:
                notes += '; cell reused from available .out snapshots (verify variable-cell runs)'
            if matched:
                notes += '; per-step energies available'
            else:
                notes += '; per-step energies unavailable or not uniquely matchable'
            return finish(ani_frames, notes)
    if output_frames and not any(f.energy_ev is not None for f in output_frames):
        if _add_mde_energies(path, output_frames):
            output_note = 'Per-step energies from matching SIESTA MDE.'
            output_results = results_from_frames(output_frames, output_note)
    return finish(output_frames, output_note, output_results)
