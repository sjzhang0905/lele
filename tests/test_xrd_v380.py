"""Analytical powder-XRD geometry, extinction, occupancy and export checks."""
import csv
import math
import numpy as np
import pytest

from lele.core import Frame
from lele.xrd import atomic_scattering_factor, export_pattern_csv, simulate_powder_xrd


def crystal(symbols, fractions, cell=4.):
    matrix = np.eye(3) * cell if np.ndim(cell) == 0 else np.asarray(cell)
    return Frame(symbols, np.asarray(fractions) @ matrix, matrix, (True, True, True))


def test_simple_cubic_bragg_positions_and_multiplicity():
    frame = crystal(['Si'], [[0, 0, 0]])
    pattern = simulate_powder_xrd(frame, two_theta_range=(0, 70), lorentz_polarization=False)
    first, second = pattern.peaks[:2]
    assert first.two_theta == pytest.approx(math.degrees(2 * math.asin(1.54056 / 8)))
    assert first.d_spacing == pytest.approx(4)
    assert first.multiplicity == 6
    assert second.d_spacing == pytest.approx(4 / math.sqrt(2))
    assert second.multiplicity == 12
    # Explicit enumeration already contains equivalent vectors: no second m.
    factor = atomic_scattering_factor('Si', 1 / 64)
    assert first.raw_intensity == pytest.approx(6 * factor ** 2)
    assert pattern.intensity.max() == pytest.approx(100)


def test_bcc_extinctions_and_diamond_silicon_reference_angles():
    bcc = crystal(['Fe', 'Fe'], [[0, 0, 0], [.5, .5, .5]], 2.866)
    pattern = simulate_powder_xrd(bcc, two_theta_range=(0, 90))
    assert all(sum(hkl) % 2 == 0 for peak in pattern.peaks for hkl in peak.hkls)
    assert pattern.peaks[0].d_spacing == pytest.approx(2.866 / np.sqrt(2))
    fractions = [[0, 0, 0], [0, .5, .5], [.5, 0, .5], [.5, .5, 0],
                 [.25, .25, .25], [.25, .75, .75], [.75, .25, .75], [.75, .75, .25]]
    si = crystal(['Si'] * 8, fractions, 5.431)
    result = simulate_powder_xrd(si)
    assert [p.two_theta for p in result.peaks[:3]] == pytest.approx([28.44, 47.30, 56.12], abs=.01)
    assert [p.multiplicity for p in result.peaks[:3]] == [8, 12, 24]
    assert not any((2, 0, 0) in p.hkls for p in result.peaks)


def test_occupancy_weights_amplitudes_not_intensities():
    full = crystal(['C'], [[0, 0, 0]])
    partial = crystal(['C'], [[0, 0, 0]])
    partial.info['site_occupancies'] = [{'C': .5}]
    mixed = crystal(['C'], [[0, 0, 0]])
    mixed.info['site_occupancies'] = [{'C': .25, 'Si': .5}]
    kwargs = dict(two_theta_range=(0, 30), lorentz_polarization=False)
    first = simulate_powder_xrd(full, **kwargs).peaks[0]
    half = simulate_powder_xrd(partial, **kwargs).peaks[0]
    blend = simulate_powder_xrd(mixed, **kwargs).peaks[0]
    assert half.raw_intensity == pytest.approx(first.raw_intensity * .25)
    amplitude = .25 * atomic_scattering_factor('C', 1 / 64) + .5 * atomic_scattering_factor('Si', 1 / 64)
    assert blend.raw_intensity == pytest.approx(6 * amplitude ** 2)


def test_oblique_cell_and_rigid_rotation_translation_invariance():
    cell = [[3.1, .2, 0], [.5, 4.2, .1], [.3, .7, 5.3]]
    frame = crystal(['Na', 'Cl'], [[.13, .27, .4], [.61, .72, .86]], cell)
    angle = .37
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                         [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    moved = Frame(frame.symbols, frame.positions @ rotation + [8.1, -4, 2],
                  frame.cell @ rotation, frame.pbc)
    result = simulate_powder_xrd(frame, two_theta_range=(5, 55))
    other = simulate_powder_xrd(moved, two_theta_range=(5, 55))
    assert [p.two_theta for p in result.peaks] == pytest.approx([p.two_theta for p in other.peaks])
    assert [p.raw_intensity for p in result.peaks] == pytest.approx([p.raw_intensity for p in other.peaks])
    for peak in result.peaks:
        for hkl in peak.hkls:
            assert peak.d_spacing == pytest.approx(1 / np.linalg.norm(np.array(hkl) @ np.linalg.inv(cell).T))


def test_uniform_b_factor_and_lp_apply_once():
    frame = crystal(['Cu'], [[0, 0, 0]])
    base = simulate_powder_xrd(frame, lorentz_polarization=False, b_iso=0).peaks[0]
    damped = simulate_powder_xrd(frame, lorentz_polarization=False, b_iso=2).peaks[0]
    corrected = simulate_powder_xrd(frame, lorentz_polarization=True, b_iso=0).peaks[0]
    s2 = 1 / (4 * base.d_spacing ** 2)
    assert damped.raw_intensity / base.raw_intensity == pytest.approx(np.exp(-4 * s2))
    theta = np.radians(base.two_theta / 2)
    assert corrected.raw_intensity / base.raw_intensity == pytest.approx(
        (1 + np.cos(2 * theta) ** 2) / (np.sin(theta) ** 2 * np.cos(theta)))


def test_profiles_csv_and_zero_angle_handling(tmp_path):
    frame = crystal(['Si'], [[0, 0, 0]])
    result = simulate_powder_xrd(frame, two_theta_range=(0, 40), profile='Lorentzian')
    assert np.isfinite(result.intensity).all()
    path = export_pattern_csv(result, tmp_path / 'curve')
    assert path.name == 'curve.csv'
    with path.open(encoding='utf-8-sig') as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == len(result.two_theta) + 1
    table = export_pattern_csv(result, tmp_path / 'peaks.csv', reflections=True)
    with table.open(encoding='utf-8-sig') as stream:
        rows = list(csv.reader(stream))
    assert len(rows) == len(result.peaks) + 1
    assert int(rows[1][4]) == 6


def test_scattering_factors_and_invalid_inputs():
    assert atomic_scattering_factor('Si', 0) == 14
    assert 0 < atomic_scattering_factor('Si', 1.) < 14
    frame = crystal(['Si'], [[0, 0, 0]])
    with pytest.raises(ValueError, match='coefficients'):
        atomic_scattering_factor('Og', .1)
    for kwargs in ({'wavelength': 0}, {'two_theta_range': (90, 10)},
                   {'fwhm': 0}, {'b_iso': -1}, {'step': np.nan}):
        with pytest.raises(ValueError):
            simulate_powder_xrd(frame, **kwargs)
    frame.pbc = (True, True, False)
    with pytest.raises(ValueError, match='three-dimensionally'):
        simulate_powder_xrd(frame)


def test_cancellation_and_input_frame_unchanged():
    from lele.output_text import LoadCancelled, output_read_session
    frame = crystal(['C'], [[1.1, -.2, .3]])
    initial = frame.positions.copy()
    simulate_powder_xrd(frame)
    assert np.array_equal(frame.positions, initial)
    with pytest.raises(LoadCancelled), output_read_session(cancelled=lambda: True):
        simulate_powder_xrd(frame)
