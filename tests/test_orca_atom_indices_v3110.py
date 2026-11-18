"""ORCA indexing remains an atom-label option; other controls are one-based."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from lele.atom_appearance import AtomAppearance, LABEL_MODES
from lele.atoms_selection_panel import AtomsSelectionPanel, parse_atom_indices
from lele.core import Frame, atom_label_texts
from lele.saved_fragments import index_summary
from lele.geometry_curve_dialog import parse_atoms
from test_periodic_fragment_ui_v171 import gui


def test_orca_label_modes_are_global_and_compatible_with_appearance_validation():
    symbols = ['O', 'H', 'C', 'H']
    for mode, expected in (
            ('ORCA index (0..N-1)', ['0', '1', '2', '3']),
            ('Element + ORCA index', ['O0', 'H1', 'C2', 'H3'])):
        assert mode in LABEL_MODES
        assert AtomAppearance(label_mode=mode).label_mode == mode
        assert atom_label_texts(symbols, mode) == expected
    assert atom_label_texts(symbols, 'Index (1..N)') == ['1', '2', '3', '4']
    assert index_summary([0, 1, 2, 4]) == '1-3, 5'


def test_one_based_range_parsers_reject_out_of_range():
    assert parse_atom_indices('1, 3-5', 5) == [0, 2, 3, 4]
    assert parse_atoms('1 2,5') == (0, 1, 4)
    for text in ('0', '6', '-1', '4-2', '1-999999999999999999'):
        with pytest.raises(ValueError):
            parse_atom_indices(text, 5)
    with pytest.raises(ValueError):
        parse_atoms('0 1')


def test_global_and_element_rows_combine_without_orca_row():
    app = QApplication.instance() or QApplication([])
    panel = AtomsSelectionPanel()
    frame = Frame(['O', 'H', 'C', 'H', 'O'], np.zeros((5, 3)))
    panel.set_frame(frame)
    emitted = []
    panel.selectionRequested.connect(emitted.append)
    assert list(panel.index_inputs) == ['global'] and not hasattr(panel, 'orca_input')
    panel.global_input.setText('1,3-4')
    panel.inputs['O'].setText('2')
    QTest.keyClick(panel.global_input, Qt.Key.Key_Return)
    assert emitted == [[0, 2, 3, 4]]
    panel.global_input.setText('6')
    assert not panel.submit()
    assert emitted == [[0, 2, 3, 4]]
    assert '1 to 5' in panel.index_errors['global'].text()
    panel.global_input.setText('1-')
    frame.positions[0] = [2, 3, 4]
    panel.set_frame(frame)
    assert panel.global_input.text() == '1-'
    panel.set_frame(frame.clone())
    assert panel.global_input.text() == ''
    panel.close();panel.deleteLater();app.processEvents()


def test_orca_labels_follow_boundary_source_ids_without_extra_atom_columns(gui):
    frame = Frame(['Si'], [[0, 1, 1]], np.eye(3) * 5, (True,) * 3)
    gui.attach(frame);gui.select([0])
    assert gui.window.atom_table.columnCount() == 4
    panel = gui.window.atom_panel
    assert all('ORCA' not in panel.tree.headerItem().text(i) for i in range(panel.tree.columnCount()))
    assert 'ORCA' not in panel.target_label.text() and 'ORCA' not in panel._items[0].toolTip(0)
    assert 'ORCA' not in gui.window.selection_panel.summary_label.toolTip()
    panel.label_combo.setCurrentIndex(panel.label_combo.findData('ORCA index (0..N-1)'))
    assert [actor.GetInput() for actor in gui.window.renderer._label_actors] == ['0', '0']
    assert gui.window.frame.atom_appearance[0].label_mode == 'ORCA index (0..N-1)'


def test_geometry_monitors_use_only_one_based_atom_numbers(gui):
    from lele.geometry_curve_dialog import GeometryCurveDialog
    frame = Frame(['C', 'H', 'O'], [[0, 0, 0], [1, 0, 0], [0, 2, 0]])
    gui.attach(frame);gui.select([0, 2])
    dialog = GeometryCurveDialog(gui.window.doc, gui.window)
    gui.addCleanup(dialog.close)
    assert not hasattr(dialog, 'index_combo')
    assert dialog.table.item(0, 0).text() == 'Distance 1–3'
    assert dialog.parameters[0].atoms == (0, 2)
    np.testing.assert_allclose(dialog.values[0], [2])


def test_nmr_keeps_real_source_numbers_without_extra_orca_index_column(gui):
    from lele.nmr_input import orca
    from test_nmr_v350 import ORCA
    frame = Frame(['O', 'H', 'H'], [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    gui.attach(frame)
    result = orca(ORCA.splitlines())[0]
    result.frame_index = 0;result.reference = frame.clone()
    gui.window.doc.nmr_results = [result]
    dialog = gui.window.show_nmr_results();gui.addCleanup(dialog.close)
    assert dialog.table.columnCount() == 8 and not hasattr(dialog, 'index_combo')
    assert [dialog.table.item(i, 0).text() for i in range(2)] == ['2', '3']
    assert [dialog.table.item(i, 6).text() for i in range(2)] == ['1', '2']
    assert [text.get_text() for text in dialog.figure.axes[0].texts] == ['2', '3']
    dialog.table.setCurrentCell(0, 0)
    dialog.request_atom(dialog.table.item(0, 0))
    assert gui.window.selection == [1]


def test_reorientation_has_one_based_fields_only(gui):
    from lele.reorientation_dialog import ReorientationDialog
    frame = Frame(['C', 'H', 'O'], [[0, 0, 0], [1, 0, 0], [0, 0, 1]])
    gui.attach(frame)
    dialog = ReorientationDialog(frame, [0, 1, 2], gui.window);gui.addCleanup(dialog.close)
    assert not any(hasattr(dialog, attr) for attr in ('orca_origin', 'orca_x_atom', 'orca_z_atom'))
    assert (dialog.origin.value(), dialog.x_atom.value(), dialog.z_atom.value()) == (1, 2, 3)
    assert dialog.plan()[3]['selection'] == [0, 1, 2]


def test_neb_uses_one_based_migrating_atom_numbers(gui):
    from lele.vasp_neb import build_neb_path, natural_path_key
    from lele.vasp_neb_dialog import VaspNebDialog
    from test_vasp_neb_dialog_v370 import documents
    docs = sorted(documents(), key=natural_path_key)
    window = gui.window
    window.documents = docs;window.current_doc = 0;window.change_frame(0);window.selection = [2]
    dialog = VaspNebDialog(build_neb_path(docs), window);gui.addCleanup(dialog.close)
    assert not hasattr(dialog, 'atom_numbering') and dialog.atoms.text() == '3'
    before = dialog.caterpillar_frame.positions.copy()
    dialog.image_labels.setChecked(True);dialog.rebuild_caterpillar()
    np.testing.assert_allclose(dialog.caterpillar_frame.positions, before)
    assert [a.GetInput() for a in dialog.track_drawing._label_actors] == ['3:0', '3:1', '3:2']
