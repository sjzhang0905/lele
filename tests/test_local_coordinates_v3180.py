from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtWidgets import QDialog

from lele.coordinate_update import prepare_coordinate_update, save_coordinate_update
from lele.coordinate_update_actions import CoordinateUpdateDialog
from lele.core import Frame
from lele.formats import load_document
from test_coordinate_update_ui_v360 import browse_to
from test_periodic_fragment_ui_v171 import gui


TEMPLATE = ('slab\n1\n8 0 0\n0 8 0\n0 0 8\nC H\n1 2\nSelective dynamics\nDirect\n'
            '0.1 0.2 0.3   F  t  F ! row one\n0.2 0.3 0.4   t  F  T\n0.3 0.4 0.5   F  F  F\n')


def geometry(symbols):
    return Frame(symbols, np.arange(3 * len(symbols)).reshape(-1, 3) / 3,
                 [[9, 0, 0], [1, 8, 0], [0, 1, 7]], (True,)*3)


@pytest.mark.parametrize('mode', ['Direct', 'Cartesian'])
@pytest.mark.parametrize('symbols', [['C'], ['C', 'C', 'H', 'H', 'O']])
def test_resize_flags_and_velocity_rows_on_disk(tmp_path, mode, symbols):
    path = tmp_path / 'CONTCAR'
    raw = (TEMPLATE.replace('Direct', mode) + '\n0.1 0.2 0.3\n0 0 0\n0.4 0.5 0.6').replace('\n', '\r\n').encode()
    path.write_bytes(raw)
    frame = geometry(symbols)
    frame.info['vasp_fixed_axes'] = [[False]*3 for _ in symbols]
    plan = prepare_coordinate_update(path, frame)
    assert path.read_bytes() == raw and plan.changed
    save_coordinate_update(plan)
    assert path.with_name('CONTCAR.lele.bak').read_bytes() == raw
    saved = path.read_bytes()
    assert b'\n' not in saved.replace(b'\r\n', b'') and not saved.endswith(b'\n')
    lines = saved.decode().splitlines()
    assert lines[7:9] == ['Selective dynamics', mode]
    assert lines[9].endswith('   F  t  F ! row one')
    restored = load_document(path).frames[0]
    assert restored.symbols == symbols
    np.testing.assert_allclose(restored.positions, frame.positions, atol=1e-12)
    np.testing.assert_allclose(restored.cell, frame.cell)
    expected = ([[True, False, True], [False, True, False], [True]*3] + [[False]*3]*2)[:len(symbols)]
    assert restored.info['vasp_fixed_axes'] == expected
    velocities = [list(map(float, row.split())) for row in lines[10+len(symbols):]]
    expected_velocities = ([[.1, .2, .3], [0., 0., 0.], [.4, .5, .6]] + [[0.]*3]*2)[:len(symbols)]
    assert velocities == expected_velocities
    if len(symbols) > 3:
        assert lines[12].endswith('  T  T  T') and lines[13].endswith('  T  T  T')


def test_no_selective_header_does_not_import_source_constraints(tmp_path):
    path = tmp_path / 'POSCAR'
    path.write_text('C\n1\n4 0 0\n0 4 0\n0 0 4\nC\n1\nCartesian\n1 1 1')
    frame = geometry(['C', 'C'])
    frame.info['vasp_fixed_axes'] = [[True]*3]*2
    plan = prepare_coordinate_update(path, frame)
    assert 'Selective' not in plan.new_bytes.decode()
    assert all(len(row.split()) == 3 for row in plan.new_bytes.decode().splitlines()[8:])
    assert 'vasp_fixed_axes' not in plan.validated_document.frames[0].info


