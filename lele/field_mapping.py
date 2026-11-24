"""Coordinate-correct scalar sampling and field attachment, without Qt/VTK.

Mapping samples the actual isosurface vertices (zero normal offset). It never
computes ESP or guesses the physical meaning / units of an imported CUBE.
"""
import re
import numpy as np
from copy import deepcopy
from .core import Volume
from .output_text import check_load_cancelled, load_progress

PALETTES = ('VMD RWB', 'VMD BWR', 'Red-white-blue', 'Blue-white-red', 'Viridis')
DEFAULT_PALETTE = 'VMD RWB'
DEFAULT_ESP_RANGE = (-.03, .03)


def is_esp_field(volume):
    """Recognize an explicitly assigned or named potential in the generic layer editor."""
    return (volume.provenance.get('pair_role') == 'ESP' or volume.unit in ('V', 'Hartree/e')
            or bool(re.search(r'(?:^|[^a-z])(?:esp|mep|electrostatic[ _-]+potential)(?:$|[^a-z])',
                              volume.label or '', re.IGNORECASE)))


def legend_unit(unit):
    label = (unit or '').strip()
    return '' if label.casefold() in ('source units', 'unknown source units') else label


def _finite_range(values):
    data = np.asarray(values)
    if not data.size:
        return None
    low, high = float(np.min(data)), float(np.max(data))
    if np.isfinite(low) and np.isfinite(high):
        return low, high
    # Imported fields are normally finite. Only the exceptional path needs a
    # mask, and never one as large as a multi-gigabyte grid.
    low, high = np.inf, -np.inf
    for block in np.nditer(data, flags=['external_loop', 'buffered'], order='K',
                           op_flags=['readonly', 'contig'], buffersize=262144):
        check_load_cancelled()
        finite = block[np.isfinite(block)]
        if finite.size:
            low, high = min(low, float(finite.min())), max(high, float(finite.max()))
    return (low, high) if low <= high else None


def field_data_limits(values):
    """Finite scalar range, expanded only for a constant field."""
    limits = _finite_range(values)
    if limits is None:
        raise ValueError('The field contains no finite scalar values.')
    low, high = limits
    if low == high:
        delta = max(abs(low)*1e-6, 1e-12)
        return low-delta, high+delta
    return low, high


def suggested_isovalue(values, requested):
    """Keep a useful level when changing source, including positive-only grids.

    A signed orbital level is kept if it lies strictly inside the new range.
    For a density field, try its positive magnitude before choosing an interior
    level. Never alter the underlying density or silently normalize it.
    """
    limits = _finite_range(values)
    if limits is None:
        return float(requested)
    low, high = limits
    requested = float(requested)
    if low < requested < high or low == high:
        return requested
    magnitude = abs(requested)
    if low >= 0 and low < magnitude < high:
        return magnitude
    if high <= 0 and low < -magnitude < high:
        return -magnitude
    if low >= 0:
        value = low + .1*(high-low)
    elif high <= 0:
        value = high - .1*(high-low)
    else:
        value = .1*high if requested >= 0 else .1*low
    # Imported volume storage is float32; avoid presenting its roundoff digits
    # as an apparently significant user-selected level.
    rounded = float(f'{value:.6g}')
    return rounded if low < rounded < high else value


def field_transform(active):
    rotation = np.linalg.solve(active.reference_voxel_vectors, active.voxel_vectors)
    translation = active.origin - active.reference_origin @ rotation
    return rotation, translation


def transformed_fields(fields, active, rotation=None, translation=None):
    """Non-mutating views of all grids in the active field's coordinate frame."""
    transform, shift = field_transform(active)
    rotation = np.eye(3) if rotation is None else np.asarray(rotation)
    translation = np.zeros(3) if translation is None else np.asarray(translation)
    return [Volume(v.data, (v.reference_origin @ transform + shift) @ rotation + translation,
                   v.reference_voxel_vectors @ transform @ rotation, v.label, v.unit, v.periodic,
                   provenance=v.provenance)
            for v in fields]


def sample_field(volume, points, *, chunk_size=65536, progress=None):
    """Trilinear samples at Cartesian Angstrom points; NaN outside the domain.

    Periodic fields wrap using all three grid periods. Nonperiodic fields are
    sampled only from their first through last grid nodes; no extrapolation.
    """
    from scipy.ndimage import map_coordinates
    data = np.asarray(volume.data)
    basis = np.asarray(volume.voxel_vectors, float)
    if not np.isfinite(basis).all() or abs(np.linalg.det(basis)) < 1e-15:
        raise ValueError('Mapping grid has invalid or singular voxel vectors.')
    inverse = np.linalg.inv(basis)
    points = np.asarray(points, float).reshape(-1, 3)
    result = np.full(len(points), np.nan, dtype=float)
    shape = np.asarray(data.shape)
    report = load_progress('Sampling color field on surface', len(points))
    for start in range(0, len(points), chunk_size):
        check_load_cancelled()
        p = (points[start:start+chunk_size] - volume.origin) @ inverse
        valid = np.isfinite(p).all(axis=1)
        if volume.periodic:
            p = np.mod(np.where(np.isfinite(p), p, 0), shape)
        else:
            # Mesh vertices come from VTK float32 geometry; tolerate sub-voxel
            # roundoff at the exact edge without allowing real extrapolation.
            valid &= ((p >= -2e-5) & (p <= shape-1+2e-5)).all(axis=1)
            p = np.clip(np.where(np.isfinite(p), p, 0), 0, shape-1)
        values = result[start:start+len(p)]
        map_coordinates(data, p.T, output=values, order=1, prefilter=False,
                        mode='grid-wrap' if volume.periodic else 'nearest')
        values[~valid] = np.nan
        report(start+len(p))
        if progress is not None:
            progress('Sampling color field on surface', start+len(p), len(points))
    return result


