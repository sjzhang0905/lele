"""Element-local selection syntax and real Qt Enter interaction."""
import os

import numpy as np
import pytest

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lele.atoms_selection_panel import AtomsSelectionPanel, element_indices, parse_element_indices
from lele.core import Frame
from test_periodic_fragment_ui_v171 import gui


def make_frame():
    return Frame(['O', 'H', 'C', 'H', 'O'], np.zeros((5, 3)))


@pytest.fixture
def panel():
    app = QApplication.instance() or QApplication([])
    panel = AtomsSelectionPanel()
    panel.set_frame(make_frame())
    panel.show()
    app.processEvents()
    yield panel
    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_syntax_ranges_chinese_commas_deduplication_and_empty():
    assert parse_element_indices('1， 2-10,24, 5, 10', 24) == list(range(10)) + [23]
    assert parse_element_indices(' 3 - 5 , 2 ', 5) == [1, 2, 3, 4]
    assert parse_element_indices('1-1', 1) == [0]
    assert parse_element_indices('   ', 0) == []


@pytest.mark.parametrize('value', ['0', '6', '2-6', '4-2', '-1', '1.5', '1,,2', '1,', 'a',
                                  '1-2-3', '1 2', '1-99999999999999999999'])
def test_invalid_syntax_and_range_never_partially_select(value):
    with pytest.raises(ValueError):
        parse_element_indices(value, 5)


def test_group_order_and_mixed_sites_follow_atoms_browser_numbering():
    frame = make_frame()
    frame.info = {'site_occupancies': [
        {'O': .6, 'S': .4}, {'H': 1.}, {'C': 1.}, {'H': 1.}, {'O': 1.}],
        'cif_row_order': [(4, 'O'), (0, 'S'), (0, 'O'), (1, 'H'), (2, 'C'), (3, 'H')]}
    assert element_indices(frame) == {'O': [4, 0], 'S': [0], 'H': [1, 3], 'C': [2]}


def test_enter_combines_rows_without_stealing_numeric_text_input(panel):
    emitted = []
    panel.selectionRequested.connect(emitted.append)
    QTest.keyClicks(panel.inputs['O'], '2')
    QTest.keyClicks(panel.inputs['H'], '1-2')
    assert emitted == []
    QTest.keyClick(panel.inputs['H'], Qt.Key.Key_Return)
    assert emitted == [[1, 3, 4]]
    assert panel.element_labels['H'].text() == 'H (2)'
    for editor in panel.inputs.values():
        editor.clear()
    QTest.keyClick(panel.inputs['O'], Qt.Key.Key_Return)
    assert emitted[-1] == []


def test_invalid_row_retains_selection_and_displays_inline_error(panel):
    emitted = []
    panel.selectionRequested.connect(emitted.append)
    panel.inputs['O'].setText('1')
    panel.inputs['H'].setText('1-3')
    QTest.keyClick(panel.inputs['O'], Qt.Key.Key_Return)
    assert emitted == []
    assert '1 to 2' in panel.errors['H'].text()
    assert not panel.errors['H'].isHidden()
    panel.inputs['H'].setText('2')
    QTest.keyClick(panel.inputs['H'], Qt.Key.Key_Return)
    assert emitted == [[0, 3]]
    assert panel.errors['H'].isHidden()


def test_shared_mixed_site_selected_once(panel):
    frame = make_frame()
    frame.info['site_occupancies'] = [
        {'O': .6, 'S': .4}, {'H': 1.}, {'C': 1.}, {'H': 1.}, {'O': 1.}]
    panel.set_frame(frame)
    emitted = []
    panel.selectionRequested.connect(emitted.append)
    panel.inputs['O'].setText('1')
    panel.inputs['S'].setText('1')
    QTest.keyClick(panel.inputs['S'], Qt.Key.Key_Return)
    assert emitted == [[0]]


def test_coordinate_and_selection_refresh_preserve_partial_input(panel):
    frame = panel._frame
    editor = panel.inputs['H']
    editor.setText('1-')
    frame.positions[0, 0] = 4.
    frame.info['saved_fragments'] = [{'name': 'fragment1', 'indices': [0]}]
    panel.set_frame(frame)
    assert panel.inputs['H'] is editor
    assert editor.text() == '1-'


def test_frame_switch_reorder_and_chemistry_change_clear_stale_input(panel):
    from lele.atom_indices import reorder_atoms
    from lele.site_occupancy import change_site_species
    frame = panel._frame
    panel.inputs['H'].setText('2')
    panel.set_frame(frame.clone())
    assert panel.inputs['H'].text() == ''
    frame = panel._frame
    panel.inputs['H'].setText('2')
    reorder_atoms(frame, [0, 3, 2, 1, 4])  # Identical symbols, different identities.
    panel.set_frame(frame)
    assert panel.inputs['H'].text() == ''
    panel.inputs['H'].setText('2')
    change_site_species(frame, 1, [('N', 1)])
    panel.set_frame(frame)
    assert list(panel.inputs) == ['O', 'N', 'C', 'H']
    assert panel.inputs['H'].text() == ''
    panel.set_frame(None)
    assert panel.inputs == {} and panel.submit() is False


