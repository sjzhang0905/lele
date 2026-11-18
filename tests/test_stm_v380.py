from pathlib import Path
import numpy as np
import pytest
from lele.core import Frame, Volume, Document
from lele.stm import (can_simulate_stm, slab_geometry, partial_density,
                      simulate_stm, export_stm_csv)
from lele.vasp_volume_detection import named_vasp_volume_kind


def slab(shape=(8, 8, 100), cell=None, z=(2., 4.)):
    cell = np.diag([4., 4., 10.]) if cell is None else np.asarray(cell, float)
    fractions = np.indices(shape).transpose(1, 2, 3, 0)/np.asarray(shape)
    normal_z = fractions[..., 2]*10
    distance = np.abs((normal_z-3+5) % 10-5)
    data = np.exp(-distance).astype(np.float32)
    frame = Frame(['H']*len(z), [[0., 0., value] for value in z], cell, (True,)*3)
    field = Volume(data, np.zeros(3), cell/np.asarray(shape)[:, None],
                   'Partial charge density', 'e/Å³', True)
    return Document(Path('PARCHG+0.3'), 'VASP PARCHG', [frame], field)


@pytest.mark.parametrize('name', ['PARCHG', 'PARCHG+0.3', 'PARCHG-0.3',
    'PARCHG.0001.ALLK', 'parchg_bias', 'PARCHGcopy'])
def test_parchg_prefix_kind(name):
    assert named_vasp_volume_kind(name) == 'PARCHG'


def test_constant_height_and_first_current_crossing():
    doc = slab()
    height = simulate_stm(doc, height=2.)
    np.testing.assert_allclose(height.values, np.exp(-3), rtol=2e-6)
    current = simulate_stm(doc, mode='current', setpoint=np.exp(-3))
    assert current.valid_fraction == 1.
    np.testing.assert_allclose(current.values, 2., atol=1e-6)
    lower = simulate_stm(doc, mode='current', side=-1, setpoint=np.exp(-3))
    np.testing.assert_allclose(lower.values, 2., atol=1e-6)
    assert height.unit == 'e/Å³'


def test_unbracketed_current_is_nan_not_fake_height():
    doc = slab()
    too_high = simulate_stm(doc, mode='current', setpoint=20.)
    too_low = simulate_stm(doc, mode='current', setpoint=1e-8)
    assert np.isnan(too_high.values).all()
    assert np.isnan(too_low.values).all()
    clipped = simulate_stm(doc, mode='current', setpoint=np.exp(-3), minimum_height=3.)
    assert np.isnan(clipped.values).all()


def test_multiple_crossings_chooses_outermost():
    doc = slab()
    z = np.arange(100)*.1
    # Two lobes in the vacuum: first entry must select the outer one at z≈7.2.
    values = np.exp(-((z-7)/.2)**2) + np.exp(-((z-5)/.2)**2)
    doc.volume.data[:] = values
    result = simulate_stm(doc, mode='current', setpoint=np.exp(-1))
    np.testing.assert_allclose(result.values, 3.2, atol=1e-6)


def test_skew_third_vector_scans_normal_without_lateral_drift():
    doc = slab((4, 4, 10), [[4, 0, 0], [1, 4, 0], [2, 0, 10]])
    ix, _, iz = np.indices(doc.volume.data.shape)
    doc.volume.data[:] = 1 + ix + .1*iz
    result = simulate_stm(doc, height=1.)
    # z=5: skew c displaces the grid by x=1. Fixed physical x therefore
    # samples the previous periodic x voxel, not the same fractional column.
    np.testing.assert_allclose(result.values[:, 0], [4.5, 1.5, 2.5, 3.5])
    np.testing.assert_allclose(result.normal, [0, 0, 1])
    assert result.x[0, 1] == pytest.approx(.25)
    assert result.y[0, 1] == pytest.approx(1.)


def test_strong_skew_scan_resolves_lateral_voxels_and_outer_crossing():
    doc = slab((32, 4, 10), [[4, 0, 0], [0, 4, 0], [80, 0, 10]])
    ix, _, _ = np.indices(doc.volume.data.shape)
    doc.volume.data[:] = np.minimum(ix, 32-ix)/16.
    # Along the normal, lateral grid index changes 64 voxels/Å. At u=0
    # the vacuum starts at index 0; rho=.5 is first reached at index 8,
    # exactly .125 Å inward. An axial-only .5 Å step aliases the whole
    # triangular lobe and would falsely report no crossing.
    result = simulate_stm(doc, mode='current', setpoint=.5)
    np.testing.assert_allclose(result.values[0], 4.-.125, atol=1e-6)
    assert result.parameters['scan_step'] <= .5/64 + 1e-10


