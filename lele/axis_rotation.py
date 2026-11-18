"""Validated rotations of connected fragments about an atom-defined axis."""
from collections import deque

import numpy as np

from .core import canonical_pair, visible_bonds
from .fragment import rotation_about_axis
from .internal_coordinates import InternalEdit
from .periodic_geometry import (minimum_image, normalized_positions,
                                periodic_basis, periodic_bonds)


def plan_axis_rotation(frame, selected, degrees, cutoff=1.0):
    """Return an edit without mutating the frame or its frozen connectivity.

    The first two selected atoms define a directed axis. With only two atoms,
    rotate every branch on the second atom's side of the cut bond. With more
    atoms, the later picks seed connected components after removing the two
    axis vertices from traversal. Axis atoms always retain their coordinates.

    Finite periodic fragments are unwrapped around the same axis image before
    rotation; periodic edge shifts follow that representation change. A
    winding network or inconsistent attachment to different axis images is
    rejected, rather than silently stretching a covalent bond.
    """
    ids = [int(i) for i in selected]
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ValueError('Select at least two distinct atoms, in axis order.')
    if any(i < 0 or i >= len(frame.symbols) for i in ids):
        raise ValueError('Selected atom index is outside the current structure.')
    degrees = float(degrees)
    if not np.isfinite(degrees):
        raise ValueError('Enter a finite rotation angle.')
    a, b = ids[:2]
    periodic = periodic_basis(frame) is not None
    if periodic:
        _, floors = normalized_positions(frame)
        edges = [(i, j, np.asarray(s, dtype=int) + floors[i] - floors[j])
                 for i, j, s in periodic_bonds(frame, cutoff)]
    else:
        edges = [(i, j, np.zeros(3, dtype=int))
                 for i, j in visible_bonds(frame, cutoff)]
    graph = [[] for _ in frame.symbols]
    for i, j, shift in edges:
        graph[i].append((j, shift))
        graph[j].append((i, -shift))
    axis_edges = [s for j, s in graph[a] if j == b]
    if len(axis_edges) > 1:
        raise ValueError('The selected axis joins multiple periodic images; choose an unambiguous finite fragment.')
    if axis_edges:
        b_shift = axis_edges[0].copy()
    else:
        _, image = minimum_image(frame.positions[b] - frame.positions[a], frame)
        b_shift = np.asarray(image, dtype=int)
    axis_shifts = {a: np.zeros(3, dtype=int), b: b_shift}
    pivot = frame.positions[a]
    axis_end = frame.positions[b] + b_shift @ frame.cell
    axis = axis_end - pivot
    if np.linalg.norm(axis) < 1.e-12:
        raise ValueError('Coincident atoms do not define a rotation axis.')
    rotation = rotation_about_axis(axis, degrees)
    implicit = len(ids) == 2
    roots = [j for j, _ in graph[b] if j not in (a, b)] if implicit else ids[2:]
    shifts = {}
    for root in roots:
        if root in shifts:
            continue
        component = {root: np.zeros(3, dtype=int)}
        queue = deque([root])
        offsets = []
        while queue:
            i = queue.popleft()
            for j, shift in graph[i]:
                if j in axis_shifts:
                    if implicit and j == a:
                        raise ValueError('A ring or another bond path joins both sides of the axis. Select the two axis atoms first, then an atom in the specific fragment to rotate.')
                    offsets.append(axis_shifts[j] - shift - component[i])
                    continue
                wanted = component[i] + shift
                if j in component:
                    if not np.array_equal(component[j], wanted):
                        raise ValueError('The moving fragment belongs to an infinite periodic bonded network and cannot rotate independently.')
                else:
                    component[j] = wanted
                    queue.append(j)
        if offsets:
            offset = offsets[0]
            if any(not np.array_equal(value, offset) for value in offsets[1:]):
                raise ValueError('The fragment attaches to different periodic images of the axis and cannot rotate without stretching bonds.')
        else:
            _, image = minimum_image(frame.positions[root] - axis_end, frame)
            offset = np.asarray(image, dtype=int)
        shifts.update({i: shift + offset for i, shift in component.items()})
    if not shifts:
        raise ValueError('There are no atoms to rotate on the second side. Select the axis atoms first, then one or more atoms in the moving fragment.')
    moving = sorted(shifts)
    positions = frame.positions.copy()
    unwrapped = np.array([positions[i] + shifts[i] @ frame.cell for i in moving])
    positions[moving] = (unwrapped - pivot) @ rotation.T + pivot
    new_edges = None
    hbonds = dict(frame.hbond_added)
    if periodic:
        zero = np.zeros(3, dtype=int)
        new_edges = tuple((i, j, tuple(int(x) for x in shift + shifts.get(i, zero) - shifts.get(j, zero)))
                          for i, j, shift in edges)
        hbonds = {pair: tuple(int(x) for x in np.asarray(shift) + shifts.get(pair[0], zero) - shifts.get(pair[1], zero))
                  for pair, shift in hbonds.items()}
    return InternalEdit(positions, moving, new_edges, hbonds)
