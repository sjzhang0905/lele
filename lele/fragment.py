#!/usr/bin/env python3
"""Connected-fragment selection and rigid mouse-driven geometry edits.

A fragment is a component of the finite, currently displayed bond graph.
Minimum-image periodic bonds are not inferred by the current renderer.
"""
from __future__ import annotations

from collections import deque
import math
import numpy as np

from .core import Frame, visible_bonds


def selected_fragments(frame: Frame, selected, cutoff: float = 1.0) -> list[int]:
    """Union of connected components containing the selected 0-based atoms."""
    roots = list(dict.fromkeys(int(i) for i in selected))
    n = len(frame.symbols)
    if any(i < 0 or i >= n for i in roots):
        raise IndexError('Atom index out of range')
    if not roots:
        return []
    neighbours = [[] for _ in range(n)]
    for i, j in visible_bonds(frame, cutoff):
        neighbours[i].append(j)
        neighbours[j].append(i)
    found = set(roots)
    todo = deque(roots)
    while todo:
        i = todo.popleft()
        for j in neighbours[i]:
            if j not in found:
                found.add(j)
                todo.append(j)
    return sorted(found)


def rotation_about_axis(axis, degrees: float) -> np.ndarray:
    """Right-hand Rodrigues matrix for Cartesian column vectors."""
    direction = np.asarray(axis, dtype=float).reshape(3)
    length = float(np.linalg.norm(direction))
    if length < 1e-12:
        raise ValueError('Rotation axis is zero')
    x, y, z = direction / length
    t = math.radians(float(degrees))
    c, s = math.cos(t), math.sin(t)
    k = 1 - c
    return np.array([
        [c + x*x*k, x*y*k - z*s, x*z*k + y*s],
        [y*x*k + z*s, c + y*y*k, y*z*k - x*s],
        [z*x*k - y*s, z*y*k + x*s, c + z*z*k],
    ], dtype=float)


def apply_fragment_rotation(frame: Frame, indices, rotation, pivot) -> None:
    """Rigidly rotate selected atomic coordinates, without changing the cell."""
    ids = np.asarray(sorted(set(int(i) for i in indices)), dtype=int)
    if ids.size == 0:
        return
    if ids.min() < 0 or ids.max() >= len(frame.symbols):
        raise IndexError('Atom index out of range')
    R = np.asarray(rotation, dtype=float).reshape(3, 3)
    if not np.allclose(R @ R.T, np.eye(3), atol=1e-8):
        raise ValueError('Rotation is not orthogonal')
    center = np.asarray(pivot, dtype=float).reshape(3)
    frame.positions[ids] = (frame.positions[ids] - center) @ R.T + center


def apply_fragment_translation(frame: Frame, indices, offset) -> None:
    ids = np.asarray(sorted(set(int(i) for i in indices)), dtype=int)
    if ids.size == 0:
        return
    if ids.min() < 0 or ids.max() >= len(frame.symbols):
        raise IndexError('Atom index out of range')
    frame.positions[ids] += np.asarray(offset, dtype=float).reshape(3)


def camera_basis(camera):
    """Return view direction, screen-right and screen-up unit vectors."""
    forward = np.asarray(camera.GetDirectionOfProjection(), dtype=float)
    up = np.asarray(camera.GetViewUp(), dtype=float)
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)
    return forward, right, up


def screen_translation(camera, dx: float, dy: float, logical_height: int, pivot):
    """Map a Qt screen drag (positive y downward) to a world-space offset."""
    if logical_height <= 0:
        raise ValueError('Viewport height must be positive')
    forward, right, up = camera_basis(camera)
    if camera.GetParallelProjection():
        world_height = 2.0 * float(camera.GetParallelScale())
    else:
        distance = abs(float(np.dot(
            np.asarray(pivot, dtype=float) - np.asarray(camera.GetPosition(), dtype=float), forward)))
        world_height = 2.0 * distance * math.tan(math.radians(float(camera.GetViewAngle())) / 2.0)
    return (right * float(dx) - up * float(dy)) * (world_height / logical_height)


def screen_rotation(camera, kind: str, dx: float, dy: float, sensitivity: float = .65):
    """World rotation from trackball-like or in-plane screen dragging."""
    forward, right, up = camera_basis(camera)
    if kind == 'roll':
        return rotation_about_axis(forward, dx * sensitivity)
    if kind == 'orbit':
        return rotation_about_axis(up, dx * sensitivity) @ rotation_about_axis(right, dy * sensitivity)
    raise ValueError('Unknown rotation gesture')