def mapping_limits(spec, samples, color_values=None):
    finite = np.asarray(samples)[np.isfinite(samples)]
    if not len(finite):
        raise ValueError('The color field does not cover any surface vertices.')
    limits = spec.get('map_range')
    if limits is None:
        if spec.get('map_palette', DEFAULT_PALETTE).startswith('VMD '):
            # VMD scales the selected volume's data range, not just the values
            # touched by this particular isosurface. White is the range midpoint.
            return field_data_limits(finite if color_values is None else color_values)
        bound = max(float(np.max(np.abs(finite))), 1e-12)
        return -bound, bound
    limits=np.asarray(limits,float)
    if limits.shape != (2,) or not np.isfinite(limits).all() or limits[0]>=limits[1]:
        raise ValueError('Color limits must be finite with Min < Max.')
    if spec.get('map_palette',DEFAULT_PALETTE) in ('Red-white-blue','Blue-white-red') and not limits[0]<0<limits[1]:
        raise ValueError('Red/white/blue color limits must straddle zero (white).')
    return tuple(map(float, limits))


def validate_field_geometry(frame, source, transform, shift, *, periodic):
    from .site_occupancy import is_disordered
    if is_disordered(frame) or is_disordered(source):
        raise ValueError('A scalar field requires its fully specified atomic structure, not mixed or partial occupancies.')
    if frame.symbols != source.symbols or not np.allclose(
            source.positions @ transform + shift, frame.positions, atol=2e-4, rtol=0):
        raise ValueError('Atom order/elements or coordinates differ. Export both fields for the same geometry in the same coordinate frame.')
    if periodic and not np.allclose(source.cell @ transform, frame.cell, atol=2e-4, rtol=1e-6):
        raise ValueError('Periodic field lattice does not match the current structure.')


def prepare_field_attachment(target, frame, incoming):
    """Validate and copy incoming grids into the active document atomically."""
    if frame is None or not incoming.frames or not incoming.volumes:
        raise ValueError('Choose an XSF, CUBE or VASP file containing structure and complete scalar grids.')
    if target.modified and target.volume is None:
        raise ValueError('Fields were detached by a structure edit. Undo or reopen the source before importing fields.')
    transform, shift = (field_transform(target.volume) if target.volume is not None else (np.eye(3),np.zeros(3)))
    validate_field_geometry(frame, incoming.frames[0], transform, shift,
                            periodic=any(v.periodic for v in incoming.volumes))
    total = sum(v.data.size for v in target.volumes) + sum(v.data.size for v in incoming.volumes)
    from .grid_memory import scalar_limit
    if total > scalar_limit():
        raise ValueError('Combined fields exceed the available scalar-field memory budget.')
    added=[]
    for volume in incoming.volumes:
        check_load_cancelled()
        basis=volume.voxel_vectors
        if not np.isfinite(volume.data).all() or abs(np.linalg.det(basis))<1e-15:
            raise ValueError('Imported field must have finite data and independent grid vectors.')
        copy=Volume(volume.data.copy(), volume.origin@transform+shift, basis@transform,
                    f'{incoming.path.name} · {volume.label or "Field"}', volume.unit, volume.periodic,
                    volume.origin.copy(),basis.copy(),deepcopy(volume.provenance))
        added.append(copy)
    return added


def attach_field_document(target, frame, incoming):
    added=prepare_field_attachment(target,frame,incoming)
    target.volumes.extend(added)
    if target.volume is None:target.volume=added[0]
    return len(added)


def validate_layer_mapping(spec):
    """Validate persistent references and mapping controls before rendering."""
    for name in ('dataset','map_dataset'):
        index=spec.get(name,-1)
        if isinstance(index,bool) or not isinstance(index,(int,np.integer)) or index < -1:
            raise ValueError('Surface field selections must be valid dataset indices.')
    if spec.get('map_palette',DEFAULT_PALETTE) not in PALETTES:
        raise ValueError('Unknown surface color palette.')
    if spec.get('map_range') is not None:
        mapping_limits(spec,[0.])
    return spec
