#!/usr/bin/env python3
"""Rendering-independent atom, bond and measurement utilities.

No chemistry file reader or GUI dependency is imported here; this keeps the
geometry computations testable without a graphics display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import math
import numpy as np
from .atom_appearance import AtomAppearance

# CPK-inspired colours. Unlisted species get a neutral medium grey.
ELEMENT_COLORS = {
    "H": "#F8F9FA", "He": "#D9FFFF", "Li": "#CC80FF", "Be": "#C2FF00",
    "B": "#FFB5B5", "C": "#747980", "N": "#3366CC", "O": "#E43C3C",
    "F": "#8DDC58", "Ne": "#B3E3F5", "Na": "#AB5CF2", "Mg": "#86D85D",
    "Al": "#BFA6A6", "Si": "#E6BD91", "P": "#F19C36", "S": "#EDCF3C",
    "Cl": "#48B65F", "Ar": "#80D0E6", "K": "#9256CA", "Ca": "#65AC39",
    "Ti": "#BFC4CB", "V": "#A5A5B8", "Cr": "#899BA6", "Mn": "#8B70AD",
    "Fe": "#C78039", "Co": "#E08AA0", "Ni": "#55B78E", "Cu": "#C68B52",
    "Zn": "#95A2B7", "Ga": "#C5A5A5", "Ge": "#719494", "As": "#BD81D4",
    "Se": "#E5A43A", "Br": "#A53B2B", "Ag": "#B5BDCB", "Cd": "#E3C55A",
    "I": "#8450AB", "Pt": "#C7D0D9", "Au": "#E2BE31", "Hg": "#B6B6C6",
    "Pb": "#626B7A", "Ru": "#2489B6", "Rh": "#0F93A7", "Pd": "#4BACC3",
    "La": "#70BFFF", "Ce": "#FFFFC7", "U": "#008FFF",
}

# Covalent-radius approximations in Angstrom.  Used for drawing only, never
# for determining actual bond order or chemical validity.
COVALENT_RADII = {
    "H": .31, "He": .28, "Li": 1.28, "Be": .96, "B": .84, "C": .76,
    "N": .71, "O": .66, "F": .57, "Ne": .58, "Na": 1.66, "Mg": 1.41,
    "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02,
    "Ar": 1.06, "K": 2.03, "Ca": 1.76, "Ti": 1.60, "V": 1.53,
    "Cr": 1.39, "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24,
    "Cu": 1.32, "Zn": 1.22, "Ga": 1.22, "Ge": 1.20, "As": 1.19,
    "Se": 1.20, "Br": 1.20, "Ag": 1.45, "Cd": 1.44, "I": 1.39,
    "Pt": 1.36, "Au": 1.36, "Hg": 1.32, "Pb": 1.46, "Ru": 1.46,
    "Rh": 1.42, "Pd": 1.39, "La": 1.80, "Ce": 1.63, "U": 1.70,
}


def colour(symbol: str) -> str:
    return ELEMENT_COLORS.get(symbol, "#A9AEB5")


def radius(symbol: str) -> float:
    return COVALENT_RADII.get(symbol, 1.20)


@dataclass
class Frame:
    symbols: list[str]
    positions: np.ndarray
    cell: np.ndarray = field(default_factory=lambda: np.zeros((3, 3)))
    pbc: tuple[bool, bool, bool] = (False, False, False)
    energy_ev: Optional[float] = None
    info: dict = field(default_factory=dict)
    # Explicit on/off overrides for display-only bonds. Pairs are canonical
    # (min index, max index); each trajectory frame owns its own overrides.
    bond_added: set[tuple[int, int]] = field(default_factory=set)
    bond_removed: set[tuple[int, int]] = field(default_factory=set)
    atom_appearance: dict[int, AtomAppearance] = field(default_factory=dict)
    # Captured before the first geometry edit. None means initial inference;
    # an empty snapshot deliberately means no bonds. Periodic shifts refer to
    # original atom coordinates, so wrapping cannot silently change an edge.
    bond_snapshot: Optional[frozenset[tuple[int, int]]] = None
    periodic_bond_snapshot: Optional[tuple] = None
    # Independent dashed annotations; shifts refer to original coordinates.
    hbond_added: dict[tuple[int, int], tuple[int, int, int]] = field(default_factory=dict)
    hbond_removed: set[tuple[int, int]] = field(default_factory=set)

    def __post_init__(self):
        self.positions = np.asarray(self.positions, dtype=float).reshape(-1, 3)
        self.cell = np.asarray(self.cell, dtype=float).reshape(3, 3)
        if self.positions.shape[0] != len(self.symbols):
            raise ValueError("Number of symbols and 3D positions differs")
        if not np.isfinite(self.positions).all() or not np.isfinite(self.cell).all():
            raise ValueError("Atom coordinates or cell contain non-finite values")
        if not isinstance(self.pbc, tuple):
            self.pbc = tuple(bool(x) for x in self.pbc)
        self.bond_added = {canonical_pair(*pair) for pair in self.bond_added}
        self.bond_removed = {canonical_pair(*pair) for pair in self.bond_removed}
        if self.bond_added & self.bond_removed:
            raise ValueError('Contradictory bond overrides')
        if any(i < 0 or j >= len(self.symbols) for i, j in self.bond_added | self.bond_removed):
            raise ValueError('Bond override atom index out of range')
        self.atom_appearance = dict(self.atom_appearance)
        if any(i < 0 or i >= len(self.symbols) or not isinstance(style, AtomAppearance)
               for i, style in self.atom_appearance.items()):
            raise ValueError('Invalid atom display override')
        if self.bond_snapshot is not None:
            self.bond_snapshot = frozenset(canonical_pair(i, j) for i, j in self.bond_snapshot)
            if any(i < 0 or j >= len(self.symbols) for i, j in self.bond_snapshot):
                raise ValueError('Frozen bond atom index out of range')
        if self.periodic_bond_snapshot is not None:
            self.periodic_bond_snapshot = tuple((int(i), int(j), tuple(int(x) for x in shift))
                                                for i, j, shift in self.periodic_bond_snapshot)
            if any(i < 0 or i > j or j >= len(self.symbols) or len(s) != 3
                   for i, j, s in self.periodic_bond_snapshot):
                raise ValueError('Invalid frozen periodic bond')
        self.hbond_added = {canonical_pair(i, j): tuple(int(x) * (1 if i < j else -1) for x in shift)
                            for (i, j), shift in self.hbond_added.items()}
        self.hbond_removed = {canonical_pair(i, j) for i, j in self.hbond_removed}
        if (self.hbond_added.keys() & self.hbond_removed
                or any(i < 0 or j >= len(self.symbols) for i, j in self.hbond_added.keys() | self.hbond_removed)
                or any(len(s) != 3 for s in self.hbond_added.values())):
            raise ValueError('Invalid hydrogen-bond override')

    def clone(self):
        return Frame(list(self.symbols), self.positions.copy(), self.cell.copy(), tuple(self.pbc),
                     self.energy_ev, dict(self.info), self.bond_added.copy(), self.bond_removed.copy(),
                     self.atom_appearance.copy(), self.bond_snapshot, self.periodic_bond_snapshot,
                     self.hbond_added.copy(), self.hbond_removed.copy())


@dataclass
class Volume:
    # data shape: nx,ny,nz; voxel_vectors are row basis, NOT full cell vectors
    data: np.ndarray
    origin: np.ndarray
    voxel_vectors: np.ndarray

    def __post_init__(self):
        self.data = np.asarray(self.data, dtype=np.float32)
        self.origin = np.asarray(self.origin, dtype=float).reshape(3)
        self.voxel_vectors = np.asarray(self.voxel_vectors, dtype=float).reshape(3, 3)
        if self.data.ndim != 3 or min(self.data.shape) < 2:
            raise ValueError("Volumetric data must be a 3D grid with at least 2 points per axis")


@dataclass
class NormalMode:
    number: int
    frequency_cm1: float
    displacements: Optional[np.ndarray] = None
    ir_intensity: Optional[float] = None
    reduced_mass: Optional[float] = None
    force_constant: Optional[float] = None
    symmetry: str = ''
    raman_activity: Optional[float] = None
    ir_intensity_unit: str = 'km/mol'

    def __post_init__(self):
        if self.number < 0 or not math.isfinite(self.frequency_cm1):
            raise ValueError('Invalid normal mode number or frequency')
        if self.displacements is not None:
            self.displacements = np.asarray(self.displacements, dtype=float).reshape(-1, 3).copy()
            if not np.isfinite(self.displacements).all():
                raise ValueError('Normal mode contains non-finite displacements')

    @property
    def imaginary(self):
        return self.frequency_cm1 < 0

    @property
    def can_animate(self):
        return (self.displacements is not None and self.displacements.size > 0
                and float(np.linalg.norm(self.displacements, axis=1).max()) > 0)

    def positions_at(self, reference: Frame, phase: float, amplitude: float):
        """A visual oscillation with maximum atom displacement in Angstrom.

        Imaginary modes use the same reversible preview, not real dynamics.
        Printed Cartesian vectors are relative; their direction and relative
        atom motion are preserved, with one common scale for the whole mode.
        """
        if not self.can_animate:
            return reference.positions.copy()
        if self.displacements.shape != reference.positions.shape:
            raise ValueError('Normal mode atom count differs from its reference geometry')
        peak = float(np.linalg.norm(self.displacements, axis=1).max())
        return reference.positions + self.displacements * (amplitude * math.sin(phase) / peak)


@dataclass
class VibrationalAnalysis:
    reference: Frame
    modes: list[NormalMode] = field(default_factory=list)
    source_line: int = 0
    note: str = ''
    purpose: str = ''
    stage_index: Optional[int] = None
    cycle: Optional[int] = None

    def __post_init__(self):
        if any(m.displacements is not None and m.displacements.shape != self.reference.positions.shape
               for m in self.modes):
            raise ValueError('Normal mode atom count differs from its reference geometry')


@dataclass
class Document:
    path: Path
    format_name: str
    frames: list[Frame]
    volume: Optional[Volume] = None
    note: str = ""
    modified: bool = False
    vibrations: list[VibrationalAnalysis] = field(default_factory=list)
    dipoles: list = field(default_factory=list)
    electronic_spectra: list = field(default_factory=list)
    calculation_results: object = None
    neb_runs: list = field(default_factory=list)
    conformer_ensembles: list = field(default_factory=list)
    soc_results: list = field(default_factory=list)

    def __post_init__(self):
        if not self.frames:
            from .result_availability import has_calculation_data
            if not has_calculation_data(self.calculation_results):
                raise ValueError("Document contains no atoms or calculation results")


def canonical_pair(i: int, j: int) -> tuple[int, int]:
    i, j = int(i), int(j)
    if i == j:
        raise ValueError('Self bonds are not supported')
    return (min(i, j), max(i, j))


def visible_bonds(frame: Frame, multiplier: float = 1.18) -> list[tuple[int, int]]:
    """Distance-estimated bonds with frame-local manually added/removed links."""
    pairs = set(find_bonds(frame, multiplier) if frame.bond_snapshot is None else frame.bond_snapshot)
    pairs.difference_update(frame.bond_removed)
    pairs.update(frame.bond_added)
    return sorted(pairs)


def freeze_bonds(frame: Frame, multiplier: float = 1.18):
    """Capture both display and periodic connectivity before changing positions."""
    if frame.bond_snapshot is not None:
        return
    frame.bond_snapshot = frozenset(visible_bonds(frame, multiplier))
    from .periodic_geometry import periodic_basis, periodic_bonds, normalized_positions
    if periodic_basis(frame) is not None:
        _, floors = normalized_positions(frame)
        frame.periodic_bond_snapshot = tuple(
            (i, j, tuple(int(x) for x in np.asarray(shift) + floors[i] - floors[j]))
            for i, j, shift in periodic_bonds(frame, multiplier))


def _set_manual_periodic_paths(frame, pairs):
    if frame.periodic_bond_snapshot is None: return
    from .periodic_geometry import minimum_image
    pairs = set(pairs)
    edges = [edge for edge in frame.periodic_bond_snapshot if edge[:2] not in pairs]
    for i, j in sorted(pairs):
        _, shift = minimum_image(frame.positions[j] - frame.positions[i], frame)
        edges.append((i, j, shift))
    frame.periodic_bond_snapshot = tuple(sorted(edges))


def toggle_selected_bonds(frame: Frame, selected, multiplier: float = 1.18) -> tuple[str, int]:
    """Two atoms toggle unconditionally; 3+ toggle all internal visible bonds.

    If any internal links currently exist, remove *all* of them. Otherwise
    restore only links passing the normal automatic distance test. All
    external links are untouched, and explicit pairs override distance.
    """
    indices = list(dict.fromkeys(int(i) for i in selected))
    if len(indices) < 2:
        raise ValueError('Select at least two atoms for Ctrl+B')
    if any(i < 0 or i >= len(frame.symbols) for i in indices):
        raise IndexError('Selected atom out of range')
    subset = set(indices)
    from .periodic_geometry import periodic_basis, periodic_bonds
    if periodic_basis(frame) is not None:
        bonded = {(i, j) for i, j, _ in periodic_bonds(frame, multiplier) if i != j}
    else:
        bonded = set(visible_bonds(frame, multiplier))
    current = {pair for pair in bonded
               if pair[0] in subset and pair[1] in subset}
    if len(indices) == 2:
        pair = canonical_pair(*indices)
        if pair in current:
            frame.bond_added.discard(pair)
            frame.bond_removed.add(pair)
            return 'removed', 1
        frame.bond_removed.discard(pair)
        frame.bond_added.add(pair)
        _set_manual_periodic_paths(frame, [pair])
        return 'added', 1
    if current:
        for pair in current:
            frame.bond_added.discard(pair)
            frame.bond_removed.add(pair)
        return 'removed', len(current)
    # Return to automatic distance-based bonding; don't create far-away pairs.
    if periodic_basis(frame) is not None:
        probe = frame.clone()
        probe.bond_snapshot = probe.periodic_bond_snapshot = None
        probe.bond_removed.difference_update(
            canonical_pair(a, b) for a in subset for b in subset if a < b)
        candidates = {(i, j) for i, j, _ in periodic_bonds(probe, multiplier)
                      if i != j and i in subset and j in subset}
    else:
        candidates = {pair for pair in find_bonds(frame, multiplier)
                      if pair[0] in subset and pair[1] in subset}
    frame.bond_removed.difference_update(candidates)
    if frame.bond_snapshot is not None:
        frame.bond_snapshot = frame.bond_snapshot | frozenset(candidates)
    _set_manual_periodic_paths(frame, candidates)
    # Any user-added bonds within the selection are already absent when
    # reaching here (otherwise current was nonempty).
    return 'restored', len(candidates)


def move_atom_to_origin(frame: Frame, index: int) -> np.ndarray:
    """Translate all atom positions; preserve the cell vectors and distances.

    Returns the applied translation for use by attached volumetric fields.
    """
    if not 0 <= index < len(frame.symbols):
        raise IndexError('Anchor atom out of range')
    translation = -frame.positions[index].copy()
    frame.positions += translation
    return translation


def rotation_between_vectors(source, target) -> np.ndarray:
    """Proper 3-D rotation that sends source onto target (both may be skew)."""
    a = np.asarray(source, dtype=float).reshape(3)
    b = np.asarray(target, dtype=float).reshape(3)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na < 1e-10 or nb < 1e-10:
        raise ValueError('Cannot align coincident atoms or a zero-length axis')
    a, b = a / na, b / nb
    cosine = float(np.clip(a @ b, -1., 1.))
    if cosine > 1. - 1e-12:
        return np.eye(3)
    if cosine < -1. + 1e-12:
        # Deterministic perpendicular axis for the 180-degree case.
        basis = np.zeros(3)
        basis[int(np.argmin(np.abs(a)))] = 1.
        axis = np.cross(a, basis)
        axis /= np.linalg.norm(axis)
        return 2. * np.outer(axis, axis) - np.eye(3)
    cross = np.cross(a, b)
    skew = np.array([[0., -cross[2], cross[1]],
                     [cross[2], 0., -cross[0]],
                     [-cross[1], cross[0], 0.]])
    return np.eye(3) + skew + skew @ skew / (1. + cosine)


def align_pair_to_axis(frame: Frame, first: int, second: int, axis: str) -> tuple[np.ndarray, np.ndarray, bool]:
    """Rotate the atomic positions around the first atom, keeping the cell fixed.

    Both XYZ (Cartesian) and abc (lattice direction) alignments update only
    frame.positions; frame.cell always remains unchanged. This is a real
    geometry edit relative to a periodic lattice, not a camera rotation or
    a change of basis for the complete infinite crystal.

    Returns (column-vector rotation matrix, pivot, cell_rotated=False).
    The final False retains the public return shape of earlier versions.
    """
    if not (0 <= first < len(frame.symbols) and 0 <= second < len(frame.symbols)) or first == second:
        raise ValueError('Select two different atoms')
    axis = str(axis).strip()
    if axis.lower() in ('x', 'y', 'z'):
        target = np.eye(3)[('x', 'y', 'z').index(axis.lower())]
    elif axis.lower() in ('a', 'b', 'c'):
        if not valid_lattice(frame):
            raise ValueError('a/b/c alignment requires a valid periodic cell')
        target = frame.cell[('a', 'b', 'c').index(axis.lower())].copy()
    else:
        raise ValueError('Axis must be X, Y, Z, a, b or c')
    pivot = frame.positions[first].copy()
    vector = frame.positions[second] - pivot
    R = rotation_between_vectors(vector, target)
    frame.positions = (frame.positions - pivot) @ R.T + pivot
    return R, pivot, False


def find_bonds(frame: Frame, multiplier: float = 1.18, *, max_bonds: int = 60000) -> list[tuple[int, int]]:
    """Distance-based bonds between atoms as drawn in the *visible* cell.

    In a periodic model, bonds that need a translated image atom are omitted
    deliberately, rather than drawing an invalid long diagonal across cell.
    Periodic-image expansion is scheduled for a later version.
    """
    from scipy.spatial import cKDTree

    xyz = frame.positions
    if len(xyz) < 2:
        return []
    r = np.asarray([radius(s) for s in frame.symbols], dtype=float)
    search_range = min(float(r.max()) * 2.0 * multiplier, 6.5)
    pairs = cKDTree(xyz).query_pairs(r=search_range, output_type="ndarray")
    result = []
    for a, b in pairs:
        distance = np.linalg.norm(xyz[a] - xyz[b])
        if .2 < distance <= min(6.5, (r[a] + r[b]) * multiplier):
            result.append((int(a), int(b)))
            if len(result) >= max_bonds:
                break
    from .bond_filter import prune_occluded
    return [(a, b) for a, b, _ in prune_occluded(xyz, [(a,b,(0,0,0)) for a,b in result])]


def unit_cell_edges(cell: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    cell = np.asarray(cell, dtype=float).reshape(3, 3)
    if abs(np.linalg.det(cell)) < 1.e-9:
        return []
    points = {tuple(bits): np.asarray(bits, dtype=float) @ cell
              for bits in __import__("itertools").product([0, 1], repeat=3)}
    return [(points[key], points[tuple((1 - v) if j == axis else v for j, v in enumerate(key))])
            for key in points for axis in range(3) if key[axis] == 0]


def measure(frame: Frame, atoms: list[int]) -> tuple[str, float]:
    """2=distance(Å), 3=angle(deg), 4=dihedral(deg); 0-based atom indices."""
    if len(atoms) not in (2, 3, 4) or len(set(atoms)) != len(atoms):
        raise ValueError("Select 2, 3, or 4 distinct atoms")
    if any(i < 0 or i >= len(frame.symbols) for i in atoms):
        raise IndexError("Atom index out of range")
    p = [frame.positions[i] for i in atoms]
    if len(p) == 2:
        return "distance", float(np.linalg.norm(p[0] - p[1]))
    if len(p) == 3:
        a, b = p[0] - p[1], p[2] - p[1]
        norm = np.linalg.norm(a) * np.linalg.norm(b)
        if norm <= 1e-14:
            raise ValueError("Degenerate bond angle")
        return "angle", math.degrees(math.acos(float(np.clip(a @ b / norm, -1, 1))))
    # Convention: dihedral around bond (atom2 -> atom3), 0..+-180 degrees.
    b0 = -(p[1] - p[0]); b1 = p[2] - p[1]; b2 = p[3] - p[2]
    length = np.linalg.norm(b1)
    if length < 1e-14:
        raise ValueError("Degenerate dihedral axis")
    b1 /= length
    v = b0 - (b0 @ b1) * b1
    w = b2 - (b2 @ b1) * b1
    if np.linalg.norm(v) < 1e-12 or np.linalg.norm(w) < 1e-12:
        raise ValueError("Collinear dihedral points")
    return "dihedral", math.degrees(math.atan2(float(np.cross(b1, v) @ w), float(v @ w)))


def atom_label_texts(symbols: list[str], mode: str, poscar_groups=None) -> list[str]:
    """Generate GUI labels; indices always start at 1.

    VESTA grouping restarts at each declared POSCAR species block.
    VESTA POSCAR grouping instead RESTARTS the counter at every declared
    species block, even when the same symbol appears in adjacent blocks.
    e.g. Li Li / 10 5 -> Li1..Li10, Li1..Li5.
    """
    from collections import defaultdict
    if mode == 'None':
        return []
    if mode == 'VESTA (POSCAR groups)':
        if poscar_groups is not None:
            # A species block is identified by its position in POSCAR line 6,
            # NOT by symbol. Duplicate symbols are valid, distinct blocks.
            blocks = [(str(symbol), int(count)) for symbol, count in poscar_groups]
            if (any(count < 0 for _, count in blocks)
                or sum(count for _, count in blocks) != len(symbols)
                or [s for sym, count in blocks for s in [sym] * count] != list(symbols)):
                raise ValueError('POSCAR group metadata does not match atomic symbols')
            return [f'{sym}{j}' for sym, count in blocks for j in range(1, count + 1)]
        # Other file formats have no explicit POSCAR species-block boundary.
        # Never invent independent crystallographic sites from coordinates.
        # For non-POSCAR data use element-wise numbering as a graceful
        # fallback, without exposing a redundant second GUI mode.
        mode = 'VESTA fallback'
    counters = defaultdict(int)
    result = []
    for i, symbol in enumerate(symbols, 1):
        counters[symbol] += 1
        if mode == 'Element':
            result.append(symbol)
        elif mode in ('Index', 'Index (1..N)'):
            result.append(str(i))
        elif mode == 'VESTA fallback':
            result.append(f'{symbol}{counters[symbol]}')
        elif mode in ('Element + index (global)', 'Element + index'):
            result.append(f'{symbol}{i}')
        else:
            raise ValueError(f'Unknown atom-label mode: {mode}')
    return result


def valid_lattice(frame: Frame) -> bool:
    """True when a real periodic cell and three nondegenerate basis vectors exist."""
    return bool(any(frame.pbc) and abs(float(np.linalg.det(frame.cell))) > 1e-9)


def axis_vectors(frame: Frame, basis='XYZ', length=2.5, *, corner=False):
    """Return name, direction-vector tuples in Angstrom or corner units.

    XYZ are true Cartesian axes; abc use the actual three cell row vectors.
    The corner overlay preserves lattice angles while normalizing arrow lengths.
    """
    if basis == 'abc':
        if not valid_lattice(frame):
            return []
        vectors = np.asarray(frame.cell, dtype=float)
        names = ('a', 'b', 'c')
    elif basis == 'XYZ':
        vectors = np.eye(3) * float(length)
        names = ('X', 'Y', 'Z')
    else:
        raise ValueError(f'Unknown axis basis: {basis}')
    if corner:
        vectors = np.array([v / np.linalg.norm(v) for v in vectors])
    return [(name, np.asarray(vec, dtype=float)) for name, vec in zip(names, vectors)]


def coordinate_table_rows(frame: Frame, precision: int = 6) -> list[tuple[str, str, str, str]]:
    """View formatting of the current in-memory coordinates, including edits."""
    fmt = f'{{:.{precision}f}}'
    return [
        (f'{i + 1} {symbol}', *(fmt.format(float(value)) for value in xyz))
        for i, (symbol, xyz) in enumerate(zip(frame.symbols, frame.positions))
    ]
