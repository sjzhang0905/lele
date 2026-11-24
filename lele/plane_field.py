"""Geometry and display settings for scalar fields sampled on arbitrary planes.

Positions are Cartesian Angstrom coordinates. A slice samples the original
field by trilinear interpolation; no value is inferred outside a finite grid.
"""
import re
import numpy as np
from .crystal_planes import plane_polygon, clip_polygon

FIELD_PALETTES = ('Auto', 'Blue-white-red', 'Viridis')
FIELD_STYLE_KEYS = ('field', 'field_palette', 'field_range', 'field_contours', 'field_legend', 'field_resolution')


def default_plane_style():
    return dict(field=True, field_palette='Auto', field_range=None,
                field_contours=False, field_legend=True, field_resolution=256,
                opacity=.22, color='#36A8D8')


def validate_plane_style(values):
    if not isinstance(values, dict):raise ValueError('Plane display settings must be an object.')
    style = {**default_plane_style(), **values}
    if style['field_palette'] not in FIELD_PALETTES:raise ValueError('Choose a valid slice color palette.')
    if not isinstance(style['color'], str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', style['color']):
        raise ValueError('Choose a valid plane color.')
    for name in ('field', 'field_contours', 'field_legend'):style[name] = bool(style[name])
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


def fitted_plane_polygon(frame, fitted, *, volume=None, bounds=((0., 1.),)*3,
                         rotation=None, translation=None,preserve_cell_origin=True):
    """Full plane/cell or plane/field intersection, rather than selection patch."""
    rotation = np.eye(3) if rotation is None else np.asarray(rotation, float)
    translation = np.zeros(3) if translation is None else np.asarray(translation, float)
    center = fitted.center @ rotation+translation
    normal = fitted.normal @ rotation
    from .core import valid_lattice
    if valid_lattice(frame):
        from .cell_origin import cell_origin
        offset=cell_origin(frame) if preserve_cell_origin else np.zeros(3)
        return plane_polygon(frame.cell, normal, center, bounds, translation+offset)
    if volume is not None:
        span = np.asarray(volume.data.shape)-(0 if volume.periodic else 1)
        cell = span[:, None]*volume.voxel_vectors
        return plane_polygon(cell, normal, center, translation=volume.origin)
    # Isolated structures without a field still show the complete projected
    # structure extent, with a margin; there is no crystal boundary to use.
    u, v, _ = plane_axes(normal)
    points = np.asarray(frame.positions)
    if not len(points):return np.empty((0, 3))
    uv = (points-center) @ np.stack((u, v), axis=1)
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
