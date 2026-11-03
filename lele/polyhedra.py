"""Coordination polyhedra from explicit periodic neighbour images.

Polyhedra use a convex hull of ligand positions. Coplanar ligands produce a
polygon; triangulation diagonals are excluded from the visible edge network.
"""
from dataclasses import dataclass
from itertools import combinations
import re
import numpy as np
from ase.data import atomic_numbers
from scipy.spatial import ConvexHull, QhullError

from .core import radius
from .atom_appearance import atom_is_drawn
from .periodic_geometry import periodic_neighbors
from .element_rules import validate_rules, pair_decision, search_radius

AUTO_LIGANDS = {'O', 'N', 'F', 'Cl', 'S', 'Br', 'I'}


def element_set(text):
    if not text.strip() or text.strip().lower() == 'auto':return None
    if text.strip() == '*':return set()
    values = set(re.split(r'[\s,;]+', text.strip()))
    if not values <= atomic_numbers.keys():raise ValueError('Use element symbols separated by spaces, Auto, or *.')
    return values


def validate_polyhedra(options):
    validate_rules(options.element_pair_rules)
    element_set(options.polyhedra_centers);element_set(options.polyhedra_ligands)
    lo, hi = options.polyhedra_min_distance, options.polyhedra_max_distance
    if not np.isfinite([lo, hi, options.polyhedra_opacity]).all() or not 0 <= lo < hi:
        raise ValueError('Use 0 ≤ minimum distance < maximum distance, in Å.')
    if options.polyhedra_search not in ('Covalent radii', 'Distance range'):
        raise ValueError('Choose a valid coordination search method.')
    if not 0 <= options.polyhedra_opacity <= 1:
        raise ValueError('Polyhedron opacity must be between 0 and 1.')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', options.polyhedra_edge_color):raise ValueError('Choose a valid edge colour.')


@dataclass
class CoordinationPolyhedron:
    center: int
    ligand_indices: np.ndarray
    image_shifts: np.ndarray
    vectors: np.ndarray
    faces: list
    edges: list
    planar: bool = False


def convex_faces(points):
    xyz = np.asarray(points, float)
    if len(xyz) < 3:return [], [], False
    centered = xyz-xyz.mean(axis=0)
    _, singular, axes = np.linalg.svd(centered, full_matrices=False)
    rank = int(np.count_nonzero(singular > max(1.e-8, singular[0]*1.e-8)))
    if rank < 2:return [], [], False
    try:
        if rank == 2:
            order = ConvexHull(centered @ axes[:2].T).vertices.tolist()
            return [order], [tuple(sorted((order[i], order[(i+1) % len(order)]))) for i in range(len(order))], True
        hull = ConvexHull(xyz)
    except QhullError:
        return [], [], False
    faces = [row.tolist() for row in hull.simplices]
    # Consistent winding improves lighting and transparency without changing
    # the geometric hull or its coordination vertices.
    for face, equation in zip(faces, hull.equations):
        a, b, c = xyz[face]
        if np.dot(np.cross(b-a, c-a), equation[:3]) < 0:face.reverse()
    adjacent = {}
    for fi, face in enumerate(faces):
        for edge in combinations(face, 2):adjacent.setdefault(tuple(sorted(edge)), []).append(fi)
    edges = [edge for edge, fs in adjacent.items() if len(fs) != 2 or
             not np.allclose(hull.equations[fs[0]], hull.equations[fs[1]], atol=1.e-7, rtol=0)]
    return faces, sorted(edges), False


def coordination_shells(frame, options, center_indices=None):
    validate_polyhedra(options)
    present = set(frame.symbols)
    ligands = element_set(options.polyhedra_ligands)
    if ligands is None:ligands = (present & AUTO_LIGANDS) or (present-{'H'})
    if not ligands:ligands = present
    centers = element_set(options.polyhedra_centers)
    if centers is None:centers = (present-ligands-{'H'}) or (present-{'H'})
    if not centers:centers = present
    rules = options.element_pair_rules
    declared_centers = {symbol for symbol in present if any(row['enabled'] and row['polyhedra']
                        and row['a1'] in ('*', symbol) for row in rules)}
    candidate_centers = declared_centers if options.pair_rules_only else centers | declared_centers
    requested = None if center_indices is None else set(center_indices)
    indices = [i for i, symbol in enumerate(frame.symbols) if symbol in candidate_centers and atom_is_drawn(frame, i)
               and (requested is None or i in requested)]
    if not indices:return []
    cutoff = search_radius(rules, options.polyhedra_max_distance, only=options.pair_rules_only, polyhedra=True)
    if cutoff > 0:first, second, vectors, shifts = periodic_neighbors(frame, cutoff+1.e-8)
    else:first, second, vectors, shifts = [], [], [], []
    grouped = {}
    allowed_indices = set(indices)
    for i, j, vector, shift in zip(first, second, vectors, shifts):
        if int(i) not in allowed_indices:continue
        if not atom_is_drawn(frame, int(i)) or not atom_is_drawn(frame, int(j)):continue
        distance = float(np.linalg.norm(vector))
        default = (frame.symbols[i] in centers and frame.symbols[j] in ligands and distance >= max(1.e-7, options.polyhedra_min_distance)-1.e-8
                   and distance <= options.polyhedra_max_distance+1.e-8)
        if options.polyhedra_search == 'Covalent radii':default &= distance <= (radius(frame.symbols[i])+radius(frame.symbols[j]))*options.bond_cutoff
        include, _ = pair_decision(rules, frame.symbols[i], frame.symbols[j], distance, default,
                                   only=options.pair_rules_only, polyhedra=True)
        if not include:continue
        grouped.setdefault(int(i), []).append((int(j), tuple(int(x) for x in shift), vector))
    polyhedra = []
    for center in indices:
        rows = grouped.get(center, [])
        rows.sort(key=lambda row: (row[0], row[1]))
        unique = {};clean = []
        for row in rows:
            key = tuple(np.round(row[2], 8))
            if key not in unique:unique[key] = True;clean.append(row)
        vectors = np.asarray([r[2] for r in clean]).reshape(-1, 3)
        faces, edges, planar = convex_faces(vectors)
        polyhedra.append(CoordinationPolyhedron(center, np.asarray([r[0] for r in clean], int),
            np.asarray([r[1] for r in clean], int).reshape(-1, 3), vectors, faces, edges, planar))
    return polyhedra


def coordination_polyhedra(frame, options):
    return [shell for shell in coordination_shells(frame, options) if shell.faces]
