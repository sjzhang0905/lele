"""Cross-cell Ctrl+G must expose real, independently selectable atom rows."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.core import Frame, Volume


@pytest.fixture
def gui():
    path = Path(__file__).with_name('test_selection_ui_v090.py')
    spec = importlib.util.spec_from_file_location('fragment_ui_harness', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = module.SelectionWorkflowTests
    cls.setUpClass()
    case = cls('test_invert_complements_selection_and_updates_coordinate_table')
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()
        cls.app.processEvents()


def crossing_water():
    return Frame(['O', 'H', 'H', 'He'],
                 [[9.7, 1, 1], [.58, 1, 1], [9.4, 1.89, 1], [5, 5, 5]],
                 np.eye(3) * 10, (True, True, True), -12.,
                 {'converter_charge': 1, 'converter_mult': 2},
                 atom_appearance={1: AtomAppearance(color='#123456', opacity=.4)})


def prepare(gui, *, volume=None):
    source = crossing_water()
    gui.attach(source, volume=volume, second_frame=source.clone())
    w = gui.window
    w.vtk.GetRenderWindow().SetSize(600, 400)
    w.refresh_scene(reset_camera=True)
    gui.select([0])
    return w


def selected_rows(w):
    return {index.row() for index in w.atom_table.selectionModel().selectedRows()}


def test_ctrl_g_populates_expanded_coordinate_rows_and_independent_ids(gui):
    w = prepare(gui)
    w.fragment_btn.click()
    assert w.atom_table.rowCount() == 8
    assert len(w.frame.symbols) == len(w.renderer.displayed_atoms()) == 8
    np.testing.assert_allclose(w.frame.cell, np.diag([20, 10, 10]))
    assert w.selection == [0, 5, 2]
    assert selected_rows(w) == {0, 2, 5}
    for i, position in enumerate(w.frame.positions):
        assert w.atom_table.item(i, 0).text() == f'{i + 1} {w.frame.symbols[i]}'
        np.testing.assert_allclose([float(w.atom_table.item(i, j).text()) for j in (1, 2, 3)], position)
    assert w.atom_panel._items[5].text(0).startswith('H')
    assert w.frame.atom_appearance[5].color == '#123456'
    assert w.frame.atom_appearance[5].opacity == .4


def test_ctrl_i_after_auto_expansion_complements_every_new_atom(gui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    w = prepare(gui)
    w.show()
    gui.app.processEvents()
    w.vtk.setFocus()
    QTest.keyClick(w.vtk, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    before = set(w.selection)
    QTest.keyClick(w.vtk, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert set(w.selection) == set(range(8)) - before
    assert selected_rows(w) == set(w.selection)
    QTest.keyClick(w.vtk, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    assert set(w.selection) == before
    assert w.atom_table.rowCount() == 8
    assert len(w.undo_stack) == 1


def test_auto_expansion_undo_restores_frame_volume_energy_and_other_frame(gui):
    volume = Volume(np.linspace(-1, 1, 64).reshape(4, 4, 4), np.zeros(3), np.eye(3))
    w = prepare(gui, volume=volume)
    original = w.frame.clone()
    other_frame = w.doc.frames[1]
    w.fragment_btn.click()
    assert w.doc.modified and w.frame.energy_ev is None
    assert w.doc.volume is None and w.renderer.volume is None
    assert w.frame.info['converter_charge'] == 2
    assert 'converter_mult' not in w.frame.info
    assert w.doc.frames[1] is other_frame
    np.testing.assert_array_equal(other_frame.positions, original.positions)
    w.undo_edit()
    assert w.frame.symbols == original.symbols
    np.testing.assert_array_equal(w.frame.positions, original.positions)
    np.testing.assert_array_equal(w.frame.cell, original.cell)
    assert w.frame.info == original.info and w.frame.energy_ev == -12.
    assert w.doc.volume is volume and w.renderer.volume is volume
    assert w.selection == [0] and selected_rows(w) == {0}
    assert w.atom_table.rowCount() == 4


def test_repeated_ctrl_g_does_not_grow_an_already_complete_fragment(gui):
    w = prepare(gui)
    w.fragment_btn.click()
    assert len(w.frame.symbols) == 8
    before = w.frame.clone()
    selected = set(w.selection)
    w.fragment_btn.click()
    assert w.frame.symbols == before.symbols
    np.testing.assert_array_equal(w.frame.positions, before.positions)
    assert set(w.selection) == selected and len(w.undo_stack) == 1


def test_invert_delete_and_undo_keep_only_selected_complete_molecule(gui):
    w = prepare(gui)
    w.fragment_btn.click()
    fragment = w.frame.positions[w.selection].copy()
    w.invert_btn.click()
    w.delete_btn.click()
    assert len(w.frame.symbols) == w.atom_table.rowCount() == 3
    assert set(w.frame.symbols) == {'O', 'H'}
    actual = sorted(map(tuple, w.frame.positions))
    assert actual == sorted(map(tuple, fragment))
    w.undo_edit()
    assert len(w.frame.symbols) == w.atom_table.rowCount() == 8
    w.undo_edit()
    assert len(w.frame.symbols) == w.atom_table.rowCount() == 4


def test_fragment_inside_cell_keeps_geometry_and_creates_no_undo(gui):
    source = Frame(['O', 'H', 'H', 'He'], [[3, 3, 3], [3.9, 3, 3], [3, 3.9, 3], [7, 7, 7]],
                   np.eye(3) * 10, (True,) * 3, -12.)
    gui.attach(source)
    gui.select([0])
    gui.window.fragment_btn.click()
    assert gui.window.selection == [0, 1, 2]
    assert gui.window.doc.frames[0] is source
    assert gui.window.undo_stack == []
    assert gui.window.frame.energy_ev == -12.
