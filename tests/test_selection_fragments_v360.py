"""Selected-site details and frame-local named fragments."""
import numpy as np
import pytest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lele.core import Frame
from lele.saved_fragments import (
    add_fragment, fragment_order, fragments, get_fragment, index_summary,
    remove_fragment, subset_fragments,
)
from lele.selection_panel import FragmentPanel, SelectionPanel, SelectionTableModel


def frame(count=6):
    return Frame(['C', 'N', 'O', 'H', 'H', 'H'][:count], np.arange(count * 3).reshape(count, 3) * .1)


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def test_atom_summary_uses_source_order_and_three_or_more_atom_ranges():
    assert index_summary([23, 6, 1, 7, 0, 5, 4, 6]) == '1, 2, 5-8, 24'
    assert index_summary([]) == ''
    assert index_summary([2]) == '3'
    assert index_summary([2, 3]) == '3, 4'


def test_fragment_save_delete_monotonic_names_and_undo_snapshot():
    f = frame()
    first = add_fragment(f, [4, 1, 4, 2])
    assert first == {'name': 'fragment1', 'indices': [1, 2, 4]}
    snapshot = f.clone()
    second = add_fragment(f, [0])
    assert second['name'] == 'fragment2'
    assert fragments(snapshot) == [first]
    assert remove_fragment(f, 'fragment2')
    assert not remove_fragment(f, 'missing')
    assert add_fragment(f, [3])['name'] == 'fragment3'
    assert fragments(snapshot) == [first]
    assert snapshot.info['fragment_next_id'] == 2


def test_fragment_records_do_not_expose_mutable_internal_indices():
    f = frame()
    added = add_fragment(f, [1, 2])
    added['indices'].append(5)
    returned = get_fragment(f, 'fragment1')
    returned['indices'].clear()
    assert get_fragment(f, 'fragment1')['indices'] == [1, 2]


def test_fragment_name_collision_from_loaded_project_and_invalid_records():
    f = frame()
    f.info['saved_fragments'] = [
        {'name': 'fragment9', 'indices': [0]}, {'name': '', 'indices': [1]},
        {'name': 'broken', 'indices': [99]}, {'name': 'fragment9', 'indices': [2]},
    ]
    assert add_fragment(f, [4])['name'] == 'fragment10'
    assert len(fragments(f)) == 2
    with pytest.raises(ValueError, match='Select'):
        add_fragment(f, [])
    with pytest.raises(ValueError, match='outside'):
        add_fragment(f, [-1])


def test_fragment_moves_preserve_selected_and_unselected_internal_orders():
    f = frame()
    add_fragment(f, [4, 1, 3])
    assert fragment_order(f, 'fragment1', 'front') == [1, 3, 4, 0, 2, 5]
    assert fragment_order(f, 'fragment1', 'back') == [0, 2, 5, 1, 3, 4]
    with pytest.raises(ValueError, match='no longer exists'):
        fragment_order(f, 'missing', 'front')
    with pytest.raises(ValueError, match='destination'):
        fragment_order(f, 'fragment1', 'middle')


def test_fragment_subset_remaps_survivors_discards_empty_and_maps_replicas():
    source = [{'name': 'fragment1', 'indices': [1, 3]}, {'name': 'fragment2', 'indices': [0]}]
    assert subset_fragments(source, [3, 2, 1]) == [{'name': 'fragment1', 'indices': [0, 2]}]
    assert subset_fragments(source, [0, 1, 2, 3, 0, 1, 2, 3]) == [
        {'name': 'fragment1', 'indices': [1, 3, 5, 7]}, {'name': 'fragment2', 'indices': [0, 4]},
    ]
    assert source[0]['indices'] == [1, 3]


def text(model, row, header):
    return model.data(model.index(row, model.headers.index(header)))


