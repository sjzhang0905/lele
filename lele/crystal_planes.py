"""Miller planes and display half-spaces for a row-vector unit cell.

No 2π factor is used: r @ inv(cell) @ hkl = offset/d for offsets in Å.
All clipping half-spaces retain points with dot(normal, r-origin) >= 0.
"""
from dataclasses import dataclass
from itertools import product
import re
import numpy as np
from .crystal_settings import PLANE_MODES, default_plane


def validate_planes(values):
    result = []
    cuts = 0
    for value in values:
        p = {**default_plane(), **value}
        raw = np.asarray(p['hkl'], float)
        if raw.shape != (3,) or not np.isfinite(raw).all() or not np.all(raw == np.rint(raw)) or not np.any(raw):
            raise ValueError('Miller indices must be three integers; (0 0 0) does not define a plane.')
        p['hkl'] = tuple(int(x) for x in raw)
        if p['mode'] not in PLANE_MODES or p['unit'] not in ('d', 'Å'):
            raise ValueError('Choose a valid cutting direction and distance unit.')
        for key in ('offset', 'thickness', 'opacity'):
            p[key] = float(p[key])
            if not np.isfinite(p[key]):raise ValueError('Plane values must be finite.')
        if p['thickness'] <= 0 or not 0 <= p['opacity'] <= 1:
            raise ValueError('Slab thickness must be positive and opacity must be between 0 and 1.')
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}', p['color']):raise ValueError('Choose a valid plane colour.')
        p['enabled'], p['show'] = bool(p['enabled']), bool(p['show'])
        if p['enabled']:
            cuts += 2 if p['mode'] == 'Slab' else int(p['mode'] != 'Show only')
        result.append(p)
    if cuts > 6:
        raise ValueError('Use at most six active cutting faces (a slab uses two).')
    return result


@dataclass
class MillerPlane:
    normal: np.ndarray
    origin: np.ndarray
    spacing: float
    distance: float


def miller_plane(cell, hkl, offset=0., unit='d', translation=(0., 0., 0.)):
    cell = np.asarray(cell, float).reshape(3, 3)
    hkl = np.asarray(hkl, float)
    if not np.isfinite(cell).all() or abs(np.linalg.det(cell)) < 1.e-10:
        raise ValueError('Miller planes require a non-singular unit cell.')
    if hkl.shape != (3,) or not np.isfinite(hkl).all() or not np.any(hkl) or not np.all(hkl == np.rint(hkl)):
        raise ValueError('Use nonzero integer Miller indices.')
    reciprocal = np.linalg.solve(cell, hkl)
    spacing = 1. / np.linalg.norm(reciprocal)
    normal = reciprocal * spacing
    distance = float(offset) * (spacing if unit == 'd' else 1.)
    return MillerPlane(normal, np.asarray(translation, float) + distance * normal, float(spacing), distance)


def prepare_planes(cell, values, translation=(0., 0., 0.)):
    """Return display planes and inward-normal clipping half-spaces."""
    displays, cuts = [], []
    for p in validate_planes(values):
        if not p['enabled']:continue
        plane = miller_plane(cell, p['hkl'], p['offset'], p['unit'], translation)
        n, origin = plane.normal, plane.origin
        surfaces = [origin]
        if p['mode'] == 'Keep below':cuts.append((-n, origin))
        elif p['mode'] == 'Keep above':cuts.append((n, origin))
        elif p['mode'] == 'Slab':
            half = p['thickness'] * (plane.spacing if p['unit'] == 'd' else 1.) / 2.
            surfaces = [origin-half*n, origin+half*n]
            cuts.extend(((n, surfaces[0]), (-n, surfaces[1])))
        if p['show']:
            displays.extend((p, plane, point) for point in surfaces)
    return displays, cuts


def inside_cuts(points, cuts, tolerance=1.e-8):
    xyz = np.asarray(points, float).reshape(-1, 3)
    keep = np.ones(len(xyz), bool)
    for normal, origin in cuts:keep &= ((xyz-origin) @ normal >= -tolerance)
    return keep


def plane_polygon(cell, normal, origin, bounds=((0., 1.),)*3, translation=(0., 0., 0.)):
    """Ordered intersection of a plane and a fractional parallelepiped."""
    corners = np.asarray(list(product(*bounds)), float) @ np.asarray(cell) + translation
    distance = (corners-origin) @ normal
    points = []
    for i in range(8):
        if abs(distance[i]) < 1.e-8:points.append(corners[i])
        for bit in (1, 2, 4):
            j = i ^ bit
            if j <= i or distance[i]*distance[j] >= 0:continue
            points.append(corners[i]+(corners[j]-corners[i]) * distance[i]/(distance[i]-distance[j]))
    unique = []
    for p in points:
        if not any(np.linalg.norm(p-q) < 1.e-7 for q in unique):unique.append(p)
    if len(unique) < 3:return np.empty((0, 3))
    points = np.asarray(unique)
    center = points.mean(axis=0)
    u = points[0]-center;u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    angle = np.arctan2((points-center) @ v, (points-center) @ u)
    return points[np.argsort(angle)]


def clip_polygon(polygon, cuts):
    points = list(np.asarray(polygon).reshape(-1, 3))
    for normal, origin in cuts:
        output = []
        for i, p in enumerate(points):
            q = points[(i+1) % len(points)]
            a, b = np.dot(p-origin, normal), np.dot(q-origin, normal)
            if a >= -1.e-8:output.append(p)
            if (a < -1.e-8) != (b < -1.e-8):output.append(p+(q-p)*a/(a-b))
        points = output
    return np.asarray(points).reshape(-1, 3)
