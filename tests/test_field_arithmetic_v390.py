"""Physical units, grid identity, transactions and persistent derived fields."""
from pathlib import Path
import json
import zipfile
from unittest.mock import patch
import numpy as np
import pytest
from ase.units import Bohr, Hartree
from lele.core import Document, Frame, Volume
from lele.field_arithmetic import (FieldTerm, combine_fields, append_field_result,
                                   unit_spec)
from lele.output_text import output_read_session, LoadCancelled
from test_periodic_fragment_ui_v171 import gui


def document(value=1., *, unit='e/Å³', name='CHGCAR', shape=(4, 5, 6), symbols=None,
             periodic=True):
    basis = np.array([[.3, 0, 0], [.1, .4, 0], [.02, .03, .5]])
    symbols = ['H'] if symbols is None else symbols
    frame = Frame(symbols, np.zeros((len(symbols), 3)), basis*np.asarray(shape)[:, None], (periodic,)*3)
    data = np.full(shape, value, dtype=np.float32)
    volume = Volume(data, [.12, .23, .34], basis, 'Density', unit, periodic)
    return Document(Path(name), 'Test', [frame], volume)


def test_signed_addition_different_fragments_and_no_source_mutation():
    a, b, c = document(8., symbols=['C', 'H']), document(3.), document(2., symbols=['C'])
    a.frames[0].energy_ev = -123.4
    original = [d.volume.data.copy() for d in (a, b, c)]
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0), FieldTerm(c, 0, -1)])
    np.testing.assert_array_equal(result.data, 9.)
    assert result.provenance['formula'] == 'A + B − C'
    assert result.label.startswith('Density arithmetic')
    assert result.unit == 'e/Å³'
    assert a.volume is a.volumes[0] and len(a.volumes) == 1
    for before, doc in zip(original, (a, b, c)):
        np.testing.assert_array_equal(before, doc.volume.data)
        assert not np.shares_memory(result.data, doc.volume.data)
    append_field_result(a, result, expected_active=a.volume)
    assert a.volume is result and len(a.volumes) == 2
    assert a.frames[0].symbols == ['C', 'H']
    assert a.frames[0].energy_ev == -123.4 and not a.modified


@pytest.mark.parametrize('first,second,value,expected', [
    ('e/Å³', 'e/Bohr³', Bohr**3, 2.),
    ('e/Bohr³', 'e/Å³', 1/Bohr**3, 2.),
    ('eV', 'Hartree', 1/Hartree, 2.),
    ('Hartree', 'eV', Hartree, 2.),
    ('Å⁻³ᐟ²', 'Bohr⁻³ᐟ²', Bohr**1.5, 2.),
])
def test_explicit_compatible_unit_conversion(first, second, value, expected):
    a, b = document(unit=first), document(value, unit=second)
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    np.testing.assert_allclose(result.data, expected, rtol=2e-7)
    assert result.unit == first
    assert result.provenance['terms'][1]['conversion_factor'] != 1


@pytest.mark.parametrize('unit', ['eV', 'Å⁻³ᐟ²', 'dimensionless'])
def test_incompatible_quantities_are_rejected(unit):
    a, b = document(), document(unit=unit)
    with pytest.raises(ValueError, match='incompatible physical units'):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    assert len(a.volumes) == 1


def test_unknown_units_require_declaration_and_known_units_cannot_be_relabeled():
    a, b = document(), document(unit='source units')
    with pytest.raises(ValueError, match='Unknown scalar units'):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0, -1, 'e/Å³')])
    np.testing.assert_array_equal(result.data, 0.)
    assert result.provenance['terms'][1]['declared_unit'] == 'e/Å³'
    assert b.volume.unit == 'source units'
    with pytest.raises(ValueError, match='cannot be relabeled'):
        combine_fields([FieldTerm(a, 0, declared_unit='eV'), FieldTerm(b, 0, declared_unit='eV')])
    with pytest.raises(ValueError):
        unit_spec('a.u.')


@pytest.mark.parametrize('change,message', [
    ('shape', 'grid shape'), ('origin', 'grid origin'), ('basis', 'voxel vectors'),
    ('periodic', 'periodicity'), ('cell', 'structure cell'), ('detached', 'detached'),
])
def test_grid_and_cell_mismatches_are_rejected(change, message):
    a, b = document(), document()
    if change == 'shape':
        b = document(shape=(4, 5, 7))
    elif change == 'origin':
        b.volume.origin[0] += .01
    elif change == 'basis':
        b.volume.voxel_vectors[0, 0] += .01
    elif change == 'periodic':
        b.volume.periodic = False
    elif change == 'cell':
        b.frames[0].cell[0, 0] += .01
    elif change == 'detached':
        b.volume = None
    with pytest.raises(ValueError, match=message):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    assert len(a.volumes) == 1


