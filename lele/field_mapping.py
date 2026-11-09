"""Coordinate-correct scalar sampling and field attachment, without Qt/VTK.

Mapping samples the actual isosurface vertices (zero normal offset). It never
computes ESP or guesses the physical meaning / units of an imported CUBE.
"""
import numpy as np
from .core import Volume
from .output_text import check_load_cancelled, load_progress

PALETTES = ('Red-white-blue', 'Blue-white-red', 'Viridis')


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
                   v.reference_voxel_vectors @ transform @ rotation, v.label, v.unit, v.periodic)
            for v in fields]


def sample_field(volume, points, *, chunk_size=65536, progress=None):
    """Trilinear samples at Cartesian Angstrom points; NaN outside the domain.

    Periodic fields wrap using all three grid periods. Nonperiodic fields are
    sampled only from their first through last grid nodes; no extrapolation.
    """
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
        low = np.floor(p).astype(int)
        fraction = p-low
        # mod(-epsilon, n) can round to exactly n at a periodic seam.
        # Keep its zero fractional weight, but wrap both integer neighbors.
        if volume.periodic:
            low %= shape
        high = (low+1) % shape if volume.periodic else np.minimum(low+1, shape-1)
        values = np.zeros(len(p))
        for x in (0,1):
            for y in (0,1):
                for z in (0,1):
                    bit=np.array([x,y,z]);index=np.where(bit, high, low)
                    weight=np.prod(np.where(bit, fraction, 1-fraction),axis=1)
                    values += data[tuple(index.T)] * weight
        result[start:start+len(p)] = np.where(valid, values, np.nan)
        report(start+len(p))
        if progress is not None:
            progress('Sampling color field on surface', start+len(p), len(points))
    return result


def mapping_limits(spec, samples):
    finite = np.asarray(samples)[np.isfinite(samples)]
    if not len(finite):
        raise ValueError('The color field does not cover any surface vertices.')
    limits = spec.get('map_range')
    if limits is None:
        bound = max(float(np.max(np.abs(finite))), 1e-12)
        return -bound, bound
    limits=np.asarray(limits,float)
    if limits.shape != (2,) or not np.isfinite(limits).all() or limits[0]>=limits[1]:
        raise ValueError('Color limits must be finite with Min < Max.')
    if spec.get('map_palette','Red-white-blue') != 'Viridis' and not limits[0]<0<limits[1]:
        raise ValueError('Red/white/blue color limits must straddle zero (white).')
    return tuple(map(float, limits))


def prepare_field_attachment(target, frame, incoming):
    """Validate and copy incoming grids into the active document atomically.

    Atom symbols/order and positions must match in the untransformed source
    frame. We do not fit/reorder unrelated structures or silently align grids.
    This operation embeds grid bytes in projects; no source-file dependency.
    """
    if frame is None or not incoming.frames or not incoming.volumes:
        raise ValueError('Choose a CUBE or VASP file containing structure and complete scalar grids.')
    if target.modified and target.volume is None:
        raise ValueError('Fields were detached by a structure edit. Undo or reopen the source before importing fields.')
    source = incoming.frames[0]
    from .site_occupancy import is_disordered
    if is_disordered(frame) or is_disordered(source):
        raise ValueError('A scalar field requires its fully specified atomic structure, not mixed or partial occupancies.')
    transform, shift = (field_transform(target.volume) if target.volume is not None else (np.eye(3),np.zeros(3)))
    if frame.symbols != source.symbols or not np.allclose(
            source.positions @ transform + shift, frame.positions, atol=2e-4, rtol=0):
        raise ValueError('Atom order/elements or coordinates differ. Export both fields for the same geometry in the same coordinate frame.')
    periodic = [v for v in incoming.volumes if v.periodic]
    if periodic and not np.allclose(source.cell @ transform, frame.cell, atol=2e-4, rtol=1e-6):
        raise ValueError('Periodic field lattice does not match the current structure.')
    total = sum(v.data.size for v in target.volumes) + sum(v.data.size for v in incoming.volumes)
    if total > 64_000_000:
        raise ValueError('Combined fields exceed the 64,000,000 scalar-value memory limit.')
    added=[]
    for volume in incoming.volumes:
        check_load_cancelled()
        basis=volume.voxel_vectors
        if not np.isfinite(volume.data).all() or abs(np.linalg.det(basis))<1e-15:
            raise ValueError('Imported field must have finite data and independent grid vectors.')
        copy=Volume(volume.data.copy(), volume.origin@transform+shift, basis@transform,
                    f'{incoming.path.name} · {volume.label or "Field"}', volume.unit, volume.periodic,
                    volume.origin.copy(),basis.copy())
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
    if spec.get('map_palette','Red-white-blue') not in PALETTES:
        raise ValueError('Unknown surface color palette.')
    if spec.get('map_range') is not None:
        mapping_limits(spec,[0.])
    return spec
