"""STM contrast from a VASP partial density; independent of GUI/rendering.

Constant height samples the partial density; constant current finds its first
isosurface from the vacuum toward the selected slab surface.  The latter is
an iso-density approximation, not an absolute tunnelling-current calculation.
Sampling follows the *normal* to the selected lattice plane, even for a skew
third lattice vector.  Input Volume values already have units e/Å³.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
import numpy as np

from .output_text import check_load_cancelled, load_progress


@dataclass
class SlabGeometry:
    cell: np.ndarray
    axis: int
    lateral: tuple
    normal: np.ndarray
    u: np.ndarray
    v: np.ndarray
    period: float
    lower: float
    upper: float
    vacuum: float


@dataclass
class STMMap:
    x: np.ndarray
    y: np.ndarray
    values: np.ndarray
    mode: str
    unit: str
    normal: np.ndarray
    parameters: dict

    @property
    def valid_fraction(self):
        return float(np.isfinite(self.values).mean())


def can_simulate_stm(document):
    """Require PARCHG provenance recorded by the VASP reader.

    Inspecting a filename alone could accept a converted CUBE or a document
    renamed after loading another scalar field. Projects preserve format_name.
    """
    return bool(document is not None and document.frames and document.volumes
                and document.format_name == 'VASP PARCHG')


def slab_geometry(frame, axis=2):
    """Unwrap the slab across its largest atom-free periodic gap.

    lower/upper are signed normal distances from the cell origin, possibly
    outside the original cell. This avoids selecting the wrong surface when
    the slab crosses a periodic boundary.
    """
    if axis not in (0, 1, 2):
        raise ValueError('Surface axis must be a, b or c.')
    cell = np.asarray(frame.cell, dtype=float)
    if abs(np.linalg.det(cell)) < 1e-10 or not len(frame.positions):
        raise ValueError('STM needs a nonzero periodic cell and atomic coordinates.')
    lateral = tuple(i for i in range(3) if i != axis)
    a, b = cell[list(lateral)]
    normal = np.cross(a, b)
    normal /= np.linalg.norm(normal)
    if np.dot(normal, cell[axis]) < 0:
        normal = -normal
    period = float(np.dot(cell[axis], normal))
    u = a / np.linalg.norm(a)
    v = b - np.dot(b, u)*u
    v /= np.linalg.norm(v)
    fractions = np.sort(np.mod(frame.positions @ np.linalg.inv(cell), 1.)[:, axis])
    gaps = np.diff(np.r_[fractions, fractions[0] + 1.])
    gap_index = int(np.argmax(gaps))
    start = fractions[(gap_index + 1) % len(fractions)]
    unwrapped = start + np.mod(fractions - start, 1.)
    lower, upper = float(unwrapped.min()*period), float(unwrapped.max()*period)
    vacuum = float(gaps[gap_index]*period)
    if vacuum < 1.0:
        raise ValueError('No clear vacuum gap (at least 1 Å) along this surface normal. Choose another plane.')
    return SlabGeometry(cell, axis, lateral, normal, u, v, period, lower, upper, vacuum)


def partial_density(document, spin='total'):
    """Select total or collinear spin density without changing the source."""
    if not can_simulate_stm(document):
        raise ValueError('Load a VASP PARCHG* file with a complete partial-density grid first.')
    if spin not in ('total', 'up', 'down'):
        raise ValueError('Choose total, up or down spin density.')
    fields = document.volumes
    data = fields[0].data
    if spin != 'total':
        if len(fields) != 2:
            raise ValueError('Separate up/down densities require a collinear two-channel PARCHG file.')
        if (fields[1].data.shape != data.shape or
                not np.allclose(fields[0].voxel_vectors, fields[1].voxel_vectors) or
                not np.allclose(fields[0].origin, fields[1].origin)):
            raise ValueError('Spin density grids are incompatible.')
        data = (data + (1 if spin == 'up' else -1)*fields[1].data)*.5
    # Tiny negative numerical noise is harmless; a signed/difference density
    # is not a physical integrated LDOS and must not masquerade as STM.
    if not np.isfinite(data).all():
        raise ValueError('STM requires a finite partial-density grid.')
    minimum, maximum = float(np.min(data)), float(np.max(data))
    if maximum <= 0 or minimum < -max(1e-8, maximum*1e-5):
        raise ValueError('STM requires a nonnegative partial density, not a signed difference field.')
    return np.maximum(data, 0.) if minimum < 0 else data


def _surface_grid(geometry, shape, repeat):
    repeat = tuple(int(n) for n in repeat)
    if len(repeat) != 2 or min(repeat) < 1 or max(repeat) > 12:
        raise ValueError('In-plane repeats must be between 1 and 12.')
    nx, ny = (int(shape[i]) for i in geometry.lateral)
    if nx*ny*repeat[0]*repeat[1] > 4_000_000:
        raise ValueError('STM image exceeds 4 million samples; reduce the repeats.')
    fi, fj = np.meshgrid(np.arange(nx*repeat[0])/nx,
                         np.arange(ny*repeat[1])/ny, indexing='ij')
    a, b = geometry.cell[list(geometry.lateral)]
    base = fi[..., None]*a + fj[..., None]*b
    return base, base @ geometry.u, base @ geometry.v


def simulate_stm(document, *, mode='height', axis=2, side=1, height=2.,
                 setpoint=1e-4, spin='total', repeat=(1, 1), smoothing=0.,
                 minimum_height=0., scan_step=None):
    """Calculate an STM map, preserving all source arrays.

    Height and minimum_height are outward Å from the outermost atom.
    Constant-current search starts at the center of the largest vacuum gap.
    Unbracketed pixels are NaN, never fabricated surface heights.
    smoothing is Gaussian sigma in grid points, applied periodically to the
    source density before either operation; zero leaves the density intact.
    """
    from scipy.ndimage import map_coordinates, gaussian_filter
    data = partial_density(document, spin)
    if mode not in ('height', 'current') or side not in (-1, 1):
        raise ValueError('Invalid STM mode or surface side.')
    if not np.isfinite([height, setpoint, smoothing, minimum_height]).all():
        raise ValueError('STM settings must be finite numbers.')
    if smoothing < 0 or smoothing > 10 or minimum_height < 0:
        raise ValueError('Smoothing must be 0–10 grid points and minimum height must be nonnegative.')
    if not 0 <= height or setpoint <= 0:
        raise ValueError('Tip height must be nonnegative and density setpoint must be positive.')
    geometry = slab_geometry(document.frames[0], axis)
    volume = document.volumes[0]
    source_cell = volume.voxel_vectors * np.asarray(data.shape)[:, None]
    if not volume.periodic or not np.allclose(source_cell, geometry.cell, rtol=1e-5, atol=1e-7):
        raise ValueError('The partial-density grid must match the current periodic structure cell.')
    half_gap = geometry.vacuum*.5
    if mode == 'height' and height >= half_gap:
        raise ValueError(f'Tip height must be below the vacuum midpoint ({half_gap:.4g} Å above this surface).')
    if mode == 'current' and minimum_height >= half_gap:
        raise ValueError('Minimum scan height must be below the vacuum midpoint.')
    if smoothing:
        check_load_cancelled()
        data = gaussian_filter(data, smoothing, mode='wrap')
    base, x, y = _surface_grid(geometry, data.shape, repeat)
    inv_voxels = np.linalg.inv(volume.voxel_vectors)
    base_indices = (base - volume.origin) @ inv_voxels
    normal_indices = geometry.normal @ inv_voxels
    surface = geometry.upper if side == 1 else geometry.lower

    def sample(distance):
        check_load_cancelled()
        coords = base_indices + (surface + side*distance)*normal_indices
        return map_coordinates(data, np.moveaxis(coords, -1, 0), order=1,
                               mode='grid-wrap', prefilter=False)

    parameters = dict(axis=axis, side=side, height=height, setpoint=setpoint,
        spin=spin, repeat=tuple(repeat), smoothing=smoothing,
        minimum_height=minimum_height, vacuum_gap=geometry.vacuum,
        surface_normal_position=surface)
    if mode == 'height':
        values = sample(height)
        unit = 'e/Å³'
    else:
        # A true normal can cross lateral voxel planes much faster than it
        # crosses the selected axial planes when the cell is strongly skewed.
        # Bound *every* grid-coordinate increment by half a voxel; using only
        # the axial spacing can alias narrow lateral density lobes completely.
        step = .5/float(np.max(np.abs(normal_indices))) if scan_step is None else float(scan_step)
        if not np.isfinite(step) or step <= 0:
            raise ValueError('Scan step must be a positive finite distance.')
        count = int(np.ceil((half_gap - minimum_height)/step)) + 1
        if count > 20000:
            raise ValueError('Scan requires more than 20,000 planes; increase the scan step.')
        distances = np.linspace(half_gap, minimum_height, max(2, count))
        values = np.full(x.shape, np.nan)
        previous = sample(distances[0])
        # Vacuum must be below the setpoint: otherwise the outer crossing
        # lies outside this unambiguous half-gap and cannot be determined.
        active = previous < setpoint
        report = load_progress('Scanning STM isodensity', len(distances)-1)
        for i, distance in enumerate(distances[1:], 1):
            current = sample(distance)
            crossed = active & (current >= setpoint) & (current > previous)
            if np.any(crossed):
                fraction = (setpoint-previous[crossed])/(current[crossed]-previous[crossed])
                values[crossed] = distances[i-1] + fraction*(distance-distances[i-1])
                active[crossed] = False
            previous = current
            report(i)
            if not active.any():
                break
        unit = 'Å above outermost atom'
        parameters['scan_step'] = float(distances[0]-distances[1])
    return STMMap(x, y, values, mode, unit, geometry.normal, parameters)


def export_stm_csv(result, path):
    """Export exact computed samples (NaN denotes no bracketed crossing)."""
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        stream.write('# STM mode: ' + result.mode + '\n')
        for key, value in result.parameters.items():
            stream.write(f'# {key}: {value}\n')
        writer = csv.writer(stream)
        writer.writerow(['u_A', 'v_A', 'density_e_per_A3' if result.mode == 'height' else 'height_above_surface_A'])
        for i in range(result.values.shape[0]):
            check_load_cancelled()
            for j in range(result.values.shape[1]):
                writer.writerow([f'{result.x[i,j]:.10g}', f'{result.y[i,j]:.10g}', f'{result.values[i,j]:.10g}'])
