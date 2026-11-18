"""Text-preserving coordinate plans and atomic, stale-aware saves."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from lele.core import Frame
from lele.coordinate_update import (supported_input_kind, prepare_coordinate_update,
                                    save_coordinate_update)
from lele.coordinate_templates_poscar import replace_poscar_coordinates
from lele.formats import load_document


POSCAR = '''unchanged comment
2.0
 3.0 0 0 ! a
 0 3.0 0
 0 0 3.0
C H
1 1
Selective dynamics
Direct
 0.0 0.0 0.0 F T F # carbon
 0.5 0.5 0.5 T T T # hydrogen
'''
GJF = '''%chk=test.chk
#p hf/sto-3g opt

kept title

0 1
H 0.0 0.0 0.0
H 0.0 0.0 0.74

'''


def molecule():
    return Frame(['H', 'H'], [[1.2, -2.3, 3.4], [2.4, -3.5, 4.6]])


def periodic():
    return Frame(['C', 'H'], [[1.2, -2.3, 3.4], [2.4, -3.5, 4.6]],
                 [[8, 0, 0], [1, 9, 0], [.2, .3, 10]], (True, True, True))


def test_prepare_is_read_only_and_preserves_utf8_bom_and_crlf(tmp_path):
    path = tmp_path / 'water.gjf'
    raw = b'\xef\xbb\xbf' + GJF.replace('\n', '\r\n').encode()
    path.write_bytes(raw)
    plan = prepare_coordinate_update(path, molecule())
    assert path.read_bytes() == raw and plan.original_bytes == raw
    assert plan.new_bytes.startswith(b'\xef\xbb\xbf%chk=test.chk\r\n')
    assert b'\n' not in plan.new_bytes.replace(b'\r\n', b'')
    assert plan.validated_document.path == path
    np.testing.assert_allclose(plan.validated_document.frames[0].positions, molecule().positions)
    assert 'kept title' not in plan.preview_text or ' kept title' in plan.preview_text


def test_legacy_comment_bytes_roundtrip(tmp_path):
    path = tmp_path / 'latin.gjf'
    raw = GJF.replace('kept title', 'café title').encode('latin-1')
    path.write_bytes(raw)
    plan = prepare_coordinate_update(path, molecule())
    assert b'caf\xe9 title' in plan.new_bytes
    assert b'caf\xc3\xa9' not in plan.new_bytes


def test_utf16_bom_and_comment_are_retained(tmp_path):
    path = tmp_path / 'unicode.gjf'
    text = GJF.replace('kept title', '计算结构')
    original = b'\xff\xfe' + text.encode('utf-16-le')
    path.write_bytes(original)
    plan = prepare_coordinate_update(path, molecule())
    assert plan.new_bytes.startswith(b'\xff\xfe')
    assert '计算结构' in plan.new_bytes[2:].decode('utf-16-le')
    assert path.read_bytes() == original


def test_atomic_save_backups_and_stale_preview_refusal(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    original = path.read_bytes();path.chmod(0o600)
    plan = prepare_coordinate_update(path, molecule())
    assert save_coordinate_update(plan) == path
    assert path.read_bytes() == plan.new_bytes
    assert (tmp_path / 'water.gjf.lele.bak').read_bytes() == original
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / 'water.gjf.lele.bak').stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match='changed'):
        save_coordinate_update(plan)
    # A later legitimate update keeps the previous backup instead of clobbering it.
    second = prepare_coordinate_update(path, Frame(['H', 'H'], [[2, 0, 0], [2, 0, 1]]))
    save_coordinate_update(second)
    assert (tmp_path / 'water.gjf.lele.bak.1').read_bytes() == plan.new_bytes
    assert (tmp_path / 'water.gjf.lele.bak').read_bytes() == original


def test_edit_after_preview_never_overwrites_external_change(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    plan = prepare_coordinate_update(path, molecule())
    path.write_text('externally changed')
    with pytest.raises(ValueError, match='changed'):
        save_coordinate_update(plan)
    assert path.read_text() == 'externally changed'
    assert not list(tmp_path.glob('*.bak*'))


def test_failed_atomic_replace_keeps_original_and_removes_temporary(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    plan = prepare_coordinate_update(path, molecule())
    with patch('lele.coordinate_update.os.replace', side_effect=OSError('disk unavailable')):
        with pytest.raises(OSError, match='disk unavailable'):
            save_coordinate_update(plan)
    assert path.read_text() == GJF
    assert not list(tmp_path.glob('.*.tmp'))


def test_validation_failure_is_read_only(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    with patch('lele.coordinate_templates_molecular.replace_molecular_coordinates', return_value=GJF):
        with pytest.raises(ValueError, match='Cartesian'):
            prepare_coordinate_update(path, molecule())
    assert path.read_text() == GJF


def test_output_and_volume_are_not_input_targets(tmp_path):
    path = tmp_path / 'test.xyz';path.write_text('1\nH\nH 0 0 0\n')
    assert supported_input_kind(path) is None
    path = tmp_path / 'CHGCAR';path.write_text(POSCAR + '\n2 2 2\n1 2 3 4 5\n6 7 8\n')
    assert supported_input_kind(path) is None
    assert supported_input_kind(tmp_path / 'missing.inp') is None


def test_disordered_frame_is_not_silently_projected(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    frame = molecule();frame.info['site_occupancies'] = [{'H': .5}, {'H': 1}]
    with pytest.raises(ValueError, match='occupancies'):
        prepare_coordinate_update(path, frame)
    assert path.read_text() == GJF


@pytest.mark.parametrize('scale', ['2.0', '-216', '2 3 4'])
@pytest.mark.parametrize('mode', ['Direct', 'Cartesian'])
def test_poscar_scale_modes_cell_and_exact_suffixes(tmp_path, scale, mode):
    text = POSCAR.replace('2.0\n', scale + '\n', 1).replace('Direct', mode)
    path = tmp_path / 'POSCAR';path.write_text(text)
    plan = prepare_coordinate_update(path, periodic())
    changed = plan.new_bytes.decode()
    assert changed.splitlines()[0] == text.splitlines()[0]
    assert changed.splitlines()[5:9] == text.splitlines()[5:9]
    assert changed.splitlines()[9].endswith(' F T F # carbon')
    assert changed.splitlines()[10].endswith(' T T T # hydrogen')
    if scale[0] != '-':
        assert changed.splitlines()[1] == scale
    restored = plan.validated_document.frames[0]
    np.testing.assert_allclose(restored.positions, periodic().positions, atol=1.e-10)
    np.testing.assert_allclose(restored.cell, periodic().cell, atol=1.e-10)
    assert restored.info['vasp_fixed_axes'] == [[True, False, True], [False, False, False]]


def test_poscar_isolated_source_gets_30_angstrom_box(tmp_path):
    path = tmp_path / 'POSCAR';path.write_text(POSCAR)
    frame = periodic();frame.pbc = (False,) * 3
    plan = prepare_coordinate_update(path, frame)
    np.testing.assert_allclose(plan.validated_document.frames[0].cell, np.eye(3) * 30)


def test_poscar_cartesian_velocities_preserved_and_reordered_restart_rejected(tmp_path):
    text = POSCAR + '\nCartesian\n 0.1 0.2 0.3\n 0.4 0.5 0.6\n'
    new = replace_poscar_coordinates(text, periodic())
    assert new.endswith('\nCartesian\n 0.1 0.2 0.3\n 0.4 0.5 0.6\n')
    frame = periodic();frame.info['atom_order_edited'] = True
    with pytest.raises(ValueError, match='Reordered'):
        replace_poscar_coordinates(text, frame)


def test_poscar_rejects_species_change_and_complex_restart_tail():
    frame = periodic();frame.symbols.reverse()
    with pytest.raises(ValueError, match='POTCAR'):
        replace_poscar_coordinates(POSCAR, frame)
    with pytest.raises(ValueError, match='predictor'):
        replace_poscar_coordinates(POSCAR + '\nPREDICTOR-CORRECTOR\n1 2 3\n', periodic())


def test_save_as_new_file_does_not_overwrite_another_existing_file(tmp_path):
    path = tmp_path / 'water.gjf';path.write_text(GJF)
    plan = prepare_coordinate_update(path, molecule())
    destination = tmp_path / 'updated.gjf'
    save_coordinate_update(plan, destination)
    assert destination.read_bytes() == plan.new_bytes and path.read_text() == GJF
    with pytest.raises(FileExistsError):
        save_coordinate_update(plan, destination)
