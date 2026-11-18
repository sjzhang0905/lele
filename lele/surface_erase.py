"""Non-destructive, through-depth rectangular masks for isosurface meshes.

Four inward half-planes describe a rectangle extruded through the view.  They
are stored in model coordinates, so changing the camera or display alignment
does not move an existing mask.  Grid values and atomic structures are never
modified.
"""
import numpy as np


def validate_hidden_regions(regions):
    """Return a normalized JSON-compatible copy, rejecting malformed projects."""
    if not isinstance(regions, (list, tuple)) or len(regions) > 1024:
        raise ValueError('Isosurface hidden regions must be a list of at most 1024 rectangles.')
    result = []
    for region in regions:
        if not isinstance(region, dict) or set(region) != {'planes'}:
            raise ValueError('Invalid isosurface hidden region.')
        try:
            planes = np.asarray(region['planes'], dtype=float)
        except (TypeError, ValueError):
            raise ValueError('Invalid isosurface hide-plane coordinates.') from None
        if planes.shape != (4, 4) or not np.isfinite(planes).all():
            raise ValueError('Each hidden rectangle requires four finite planes.')
        lengths = np.linalg.norm(planes[:, :3], axis=1)
        if np.any(lengths < 1.e-12):
            raise ValueError('A hidden-region plane has no normal.')
        result.append({'planes': (planes / lengths[:, None]).tolist()})
    return result


def _world_point(renderer, x, y, depth):
    renderer.SetDisplayPoint(float(x), float(y), float(depth))
    renderer.DisplayToWorld()
    point = np.asarray(renderer.GetWorldPoint(), dtype=float)
    if not np.isfinite(point).all() or abs(point[3]) < 1.e-15:
        raise ValueError('The current camera cannot define a rectangle.')
    return point[:3] / point[3]


def rectangle_hidden_region(renderer, rectangle, *, rotation=None, translation=None):
    """Make a through-depth mask from VTK display pixels (bottom-left origin).

    Near/far planes are used only to define the four sides.  They do not limit
    the hide depth: surfaces beyond either clipping distance are also hidden.
    Both parallel and perspective cameras are supported.
    """
    x1, y1, x2, y2 = np.asarray(rectangle, dtype=float)
    if not np.isfinite([x1, y1, x2, y2]).all():
        raise ValueError('The rectangle coordinates must be finite.')
    left, right = sorted((x1, x2)); bottom, top = sorted((y1, y2))
    if right - left < 1. or top - bottom < 1.:
        raise ValueError('Drag a rectangle at least one pixel wide and high.')
    corners = [(left, bottom), (right, bottom), (right, top), (left, top)]
    near = np.asarray([_world_point(renderer, x, y, 0.) for x, y in corners])
    far = np.asarray([_world_point(renderer, x, y, 1.) for x, y in corners])
    center = (near.mean(axis=0) + far.mean(axis=0)) / 2.
    rotation = np.eye(3) if rotation is None else np.asarray(rotation, dtype=float)
    translation = np.zeros(3) if translation is None else np.asarray(translation, dtype=float)
    planes = []
    for index in range(4):
        normal = np.cross(near[(index + 1) % 4] - near[index], far[index] - near[index])
        length = np.linalg.norm(normal)
        if not np.isfinite(length) or length < 1.e-15:
            raise ValueError('The current camera produces a degenerate rectangle.')
        normal /= length
        if np.dot(center - near[index], normal) < 0.: normal = -normal
        distance = -float(np.dot(normal, near[index]))
        # x_display = x_model @ rotation + translation.
        model_normal = rotation @ normal
        model_distance = distance + float(np.dot(translation, normal))
        planes.append([*model_normal, model_distance])
    return validate_hidden_regions([{'planes': planes}])[0]


def display_region_planes(region, rotation=None, translation=None):
    """Transform stored model half-planes to the current Cartesian display."""
    source = np.asarray(region['planes'], dtype=float)
    rotation = np.eye(3) if rotation is None else np.asarray(rotation, dtype=float)
    translation = np.zeros(3) if translation is None else np.asarray(translation, dtype=float)
    normals = np.linalg.solve(rotation, source[:, :3].T).T
    distances = source[:, 3] - normals @ translation
    lengths = np.linalg.norm(normals, axis=1)
    return np.column_stack((normals, distances)) / lengths[:, None]


def hide_polydata(poly, regions, *, rotation=None, translation=None):
    """Subtract convex rectangles exactly, retaining interpolated point data.

    A single implicit max/min clipping function can miss a small rectangle
    entirely contained in a large triangle.  Instead, split at every plane:
    keep the outside piece and continue clipping only the inside remainder.
    The outside pieces form the required union, with no overlapping area.
    """
    from itertools import product
    from vtkmodules.vtkCommonDataModel import vtkPlane, vtkPolyData
    from vtkmodules.vtkFiltersCore import vtkClipPolyData, vtkAppendPolyData
    from .output_text import check_load_cancelled

    resources = []
    for region in regions:
        check_load_cancelled()
        if not poly.GetNumberOfCells(): break
        planes = display_region_planes(region, rotation, translation)
        bounds = poly.GetBounds()
        corners = np.array(list(product(*[bounds[i:i+2] for i in (0, 2, 4)])))
        sides = corners @ planes[:, :3].T + planes[:, 3]
        if np.any(np.max(sides, axis=0) < 0.): continue
        if np.all(sides >= 0.):
            poly = vtkPolyData(); resources.append(poly); break
        remaining = poly; pieces = []
        for coefficients in planes:
            check_load_cancelled()
            plane = vtkPlane(); plane.SetNormal(*coefficients[:3])
            plane.SetOrigin(*(-coefficients[3] * coefficients[:3]))
            cutter = vtkClipPolyData(); cutter.SetInputData(remaining)
            cutter.SetClipFunction(plane); cutter.SetValue(0.)
            cutter.GenerateClippedOutputOn(); cutter.Update()
            outside = cutter.GetClippedOutput()
            if outside.GetNumberOfCells(): pieces.append(outside)
            remaining = cutter.GetOutput(); resources.extend((plane, cutter))
            if not remaining.GetNumberOfCells(): break
        if pieces:
            joined = vtkAppendPolyData()
            for piece in pieces: joined.AddInputData(piece)
            joined.Update(); poly = joined.GetOutput(); resources.append(joined)
        else:
            poly = vtkPolyData(); resources.append(poly)
    return poly, resources
