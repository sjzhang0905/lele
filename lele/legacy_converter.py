#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import os
import queue
import re
import sys
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from ase import Atoms
from ase.data import atomic_numbers, chemical_symbols
from ase.io import read as ase_read
from ase.io import write as ase_write


APP_NAME = "ChemStructConverter"
APP_VERSION = "1.1.0"
BOHR_TO_ANG = 0.529177210903
DEFAULT_BOX = 30.0
DEFAULT_GAUSSIAN_ROUTE = "#p hf/sto-3g"

TARGETS = {
    "XYZ": "xyz",
    "Gaussian GJF": "gjf",
    "CIF": "cif",
    "POSCAR Direct": "poscar-direct",
    "POSCAR Cartesian": "poscar-cartesian",
}

SUPPORTED_SUFFIXES = {
    ".xyz",
    ".gjf",
    ".com",
    ".cif",
    ".log",
    ".out",
    ".inp",
    ".in",
    ".pwi",
    ".pwo",
    ".nw",
    ".nwi",
    ".nwo",
    ".fdf",
    ".pdb",
    ".pqr",
    ".mol",
    ".mol2",
    ".sdf",
    ".xsf",
    ".cube",
    ".cub",
    ".gen",
    ".cfg",
    ".gro",
    ".g96",
    ".traj",
    ".res",
    ".xsd",
    ".xtd",
    ".vasp",
    ".xv",
    ".ani",
    ".struct",
}

GENERIC_SUFFIX_READERS = {
    ".pdb": ("PDB", "proteindatabank"),
    ".mol": ("MDL MOL", "mol"),
    ".sdf": ("SDF", "sdf"),
    ".xsf": ("XCrySDen XSF", "xsf"),
    ".cube": ("Gaussian CUBE", "cube"),
    ".cub": ("Gaussian CUBE", "cube"),
    ".gen": ("DFTB+ GEN", "gen"),
    ".cfg": ("AtomEye CFG", "cfg"),
    ".gro": ("GROMACS GRO", "gromacs"),
    ".g96": ("GROMOS96", "gromos"),
    ".traj": ("ASE trajectory", "traj"),
    ".res": ("SHELX RES", "res"),
    ".xsd": ("Materials Studio XSD", "xsd"),
    ".xtd": ("Materials Studio XTD", "xtd"),
    ".xv": ("SIESTA XV", "siesta-xv"),
    ".struct": ("WIEN2k STRUCT", "struct"),
}


@dataclass
class Detection:
    kind: str
    label: str
    ase_format: Optional[str] = None


class ConversionError(RuntimeError):
    pass


def read_probe(path: Path, head_bytes: int = 256_000, tail_bytes: int = 768_000) -> str:
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(head_bytes)
        if size > head_bytes:
            try:
                handle.seek(max(0, size - tail_bytes))
                tail = handle.read(tail_bytes)
            except OSError:
                tail = b""
        else:
            tail = b""
    encoding = 'utf-8-sig'
    if head.startswith(b'\xff\xfe'):
        encoding = 'utf-16-le'
    elif head.startswith(b'\xfe\xff'):
        encoding = 'utf-16-be'
    elif head[:4096].count(b'\0') > len(head[:4096]) // 5:
        encoding = 'utf-16-le' if head[1:4096:2].count(0) >= head[:4096:2].count(0) else 'utf-16-be'
    return '\n'.join(part.decode(encoding, errors='replace').lstrip('\ufeff') for part in (head, tail))


