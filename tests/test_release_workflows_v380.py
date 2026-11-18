"""User-visible format and workspace changes in 3.8."""
import pytest


@pytest.mark.parametrize('name', ['job.gbw', 'job.GBW'])
def test_gbw_rejected_without_loading_companion_or_converter(tmp_path, name, monkeypatch):
    from lele.formats import load_document
    from lele.legacy_converter import detect_format, SUPPORTED_SUFFIXES
    source = tmp_path / name
    source.write_bytes(b'opaque ORCA wavefunction')
    source.with_suffix('.out').write_text('O   R   C   A\n')
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('No converter should run'))
    assert '.gbw' not in SUPPORTED_SUFFIXES
    with pytest.raises(ValueError, match='no longer supported'):
        load_document(source)
    with pytest.raises(Exception, match='no longer supported'):
        detect_format(source)


@pytest.mark.parametrize('target', ['gjf', 'xyz', 'cif'])
@pytest.mark.parametrize('name', ['molecule', 'molecule.out', 'molecule.v1'])
def test_structure_export_adds_selected_suffix_and_writes_readable_data(tmp_path, target, name):
    from lele.export_paths import structure_export_path
    from lele.core import Frame
    from lele.formats import export_frame, load_document
    import numpy as np
    frame = Frame(['O', 'H'], [[0, 0, 0], [0, 0, 1]], np.eye(3) * 10, (True, True, True))
    path = structure_export_path(tmp_path / name, target)
    assert path.name == name + '.' + target
    export_frame(frame, path, target)
    loaded = load_document(path).frames[0]
    assert loaded.symbols == frame.symbols
    np.testing.assert_allclose(loaded.positions, frame.positions, atol=1e-6)


def test_suffix_not_duplicated_and_poscar_name_preserved():
    from lele.export_paths import structure_export_path
    assert str(structure_export_path('a.XYZ', 'xyz')) == 'a.XYZ'
    assert str(structure_export_path('POSCAR', 'poscar-direct')) == 'POSCAR'


from test_periodic_fragment_ui_v171 import gui


def test_field_controls_live_in_left_sidebar(gui):
    w = gui.window
    assert 'Field' in [w.sidebar_tabs.tabText(i) for i in range(w.sidebar_tabs.count())]
    assert 'Field' not in [w.bottom_control_tabs.tabText(i) for i in range(w.bottom_control_tabs.count())]
