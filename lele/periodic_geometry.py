#!/usr/bin/env python3
"""Periodic minimum-image geometry and finite molecular-fragment previews.

Rows of cell are a, b, c. Preview coordinates never modify the source Frame.
A periodic network with nonzero graph winding is deliberately not expanded.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
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


def minimum_image(delta, frame: Frame):
    """Return shortest Cartesian delta + shift @ cell and its lattice shift.

    Search around the nearest fractional image, including skewed-cell neighbours.
    """
    delta = np.asarray(delta, dtype=float)
    lattice = periodic_basis(frame)
    if lattice is None:
        return delta.copy(), (0, 0, 0)
    frac = delta @ np.linalg.inv(lattice)
    base = np.array([-int(np.rint(frac[k])) if frame.pbc[k] else 0 for k in range(3)])
    best = (float('inf'), None, None)
    for nearby in translations(frame):
        shift = base + np.asarray(nearby, dtype=int)
        vector = delta + shift @ lattice
        sq = float(vector @ vector)
        if sq < best[0] - 1e-12:
            best = (sq, vector, tuple(int(x) for x in shift))
    return best[1], best[2]


def short_contacts(frame: Frame, threshold=0.6):
    """Count distinct atomic pairs shorter than threshold, including PBC images."""
    n = len(frame.symbols)
    if n < 2:
        return 0, None
    cell = periodic_basis(frame)
    if cell is None:
        tree = cKDTree(frame.positions)
        pairs = tree.query_pairs(float(threshold), output_type='ndarray')
        if not len(pairs):
            return 0, None
        d = np.linalg.norm(frame.positions[pairs[:, 0]] - frame.positions[pairs[:, 1]], axis=1)
        index = int(d.argmin())
        return len(pairs), (int(pairs[index, 0]), int(pairs[index, 1]), float(d[index]))
    normalized, _ = normalized_positions(frame)
    tree = cKDTree(normalized)
    results = {}
    for shift in translations(frame):
        translated = normalized + np.asarray(shift) @ cell
        targets = cKDTree(translated)
        for i, neighbours in enumerate(tree.query_ball_tree(targets, r=threshold)):
            for j in neighbours:
                if i == j:
                    continue
                pair = canonical_pair(i, j)
                dist = float(np.linalg.norm(normalized[i] - translated[j]))
                if dist < threshold and dist < results.get(pair, float('inf')):
                    results[pair] = dist
    if not results:
        return 0, None
    (i, j), d = min(results.items(), key=lambda item: item[1])
    return len(results), (i, j, d)


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
    radii = np.array([radius(s) for s in frame.symbols])
    search_range = min(6.5, float(2 * radii.max() * cutoff))
    tree = cKDTree(xyz)
    edges = set()
    for shift in translations(frame):
        offset = np.asarray(shift, float) @ cell if cell is not None else np.zeros(3)
        if shift == (0, 0, 0):
            neighbours = tree.query_pairs(search_range, output_type='ndarray')
            candidates = ((int(i), int(j)) for i, j in neighbours)
        else:
            other = cKDTree(xyz + offset)
            neighbours = tree.query_ball_tree(other, r=search_range)
            candidates = ((i, j) for i, js in enumerate(neighbours) for j in js)
        for i, j in candidates:
            if i == j and shift == (0, 0, 0):
                continue
            pair = (i, j) if i == j else canonical_pair(i, j)
            if pair in frame.bond_removed:
                continue
            vec = xyz[j] + offset - xyz[i]
            d = float(np.linalg.norm(vec))
            if not .2 < d <= min(6.5, (radii[i] + radii[j]) * cutoff):
                continue
            oriented_shift = tuple(int(v) for v in (shift if i <= j else tuple(-x for x in shift)))
            if i == j and oriented_shift < tuple(-v for v in oriented_shift):
                oriented_shift = tuple(-v for v in oriented_shift)
            edges.add((pair[0], pair[1], oriented_shift))
            if len(edges) > max_bonds:
                raise ValueError('Periodic graph is too large for interactive fragment expansion')
    # A manual link overrides the normal distance rule with the nearest image.
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
