"""Geometry and display settings for scalar fields sampled on arbitrary planes.

Positions are Cartesian Angstrom coordinates. A slice samples the original
field by trilinear interpolation; no value is inferred outside a finite grid.
"""
import re
from itertools import product
import numpy as np
from .crystal_planes import clip_polygon
from .crystal_settings import DEFAULT_CONTOUR_COUNT, MAX_CONTOUR_COUNT, FIELD_STYLE_KEYS

FIELD_PALETTES = ('Auto', 'Blue-white-red', 'Viridis')


def default_plane_style():
    return dict(field=True, field_palette='Auto', field_range=None,
                field_contours=False, field_contour_count=DEFAULT_CONTOUR_COUNT,
                field_contour_labels=False, field_legend=True, field_resolution=256,
                opacity=.22, color='#36A8D8')


def validate_plane_style(values):
    if not isinstance(values, dict):raise ValueError('Plane display settings must be an object.')
    style = {**default_plane_style(), **values}
    if style['field_palette'] not in FIELD_PALETTES:raise ValueError('Choose a valid slice color palette.')
    if not isinstance(style['color'], str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', style['color']):
        raise ValueError('Choose a valid plane color.')
    for name in ('field', 'field_contours', 'field_contour_labels', 'field_legend'):style[name] = bool(style[name])
    count = style['field_contour_count']
    if type(count) is not int or not 1 <= count <= MAX_CONTOUR_COUNT:
        raise ValueError(f'Contour levels must be an integer from 1 to {MAX_CONTOUR_COUNT}.')
    if style['field_range'] is not None:
        limits = np.asarray(style['field_range'], float)
        if limits.shape != (2,) or not np.isfinite(limits).all() or limits[0] >= limits[1]:
            raise ValueError('Slice color limits must be finite with Min < Max.')
        style['field_range'] = limits.tolist()
    resolution = style['field_resolution']
    if isinstance(resolution, bool) or not np.isfinite(float(resolution)) or float(resolution) != int(resolution) or not 16 <= int(resolution) <= 1024:
        raise ValueError('Slice resolution must be an integer from 16 to 1024.')
    style['field_resolution'] = int(resolution)
    style['opacity'] = float(style['opacity'])
    if not np.isfinite(style['opacity']) or not 0 <= style['opacity'] <= 1:
        raise ValueError('Plane opacity must be between 0 and 1.')
    return style


def plane_axes(normal):
    normal = np.asarray(normal, float)
    if normal.shape != (3,) or not np.isfinite(normal).all() or np.linalg.norm(normal) < 1e-12:
        raise ValueError('Plane normal must be finite and nonzero.')
    normal = normal / np.linalg.norm(normal)
    reference = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, reference);u /= np.linalg.norm(u)
    return u, np.cross(normal, u), normal


def grid_domain_cuts(volume):
    """Six inward faces of the finite first-to-last-node grid box."""
    inverse = np.linalg.inv(volume.voxel_vectors)
    extent = np.asarray(volume.data.shape)-1
    cuts = []
    for axis in range(3):
        cuts.extend(((inverse[:, axis], volume.origin),
                     (-inverse[:, axis], volume.origin+extent[axis]*volume.voxel_vectors[axis])))
    return cuts


def field_covered_polygon(polygon, volume):
    if volume.periodic:return np.asarray(polygon, float)
    return clip_polygon(polygon, grid_domain_cuts(volume))


def uncovered_field_polygons(polygon, volume):
    """Disjoint uncolored pieces outside the finite grid, on the same plane."""
    remaining = np.asarray(polygon)
    for normal, origin in grid_domain_cuts(volume):
        if len(remaining) < 3:
            break
        if np.any((remaining - origin) @ normal < -1.e-8):
            outside = clip_polygon(remaining, [(-normal, origin)])
            if len(outside) >= 3:
                yield outside
            remaining = clip_polygon(remaining, [(normal, origin)])


def fitted_plane_polygon(frame, fitted, *, volume=None, bounds=((0., 1.),)*3,
                         rotation=None, translation=None, preserve_cell_origin=True,
                         displayed_positions=None):
    """Rectangle enclosing the projection of the displayed structure, cell and grid."""
    rotation = np.eye(3) if rotation is None else np.asarray(rotation, float)
    translation = np.zeros(3) if translation is None else np.asarray(translation, float)
    center = fitted.center @ rotation+translation
    # Choose axes in the fit's source coordinates so a display rotation
    # carries all four corners rigidly along with the structure.
    u, v, _ = plane_axes(fitted.normal)
    u, v = u @ rotation, v @ rotation
    points = [fitted.points @ rotation + translation,
              frame.positions if displayed_positions is None else displayed_positions]
    from .periodic_geometry import periodic_basis
    if periodic_basis(frame) is not None:
        from .cell_origin import cell_origin
        offset = cell_origin(frame) if preserve_cell_origin else np.zeros(3)
        points.append(np.asarray(list(product(*bounds))) @ frame.cell + translation + offset)
    if volume is not None:
        span = np.asarray(volume.data.shape)-(0 if volume.periodic else 1)
        corners = np.asarray(list(product((0, 1), repeat=3))) * span
        points.append(corners @ volume.voxel_vectors + volume.origin)
    uv = (np.concatenate(points)-center) @ np.stack((u, v), axis=1)
    low, high = uv.min(axis=0), uv.max(axis=0)
    margin = np.maximum((high-low)*.08, .5)
    low -= margin;high += margin
    return np.array([center+x*u+y*v for x,y in
        ((low[0],low[1]),(high[0],low[1]),(high[0],high[1]),(low[0],high[1]))])


def plane_grid(polygon, normal, volume, max_axis=256):
    """A rectangular native-spacing sampling grid enclosing the slice polygon.

    The renderer clips triangles to the exact polygon before sampling. The
    axis cap controls display resolution only and never edits source data.
    """
    polygon = np.asarray(polygon, float).reshape(-1,3)
    if len(polygon) < 3:raise ValueError('Plane does not intersect the displayed field.')
    u, v, _ = plane_axes(normal);origin = polygon.mean(axis=0)
    uv = (polygon-origin) @ np.stack((u,v), axis=1)
    low, high = uv.min(axis=0),uv.max(axis=0)
    inverse = np.linalg.inv(volume.voxel_vectors)
    steps = 1/np.linalg.norm(np.array((u,v)) @ inverse, axis=1)
    raw = np.maximum(2, np.ceil((high-low)/steps).astype(int)+1)
    count = np.minimum(raw, int(max_axis))
    start=origin+low[0]*u+low[1]*v
    return start, u*(high[0]-low[0]), v*(high[1]-low[1]), tuple(map(int,count)), bool(np.any(count<raw))


def plane_color_limits(volume, values, style):
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if not len(values):raise ValueError('No finite field samples on this plane.')
    palette = style['field_palette']
    elf = 'elf' in (volume.label or '').lower()
    if palette == 'Auto':palette = 'Viridis' if elf else 'Blue-white-red'
    limits = style['field_range']
    if limits is not None:return palette, tuple(limits)
    if elf:return palette,(0.,1.)
    if palette == 'Blue-white-red':
        bound=max(float(np.max(np.abs(values))),1e-12)
        return palette,(-bound,bound)
    low, high=float(values.min()),float(values.max())
    if low == high:
        delta=max(abs(low)*1e-6,1e-12);low-=delta;high+=delta
    return palette,(low,high)
