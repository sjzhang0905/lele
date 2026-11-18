"""Kinematic powder X-ray diffraction from a complete periodic unit cell.

Neutral-atom scattering factors follow the parameterization documented by
pymatgen: f(s) = Z - 41.78214*s²*sum(a_i*exp(-b_i*s²)), s = sin(theta)/lambda.
All reciprocal vectors in the requested sphere are summed, including Friedel
pairs; multiplicity must NOT be multiplied a second time. Occupancies weight
amplitudes. This is a forward simulation, not experimental-data refinement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import math
import numpy as np

from .chemical_analysis import ATOMIC_NUMBERS
from .output_text import check_load_cancelled, load_progress
from .site_occupancy import site_species
from .xrd_scattering import ATOMIC_SCATTERING_PARAMS


@dataclass(frozen=True)
class XRDPeak:
    two_theta: float
    d_spacing: float
    intensity: float
    raw_intensity: float
    hkls: tuple[tuple[int, int, int], ...]

    @property
    def multiplicity(self):
        """Number of reciprocal vectors at this angle, not a symmetry guess."""
        return len(self.hkls)

    @property
    def label(self):
        # Show one representative of each Friedel pair; do not infer a Laue
        # class by sorting absolute Miller indices in a low-symmetry crystal.
        representatives = set()
        for hkl in self.hkls:
            first = next(v for v in hkl if v)
            representatives.add(hkl if first > 0 else tuple(-v for v in hkl))
        return '; '.join(' '.join(map(str, h)) for h in sorted(representatives))


@dataclass
class XRDPattern:
    peaks: list[XRDPeak]
    two_theta: np.ndarray
    intensity: np.ndarray
    wavelength: float
    fwhm: float
    lorentz_polarization: bool
    b_iso: float
    profile: str
    note: str


def atomic_scattering_factor(symbol, s_squared):
    """Neutral atom f0, in electron units; s in inverse angstroms."""
    symbol = 'H' if symbol == 'D' else symbol
    if symbol not in ATOMIC_SCATTERING_PARAMS or symbol not in ATOMIC_NUMBERS:
        raise ValueError(f'No neutral-atom X-ray scattering coefficients for {symbol}.')
    values = np.asarray(s_squared, dtype=float)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError('Scattering-vector squares must be finite and nonnegative.')
    parameters = np.asarray(ATOMIC_SCATTERING_PARAMS[symbol], dtype=float)
    return ATOMIC_NUMBERS[symbol] - 41.78214 * values * np.sum(
        parameters[:, 0] * np.exp(-values[..., None] * parameters[:, 1]), axis=-1)


def _validate_frame(frame):
    if frame is None or not len(frame.symbols):
        raise ValueError('Open a crystal structure containing atoms first.')
    cell = np.asarray(frame.cell, dtype=float)
    if not all(frame.pbc) or abs(np.linalg.det(cell)) < 1e-8:
        raise ValueError('Powder XRD needs a nonzero, three-dimensionally periodic unit cell.')
    if not np.isfinite(cell).all() or not np.isfinite(frame.positions).all():
        raise ValueError('Cell and coordinates must be finite.')
    return cell


def _species_sites(frame, cell):
    fractional = np.asarray(frame.positions) @ np.linalg.inv(cell)
    grouped = {}
    for index in range(len(frame.symbols)):
        species = site_species(frame, index)
        weights = list(species.values())
        if (not all(np.isfinite(v) and v >= 0 for v in weights)
                or math.fsum(weights) > 1.0 + 1e-8):
            raise ValueError(f'Invalid occupancies at atom {index + 1}.')
        for symbol, occupancy in species.items():
            if occupancy == 0:
                continue
            atomic_scattering_factor(symbol, 0.0)  # Fail before enumeration.
            points, occupancies = grouped.setdefault(symbol, ([], []))
            points.append(fractional[index] % 1.0)
            occupancies.append(occupancy)
    if not grouped:
        raise ValueError('The structure contains no occupied atomic sites.')
    return {symbol: (np.asarray(points), np.asarray(occupancies))
            for symbol, (points, occupancies) in grouped.items()}


def simulate_powder_xrd(frame, wavelength=1.54056, two_theta_range=(5., 90.),
                        fwhm=.15, step=.02, lorentz_polarization=True,
                        b_iso=0., profile='Gaussian'):
    """Return normalized sticks and broadened powder intensity.

    Cell rows are lattice vectors in angstroms. The complete unit cell (as
    loaded by LELE) is used, including mixed occupancies and vacancies. A
    uniform isotropic B in angstrom² applies exp(-B*s²) to amplitudes. No
    symmetry expansion or refinement, anomalous scattering, texture or
    instrumental calibration is assumed. Enumeration is bounded in memory
    and cancellable; excessive reciprocal boxes fail explicitly, never truncate.
    """
    cell = _validate_frame(frame)
    lo, hi = map(float, two_theta_range)
    values = [wavelength, lo, hi, fwhm, step, b_iso]
    if not all(np.isfinite(v) for v in values):
        raise ValueError('All XRD parameters must be finite.')
    if wavelength <= 0 or not 0 <= lo < hi < 180:
        raise ValueError('Use a positive wavelength and 0 ≤ minimum < maximum < 180°.')
    if fwhm <= 0 or step <= 0 or b_iso < 0:
        raise ValueError('FWHM and step must be positive; B must be nonnegative.')
    if profile not in ('Gaussian', 'Lorentzian'):
        raise ValueError('Profile must be Gaussian or Lorentzian.')
    count = int(math.ceil((hi - lo) / step)) + 1
    if count > 250_001:
        raise ValueError('Choose a larger angular step (at most 250,001 profile points).')
    grouped = _species_sites(frame, cell)
    g_min = 2 * math.sin(math.radians(lo / 2)) / wavelength
    g_max = 2 * math.sin(math.radians(hi / 2)) / wavelength
    reciprocal = np.linalg.inv(cell).T  # without the 2*pi convention
    # h_i = g dot a_i: valid conservative bounds even for an oblique cell.
    bounds = np.floor(np.linalg.norm(cell, axis=1) * g_max + 1e-10).astype(int)
    candidates = math.prod(int(2 * v + 1) for v in bounds)
    if candidates > 20_000_000:
        raise ValueError('This cell and angle range require over 20 million reciprocal candidates. '
                         'Use a smaller primitive cell, a longer wavelength, or a narrower angle range.')
    k, l = np.meshgrid(np.arange(-bounds[1], bounds[1] + 1),
                       np.arange(-bounds[2], bounds[2] + 1), indexing='ij')
    kl = np.column_stack((k.ravel(), l.ravel()))
    rows = []
    report = load_progress('Calculating powder XRD reflections', int(2 * bounds[0] + 1))
    for ih, h in enumerate(range(-int(bounds[0]), int(bounds[0]) + 1)):
        check_load_cancelled()
        report(ih)
        hkls = np.column_stack((np.full(len(kl), h), kl))
        norms = np.linalg.norm(hkls @ reciprocal, axis=1)
        keep = (norms > 1e-10) & (norms >= g_min - 1e-10) & (norms <= g_max + 1e-10)
        hkls, norms = hkls[keep], norms[keep]
        for start in range(0, len(hkls), 512):
            check_load_cancelled()
            indices, g = hkls[start:start + 512], norms[start:start + 512]
            s2 = (g / 2) ** 2
            structure_factor = np.zeros(len(g), dtype=complex)
            for symbol, (points, occupations) in grouped.items():
                amplitude = np.zeros(len(g), dtype=complex)
                for atom in range(0, len(points), 512):
                    check_load_cancelled()
                    phase = np.exp(2j * np.pi * (indices @ points[atom:atom + 512].T))
                    amplitude += phase @ occupations[atom:atom + 512]
                structure_factor += atomic_scattering_factor(symbol, s2) * amplitude
            structure_factor *= np.exp(-b_iso * s2)
            intensities = np.abs(structure_factor) ** 2
            theta = np.arcsin(np.clip(wavelength * g / 2, 0, 1))
            if lorentz_polarization:
                intensities *= (1 + np.cos(2 * theta) ** 2) / (np.sin(theta) ** 2 * np.cos(theta))
            angles = np.degrees(2 * theta)
            for angle, length, intensity, hkl in zip(angles, g, intensities, indices):
                if intensity > 1e-16:
                    rows.append((float(angle), float(1 / length), float(intensity), tuple(map(int, hkl))))
    report(int(2 * bounds[0] + 1))
    rows.sort(key=lambda row: row[0])
    combined = []
    for angle, spacing, intensity, hkl in rows:
        if combined and abs(angle - combined[-1][0]) < 1e-5:
            combined[-1][2] += intensity
            combined[-1][3].append(hkl)
        else:
            combined.append([angle, spacing, intensity, [hkl]])
    maximum = max((p[2] for p in combined), default=0.)
    peaks = [XRDPeak(angle, spacing, intensity / maximum * 100, intensity, tuple(hkls))
             for angle, spacing, intensity, hkls in combined
             if maximum > 0 and intensity / maximum > 1e-8]
    x = np.linspace(lo, hi, count)
    y = np.zeros(count)
    for index, peak in enumerate(peaks):
        if index % 128 == 0:
            check_load_cancelled()
        offset = (x - peak.two_theta) / fwhm
        # Profiles have equal area per unit stick intensity. A common FWHM
        # makes the omitted common area multiplier irrelevant after scaling.
        y += peak.intensity * (np.exp(-4 * np.log(2) * offset ** 2)
                               if profile == 'Gaussian' else 1 / (1 + 4 * offset ** 2))
    if y.size and y.max() > 0:
        y *= 100 / y.max()
    note = ('Kinematic powder simulation; neutral-atom scattering factors and site occupancies. '
            'Single wavelength; no anomalous scattering, preferred orientation or Rietveld refinement. '
            'The complete current unit cell is used; a vacuum slab is treated as an artificial 3D crystal. '
            'B is one user-specified isotropic factor; CIF displacement tensors are not imported.')
    return XRDPattern(peaks, x, y, float(wavelength), float(fwhm), bool(lorentz_polarization),
                      float(b_iso), profile, note)


def export_pattern_csv(pattern, path, *, reflections=False):
    path = Path(path)
    if path.suffix.lower() != '.csv':
        path = Path(str(path) + '.csv')
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        if reflections:
            writer.writerow(['two_theta_deg', 'd_angstrom', 'relative_intensity',
                             'raw_intensity_arbitrary', 'reciprocal_vector_count', 'hkl_Friedel_representatives'])
            for peak in pattern.peaks:
                writer.writerow([f'{peak.two_theta:.10g}', f'{peak.d_spacing:.10g}',
                                 f'{peak.intensity:.10g}', f'{peak.raw_intensity:.12g}',
                                 peak.multiplicity, peak.label])
        else:
            writer.writerow(['two_theta_deg', 'relative_intensity'])
            writer.writerows(zip(pattern.two_theta, pattern.intensity))
    return path