def looks_like_vasp_structure(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        return False
    try:
        float(lines[1].split()[0])
        for i in range(2, 5):
            vals = lines[i].split()
            if len(vals) < 3:
                return False
            [float(vals[j]) for j in range(3)]
    except (ValueError, IndexError):
        return False
    coord_markers = {"direct", "cartesian", "kpoints", "selective"}
    lowered = " ".join(lines[5:9]).lower()
    return any(marker in lowered for marker in coord_markers)


def detect_format(path: Path) -> Detection:
    name = path.name
    upper_name = name.upper()
    suffix = path.suffix.lower()

    if upper_name == "OUTCAR":
        return Detection("vasp_out", "VASP OUTCAR")
    if upper_name in {"POSCAR", "CONTCAR"}:
        return Detection("vasp_in", f"VASP {upper_name}")
    if suffix == ".ani":
        return Detection("siesta_ani", "SIESTA ANI trajectory")
    if suffix == ".xyz":
        probe=read_probe(path)
        if looks_like_xtb_trajectory(probe,name):
            return Detection("xtb_trj", "xTB optimization trajectory")
        return Detection("xyz", "XYZ / XYZ trajectory")
    if suffix == ".cif":
        return Detection("cif", "CIF")
    if suffix in {".gjf", ".com"}:
        return Detection("gaussian_in", "Gaussian input")
    if suffix == ".fdf":
        return Detection("siesta_in", "SIESTA input")
    if suffix == ".mol2":
        return Detection("mol2", "Tripos MOL2")
    if suffix == ".pqr":
        return Detection("pqr", "PQR")
    if suffix == ".vasp":
        return Detection("vasp_in", "VASP structure")
    if upper_name == "VASPRUN.XML":
        return Detection("ase_generic", "VASP vasprun.xml", "vasp-xml")
    if upper_name == "XDATCAR":
        return Detection("ase_generic", "VASP XDATCAR", "vasp-xdatcar")
    if suffix in GENERIC_SUFFIX_READERS:
        label, ase_format = GENERIC_SUFFIX_READERS[suffix]
        return Detection("ase_generic", label, ase_format)

    text = read_probe(path)
    upper = text.upper()

    if looks_like_xtb_trajectory(text,name):
        return Detection("xtb_trj", "xTB optimization trajectory")
    if re.search(r"(?mi)^\s*\*?\s*xtb version\s+\d",text):
        return Detection("xtb_out", "xTB output")

    if "PROGRAM PWSCF" in upper or "QUANTUM ESPRESSO" in upper and "JOB DONE" in upper:
        return Detection("qe_out", "Quantum ESPRESSO output")
    if "CP2K| VERSION STRING" in upper or "MODULE QUICKSTEP: ATOMIC COORDINATES" in upper:
        return Detection("cp2k_out", "CP2K output")
    if "ORCA TERMINATED NORMALLY" in upper or "O   R   C   A" in upper or "ORCA VERSION" in upper:
        return Detection("orca_out", "ORCA output")
    if "NORTHWEST COMPUTATIONAL CHEMISTRY PACKAGE" in upper or "NWCHEM" in upper and "TOTAL TIMES" in upper:
        return Detection("nwchem_out", "NWChem output")
    if "ENTERING GAUSSIAN SYSTEM" in upper or "GAUSSIAN, INC." in upper or "STANDARD ORIENTATION:" in upper and "SCF DONE" in upper:
        return Detection("gaussian_out", "Gaussian output")
    if "OUTCOOR:" in upper or "SIESTA: ATOMIC COORDINATES" in upper or "WELCOME TO SIESTA" in upper:
        return Detection("siesta_out", "SIESTA output")
    if "VASp".upper() in upper and "POSITION" in upper and "TOTAL-FORCE" in upper:
        return Detection("vasp_out", "VASP output")

    if re.search(r"(?mi)^\s*&GLOBAL\b", text) or re.search(r"(?mi)^\s*&FORCE_EVAL\b", text):
        return Detection("cp2k_in", "CP2K input")
    if re.search(r"(?mi)^\s*&CONTROL\b", text) and re.search(r"(?mi)^\s*&SYSTEM\b", text) and "ATOMIC_POSITIONS" in upper:
        return Detection("qe_in", "Quantum ESPRESSO input")
    if "ATOMICCOORDINATESANDATOMICSPECIES" in upper or "%BLOCK CHEMICALSPECIESLABEL" in upper:
        return Detection("siesta_in", "SIESTA input")
    if re.search(r"(?mi)^\s*\*\s*XYZ(?:FILE)?\b", text) or re.search(r"(?mi)^\s*!\s*\S+", text) and "%PAL" in upper:
        return Detection("orca_in", "ORCA input")
    if re.search(r"(?mi)^\s*GEOMETRY(?:\s+\S+)*\s*$", text) and re.search(r"(?mi)^\s*TASK\s+", text):
        return Detection("nwchem_in", "NWChem input")
    if re.search(r"(?mi)^\s*#.*(?:HF|DFT|B3LYP|PBE|OPT|FREQ|SP)\b", text) and re.search(r"(?m)^\s*[+-]?\d+\s+\d+\s*$", text):
        return Detection("gaussian_in", "Gaussian input")
    if looks_like_vasp_structure(text):
        return Detection("vasp_in", "VASP POSCAR-like input")

    if suffix in {".out", ".log"}:
        raise ConversionError("Unable to identify output format from file contents")
    if suffix in {".inp", ".in", ".pwi"}:
        raise ConversionError("Unable to identify input format from file contents")
    raise ConversionError("Unsupported or unrecognized file format")


def looks_like_xtb_trajectory(text,name=''):
    lines=text.splitlines()
    if len(lines)<2 or not lines[0].strip().isdigit():return False
    comment=lines[1].lower()
    return (bool(re.search(r'\bxtb\s*:',comment)) or
            (name.lower() in ('xtbopt.xyz','xtblast.xyz') and
             bool(re.search(r'\bscf\s+done\b|\benergy\s*:',comment))))


def normalize_element(label: str, fallback_z: Optional[int] = None) -> str:
    raw = (label or "").strip()

    if raw:
        exact = raw[0].upper() + raw[1:].lower() if raw.isalpha() else ""
        if exact in atomic_numbers:
            return exact

        prefix = re.match(r"^([A-Za-z]{1,2})(?:[_\-.:/\d].*)$", raw)
        if prefix:
            item = prefix.group(1)
            symbol = item[0].upper() + item[1:].lower()
            if symbol in atomic_numbers:
                return symbol
            symbol = item[0].upper()
            if symbol in atomic_numbers:
                return symbol

        token = re.sub(r"[^A-Za-z]", "", raw)
        if token:
            for item in (token, token[:2], token[:1]):
                if not item:
                    continue
                symbol = item[0].upper() + item[1:].lower()
                if symbol in atomic_numbers:
                    return symbol

    if fallback_z is not None and 0 < int(fallback_z) < len(chemical_symbols):
        return chemical_symbols[int(fallback_z)]
    raise ConversionError(f"Cannot determine element from label: {label!r}")


def _to_float(token: str) -> float:
    return float(token.replace("D", "E").replace("d", "e"))


def _cell_from_lengths_angles(a: float, b: float, c: float, alpha: float, beta: float, gamma: float) -> np.ndarray:
    ar = math.radians(alpha)
    br = math.radians(beta)
    gr = math.radians(gamma)
    va = np.array([a, 0.0, 0.0], dtype=float)
    vb = np.array([b * math.cos(gr), b * math.sin(gr), 0.0], dtype=float)
    cx = c * math.cos(br)
    sin_g = math.sin(gr)
    if abs(sin_g) < 1e-12:
        raise ConversionError("Invalid cell: gamma angle produces a singular lattice")
    cy = c * (math.cos(ar) - math.cos(br) * math.cos(gr)) / sin_g
    cz2 = c * c - cx * cx - cy * cy
    if cz2 < -1e-8:
        raise ConversionError("Invalid cell lengths/angles")
    vc = np.array([cx, cy, math.sqrt(max(0.0, cz2))], dtype=float)
    return np.array([va, vb, vc], dtype=float)


def _strip_inline_comment(line: str) -> str:
    for marker in ("#", "!"):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line.strip()


def parse_cp2k_input(path: Path) -> Atoms:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    stack: list[tuple[str, str]] = []
    cell = None
    cell_rows: dict[str, np.ndarray] = {}
    abc = None
    angles = (90.0, 90.0, 90.0)
    coord_unit = "angstrom"
    coord_scaled = False
    coords: list[list[float]] = []
    labels: list[str] = []
    kind_elements: dict[str, str] = {}
    periodic_none = False

    current_kind: Optional[str] = None

    for raw in lines:
        line = _strip_inline_comment(raw)
        if not line:
            continue
        if line.startswith("&"):
            parts = line[1:].split()
            key = parts[0].upper() if parts else ""
            if key == "END":
                if stack:
                    ended, arg = stack.pop()
                    if ended == "KIND":
                        current_kind = None
                continue
            arg = parts[1] if len(parts) > 1 else ""
            stack.append((key, arg))
            if key == "KIND":
                current_kind = arg
            continue

        section = stack[-1][0] if stack else ""
        parts = line.split()
        key = parts[0].upper() if parts else ""

        if section == "KIND" and current_kind and key == "ELEMENT" and len(parts) >= 2:
            kind_elements[current_kind] = normalize_element(parts[1])
            continue

        if section == "CELL":
            if key in {"A", "B", "C"} and len(parts) >= 4:
                vals = np.array([_to_float(x) for x in parts[-3:]], dtype=float)
                cell_rows[key] = vals
            elif key == "ABC" and len(parts) >= 4:
                abc = tuple(_to_float(x) for x in parts[-3:])
            elif key in {"ALPHA_BETA_GAMMA", "ANGLES"} and len(parts) >= 4:
                angles = tuple(_to_float(x) for x in parts[-3:])
            elif key == "PERIODIC" and len(parts) >= 2 and parts[1].upper() == "NONE":
                periodic_none = True
            continue

        if section == "POISSON" and key == "PERIODIC" and len(parts) >= 2 and parts[1].upper() == "NONE":
            periodic_none = True
            continue

        if section == "COORD":
            if key == "UNIT" and len(parts) >= 2:
                coord_unit = parts[1].strip("[]").lower()
                continue
            if key == "SCALED" and len(parts) >= 2:
                coord_scaled = parts[1].strip(".").upper() in {"TRUE", "T", "YES"}
                continue
            if len(parts) >= 4:
                try:
                    xyz = [_to_float(parts[1]), _to_float(parts[2]), _to_float(parts[3])]
                except ValueError:
                    continue
                labels.append(parts[0])
                coords.append(xyz)

    if all(k in cell_rows for k in ("A", "B", "C")):
        cell = np.array([cell_rows["A"], cell_rows["B"], cell_rows["C"]], dtype=float)
    elif abc is not None:
        cell = _cell_from_lengths_angles(*abc, *angles)

    if not coords:
        raise ConversionError("No inline CP2K &COORD geometry was found")

    symbols = []
    for label in labels:
        if label in kind_elements:
            symbols.append(kind_elements[label])
        else:
            symbols.append(normalize_element(label))
    positions = np.array(coords, dtype=float)
    if coord_scaled:
        if cell is None:
            raise ConversionError("CP2K SCALED coordinates require a cell")
        positions = positions @ cell
    elif coord_unit.startswith("bohr") or coord_unit in {"au", "a.u."}:
        positions *= BOHR_TO_ANG

    atoms = Atoms(symbols=symbols, positions=positions)
    if cell is not None:
        atoms.set_cell(cell)
        atoms.set_pbc(not periodic_none)
    else:
        atoms.set_pbc(False)
    return atoms


def parse_cp2k_output(path: Path) -> Atoms:
    last_cell: Optional[np.ndarray] = None
    cell_parts: dict[str, np.ndarray] = {}
    last_symbols: Optional[list[str]] = None
    last_positions: Optional[np.ndarray] = None
    periodic_none = False

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = iter(handle)
        for raw in lines:
            upper = raw.upper()
            if "PERIODIC" in upper and "NONE" in upper and ("POISSON" in upper or "CELL" in upper):
                periodic_none = True

            m = re.search(r"CELL\|\s*VECTOR\s+([ABC])\s*\[ANGSTROM\]\s*:\s*(.*)$", raw, re.I)
            if m:
                vals = re.findall(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?", m.group(2))
                if len(vals) >= 3:
                    cell_parts[m.group(1).upper()] = np.array([_to_float(x) for x in vals[:3]], dtype=float)
                    if all(k in cell_parts for k in ("A", "B", "C")):
                        last_cell = np.array([cell_parts["A"], cell_parts["B"], cell_parts["C"]], dtype=float)
                continue

            if "ATOMIC COORDINATES IN ANGSTROM" in upper:
                block_symbols: list[str] = []
                block_positions: list[list[float]] = []
                started = False
                for block_line in lines:
                    stripped = block_line.strip()
                    if not stripped:
                        if started:
                            break
                        continue
                    tokens = stripped.split()
                    if not tokens or not re.fullmatch(r"\d+", tokens[0]):
                        if started:
                            break
                        continue
                    started = True
                    elem_idx = None
                    for i in range(1, min(len(tokens), 6)):
                        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*", tokens[i]):
                            try:
                                normalize_element(tokens[i])
                                elem_idx = i
                                break
                            except ConversionError:
                                pass
                    if elem_idx is None:
                        continue
                    nums = []
                    for token in tokens[elem_idx + 1 :]:
                        try:
                            nums.append(_to_float(token))
                        except ValueError:
                            pass
                    if len(nums) >= 6 and abs(nums[0] - round(nums[0])) < 1e-8:
                        xyz = nums[1:4]
                    elif len(nums) >= 3:
                        xyz = nums[:3]
                    else:
                        continue
                    block_symbols.append(normalize_element(tokens[elem_idx]))
                    block_positions.append(xyz)
                if block_positions:
                    last_symbols = block_symbols
                    last_positions = np.array(block_positions, dtype=float)

    if last_symbols is None or last_positions is None:
        raise ConversionError("No CP2K atomic coordinate block was found")

    atoms = Atoms(symbols=last_symbols, positions=last_positions)
    if last_cell is not None:
        atoms.set_cell(last_cell)
        atoms.set_pbc(not periodic_none)
    return atoms


def _fdf_clean(line: str) -> str:
    for marker in ("#", "!"):
        idx = line.find(marker)
        if idx >= 0:
            line = line[:idx]
    return line.strip()


def _fdf_blocks(lines: list[str]) -> dict[str, list[str]]:
    blocks: dict[str, list[str]] = {}
    i = 0
    while i < len(lines):
        line = _fdf_clean(lines[i])
        m = re.match(r"%block\s+(\S+)", line, re.I)
        if not m:
            i += 1
            continue
        key = m.group(1).lower()
        data: list[str] = []
        i += 1
        while i < len(lines):
            cur = _fdf_clean(lines[i])
            if re.match(r"%endblock\b", cur, re.I):
                break
            if cur:
                data.append(cur)
            i += 1
        blocks[key] = data
        i += 1
    return blocks


def _fdf_scalar(lines: list[str], key: str) -> Optional[str]:
    key_re = re.escape(key)
    for raw in lines:
        line = _fdf_clean(raw)
        m = re.match(rf"^{key_re}\s+(.+)$", line, re.I)
        if m:
            return m.group(1).strip()
    return None


def _parse_value_unit(text: str, default_unit: str = "ang") -> tuple[float, str]:
    parts = text.split()
    value = _to_float(parts[0])
    unit = parts[1].lower() if len(parts) >= 2 else default_unit
    return value, unit


def _length_to_ang(value: float, unit: str) -> float:
    unit = unit.lower().strip("[]")
    if unit.startswith("bohr") or unit in {"au", "a.u."}:
        return value * BOHR_TO_ANG
    return value


def parse_siesta_input(path: Path) -> Atoms:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    blocks = _fdf_blocks(lines)

    species_map: dict[int, str] = {}
    for line in blocks.get("chemicalspecieslabel", []):
        parts = line.split()
        if len(parts) >= 3:
            try:
                idx = int(parts[0])
                z = int(float(parts[1]))
            except ValueError:
                continue
            try:
                species_map[idx] = normalize_element(parts[2], z)
            except ConversionError:
                species_map[idx] = normalize_element("", z)

    lc_text = _fdf_scalar(lines, "LatticeConstant") or "1.0 Ang"
    lc_value, lc_unit = _parse_value_unit(lc_text)
    lattice_constant = _length_to_ang(lc_value, lc_unit)

    cell = None
    lv = blocks.get("latticevectors", [])
    if len(lv) >= 3:
        rows = []
        for line in lv[:3]:
            parts = line.split()
            if len(parts) < 3:
                raise ConversionError("Invalid SIESTA LatticeVectors block")
            rows.append([_to_float(parts[0]), _to_float(parts[1]), _to_float(parts[2])])
        cell = np.array(rows, dtype=float) * lattice_constant
    else:
        lp = blocks.get("latticeparameters", [])
        if lp:
            parts = " ".join(lp).split()
            if len(parts) >= 6:
                vals = [_to_float(x) for x in parts[:6]]
                cell = _cell_from_lengths_angles(
                    vals[0] * lattice_constant,
                    vals[1] * lattice_constant,
                    vals[2] * lattice_constant,
                    vals[3],
                    vals[4],
                    vals[5],
                )

    coord_lines = blocks.get("atomiccoordinatesandatomicspecies", [])
    if not coord_lines:
        raise ConversionError("No inline SIESTA AtomicCoordinatesAndAtomicSpecies block was found")

    coord_format = (_fdf_scalar(lines, "AtomicCoordinatesFormat") or "Bohr").split()[0].lower()
    symbols: list[str] = []
    positions: list[list[float]] = []
    raw_coords: list[list[float]] = []

    for line in coord_lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            xyz = [_to_float(parts[0]), _to_float(parts[1]), _to_float(parts[2])]
            species_idx = int(float(parts[3]))
        except ValueError:
            continue
        symbol = species_map.get(species_idx)
        if symbol is None and len(parts) >= 5:
            try:
                symbol = normalize_element(parts[-1])
            except ConversionError:
                symbol = None
        if symbol is None:
            raise ConversionError(f"SIESTA species index {species_idx} has no ChemicalSpeciesLabel entry")
        symbols.append(symbol)
        raw_coords.append(xyz)

    arr = np.array(raw_coords, dtype=float)
    if coord_format in {"fractional", "scaledbylatticevectors"}:
        if cell is None:
            raise ConversionError("SIESTA fractional coordinates require a cell")
        arr = arr @ cell
    elif coord_format in {"scaledcartesian", "latticeconstant"}:
        arr *= lattice_constant
    elif "bohr" in coord_format:
        arr *= BOHR_TO_ANG

    positions = arr.tolist()
    atoms = Atoms(symbols=symbols, positions=positions)
    if cell is not None:
        atoms.set_cell(cell)
        atoms.set_pbc(True)
    return atoms


def _parse_siesta_coord_block(
    header: str,
    block_lines: list[str],
    cell: Optional[np.ndarray],
    species_map: Optional[dict[int, str]] = None,
) -> Optional[Atoms]:
    header_lower = header.lower()
    symbols: list[str] = []
    coords: list[list[float]] = []

    for line in block_lines:
        stripped = line.strip()
        if stripped.lower().startswith("outcoor:") or stripped.lower().startswith("siesta:"):
            stripped = stripped.split(":", 1)[1].strip()
        parts = stripped.split()
        if len(parts) < 4:
            continue
        try:
            xyz = [_to_float(parts[0]), _to_float(parts[1]), _to_float(parts[2])]
        except ValueError:
            continue
        symbol = None
        for token in reversed(parts[3:]):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*", token):
                try:
                    symbol = normalize_element(token)
                    break
                except ConversionError:
                    pass
        if symbol is None:
            numeric = []
            for token in parts[3:]:
                try:
                    numeric.append(int(float(token)))
                except ValueError:
                    pass
            if numeric and species_map:
                symbol = species_map.get(numeric[0])
            if symbol is None and numeric:
                for candidate in numeric:
                    if 0 < candidate < len(chemical_symbols):
                        symbol = chemical_symbols[candidate]
                        break
        if symbol is None:
            continue
        symbols.append(symbol)
        coords.append(xyz)

    if not coords:
        return None

    arr = np.array(coords, dtype=float)
    if "fractional" in header_lower:
        if cell is None:
            return None
        arr = arr @ cell
    elif "bohr" in header_lower:
        arr *= BOHR_TO_ANG

    atoms = Atoms(symbols=symbols, positions=arr)
    if cell is not None:
        atoms.set_cell(cell)
        atoms.set_pbc(True)
    return atoms


def parse_siesta_output(path: Path) -> Atoms:
    last_cell: Optional[np.ndarray] = None
    last_atoms: Optional[Atoms] = None
    species_map: dict[int, str] = {}

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = iter(handle)
        for raw in lines:
            lower = raw.lower()
            species_match = re.search(
                r"Species\s+number:\s*(\d+).*?Atomic\s+number:\s*([+-]?\d+).*?Label:\s*(\S+)",
                raw,
                re.I,
            )
            if species_match:
                idx = int(species_match.group(1))
                z = int(species_match.group(2))
                label = species_match.group(3)
                try:
                    species_map[idx] = normalize_element(label, abs(z))
                except ConversionError:
                    if 0 < abs(z) < len(chemical_symbols):
                        species_map[idx] = chemical_symbols[abs(z)]
                continue

            if "outcell: unit cell vectors" in lower or "siesta: automatic unit cell vectors" in lower:
                rows = []
                for _ in range(3):
                    try:
                        line = next(lines)
                    except StopIteration:
                        break
                    stripped = line.strip()
                    if stripped.lower().startswith("outcell:") or stripped.lower().startswith("siesta:"):
                        stripped = stripped.split(":", 1)[1].strip()
                    vals = re.findall(r"[-+]?\d*\.?\d+(?:[EeDd][-+]?\d+)?", stripped)
                    if len(vals) >= 3:
                        rows.append([_to_float(x) for x in vals[:3]])
                if len(rows) == 3:
                    last_cell = np.array(rows, dtype=float)
                continue

            is_outcoor = "outcoor:" in lower and "coordinate" in lower
            is_siesta_coords = "siesta: atomic coordinates" in lower
            if is_outcoor or is_siesta_coords:
                block: list[str] = []
                for block_line in lines:
                    b = block_line.strip()
                    bl = b.lower()
                    if not b:
                        if block:
                            break
                        continue
                    if b.startswith("---") or (":" in b and block and not bl.startswith(("outcoor:", "siesta:"))):
                        break
                    probe = b
                    if bl.startswith("outcoor:") or bl.startswith("siesta:"):
                        probe = b.split(":", 1)[1].strip()
                    parts = probe.split()
                    if len(parts) < 3:
                        if block:
                            break
                        continue
                    try:
                        [_to_float(parts[i]) for i in range(3)]
                    except (ValueError, IndexError):
                        if block:
                            break
                        continue
                    block.append(block_line)
                parsed = _parse_siesta_coord_block(raw, block, last_cell, species_map)
                if parsed is not None:
                    last_atoms = parsed

    if last_atoms is None:
        raise ConversionError("No SIESTA coordinate block was found")
    return last_atoms


def parse_orca_input(path: Path) -> Atoms:
    text = path.read_text(encoding="utf-8", errors="replace")

    xyz_match = re.search(r"(?ims)^\s*\*\s*xyz\s+([+-]?\d+)\s+(\d+)\s*$\n(.*?)^\s*\*\s*$", text)
    if xyz_match:
        charge = int(xyz_match.group(1))
        mult = int(xyz_match.group(2))
        body = xyz_match.group(3)
        symbols = []
        positions = []
        for line in body.splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                xyz = [_to_float(parts[1]), _to_float(parts[2]), _to_float(parts[3])]
            except ValueError:
                continue
            symbols.append(normalize_element(parts[0]))
            positions.append(xyz)
        if not positions:
            raise ConversionError("ORCA * xyz block contains no Cartesian coordinates")
        atoms = Atoms(symbols=symbols, positions=positions)
        atoms.info["converter_charge"] = charge
        atoms.info["converter_mult"] = mult
        return atoms

    coords_match = re.search(r"(?ims)%coords\b(.*?)^\s*end\s*$", text)
    if coords_match:
        body = coords_match.group(1)
        charge_m = re.search(r"(?mi)^\s*Charge\s+([+-]?\d+)\s*$", body)
        mult_m = re.search(r"(?mi)^\s*Mult\s+(\d+)\s*$", body)
        coord_m = re.search(r"(?ims)^\s*coords\s*$\n(.*?)^\s*end\s*$", body)
        if coord_m:
            symbols = []
            positions = []
            for line in coord_m.group(1).splitlines():
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    xyz = [_to_float(parts[1]), _to_float(parts[2]), _to_float(parts[3])]
                except ValueError:
                    continue
                symbols.append(normalize_element(parts[0]))
                positions.append(xyz)
            if positions:
                atoms = Atoms(symbols=symbols, positions=positions)
                if charge_m:
                    atoms.info["converter_charge"] = int(charge_m.group(1))
                if mult_m:
                    atoms.info["converter_mult"] = int(mult_m.group(1))
                return atoms

    if re.search(r"(?mi)^\s*\*\s*xyzfile\b", text):
        raise ConversionError("ORCA xyzfile inputs require the referenced XYZ file and are not self-contained")
    raise ConversionError("No supported inline ORCA coordinate block was found")



def parse_mol2(path: Path) -> Atoms:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    atom_start = None
    crystal_start = None
    for idx, raw in enumerate(lines):
        tag = raw.strip().upper()
        if tag == "@<TRIPOS>ATOM":
            atom_start = idx + 1
        elif tag == "@<TRIPOS>CRYSIN":
            crystal_start = idx + 1

    if atom_start is None:
        raise ConversionError("No @<TRIPOS>ATOM block was found")

    symbols: list[str] = []
    positions: list[list[float]] = []
    for raw in lines[atom_start:]:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("@<TRIPOS>"):
            break
        parts = stripped.split()
        if len(parts) < 6:
            continue
        try:
            xyz = [_to_float(parts[2]), _to_float(parts[3]), _to_float(parts[4])]
        except ValueError:
            continue
        atom_name = parts[1]
        atom_type = parts[5].split(".", 1)[0]
        try:
            symbol = normalize_element(atom_type)
        except ConversionError:
            symbol = normalize_element(atom_name)
        symbols.append(symbol)
        positions.append(xyz)

    if not positions:
        raise ConversionError("MOL2 atom block contains no readable coordinates")

    atoms = Atoms(symbols=symbols, positions=positions)
    if crystal_start is not None and crystal_start < len(lines):
        for raw in lines[crystal_start:]:
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("@<TRIPOS>"):
                break
            parts = stripped.split()
            if len(parts) >= 6:
                try:
                    vals = [_to_float(x) for x in parts[:6]]
                    atoms.set_cell(_cell_from_lengths_angles(*vals))
                    atoms.set_pbc(True)
                except (ValueError, ConversionError):
                    pass
            break
    return atoms


def parse_pqr(path: Path) -> Atoms:
    symbols: list[str] = []
    positions: list[list[float]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw.startswith(("ATOM  ", "HETATM")):
            continue
        try:
            x = _to_float(raw[30:38].strip())
            y = _to_float(raw[38:46].strip())
            z = _to_float(raw[46:54].strip())
        except (ValueError, IndexError):
            parts = raw.split()
            if len(parts) < 8:
                continue
            numeric = []
            for token in parts:
                try:
                    numeric.append(_to_float(token))
                except ValueError:
                    pass
            if len(numeric) < 5:
                continue
            x, y, z = numeric[-5:-2]

        element_field = raw[76:78].strip() if len(raw) >= 78 else ""
        atom_name = raw[12:16].strip() if len(raw) >= 16 else ""
        try:
            symbol = normalize_element(element_field) if element_field else normalize_element(atom_name)
        except ConversionError:
            cleaned = re.sub(r"^[0-9]+", "", atom_name)
            symbol = normalize_element(cleaned)
        symbols.append(symbol)
        positions.append([x, y, z])

    if not positions:
        raise ConversionError("No ATOM/HETATM coordinates were found in PQR file")
    return Atoms(symbols=symbols, positions=positions)


def integerize_cif_occupancies(atoms: Atoms) -> tuple[Atoms, list[str]]:
    occupancy = atoms.info.get("occupancy")
    if not isinstance(occupancy, dict) or not occupancy:
        return atoms, []

    out = atoms.copy()
    out.info = dict(atoms.info)
    kinds = out.arrays.get("spacegroup_kinds") if hasattr(out, "arrays") else None

    affected_atoms = 0
    affected_kinds: set[str] = set()
    mixed_kinds: set[str] = set()
    partial_kinds: set[str] = set()

    for index in range(len(out)):
        if kinds is not None and index < len(kinds):
            kind_key = str(int(kinds[index]))
        else:
            kind_key = str(index)

        species_map = occupancy.get(kind_key)
        if not isinstance(species_map, dict) or not species_map:
            continue

        parsed: list[tuple[str, float]] = []
        for species, value in species_map.items():
            try:
                symbol = normalize_element(str(species))
                occ = float(value)
            except (ConversionError, TypeError, ValueError):
                continue
            parsed.append((symbol, occ))
        if not parsed:
            continue

        current = out[index].symbol
        max_occ = max(value for _, value in parsed)
        tied = [symbol for symbol, value in parsed if abs(value - max_occ) <= 1e-12]
        chosen = current if current in tied else sorted(tied)[0]
        out[index].symbol = chosen

        has_mixture = len(parsed) > 1
        has_partial = any(abs(value - 1.0) > 1e-12 for _, value in parsed)
        if has_mixture or has_partial:
            affected_atoms += 1
            affected_kinds.add(kind_key)
            if has_mixture:
                mixed_kinds.add(kind_key)
            if has_partial:
                partial_kinds.add(kind_key)

    out.info.pop("occupancy", None)
    if hasattr(out, "arrays"):
        out.arrays.pop("spacegroup_kinds", None)

    if not affected_atoms:
        return out, []

    message = (
        f"CIF fractional occupancy integerized on {affected_atoms} atom site(s) "
        f"across {len(affected_kinds)} crystallographic kind(s) using the highest-occupancy species"
    )
    if mixed_kinds:
        message += f"; mixed kinds: {len(mixed_kinds)}"
    if partial_kinds:
        message += f"; partial kinds: {len(partial_kinds)}"
    return out, [message]

def parse_charge_mult_from_text(path: Path, kind: str, atoms: Atoms) -> None:
    try:
        text = read_probe(path)
    except OSError:
        return

    charge = None
    mult = None
    if kind == "gaussian_in":
        m = re.search(r"(?m)^\s*([+-]?\d+)\s+(\d+)\s*$", text)
        if m:
            charge, mult = int(m.group(1)), int(m.group(2))
    elif kind == "gaussian_out":
        matches = re.findall(r"Charge\s*=\s*([+-]?\d+)\s+Multiplicity\s*=\s*(\d+)", text, re.I)
        if matches:
            charge, mult = map(int, matches[-1])
    elif kind.startswith("orca"):
        cm = re.findall(r"Total Charge\s+Charge\s*\.\.\.\s*([+-]?\d+)", text, re.I)
        mm = re.findall(r"Multiplicity\s+Mult\s*\.\.\.\s*(\d+)", text, re.I)
        if cm:
            charge = int(cm[-1])
        if mm:
            mult = int(mm[-1])
    elif kind.startswith("nwchem"):
        cm = re.findall(r"(?mi)^\s*charge\s+([+-]?\d+)", text)
        if cm:
            charge = int(cm[-1])

    if charge is not None:
        atoms.info["converter_charge"] = charge
    if mult is not None:
        atoms.info["converter_mult"] = mult


def read_structure(path: Path, detection: Optional[Detection] = None) -> tuple[Atoms, Detection]:
    detection = detection or detect_format(path)
    kind = detection.kind

    try:
        if kind == "xyz":
            atoms = ase_read(str(path), index=-1, format="extxyz")
        elif kind == "cif":
            atoms = ase_read(str(path), index=-1, format="cif", fractional_occupancies=True)
        elif kind == "vasp_in":
            atoms = ase_read(str(path), index=-1, format="vasp")
        elif kind == "vasp_out":
            atoms = ase_read(str(path), index=-1, format="vasp-out")
        elif kind == "gaussian_in":
            atoms = ase_read(str(path), index=-1, format="gaussian-in")
        elif kind == "gaussian_out":
            atoms = ase_read(str(path), index=-1, format="gaussian-out")
        elif kind == "orca_in":
            atoms = parse_orca_input(path)
        elif kind == "orca_out":
            atoms = ase_read(str(path), index=-1, format="orca-output")
        elif kind in ("xtb_out","xtb_trj"):
            from .xtb_results import read_xtb_results
            result=read_xtb_results(path,trajectory=kind=="xtb_trj")
            frame=next((s.geometry for s in reversed(result.steps) if s.geometry is not None),None)
            if frame is None:raise ConversionError('No complete xTB geometry found')
            atoms=Atoms(frame.symbols,positions=frame.positions,info=dict(frame.info))
        elif kind == "nwchem_in":
            atoms = ase_read(str(path), index=-1, format="nwchem-in")
        elif kind == "nwchem_out":
            atoms = ase_read(str(path), index=-1, format="nwchem-out")
        elif kind == "cp2k_in":
            atoms = parse_cp2k_input(path)
        elif kind == "cp2k_out":
            atoms = parse_cp2k_output(path)
        elif kind == "qe_in":
            atoms = ase_read(str(path), index=-1, format="espresso-in")
        elif kind == "qe_out":
            atoms = ase_read(str(path), index=-1, format="espresso-out", results_required=False)
        elif kind == "siesta_in":
            atoms = parse_siesta_input(path)
        elif kind == "siesta_out":
            atoms = parse_siesta_output(path)
        elif kind == "mol2":
            atoms = parse_mol2(path)
        elif kind == "pqr":
            atoms = parse_pqr(path)
        elif kind == "ase_generic":
            if not detection.ase_format:
                raise ConversionError("Generic ASE reader has no format identifier")
            atoms = ase_read(str(path), index=-1, format=detection.ase_format)
        else:
            raise ConversionError(f"No reader is configured for {kind}")
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Reader failed for {detection.label}: {exc}") from exc

    if isinstance(atoms, list):
        if not atoms:
            raise ConversionError("Reader returned no structures")
        atoms = atoms[-1]
    if len(atoms) == 0:
        raise ConversionError("Reader returned an empty structure")

    parse_charge_mult_from_text(path, kind, atoms)
    return atoms, detection


def structure_is_periodic(atoms: Atoms) -> bool:
    try:
        cell = np.asarray(atoms.cell.array, dtype=float)
        volume = abs(float(np.linalg.det(cell)))
    except Exception:
        volume = 0.0
    return bool(np.any(atoms.get_pbc()) and volume > 1e-8)


def strip_periodicity(atoms: Atoms) -> Atoms:
    out = atoms.copy()
    out.set_pbc(False)
    out.set_cell(np.zeros((3, 3)))
    return out


def box_isolated(atoms: Atoms, requested_box: float) -> tuple[Atoms, float, bool]:
    out = atoms.copy()
    positions = out.get_positions()
    extent = np.ptp(positions, axis=0) if len(positions) else np.zeros(3)
    max_extent = float(np.max(extent)) if len(extent) else 0.0
    box = float(requested_box)
    enlarged = False
    minimum_safe = max_extent + 4.0
    if box < minimum_safe:
        box = math.ceil(minimum_safe * 10.0) / 10.0
        enlarged = True
    out.set_cell([box, box, box])
    out.set_pbc(True)
    mins = out.get_positions().min(axis=0)
    maxs = out.get_positions().max(axis=0)
    center = 0.5 * (mins + maxs)
    shift = np.array([box / 2.0, box / 2.0, box / 2.0]) - center
    out.translate(shift)
    return out, box, enlarged


def prepare_for_target(atoms: Atoms, target: str, box_size: float) -> tuple[Atoms, list[str]]:
    messages: list[str] = []
    periodic = structure_is_periodic(atoms)
    if target in {"xyz", "gjf"}:
        if periodic:
            messages.append("periodic information removed")
        return strip_periodicity(atoms), messages

    out = atoms.copy()
    if not periodic:
        out, used_box, enlarged = box_isolated(out, box_size)
        if enlarged:
            messages.append(f"isolated system boxed and auto-enlarged to {used_box:.1f} A")
        else:
            messages.append(f"isolated system boxed in {used_box:.1f} x {used_box:.1f} x {used_box:.1f} A")
    return out, messages


def write_xyz(path: Path, atoms: Atoms, source_name: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{len(atoms)}\n")
        handle.write(f"Converted from {source_name} by {APP_NAME} {APP_VERSION}\n")
        for symbol, pos in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
            handle.write(f"{symbol:<3s} {pos[0]: .12f} {pos[1]: .12f} {pos[2]: .12f}\n")


def write_gjf(path: Path, atoms: Atoms, source_name: str, route: str) -> None:
    route = route.strip() or DEFAULT_GAUSSIAN_ROUTE
    if not route.startswith("#"):
        route = "#p " + route
    charge = int(atoms.info.get("converter_charge", 0))
    mult = int(atoms.info.get("converter_mult", 1))
    if mult < 1:
        mult = 1
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"%chk={path.stem}.chk\n")
        handle.write(route + "\n\n")
        handle.write(f"Converted from {source_name} by {APP_NAME} {APP_VERSION}\n\n")
        handle.write(f"{charge} {mult}\n")
        for symbol, pos in zip(atoms.get_chemical_symbols(), atoms.get_positions()):
            handle.write(f"{symbol:<3s} {pos[0]: .12f} {pos[1]: .12f} {pos[2]: .12f}\n")
        handle.write("\n")


def make_output_path(source: Path, out_dir: Path, target: str) -> Path:
    stem = source.stem if source.suffix else source.name
    if target == "xyz":
        name = f"{stem}.xyz"
    elif target == "gjf":
        name = f"{stem}.gjf"
    elif target == "cif":
        name = f"{stem}.cif"
    elif target == "poscar-direct":
        name = f"{stem}_POSCAR_direct"
    elif target == "poscar-cartesian":
        name = f"{stem}_POSCAR_cartesian"
    else:
        raise ConversionError(f"Unknown target format: {target}")

    candidate = out_dir / name
    if candidate.resolve() == source.resolve() or candidate.exists():
        index = 2
        base = candidate.name
        suffix = candidate.suffix
        raw_stem = candidate.stem if suffix else candidate.name
        while True:
            alt_name = f"{raw_stem}_{index}{suffix}"
            alt = out_dir / alt_name
            if not alt.exists() and alt.resolve() != source.resolve():
                candidate = alt
                break
            index += 1
    return candidate


def write_target(path: Path, atoms: Atoms, target: str, source_name: str, gaussian_route: str) -> None:
    try:
        if target == "xyz":
            write_xyz(path, atoms, source_name)
        elif target == "gjf":
            write_gjf(path, atoms, source_name, gaussian_route)
        elif target == "cif":
            ase_write(str(path), atoms, format="cif")
        elif target == "poscar-direct":
            ase_write(str(path), atoms, format="vasp", direct=True, sort=True, vasp5=True)
        elif target == "poscar-cartesian":
            ase_write(str(path), atoms, format="vasp", direct=False, sort=True, vasp5=True)
        else:
            raise ConversionError(f"Unknown target format: {target}")
    except ConversionError:
        raise
    except Exception as exc:
        raise ConversionError(f"Writer failed for {target}: {exc}") from exc


def convert_one(source: Path, target: str, out_dir: Path, box_size: float, gaussian_route: str) -> tuple[Path, Detection, list[str]]:
    detection = detect_format(source)
    atoms, detection = read_structure(source, detection)
    read_messages: list[str] = []
    if detection.kind == "cif":
        atoms, occupancy_messages = integerize_cif_occupancies(atoms)
        read_messages.extend(occupancy_messages)
    prepared, messages = prepare_for_target(atoms, target, box_size)
    messages = read_messages + messages
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = make_output_path(source, out_dir, target)
    write_target(destination, prepared, target, source.name, gaussian_route)
    return destination, detection, messages


def candidate_files(folder: Path, recursive: bool = True) -> list[Path]:
    iterator: Iterable[Path] = folder.rglob("*") if recursive else folder.glob("*")
    result = []
    for path in iterator:
        if not path.is_file():
            continue
        if path.name.upper() in {"POSCAR", "CONTCAR", "OUTCAR", "XDATCAR", "VASPRUN.XML"} or path.suffix.lower() in SUPPORTED_SUFFIXES:
            result.append(path)
    return sorted(result)


def run_cli(args: argparse.Namespace) -> int:
    target = args.to
    paths: list[Path] = []
    for raw in args.paths:
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            paths.extend(candidate_files(p, recursive=not args.no_recursive))
        else:
            paths.append(p)

    if not paths:
        print("No input files found.", file=sys.stderr)
        return 2

    failures = 0
    for source in paths:
        try:
            out_dir = Path(args.outdir).expanduser().resolve() if args.outdir else source.parent / "converted"
            destination, detection, messages = convert_one(source, target, out_dir, args.box, args.route)
            note = f" ({'; '.join(messages)})" if messages else ""
            print(f"OK  {source}  [{detection.label}] -> {destination}{note}")
        except Exception as exc:
            failures += 1
            print(f"ERR {source}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def launch_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except Exception:
        DND_FILES = None
        TkinterDnD = None

    class App:
        def __init__(self, root: tk.Tk):
            self.root = root
            self.root.title(f"{APP_NAME} {APP_VERSION}")
            self.root.geometry("980x700")
            self.files: list[Path] = []
            self.events: queue.Queue = queue.Queue()
            self.running = False

            main = ttk.Frame(root, padding=10)
            main.pack(fill=tk.BOTH, expand=True)

            top = ttk.Frame(main)
            top.pack(fill=tk.X)
            ttk.Button(top, text="Add Files", command=self.add_files).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(top, text="Add Folder", command=self.add_folder).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(top, text="Remove Selected", command=self.remove_selected).pack(side=tk.LEFT, padx=(0, 6))
            ttk.Button(top, text="Clear", command=self.clear_files).pack(side=tk.LEFT)
            self.recursive_var = tk.BooleanVar(value=True)
            ttk.Checkbutton(top, text="Recursive folder scan", variable=self.recursive_var).pack(side=tk.RIGHT)

            list_frame = ttk.LabelFrame(main, text="Input files - drop mixed files or folders here", padding=6)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 8))
            self.listbox = tk.Listbox(list_frame, selectmode=tk.EXTENDED, height=14)
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
            self.listbox.configure(yscrollcommand=scrollbar.set)
            self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            if DND_FILES is not None and hasattr(self.listbox, "drop_target_register"):
                self.listbox.drop_target_register(DND_FILES)
                self.listbox.dnd_bind("<<Drop>>", self.on_drop)

            settings = ttk.LabelFrame(main, text="Conversion settings", padding=8)
            settings.pack(fill=tk.X, pady=(0, 8))

            ttk.Label(settings, text="Target format").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
            self.target_var = tk.StringVar(value="XYZ")
            target_box = ttk.Combobox(settings, textvariable=self.target_var, values=list(TARGETS.keys()), state="readonly", width=24)
            target_box.grid(row=0, column=1, sticky=tk.W, pady=4)

            ttk.Label(settings, text="Isolated-system box size (A)").grid(row=0, column=2, sticky=tk.W, padx=(24, 8), pady=4)
            self.box_var = tk.StringVar(value=str(DEFAULT_BOX))
            ttk.Entry(settings, textvariable=self.box_var, width=12).grid(row=0, column=3, sticky=tk.W, pady=4)

            ttk.Label(settings, text="Gaussian route").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
            self.route_var = tk.StringVar(value=DEFAULT_GAUSSIAN_ROUTE)
            ttk.Entry(settings, textvariable=self.route_var, width=48).grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=4)

            ttk.Label(settings, text="Output directory").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
            self.outdir_var = tk.StringVar(value="")
            ttk.Entry(settings, textvariable=self.outdir_var).grid(row=2, column=1, columnspan=2, sticky=tk.EW, pady=4)
            ttk.Button(settings, text="Browse", command=self.choose_outdir).grid(row=2, column=3, sticky=tk.W, padx=(8, 0), pady=4)
            ttk.Label(settings, text="Leave empty to create a 'converted' folder beside each input file.").grid(row=3, column=1, columnspan=3, sticky=tk.W)
            settings.columnconfigure(2, weight=1)

            action = ttk.Frame(main)
            action.pack(fill=tk.X, pady=(0, 8))
            self.convert_button = ttk.Button(action, text="Convert", command=self.start_conversion)
            self.convert_button.pack(side=tk.LEFT)
            self.progress = ttk.Progressbar(action, mode="determinate")
            self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(12, 0))

            log_frame = ttk.LabelFrame(main, text="Log", padding=6)
            log_frame.pack(fill=tk.BOTH, expand=True)
            self.log = tk.Text(log_frame, height=12, wrap=tk.WORD, state=tk.DISABLED)
            log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
            self.log.configure(yscrollcommand=log_scroll.set)
            self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

            self.root.after(100, self.poll_events)

        def write_log(self, text: str) -> None:
            self.log.configure(state=tk.NORMAL)
            self.log.insert(tk.END, text + "\n")
            self.log.see(tk.END)
            self.log.configure(state=tk.DISABLED)

        def refresh_list(self) -> None:
            self.listbox.delete(0, tk.END)
            for path in self.files:
                self.listbox.insert(tk.END, str(path))

        def on_drop(self, event) -> str:
            try:
                dropped = [Path(item) for item in self.root.tk.splitlist(event.data)]
            except Exception as exc:
                self.write_log(f"ERR drag-and-drop: {exc}")
                return "break"

            added_before = len(self.files)
            expanded: list[Path] = []
            for path in dropped:
                if path.is_dir():
                    found = candidate_files(path, recursive=self.recursive_var.get())
                    expanded.extend(found)
                    self.write_log(f"Dropped folder: {path} ({len(found)} candidate file(s))")
                elif path.is_file():
                    expanded.append(path)
            self._add_paths(expanded)
            self.write_log(f"Drag-and-drop added {len(self.files) - added_before} file(s).")
            return "break"

        def add_files(self) -> None:
            selected = filedialog.askopenfilenames(title="Select calculation files", filetypes=[("All files", "*.*")])
            self._add_paths(Path(x) for x in selected)

        def add_folder(self) -> None:
            selected = filedialog.askdirectory(title="Select folder")
            if not selected:
                return
            found = candidate_files(Path(selected), recursive=self.recursive_var.get())
            self._add_paths(found)
            self.write_log(f"Added {len(found)} candidate files from folder: {selected}")

        def _add_paths(self, paths: Iterable[Path]) -> None:
            existing = {p.resolve() for p in self.files}
            for path in paths:
                p = Path(path).resolve()
                if p.is_file() and p not in existing:
                    self.files.append(p)
                    existing.add(p)
            self.refresh_list()

        def remove_selected(self) -> None:
            indices = list(self.listbox.curselection())
            for idx in reversed(indices):
                del self.files[idx]
            self.refresh_list()

        def clear_files(self) -> None:
            self.files.clear()
            self.refresh_list()

        def choose_outdir(self) -> None:
            selected = filedialog.askdirectory(title="Select output directory")
            if selected:
                self.outdir_var.set(selected)

        def start_conversion(self) -> None:
            if self.running:
                return
            if not self.files:
                messagebox.showwarning(APP_NAME, "Add at least one input file.")
                return
            try:
                box = float(self.box_var.get())
                if box <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(APP_NAME, "Box size must be a positive number.")
                return

            target = TARGETS[self.target_var.get()]
            outdir_text = self.outdir_var.get().strip()
            outdir = Path(outdir_text).expanduser().resolve() if outdir_text else None
            route = self.route_var.get().strip() or DEFAULT_GAUSSIAN_ROUTE
            items = list(self.files)

            self.running = True
            self.convert_button.configure(state=tk.DISABLED)
            self.progress.configure(maximum=len(items), value=0)
            self.write_log(f"Starting conversion of {len(items)} file(s) to {self.target_var.get()}.")

            thread = threading.Thread(target=self.worker, args=(items, target, outdir, box, route), daemon=True)
            thread.start()

        def worker(self, items: list[Path], target: str, outdir: Optional[Path], box: float, route: str) -> None:
            success = 0
            failed = 0
            for idx, source in enumerate(items, start=1):
                try:
                    destination_dir = outdir if outdir is not None else source.parent / "converted"
                    destination, detection, messages = convert_one(source, target, destination_dir, box, route)
                    note = f"; {'; '.join(messages)}" if messages else ""
                    self.events.put(("log", f"OK  {source.name} [{detection.label}] -> {destination}{note}"))
                    success += 1
                except Exception as exc:
                    self.events.put(("log", f"ERR {source}: {exc}"))
                    failed += 1
                self.events.put(("progress", idx))
            self.events.put(("done", success, failed))

        def poll_events(self) -> None:
            try:
                while True:
                    event = self.events.get_nowait()
                    if event[0] == "log":
                        self.write_log(event[1])
                    elif event[0] == "progress":
                        self.progress.configure(value=event[1])
                    elif event[0] == "done":
                        self.running = False
                        self.convert_button.configure(state=tk.NORMAL)
                        success, failed = event[1], event[2]
                        self.write_log(f"Finished. Success: {success}; Failed: {failed}.")
                        if failed:
                            messagebox.showwarning(APP_NAME, f"Finished with {failed} failure(s). See the log for details.")
                        else:
                            messagebox.showinfo(APP_NAME, f"Finished. Converted {success} file(s).")
            except queue.Empty:
                pass
            self.root.after(100, self.poll_events)

    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch structure converter for computational chemistry files.")
    parser.add_argument("paths", nargs="*", help="Input files or folders. Launches the GUI when omitted.")
    parser.add_argument("--to", choices=list(TARGETS.values()), default="xyz", help="Target format for CLI mode.")
    parser.add_argument("--outdir", default="", help="Output directory. Default: converted folder beside each input.")
    parser.add_argument("--box", type=float, default=DEFAULT_BOX, help="Cubic box size in Angstrom for isolated systems.")
    parser.add_argument("--route", default=DEFAULT_GAUSSIAN_ROUTE, help="Gaussian route line used for GJF output.")
    parser.add_argument("--no-recursive", action="store_true", help="Do not scan folders recursively in CLI mode.")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.paths:
        return run_cli(args)
    return launch_gui()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if len(sys.argv) > 1:
            traceback.print_exc()
            raise
        try:
            import tkinter.messagebox as messagebox

            messagebox.showerror(APP_NAME, f"Fatal error: {exc}")
        except Exception:
            traceback.print_exc()
        raise
