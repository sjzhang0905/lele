"""Main-window scan navigation follows relaxed endpoints, not inner cycles."""
from pathlib import Path
from types import SimpleNamespace

from lele.core import Document
from lele.orca_results import read_orca_results
from test_orca_scan_v3110 import sample_text
from test_periodic_fragment_ui_v171 import gui


def test_curve_entry_navigation_and_editable_coordinates(gui, tmp_path):
    path = tmp_path / 'scan.out'
    path.write_text(sample_text())
    result = read_orca_results(path)
    doc = Document(path, 'ORCA output', result.frames(), calculation_results=result)
    w = gui.window
    w.documents = []; w.current_doc = -1; w.files_tree.clear()
    w._attach_loaded_document(doc)
    assert w.scan_action.isEnabled() and w.scan_curve_button.isEnabled()
    curve = w.show_scan_curve()
    try:
        point = result.scans[0].points[0]
        curve.navigate(point)
        assert w.frame_index == point.frame_index
        expected = [p.frame_index for p in result.scans[0].points if p.converged]
        assert list(w._navigation_indices()) == expected
        w._step_next()
        assert w.frame_index == expected[1]
        assert w.atom_table.columnCount() == 4
        assert result.scans[0].coordinates[0].atoms == (1, 0)
        from PySide6.QtCore import Qt
        assert all(w.atom_table.item(0, column).flags() & Qt.ItemFlag.ItemIsEditable
                   for column in (1, 2, 3))
        gui.select([0, 2])
        w.selection_panel.copy_coordinates_button.click()
        rows = gui.app.clipboard().text().splitlines()
        assert [row.split()[0] for row in rows] == ['C', 'H']
        assert w.rotate_axis_action.isEnabled() and not w.dihedral_action.isEnabled()
        gui.select([0, 1, 2, 3])
        assert w.dihedral_action.isEnabled()
    finally:
        curve.close(); gui.app.processEvents()


def test_scan_step_parent_opens_last_optimization_frame_and_children_stay_selectable(gui, tmp_path):
    from PySide6.QtCore import Qt
    path = tmp_path / 'scan.out'
    path.write_text(sample_text())
    result = read_orca_results(path)
    doc = Document(path, 'ORCA output', result.frames(), calculation_results=result)
    w = gui.window
    w.documents = []; w.current_doc = -1; w.files_tree.clear()
    w._attach_loaded_document(doc)
    root = w.files_tree.topLevelItem(0)
    history = root.child(0).child(root.child(0).childCount()-1)
    assert history.text(0) == 'Optimization history by scan step'
    for k in range(history.childCount()):
        heading = history.child(k)
        data = heading.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            continue
        sequence = w._tree_sequences[data[2]]
        w.files_tree.setCurrentItem(heading)
        assert w.frame_index == sequence[-1]
        assert list(w._navigation_indices()) == list(sequence)
        w.files_tree.setCurrentItem(heading.child(0))
        assert w.frame_index == sequence[0]