def test_transformed_inactive_channels_and_result_switching():
    from lele.field_actions import select_field
    a = document(3.)
    original = a.volume
    b = Volume(np.full(original.data.shape, 2.), original.origin.copy(), original.voxel_vectors.copy(),
               'Other', original.unit, True)
    a.volumes.append(b)
    rotation = np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1.]])
    shift = np.array([2., -1., .7])
    a.volume.origin = a.volume.origin@rotation + shift
    a.volume.voxel_vectors = a.volume.voxel_vectors@rotation
    a.frames[0].positions = a.frames[0].positions@rotation + shift
    a.frames[0].cell = a.frames[0].cell@rotation
    result = combine_fields([FieldTerm(a, 0), FieldTerm(a, 1, -1)], target_frame=a.frames[0])
    np.testing.assert_array_equal(result.data, 1.)
    np.testing.assert_allclose(result.origin, original.origin)
    append_field_result(a, result, expected_active=original)
    before = result.origin.copy(), result.voxel_vectors.copy()
    select_field(a, 1)
    select_field(a, 2)
    np.testing.assert_allclose(result.origin, before[0])
    np.testing.assert_allclose(result.voxel_vectors, before[1])


def test_float64_accumulation_and_fortran_input_order():
    a, b, c = document(1e8), document(1.), document(1e8)
    b.volume.data = np.asfortranarray(np.arange(120, dtype=np.float32).reshape(4, 5, 6))
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0), FieldTerm(c, 0, -1)], chunk_size=17)
    np.testing.assert_array_equal(result.data, b.volume.data)


def test_cancellation_and_nonfinite_failure_are_transactional():
    a, b = document(), document()
    active = a.volume
    calls = 0
    def cancelled():
        nonlocal calls
        calls += 1
        return calls > 7
    with pytest.raises(LoadCancelled), output_read_session(cancelled=cancelled):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)], chunk_size=5)
    assert a.volume is active and len(a.volumes) == 1
    np.testing.assert_array_equal(active.data, 1.)
    b.volume.data.flat[-1] = np.nan
    with pytest.raises(ValueError, match='nonfinite'):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)], chunk_size=5)
    assert a.volume is active and len(a.volumes) == 1


def test_overflow_and_stale_commit_are_rejected():
    a, b = document(np.finfo(np.float32).max), document(np.finfo(np.float32).max)
    with pytest.raises(ValueError, match='float32'):
        combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    a, b = document(), document()
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0)])
    active = a.volume
    a.volume = None
    with pytest.raises(ValueError, match='changed'):
        append_field_result(a, result, expected_active=active)
    assert len(a.volumes) == 1


def test_project_cube_and_field_import_preserve_values_geometry_and_provenance(tmp_path):
    from lele.project_file import save_project, load_project
    from lele.field_export import export_active_cube
    from lele.volumetric_input import read_cube_document
    from lele.field_mapping import prepare_field_attachment
    from test_field_projects_v320 import state_for
    a, b = document(3.), document(1.)
    result = combine_fields([FieldTerm(a, 0), FieldTerm(b, 0, -1)])
    append_field_result(a, result, expected_active=a.volume)
    project = tmp_path/'derived.lele'
    save_project(project, state_for(a))
    # Source files do not exist. The project must contain actual result bytes.
    restored = load_project(project)['documents'][0]['document']
    np.testing.assert_array_equal(restored.volume.data, 2.)
    assert restored.volume is restored.volumes[1]
    assert restored.volume.provenance == result.provenance
    cube = tmp_path/'derived.cube'
    export_active_cube(cube, a, a.frames[0])
    imported = read_cube_document(cube)
    assert imported.volume.unit == 'e/Bohr³' and imported.volume.periodic
    np.testing.assert_allclose(imported.volume.data, 2*Bohr**3, rtol=1e-7)
    np.testing.assert_allclose(imported.volume.voxel_vectors, result.voxel_vectors)
    assert imported.volume.provenance == result.provenance
    added = prepare_field_attachment(a, a.frames[0], imported)
    assert added[0].provenance == result.provenance
    assert added[0].provenance is not result.provenance
    recovered = combine_fields([FieldTerm(a, 1), FieldTerm(imported, 0, -1)])
    np.testing.assert_allclose(recovered.data, 0., atol=2e-7)


def test_large_bounded_cube_metadata_roundtrip_and_legacy_project_default(tmp_path):
    from lele.field_export import export_active_cube
    from lele.volumetric_input import read_cube_document
    from lele.project_file import save_project, load_project
    from test_field_projects_v320 import state_for
    a = document()
    a.volume.provenance = {'operation':'field_arithmetic', 'formula':'A + B', 'details':'p'*20000}
    path = tmp_path/'large_metadata.cube'
    export_active_cube(path, a, a.frames[0])
    incoming = read_cube_document(path)
    assert incoming.volume.unit == 'e/Bohr³'
    assert incoming.volume.provenance == a.volume.provenance
    project = tmp_path/'legacy.lele'
    save_project(project, state_for(a))
    from project_archive_v1 import legacy_archive
    with legacy_archive(project) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(payload['manifest.json'])
    for node in manifest['nodes']:
        if node.get('type') == 'lele.core:Volume':
            node['attributes'].pop('provenance', None)
    payload['manifest.json'] = json.dumps(manifest).encode()
    with zipfile.ZipFile(project, 'w') as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    assert load_project(project)['documents'][0]['document'].volume.provenance == {}