def test_selection_model_mixed_sites_sorted_ids_and_unwrapped_direct_coordinates(app):
    f = frame(3)
    f.cell = np.array([[2., 0, 0], [1., 3, 0], [.5, .2, 4.]])
    f.pbc = (True, True, True)
    f.positions = np.array([[1.2, -.2, .7], [.2, .3, .4], [.4, .5, .6]]) @ f.cell
    f.info['site_occupancies'] = [{'C': .4, 'N': .5}, {'N': 1.}, {'O': 1.}]
    model = SelectionTableModel()
    model.set_frame(f, [2, 0, 2])
    assert model.rowCount() == 3
    assert [text(model, row, 'Index') for row in range(3)] == ['1', '1', '3']
    assert [text(model, row, 'Element') for row in range(3)] == ['C', 'N', 'O']
    assert text(model, 0, 'Occ. %') == '40'
    assert text(model, 1, 'Occ. %') == '50'
    assert text(model, 0, 'Direct X') == '1.20000000'
    assert text(model, 0, 'Direct Y') == '-0.20000000'
    assert float(text(model, 0, 'Cartesian Z')) == pytest.approx(2.8)
    assert 'Free X' not in model.headers


def test_selection_fixed_flags_keep_unknown_and_axis_basis_explicit(app):
    f = frame(3)
    f.info.update(fixed_axes=[[True, False, True], [False, False, False], [None, None, None]],
                  fixed_axes_basis='cartesian')
    model = SelectionTableModel()
    model.set_frame(f, [0, 1, 2])
    assert [text(model, 0, f'Free {axis}') for axis in 'XYZ'] == ['F', 'T', 'F']
    assert text(model, 1, 'Free X') == 'T'
    assert text(model, 2, 'Free Z') == '—'
    tooltip = model.headerData(model.headers.index('Free X'), Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    assert 'F = fixed' in tooltip and 'cartesian' in tooltip
    assert 'Direct X' not in model.headers


def test_legacy_selective_dynamics_and_invalid_fixed_arrays(app):
    f = frame(3)
    f.info['vasp_fixed_axes'] = [[True, False, False]] * 3
    model = SelectionTableModel()
    model.set_frame(f, [1])
    assert model.fixed_basis == 'direct' and text(model, 0, 'Free X') == 'F'
    f.info['vasp_fixed_axes'] = [[True, False, False]]
    model.set_frame(f, [1])
    assert 'Free X' not in model.headers


def test_panel_plain_text_tracks_periodic_and_fixed_fields(app):
    f = frame(3)
    f.cell = np.eye(3) * 5
    f.pbc = (True, True, True)
    f.info['fixed_axes'] = [[False] * 3] * 3
    panel = SelectionPanel()
    try:
        panel.show(); app.processEvents()
        panel.set_frame(f, [2, 0])
        assert panel.summary_label.text() == 'Atoms 1, 3'
        assert 'Direct X' in panel.text.toPlainText()
        assert 'Free X' in panel.text.toPlainText()
        panel.set_frame(frame(3), [0])
        assert 'Direct X' not in panel.model.headers
        assert 'Direct X' not in panel.text.toPlainText()
        assert 'Free X' not in panel.text.toPlainText()
        panel.set_frame(f, [2])
        assert 'Direct X' in panel.text.toPlainText()
        assert 'Free X' in panel.text.toPlainText()
        panel.set_frame(None, [])
        assert panel.model.rowCount() == 0 and panel.summary_label.text() == 'No atoms selected'
        assert panel.text.toPlainText() == ''
    finally:
        panel.close()


def test_panel_nonaxis_constraints_are_notes_not_fake_fixed_flags(app):
    f = frame(3)
    f.info['constraint_notes'] = ['Bond 1–2 distance constrained; not a fixed atom.']
    panel = SelectionPanel()
    try:
        panel.set_frame(f, [0])
        assert 'Free X' not in panel.model.headers
        assert 'Bond 1–2' in panel.note_label.text()
    finally:
        panel.close()


def test_fragment_panel_emits_current_frame_selection_and_compact_actions(app):
    f = frame()
    add_fragment(f, [3, 1])
    panel = FragmentPanel()
    events = []
    panel.saveRequested.connect(lambda: events.append(('save',)))
    panel.selectRequested.connect(lambda indices: events.append(('select', indices)))
    panel.deleteRequested.connect(lambda name: events.append(('delete', name)))
    panel.moveRequested.connect(lambda name, destination: events.append(('move', name, destination)))
    try:
        panel.set_frame(f, [1, 3])
        panel.resize(800, 250)
        panel.show(); app.processEvents()
        panel.save_button.click()
        first = panel.list_widget.item(0)
        QTest.mouseClick(panel.list_widget.viewport(), Qt.MouseButton.LeftButton,
                         pos=panel.list_widget.visualItemRect(first).center())
        panel.front_button.click()
        panel.back_button.click()
        panel.delete_button.click()
        assert events == [('save',), ('select', [1, 3]), ('move', 'fragment1', 'front'),
                          ('move', 'fragment1', 'back'), ('delete', 'fragment1')]
        assert all(button.width() < 200 for button in (panel.save_button, panel.delete_button,
                                                       panel.front_button, panel.back_button))
        panel.set_frame(frame(), [], editable=True)
        assert panel.list_widget.count() == 0 and not panel.delete_button.isEnabled()
        assert not panel.save_button.isEnabled()
        panel.set_frame(f, [0], editable=False)
        assert not panel.save_button.isEnabled() and not panel.front_button.isEnabled()
    finally:
        panel.close()


def test_empty_selection_does_not_scan_all_fixed_atom_flags(app):
    class LazyFlags:
        def __len__(self):
            return 100000

        def __getitem__(self, index):
            raise AssertionError('Unselected fixed-axis rows must not be read')

    f = Frame(['C'] * 100000, np.zeros((100000, 3)))
    f.info['fixed_axes'] = LazyFlags()
    model = SelectionTableModel()
    model.set_frame(f, [])
    assert model.rowCount() == 0
    assert 'Free X' in model.headers


def test_refreshing_coordinates_keeps_plain_text_horizontal_scroll(app):
    f = frame(3)
    f.cell = np.eye(3) * 2
    f.pbc = (True, True, True)
    panel = SelectionPanel()
    try:
        panel.resize(320, 200)
        panel.set_frame(f, [0, 1, 2])
        panel.show(); app.processEvents()
        panel.text.horizontalScrollBar().setValue(150)
        scroll = panel.text.horizontalScrollBar().value()
        resets = []
        changes = []
        panel.model.modelReset.connect(lambda: resets.append(True))
        panel.model.dataChanged.connect(lambda *_: changes.append(True))
        f.positions[0, 0] = 8.5
        f.cell[0, 0] = 5.
        panel.set_frame(f, [0, 1, 2]); app.processEvents()
        assert not resets and changes
        assert text(panel.model, 0, 'Cartesian X') == '8.50000000'
        assert text(panel.model, 0, 'Direct X') == '1.70000000'
        assert panel.text.horizontalScrollBar().value() == scroll
        assert '8.50000000' in panel.text.toPlainText()
        assert '1.70000000' in panel.text.toPlainText()
        # A new trajectory frame also changes only data when the schema and
        # selected row count remain the same.
        next_frame = f.clone()
        next_frame.positions[0, 0] = 10.
        panel.set_frame(next_frame, [0, 1, 2])
        assert not resets
        assert text(panel.model, 0, 'Direct X') == '2.00000000'
    finally:
        panel.close()


def test_fragment_refresh_reuses_unchanged_members_but_detects_copy_on_write(app):
    f = frame()
    add_fragment(f, [0, 1, 2, 3, 4, 5])
    panel = FragmentPanel()
    try:
        with patch('lele.selection_panel.fragments', wraps=fragments) as read:
            panel.set_frame(f, [])
            assert read.call_count == 1
            first = panel.list_widget.item(0)
            panel.set_frame(f, [1, 2], editable=False)
            panel.set_frame(f, [], editable=True)
            assert read.call_count == 1
            assert panel.list_widget.item(0) is first
            add_fragment(f, [4])
            panel.set_frame(f, [])
            assert read.call_count == 2 and panel.list_widget.count() == 2
            remove_fragment(f, 'fragment1')
            panel.set_frame(f, [])
            assert read.call_count == 3 and panel.list_widget.count() == 1
    finally:
        panel.close()