def test_periodic_slab_crossing_boundary_is_unwrapped():
    doc = slab(z=(9., 1.))
    geometry = slab_geometry(doc.frames[0])
    assert geometry.lower == pytest.approx(9.)
    assert geometry.upper == pytest.approx(11.)
    assert geometry.vacuum == pytest.approx(8.)


def test_spin_reconstruction_and_source_immutability():
    doc = slab()
    magnetization = Volume(doc.volume.data*.2, np.zeros(3), doc.volume.voxel_vectors,
                           'Magnetization density', 'e/Å³', True)
    doc.volumes.append(magnetization)
    original = doc.volume.data.copy()
    np.testing.assert_allclose(partial_density(doc, 'up'), original*.6, rtol=2e-7)
    np.testing.assert_allclose(partial_density(doc, 'down'), original*.4, rtol=2e-7)
    simulate_stm(doc, smoothing=.5, repeat=(2, 1), spin='down')
    np.testing.assert_array_equal(doc.volume.data, original)


def test_invalid_inputs_and_unknown_current_units():
    doc = slab()
    doc.format_name = 'Gaussian CUBE'
    assert not can_simulate_stm(doc)  # A PARCHG-named converted CUBE has different units.
    doc.format_name = 'VASP LOCPOT'
    assert not can_simulate_stm(doc)  # A renamed potential is not a partial density.
    doc.format_name = 'VASP CHGCAR'
    assert not can_simulate_stm(doc)  # Total density does not encode an energy window.
    doc.format_name = 'VASP PARCHG'
    with pytest.raises(ValueError, match='vacuum midpoint'):
        simulate_stm(doc, height=5.)
    with pytest.raises(ValueError, match='positive'):
        simulate_stm(doc, mode='current', setpoint=0.)
    with pytest.raises(ValueError, match='two-channel'):
        simulate_stm(doc, spin='up')
    doc.volume.data[0, 0, 0] = -1.
    with pytest.raises(ValueError, match='nonnegative'):
        simulate_stm(doc)
    doc.path = Path('LOCPOT')
    doc.format_name = 'VASP LOCPOT'
    assert not can_simulate_stm(doc)


def test_repeat_export_and_normalization(tmp_path):
    doc = slab()
    result = simulate_stm(doc, repeat=(2, 3))
    assert result.values.shape == (16, 24)
    np.testing.assert_allclose(result.values[:8], result.values[8:])
    path = tmp_path/'stm.csv'
    export_stm_csv(result, path)
    assert 'density_e_per_A3' in path.read_text()
    assert '# spin: total' in path.read_text()
    # Existing VASP reader must retain the electron-count integral:
    # rho = raw / cell_volume, not raw / (grid_size * cell_volume).
    from test_volumetric_readers_v320 import vasp_text
    from lele.formats import load_document
    source = tmp_path/'PARCHG+0.3'
    source.write_text(vasp_text([24.]*8))
    loaded = load_document(source)
    assert loaded.format_name == 'VASP PARCHG'
    np.testing.assert_allclose(loaded.volume.data, 1.)
    assert loaded.volume.label == 'Partial charge density'
    assert can_simulate_stm(loaded)


def test_stm_dialog_mode_controls_and_plot():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from lele.stm_dialog import STMDialog
    app = QApplication.instance() or QApplication([])
    dialog = STMDialog(slab())
    try:
        assert dialog.result.mode == 'height'
        dialog.mode.setCurrentIndex(1)
        assert not dialog.height.isEnabled() and dialog.setpoint.isEnabled()
        dialog.setpoint.setText(str(np.exp(-3)))
        dialog.calculate()
        assert dialog.result.mode == 'current' and dialog.result.valid_fraction == 1.
        np.testing.assert_allclose(dialog.result.values, 2., atol=1e-6)
        assert dialog.save_image.isEnabled() and dialog.save_data.isEnabled()
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