def test_direct_provenance_does_not_grow_recursively():
    a = document()
    for _ in range(8):
        active = a.volume
        index = len(a.volumes)-1
        result = combine_fields([FieldTerm(a, index), FieldTerm(a, index, -1)])
        append_field_result(a, result, expected_active=active)
    assert len(json.dumps(a.volume.provenance)) < 2000


def test_oversized_metadata_export_rejects_before_replacing_destination(tmp_path):
    from lele.field_export import export_active_cube
    a = document()
    a.volume.provenance = {'details':'x'*(1024*1024)}
    path = tmp_path/'existing.cube'
    path.write_text('keep original')
    with pytest.raises(ValueError, match='metadata exceeds'):
        export_active_cube(path, a, a.frames[0])
    assert path.read_text() == 'keep original'


def test_dialog_units_preview_and_private_import_are_transactional(gui, tmp_path):
    from lele.field_arithmetic_dialog import FieldArithmeticDialog
    from test_volumetric_readers_v320 import vasp_text
    a = document(unit='e/Å³')
    b = document(Bohr**3, unit='e/Bohr³')
    dialog = FieldArithmeticDialog([a, b], a, a.frames[0], gui.window)
    try:
        source = dialog.table.cellWidget(1, 2)
        source.setCurrentIndex(source.findData(1))
        assert 'Unit conversions' in dialog.formula.text()
        assert not dialog.table.cellWidget(1, 3).isEnabled()
        imported = tmp_path/'CHGCAR'
        imported.write_text(vasp_text([24.]*8))
        with patch('lele.field_arithmetic_dialog.QFileDialog.getOpenFileNames', return_value=([str(imported)], '')):
            dialog.import_files()
        assert len(dialog.private_documents) == 1 and len(a.volumes) == 1
        count = len(dialog.sources)
        with patch('lele.field_arithmetic_dialog.QFileDialog.getOpenFileNames', return_value=([str(imported)], '')):
            with patch('lele.field_arithmetic_dialog.run_data_task', side_effect=LoadCancelled):
                dialog.import_files()
        assert len(dialog.sources) == count
        dialog.reject()
        assert dialog.result is None and len(a.volumes) == 1
    finally:
        dialog.deleteLater()


def test_unknown_unit_dialog_declaration_does_not_relabel_source(gui):
    from lele.field_arithmetic_dialog import FieldArithmeticDialog
    a, b = document(), document(unit='source units')
    dialog = FieldArithmeticDialog([a, b], a, a.frames[0], gui.window)
    try:
        source = dialog.table.cellWidget(1, 2)
        source.setCurrentIndex(source.findData(1))
        unit = dialog.table.cellWidget(1, 3)
        assert unit.isEnabled() and unit.currentData() is None
        dialog.calculate()
        assert dialog.result is None and 'Unknown scalar units' in dialog.error.text()
        unit.setCurrentIndex(unit.findData('e/Å³'))
        dialog.table.cellWidget(1, 1).setCurrentIndex(1)
        dialog.calculate()
        np.testing.assert_array_equal(dialog.result.data, 0.)
        assert b.volume.unit == 'source units'
        assert len(a.volumes) == 1  # Dialog prepares; only FieldActions commits.
    finally:
        dialog.deleteLater()


def test_field_action_appends_selects_refreshes_and_preserves_custom_layers(gui):
    from lele.field_arithmetic_dialog import FieldArithmeticDialog
    from PySide6.QtWidgets import QDialog
    a, b = document(3.), document(1.)
    gui.attach(a.frames[0], volume=a.volume)
    w = gui.window
    w.documents.append(b)
    layers = [dict(dataset=0, value=1., color='#ff0000', opacity=.8, style='Surface')]
    w.render_options.volume_surfaces = list(layers)
    assert w.field_arithmetic_button.isEnabled()
    def accept_operation(dialog):
        source = dialog.table.cellWidget(1, 2)
        source.setCurrentIndex(source.findData(1))
        dialog.table.cellWidget(1, 1).setCurrentIndex(1)
        dialog.calculate()
        assert dialog.result is not None
        return QDialog.DialogCode.Accepted
    with patch.object(FieldArithmeticDialog, 'exec', accept_operation):
        w._field_arithmetic()
    assert len(w.doc.volumes) == 2 and w.doc.volume is w.doc.volumes[1]
    np.testing.assert_array_equal(w.doc.volume.data, 2.)
    assert w.field_combo.currentIndex() == 1
    assert 'Formula: A − B' in w.field_note.text()
    assert w.render_options.volume_surfaces == layers
    from lele.field_slice import grid_plane_slice
    np.testing.assert_array_equal(grid_plane_slice(w.doc.volume, 2, .5).values, 2.)