def test_vasp4_contcar_declared_elements_and_duplicate_potcar_slots(tmp_path):
    path = tmp_path / 'CONTCAR'
    path.write_text(TEMPLATE.replace('slab', 'C H').replace('C H\n1 2', '1 2'))
    plan = prepare_coordinate_update(path, geometry(['C', 'H', 'H', 'H']))
    assert plan.validated_document.frames[0].symbols == ['C', 'H', 'H', 'H']
    assert plan.new_bytes.decode().splitlines()[5:8] == ['C  H', '1 3', 'Selective dynamics']
    path.write_text(TEMPLATE.replace('C H\n1 2', 'H H C\n1 1 1'))
    plan = prepare_coordinate_update(path, geometry(['H', 'H', 'H', 'C']))
    assert plan.new_bytes.decode().splitlines()[5:7] == ['H H C', '1 2 1']
    path.write_text(TEMPLATE.replace('C H\n1 2', 'H_h H C\n1 1 1'))
    plan = prepare_coordinate_update(path, geometry(['H', 'H', 'C', 'O']))
    assert plan.new_bytes.decode().splitlines()[5].split() == ['H_h', 'H', 'C', 'O']


def test_md_restart_lattice_and_history_are_accounted_for_in_resize(tmp_path):
    path = tmp_path / 'CONTCAR'
    # This is the VASP MD restart layout: lattice state, ion velocities, thermostat history.
    lattice = 'Lattice velocities and vectors\n1\n0 0 0\n0 0 0\n0 0 0\n8 0 0\n0 8 0\n0 0 8\n'
    history = '\nPREDICTOR-CORRECTOR\n1.0\n1 2 3 4\n' + '0 0 0\n'*9
    raw = TEMPLATE + lattice + '\n' + '0 0 0\n'*3 + history
    path.write_text(raw)
    same = prepare_coordinate_update(path, load_document(path).frames[0])
    assert same.new_bytes.decode().endswith(history)
    added = prepare_coordinate_update(path, geometry(['C', 'H', 'H', 'H']))
    assert 'predictor-corrector' in added.summary
    assert 'PREDICTOR-CORRECTOR' not in added.new_bytes.decode()
    assert '9 0 0\n1 8 0\n0 1 7\n' in added.new_bytes.decode()
    save_coordinate_update(added)
    assert (tmp_path / 'CONTCAR.lele.bak').read_text() == raw


@pytest.mark.parametrize('incoming', [True, False])
def test_file_menu_browses_unloaded_contcar_both_directions(gui, tmp_path, incoming):
    w = gui.window
    local = tmp_path / 'CONTCAR'
    current = tmp_path / 'POSCAR'
    source = ('Donor\n1\n8 0 0\n0 8 0\n0 0 8\nC H\n1 3\nSelective dynamics\nCartesian\n'
              '1 1 1 T T T\n2 1 1 T T T\n3 1 1 T T T\n4 1 1 F F F\n')
    target, donor = (current, local) if incoming else (local, current)
    target.write_text(TEMPLATE)
    donor.write_text(source)
    w._open_path_now(current)
    count = len(w.documents)
    active = w.doc

    def choose(dialog):
        assert not dialog.apply_button.isEnabled()
        dialog.direction.setCurrentIndex(int(incoming))
        browse_to(dialog, local)
        assert dialog.apply_button.isEnabled() and dialog.plan.path == target
        assert str(target) in dialog.summary.text()
        return QDialog.DialogCode.Accepted

    with patch.object(CoordinateUpdateDialog, 'exec', choose):
        w.apply_coordinates_action.trigger()
    assert len(w.documents) == count and w.doc is active
    assert donor.read_text() == source
    assert target.with_name(target.name + '.lele.bak').read_text() == TEMPLATE
    saved = load_document(target).frames[0]
    assert saved.info['vasp_fixed_axes'] == [[True, False, True], [False, True, False],
                                             [True]*3, [False]*3]
    np.testing.assert_allclose(saved.positions, load_document(donor).frames[0].positions)
    if incoming:
        assert w.frame.info['vasp_fixed_axes'] == saved.info['vasp_fixed_axes']
        assert w.atom_table.rowCount() == 4
