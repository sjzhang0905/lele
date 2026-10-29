#!/usr/bin/env python3
"""Least-squares selection planes and frame-local atom deletion."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .core import Frame, rotation_between_vectors
from .periodic_geometry import minimum_image, periodic_basis


@dataclass
class SelectionPlane:
    indices: tuple[int, ...]
    points: np.ndarray
    center: np.ndarray
    normal: np.ndarray
    corners: np.ndarray
    rms: float
    max_distance: float


def fit_selection_plane(frame: Frame, selection, *, nearest_images=True,
                        image_positions=None) -> SelectionPlane:
    """Equal-weight orthogonal least-squares plane through the point centroid.

    Optional nearest images are anchored to the first selected atom. An active
    finite-fragment preview may supply its already unwrapped image positions.
    The returned points are copies; fitting never edits the input frame.
    """
    indices = tuple(dict.fromkeys(int(i) for i in selection))
    if len(indices) < 3:
        raise ValueError('Select at least three atoms to fit a plane')
    if any(i < 0 or i >= len(frame.symbols) for i in indices):
        raise ValueError('Selected atom index out of range')
    points = frame.positions[list(indices)].copy()
    if nearest_images and periodic_basis(frame) is not None:
        if image_positions is not None and all(i in image_positions for i in indices):
            points = np.array([image_positions[i] for i in indices], dtype=float)
        else:
            anchor = points[0].copy()
            points = np.array([anchor + minimum_image(p - anchor, frame)[0] for p in points])
    center = points.mean(axis=0)
    centered = points - center
    _, singular, axes = np.linalg.svd(centered, full_matrices=False)
    if singular[1] <= max(1.e-10, singular[0] * 1.e-10):
        raise ValueError('Selected atoms are collinear; a unique plane cannot be fitted')
    normal = axes[-1].copy()
    # Choose the sign that gives the smaller rotation onto the positive Z axis.
    sign_component = normal[2] if abs(normal[2]) > 1.e-12 else normal[np.argmax(np.abs(normal))]
    if sign_component < 0:
        normal *= -1
    u = axes[0]
    v = np.cross(normal, u)
    uv = centered @ np.stack([u, v]).T
    low, high = uv.min(axis=0), uv.max(axis=0)
    padding = np.maximum((high - low) * .12, .3)
    low, high = low - padding, high + padding
    corners = np.array([center + x * u + y * v for x, y in (
        (low[0], low[1]), (high[0], low[1]),
        (high[0], high[1]), (low[0], high[1]))])
    distances = centered @ normal
    return SelectionPlane(indices, points, center, normal, corners,
                          float(np.sqrt(np.mean(distances ** 2))),
                          float(np.max(np.abs(distances))))


def align_plane_to_xy(frame: Frame, plane: SelectionPlane, *, place_at_zero=True,
                      volume=None):
    """Rotate the complete structure, cell and optional grid with a proper R.

    Row-vector convention: r_new = r_old @ R.T + translation. An optional
    translation along Z places the fitted plane at z=0. The atomic deviations
    from the plane are preserved. Periodic image shifts remain valid when
    transformed by the same R as the cell.
    """
    rotation = rotation_between_vectors(plane.normal, [0., 0., 1.])
    translation = np.zeros(3)
    if place_at_zero:
        translation[2] = -float((plane.center @ rotation.T)[2])
    frame.positions = frame.positions @ rotation.T + translation
    frame.cell = frame.cell @ rotation.T
    if volume is not None:
        volume.origin = volume.origin @ rotation.T + translation
        volume.voxel_vectors = volume.voxel_vectors @ rotation.T
    frame.info['plane_alignment'] = {
        'rotation': rotation.tolist(), 'translation': translation.tolist(),
        'selection': list(plane.indices), 'rms_angstrom': plane.rms,
    }
    return rotation, translation


def delete_selected_atoms(frame: Frame, selection) -> int:
    """Delete selected atoms and remap surviving manual bonds and POSCAR blocks."""
    removed = set(int(i) for i in selection)
    if any(i < 0 or i >= len(frame.symbols) for i in removed):
        raise ValueError('Selected atom index out of range')
    if not removed:
        return 0
    kept = [i for i in range(len(frame.symbols)) if i not in removed]
    new_index = {old: new for new, old in enumerate(kept)}
    if frame.bond_snapshot is not None:
        frame.bond_snapshot = frozenset((new_index[i], new_index[j]) for i, j in frame.bond_snapshot
                                        if i in new_index and j in new_index)
    if frame.periodic_bond_snapshot is not None:
        frame.periodic_bond_snapshot = tuple((new_index[i], new_index[j], shift)
            for i, j, shift in frame.periodic_bond_snapshot if i in new_index and j in new_index)
    groups = frame.info.get('poscar_groups')
    if groups is not None:
        updated = []
        offset = 0
        for symbol, count in groups:
            count = int(count)
            remaining = sum(i not in removed for i in range(offset, offset + count))
            if remaining:
                updated.append((symbol, remaining))
            offset += count
        frame.info['poscar_groups'] = updated
    frame.symbols = [frame.symbols[i] for i in kept]
    frame.positions = frame.positions[kept].copy()
    for name in ('bond_added', 'bond_removed'):
        setattr(frame, name, {(new_index[i], new_index[j]) for i, j in getattr(frame, name)
                              if i in new_index and j in new_index})
    frame.atom_appearance = {new_index[i]: style for i, style in frame.atom_appearance.items()
                             if i in new_index}
    frame.hbond_added = {(new_index[i], new_index[j]): shift for (i, j), shift in frame.hbond_added.items()
                         if i in new_index and j in new_index}
    frame.hbond_removed = {(new_index[i], new_index[j]) for i, j in frame.hbond_removed
                           if i in new_index and j in new_index}
    # The input energy and the previous plane's atom indices no longer apply.
    frame.energy_ev = None
    frame.info.pop('energy_source', None)
    frame.info.pop('plane_alignment', None)
    return len(removed)