def test_large_unchanged_refresh_does_not_rescan_atoms(panel):
    from unittest.mock import patch

    frame = Frame(['H'] * 100_000, np.zeros((100_000, 3)))
    panel.hide()  # Hidden tabs receive the same main-window refresh calls.
    with patch('lele.atoms_selection_panel.element_indices', wraps=element_indices) as scan:
        panel.set_frame(frame)
        assert scan.call_count == 1
        editor = panel.inputs['H']
        editor.setText('1-100000')
        for index in range(20):
            frame.positions[0, 0] = index
            frame.info = {**frame.info, 'saved_fragments': [{'name': 'fragment1', 'indices': [0]}]}
            panel.set_frame(frame)
        assert scan.call_count == 1
        assert panel.inputs['H'] is editor
        assert editor.text() == '1-100000'


def test_cached_sources_detect_actual_paste_delete_and_mixed_component_edits(panel):
    from lele.atom_clipboard import paste_atoms
    from lele.selection_geometry import delete_selected_atoms
    from lele.site_occupancy import change_site_species

    frame = panel._frame
    symbols = frame.symbols
    panel.inputs['H'].setText('2')
    paste_atoms(frame, Frame(['H'], [[1., 1., 1.]]), [0., 0., 0.])
    assert frame.symbols is symbols  # This edit extends its list in place.
    panel.set_frame(frame)
    assert panel.groups['H'] == [1, 3, 5]
    assert panel.inputs['H'].text() == ''
    panel.inputs['H'].setText('3')
    delete_selected_atoms(frame, [1])
    panel.set_frame(frame)
    assert panel.groups['H'] == [2, 4]
    assert panel.inputs['H'].text() == ''
    change_site_species(frame, 0, [('O', .6), ('S', .4)])
    panel.set_frame(frame)
    assert panel.groups['S'] == [0]
    panel.inputs['S'].setText('1')
    change_site_species(frame, 0, [('O', .6), ('N', .4)])
    panel.set_frame(frame)
    assert 'S' not in panel.groups and panel.groups['N'] == [0]
    assert panel.inputs['N'].text() == ''


def test_force_refresh_supports_external_in_place_same_length_mutations(panel):
    frame = panel._frame
    frame.symbols[0] = 'S'
    panel.set_frame(frame, force=True)
    assert list(panel.groups) == ['S', 'H', 'C', 'O']
    assert panel.groups['S'] == [0]


def test_actual_editor_focus_emits_editing_started_once_without_swallowing_input(panel):
    panel.activateWindow()
    panel.inputs['C'].setFocus()
    QApplication.processEvents()
    started = []
    panel.editingStarted.connect(lambda: started.append(True))
    editor = panel.inputs['H']
    editor.setFocus()
    QApplication.processEvents()
    editor.setFocus()
    QTest.keyClicks(editor, '1-2')
    assert started == [True]
    assert editor.hasFocus() and editor.text() == '1-2'


def test_main_window_enter_selection_undo_text_focus_and_reorder(gui):
    from lele.saved_fragments import get_fragment

    gui.attach(make_frame())
    window = gui.window
    assert [window.selection_tabs.tabText(i) for i in range(window.selection_tabs.count())] == [
        'Current selection', 'Fragment', 'Atoms selection']
    panel = window.atoms_selection_panel
    gui.select([2])
    window.fragment_slot_shortcut('save', 1)
    window.show()
    window.activateWindow()
    window.selection_tabs.setCurrentWidget(panel)
    gui.app.processEvents()

    # Numbers typed in the input must not recall fragment1 or modify its atoms.
    gui.select([4])
    panel.inputs['H'].setFocus()
    QTest.keyClicks(panel.inputs['H'], '1-2')
    QTest.keyClick(panel.inputs['H'], Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert window.selection == [4]
    assert get_fragment(window.frame, 'fragment1')['indices'] == [2]
    assert panel.inputs['H'].text() == '1-2'
    panel.inputs['O'].setText('2')
    undo_count = len(window.undo_stack)
    QTest.keyClick(panel.inputs['H'], Qt.Key.Key_Return)
    assert window.selection == [1, 3, 4]
    assert {index.row() for index in window.atom_table.selectionModel().selectedRows()} == {1, 3, 4}
    assert window.selection_panel.model.indices == [1, 3, 4]
    assert len(window.undo_stack) == undo_count + 1

    # Undo the selection through the existing application keyboard shortcut.
    window.vtk.setFocus()
    QTest.keyClick(window.vtk, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.selection == [4]
    assert {index.row() for index in window.atom_table.selectionModel().selectedRows()} == {4}
    panel.inputs['H'].setText('2')
    window.move_named_fragment('fragment1', 'back')
    assert window.frame.symbols == ['O', 'H', 'H', 'O', 'C']
    assert all(editor.text() == '' for editor in panel.inputs.values())
    window.hide()
