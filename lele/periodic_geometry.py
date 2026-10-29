#!/usr/bin/env python3
"""Periodic minimum-image geometry and finite molecular-fragment previews.

Rows of cell are a, b, c. Preview coordinates never modify the source Frame.
A periodic network with nonzero graph winding is deliberately not expanded.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
from functools import lru_cache
import numpy as np
from scipy.spatial import cKDTree

from .core import Frame, canonical_pair, radius


def periodic_basis(frame: Frame):
    if not any(frame.pbc) or abs(float(np.linalg.det(frame.cell))) < 1e-9:
        return None
    return np.asarray(frame.cell, float)


def translations(frame: Frame):
    dimensions = [(-1, 0, 1) if use else (0,) for use in frame.pbc]
    return [tuple(v) for v in product(*dimensions)]


@lru_cache(maxsize=64)
def _reduced_cell(cell_values, pbc):
    """Unimodular reduction preserves the lattice and original shift mapping."""
    from ase.geometry import minkowski_reduce
    cell = np.asarray(cell_values, dtype=float).reshape(3, 3)
    reduced, operation = minkowski_reduce(cell, pbc=pbc)
    return np.asarray(reduced), np.asarray(operation, dtype=int)


def periodic_neighbors(frame, cutoff, positions=None):
    """Complete cutoff search in a reduced basis, shifts in the source basis.

    The ASE neighbor list derives its search from reciprocal face distances;
    no fixed image stencil is imposed on a non-reduced input lattice.
    """
    from ase.neighborlist import primitive_neighbor_list
    cell = periodic_basis(frame)
    if cell is None:
        cell = frame.cell
        pbc = (False, False, False)
        reduced, operation = cell, np.eye(3, dtype=int)
    else:
        pbc = frame.pbc
        reduced, operation = _reduced_cell(tuple(cell.ravel()), pbc)
    xyz = frame.positions if positions is None else positions
    i, j, vectors, shifts = primitive_neighbor_list('ijDS', pbc, reduced, xyz, float(cutoff))
    return i, j, vectors, shifts @ operation


def minimum_image(delta, frame: Frame):
    """Return shortest Cartesian delta + shift @ cell and its lattice shift.

    Reduce the periodic lattice before the nearest-image search; return the
    integer translation in the original basis, including partial periodicity.
    """
    delta = np.asarray(delta, dtype=float)
    lattice = periodic_basis(frame)
    if lattice is None:
        return delta.copy(), (0, 0, 0)
    from ase.geometry import find_mic
    reduced, operation = _reduced_cell(tuple(lattice.ravel()), frame.pbc)
    search_delta = delta
    if not all(frame.pbc):
        # Nonperiodic skew rows must not change the periodic projection or
        # hide a distant image behind a fractional-coordinate wrap.
        periodic = reduced[np.asarray(frame.pbc, dtype=bool)]
        search_delta = (delta @ np.linalg.pinv(periodic)) @ periodic
    vector, _ = find_mic(search_delta, reduced, pbc=frame.pbc)
    reduced_shift = np.rint(np.linalg.solve(reduced.T, vector - search_delta)).astype(int)
    reduced_shift[~np.asarray(frame.pbc, dtype=bool)] = 0
    shift = reduced_shift @ operation
    return delta + shift @ lattice, tuple(int(x) for x in shift)


@dataclass(frozen=True)
class ShortContact:
    first: int
    second: int
    distance: float
    # Translation of the second atom relative to its source coordinates.
    image_shift: tuple[int, int, int] = (0, 0, 0)


def short_contact_details(frame: Frame, threshold=0.6):
    """One shortest contact per distinct source pair, with its periodic image.

    Atom indices are canonical (first < second); image_shift translates the
    original second atom, not its wrapped representation. Display-only cell
    copies do not multiply contacts.
    """
    n = len(frame.symbols)
    if n < 2:
        return []
    cell = periodic_basis(frame)
    if cell is None:
        tree = cKDTree(frame.positions)
        pairs = tree.query_pairs(float(threshold), output_type='ndarray')
        if not len(pairs):
            return []
        d = np.linalg.norm(frame.positions[pairs[:, 0]] - frame.positions[pairs[:, 1]], axis=1)
        rows = [ShortContact(int(i), int(j), float(distance))
                for (i, j), distance in zip(pairs, d) if distance < threshold]
        return sorted(rows, key=lambda r: (r.distance, r.first, r.second))
    results = {}
    first, second, vectors, shifts = periodic_neighbors(frame, threshold)
    for i, j, vector, shift in zip(first, second, vectors, shifts):
        if i == j: continue
        pair = canonical_pair(i, j)
        dist = float(np.linalg.norm(vector))
        if dist < threshold and dist < results.get(pair, (float('inf'), None))[0]:
            raw_shift = shift if i < j else -shift
            results[pair] = (dist, tuple(int(x) for x in raw_shift))
    rows = [ShortContact(i, j, distance, shift) for (i, j), (distance, shift) in results.items()]
    return sorted(rows, key=lambda r: (r.distance, r.first, r.second))


def short_contacts(frame: Frame, threshold=0.6):
    """Count distinct atomic pairs shorter than threshold, including PBC images."""
    rows = short_contact_details(frame, threshold)
    if not rows: return 0, None
    first = rows[0]
    return len(rows), (first.first, first.second, first.distance)


def normalized_positions(frame: Frame):
    cell = periodic_basis(frame)
    if cell is None:
        return frame.positions.copy(), np.zeros((len(frame.symbols), 3), dtype=int)
    frac = frame.positions @ np.linalg.inv(cell)
    floors = np.zeros_like(frac, dtype=int)
    for axis, enabled in enumerate(frame.pbc):
        if enabled:
            floors[:, axis] = np.floor(frac[:, axis] + 1e-10).astype(int)
    return frame.positions - floors @ cell, floors


def periodic_bonds(frame: Frame, cutoff=1.18, *, max_bonds=150000):
    """All periodic covalent edges as (i,j,shift) for normalized coordinates.

    Multiple images of the same atom pair are intentionally retained so
    infinite periodic networks can be detected by graph-winding conflicts.
    """
    xyz, _ = normalized_positions(frame)
    if not len(xyz):
        return []
    cell = periodic_basis(frame)
    if frame.periodic_bond_snapshot is not None:
        _, floors = normalized_positions(frame)
        edges = set()
        for i, j, shift in frame.periodic_bond_snapshot:
            if (i, j) in frame.bond_removed: continue
            current = np.asarray(shift) - floors[i] + floors[j]
            edges.add((i, j, tuple(int(x) for x in current)))
        captured = {(i, j) for i, j, _ in frame.periodic_bond_snapshot}
        for i, j in frame.bond_added - frame.bond_removed:
            if (i, j) not in captured:
                _, shift = minimum_image(xyz[j] - xyz[i], frame)
                edges.add((i, j, shift))
        return sorted(edges)
    radii = np.array([radius(s) for s in frame.symbols])
    search_range = min(6.5, float(2 * radii.max() * cutoff))
    edges = set()
    first, second, vectors, shifts = periodic_neighbors(frame, search_range, xyz)
    for i, j, vector, shift_array in zip(first, second, vectors, shifts):
        i, j = int(i), int(j)
        shift = tuple(int(x) for x in shift_array)
        if i == j and shift == (0, 0, 0):
            continue
        pair = (i, j) if i == j else canonical_pair(i, j)
        if pair in frame.bond_removed:
            continue
        d = float(np.linalg.norm(vector))
        if not .2 < d <= min(6.5, (radii[i] + radii[j]) * cutoff):
            continue
        oriented_shift = tuple(int(v) for v in (shift if i <= j else tuple(-x for x in shift)))
        if i == j and oriented_shift < tuple(-v for v in oriented_shift):
            oriented_shift = tuple(-v for v in oriented_shift)
        edges.add((pair[0], pair[1], oriented_shift))
        if len(edges) > max_bonds:
            raise ValueError('Periodic graph is too large for interactive fragment expansion')
    # A manual link overrides the normal distance rule with the nearest image.
    from .bond_filter import prune_occluded
    edges = set(prune_occluded(xyz, edges, cell))
    for pair in frame.bond_added:
        if pair in frame.bond_removed:
            continue
        i, j = pair
        _, shift = minimum_image(xyz[j] - xyz[i], frame)
        edges.add((i, j, shift))
    return sorted(edges)


@dataclass
class FragmentPreview:
    indices: list[int]
    shifts: dict[int, tuple[int, int, int]]
    image_positions: dict[int, np.ndarray]
    extra_tiles: tuple[tuple[int, int, int], ...]
    edges: list[tuple[int, int]]
    supercell_min: tuple[int, int, int] = (0, 0, 0)
    supercell_extent: tuple[int, int, int] = (1, 1, 1)
    infinite: bool = False


def periodic_fragment(frame: Frame, selection, cutoff=1.18, max_atoms=20000, max_tiles=27):
    """Find complete periodic graph components and unwrap finite fragments.

    Returns a preview (no coordinate edits); infinite polymer/crystal networks
    raise ValueError instead of silently selecting an arbitrary finite cluster.
    """
    roots = list(dict.fromkeys(int(i) for i in selection))
    n = len(frame.symbols)
    if not roots or any(i < 0 or i >= n for i in roots):
        raise ValueError('Select valid atoms first')
    cell = periodic_basis(frame)
    if cell is None:
        from .fragment import selected_fragments
        indices = selected_fragments(frame, roots, cutoff)
        return FragmentPreview(indices, {i:(0,0,0) for i in indices},
                               {i:frame.positions[i].copy() for i in indices}, (), [])
    base, floors = normalized_positions(frame)
    graph = [[] for _ in range(n)]
    edges = periodic_bonds(frame, cutoff)
    for i, j, shift in edges:
        s = np.asarray(shift, dtype=int)
        graph[i].append((j, s))
        graph[j].append((i, -s))
    assigned = {}
    all_indices = set()
    for root in roots:
        if root in assigned:
            continue
        assigned[root] = floors[root].copy()
        todo = deque([root])
        while todo:
            i = todo.popleft()
            all_indices.add(i)
            if len(all_indices) > max_atoms:
                raise ValueError('Fragment exceeds safe interactive preview size')
            for j, shift in graph[i]:
                expected = assigned[i] + shift
                if j in assigned:
                    if not np.array_equal(expected, assigned[j]):
                        raise ValueError('Selected fragment forms an infinite periodic network; finite unwrapping is not possible')
                else:
                    assigned[j] = expected
                    todo.append(j)
    tiles = {tuple(int(x) for x in assigned[i]) for i in all_indices}
    bounds_min = tuple(min(0, *(v[k] for v in tiles)) for k in range(3))
    bounds_max = tuple(max(0, *(v[k] for v in tiles)) for k in range(3))
    extent = tuple(bounds_max[k] - bounds_min[k] + 1 for k in range(3))
    all_tiles = [tuple(int(x) for x in t) for t in product(*[
        range(bounds_min[k], bounds_max[k] + 1) for k in range(3)])]
    extra = [t for t in all_tiles if t != (0, 0, 0)]
    if len(all_tiles) > max_tiles or len(frame.symbols) * len(all_tiles) > 75000:
        raise ValueError('Fragment needs too many supercell images for interactive display')
    positions = {i:base[i] + assigned[i] @ cell for i in all_indices}
    selected_edges = [(i, j) for i, j, _ in edges if i in all_indices and j in all_indices]
    return FragmentPreview(sorted(all_indices),
                           {i:tuple(int(x) for x in assigned[i]) for i in all_indices},
                           positions, tuple(extra), selected_edges, bounds_min, extent)
