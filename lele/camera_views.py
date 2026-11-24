"""Cartesian and direct-lattice viewing directions without geometry edits.

Cell rows are the direct a/b/c vectors. The optional display rotation uses
LELE's row-vector convention: displayed_vector = source_vector @ rotation.
No reciprocal-cell normal is involved in an a/b/c camera view.
"""
from __future__ import annotations

import numpy as np


def has_crystal_axes(frame):
    """Whether a current frame has a finite, nondegenerate periodic cell."""
    if frame is None:
        return False
    try:
        cell = np.asarray(frame.cell, dtype=float)
        return bool(any(frame.pbc) and cell.shape == (3, 3)
                    and np.isfinite(cell).all()
                    and abs(float(np.linalg.det(cell))) > 1.e-9)
    except (AttributeError, TypeError, ValueError, np.linalg.LinAlgError):
        return False


def axis_camera_basis(axis, frame=None, *, display_rotation=None):
    """Return unit (focal-point-to-camera direction, view-up) vectors.

    Viewing from +a/+b prefers c upward; viewing from +c prefers b upward.
    Projecting that preference into the screen avoids collinear view-up for
    oblique cells and reproduces the old X/Y/Z convention for an orthogonal cell.
    Cartesian X/Y/Z remain world axes; only lattice axes follow display alignment.
    """
    axis = str(axis).strip()
    name = axis.lower()
    if name in ('x', 'y', 'z'):
        basis = np.eye(3)
        index = ('x', 'y', 'z').index(name)
    elif name in ('a', 'b', 'c'):
        if not has_crystal_axes(frame):
            raise ValueError('a/b/c views require a valid periodic crystal cell.')
        basis = np.asarray(frame.cell, dtype=float).copy()
        index = ('a', 'b', 'c').index(name)
        if display_rotation is not None:
            rotation = np.asarray(display_rotation, dtype=float)
            if (rotation.shape != (3, 3) or not np.isfinite(rotation).all()
                    or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1.e-7, rtol=1.e-7)
                    or np.linalg.det(rotation) <= 0):
                raise ValueError('The current display rotation is invalid.')
            basis = basis @ rotation
    else:
        raise ValueError('View axis must be X, Y, Z, a, b or c.')
    basis = basis / np.linalg.norm(basis, axis=1)[:, None]
    direction = basis[index]
    preferences = ((2, 1), (2, 0), (1, 0))[index]
    candidates = [basis[i] for i in preferences]
    # Extreme near-collinearity should never produce an undefined camera roll.
    candidates.extend(np.eye(3)[np.argsort(np.abs(direction))])
    for candidate in candidates:
        up = candidate - np.dot(candidate, direction) * direction
        length = float(np.linalg.norm(up))
        if length > 1.e-8:
            up /= length
            # Enforce an orthonormal right-handed screen basis. The camera
            # looks along -direction, so screen-right is up × direction.
            right = np.cross(up, direction)
            right /= np.linalg.norm(right)
            up = np.cross(direction, right)
            return direction.copy(), up
    raise ValueError('Could not determine a stable camera view-up direction.')


def orient_camera_to_axis(camera, axis, frame=None, *, display_rotation=None):
    """Change orientation only, retaining focal point, distance and zoom.

    Projection mode, parallel scale and perspective view angle stay untouched.
    The GUI adapter may explicitly request the existing fit-to-window behavior.
    """
    direction, up = axis_camera_basis(axis, frame, display_rotation=display_rotation)
    focal = np.asarray(camera.GetFocalPoint(), dtype=float)
    position = np.asarray(camera.GetPosition(), dtype=float)
    distance = float(np.linalg.norm(position - focal))
    if not np.isfinite(focal).all() or not np.isfinite(distance):
        raise ValueError('The current camera position is invalid.')
    if distance <= 1.e-12:
        distance = 1.0
    camera.SetPosition(*(focal + direction * distance))
    camera.SetViewUp(*up)
    return direction, up


def refresh_crystal_view_actions(window):
    """Call on every scene/frame/document change, including results-only pages."""
    enabled = has_crystal_axes(window.frame)
    for axis in ('a', 'b', 'c'):
        action = getattr(window, 'axis_actions', {}).get(axis)
        if action is not None:
            action.setEnabled(enabled)
    return enabled


def rotation_lattice_axes(frame):
    """Even an incomplete periodic cell can supply an individual rotation axis."""
    if frame is None or not any(frame.pbc):
        return ()
    return tuple(axis for axis, vector in zip('abc', frame.cell)
                 if np.isfinite(vector).all() and np.linalg.norm(vector) > 1.e-12)


def rotate_window_camera(window, basis, axis, degrees):
    """Orbit the camera so the structure turns by a right-handed view step."""
    from .fragment import camera_basis, rotation_about_axis

    if window.frame is None or window.scene is None:
        return False
    camera = window.scene.GetActiveCamera()
    if basis == 'Screen':
        forward, right, up = camera_basis(camera)
        direction = {'X': right, 'Y': up, 'Z': -forward}[axis]
    elif basis == 'Cartesian':
        direction = np.eye(3)['XYZ'.index(axis)]
    else:
        if axis not in rotation_lattice_axes(window.frame):
            return False
        direction = window.frame.cell['abc'.index(axis)] @ window.renderer.display_rotation

    focal = np.asarray(camera.GetFocalPoint())
    position = np.asarray(camera.GetPosition())
    view_up = np.asarray(camera.GetViewUp())
    center = window.renderer.atom_center()
    if center is None:
        center = focal  # Field-only scenes have no atom centroid.
    # Orbit both camera points about the displayed centroid, including after a pan.
    rotation = rotation_about_axis(direction, -degrees)
    camera.SetFocalPoint(*(center + rotation @ (focal - center)))
    camera.SetPosition(*(center + rotation @ (position - center)))
    camera.SetViewUp(*(rotation @ view_up))
    window.scene.ResetCameraClippingRange()
    window.vtk.GetRenderWindow().Render()
    return True


def align_window_camera(window, axis, *, fit=True):
    """GUI adapter shared by XYZ and abc actions; never touches source data.

    fit=True retains LELE's existing XYZ behavior: orthographic view followed
    by fit to displayed scene bounds. fit=False preserves camera focus/zoom.
    """
    frame = window.frame
    scene = getattr(window, 'scene', None)
    if frame is None or scene is None:
        return False
    if str(axis).lower() in ('a', 'b', 'c'):
        if not has_crystal_axes(frame):
            return False
    elif not frame.symbols:
        return False
    display_rotation = getattr(getattr(window, 'renderer', None), 'display_rotation', None)
    camera = scene.GetActiveCamera()
    try:
        orient_camera_to_axis(camera, axis, frame, display_rotation=display_rotation)
    except ValueError as exc:
        window.statusBar().showMessage(str(exc), 5000)
        return False
    if fit:
        camera.SetParallelProjection(True)
        scene.ResetCamera()
    scene.ResetCameraClippingRange()
    projection = 'Orthographic' if camera.GetParallelProjection() else 'Perspective'
    action = getattr(window, 'projection_actions', {}).get(projection)
    if action is not None:
        action.setChecked(True)
    if getattr(window, 'vtk', None) is not None:
        window.vtk.GetRenderWindow().Render()
    return True
