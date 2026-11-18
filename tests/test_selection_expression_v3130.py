"""Selection grammar, immutable references, bounded exact MIC and GUI undo."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from itertools import product
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from lele.core import Frame
from lele.selection_expression import evaluate_selection_expression as select, DISTANCE_PAIR_BLOCK
from lele.output_text import LoadCancelled
from test_periodic_fragment_ui_v171 import gui


def molecule():
    return Frame(['Cu', 'O', 'H', 'H', 'N', 'O'], [[0, 0, 0], [1, 0, 0],
                 [2, 0, 0], [3, 0, 0], [4, 0, 0], [6, 0, 0]])


def test_boolean_precedence_element_lists_and_source_numbering():
    frame = molecule()
    assert select(frame, 'element O H') == [1, 2, 3, 5]
    assert select(frame, 'ELEMENT o,h') == [1, 2, 3, 5]
    assert select(frame, 'element O or element H and not index 3') == [1, 3, 5]
    assert select(frame, '(element O or element H) and not index 3, 6') == [1, 3]
    assert select(frame, 'index 1, 3-5') == select(frame, 'index 1, 3 to 5') == [0, 2, 3, 4]
    assert select(frame, 'index >= 3 and index < 5') == [2, 3]
    assert select(frame, 'index = 2 or index == 6') == [1, 5]
    assert select(frame, 'all and not none') == list(range(6))
    assert select(frame, 'selected', [4, 0, 4]) == [0, 4]
    assert select(frame, 'none', [0]) == []


def test_nearest_current_selection_is_snapshotted_and_strict_bounds_are_respected():
    frame = molecule();references = [0, 5]
    assert select(frame, 'element H and distance > 1 and distance < 3', references) == [2]
    assert select(frame, 'within 2 of selected', [0]) == [0, 1, 2]
    assert select(frame, 'not selected and within 2 of selected', [0]) == [1, 2]
    assert select(frame, 'distance != 0 and distance <= 1', references) == [1]
    assert select(frame, 'distance >= 2e0 and distance <= 3.0', references) == [2, 3, 4]
    assert references == [0, 5]
    # The new atoms do not recursively become distance references.
    assert select(frame, 'within 1.1 of selected', [0]) == [0, 1]


def test_mixed_sites_match_positive_occupancy_components_once():
    frame = molecule()
    frame.info['site_occupancies'] = [{'Cu': .7, 'Ni': .3}, {'O': 1}, {'H': 1},
                                     {'H': 1}, {'N': 1, 'Fe': 0}, {'O': 1}]
    assert select(frame, 'element Ni') == [0]
    assert select(frame, 'element Cu Ni') == [0]
    assert select(frame, 'element Fe') == []


@pytest.mark.parametrize('text', ['', ' ', 'element', 'element Xx', 'element O,', 'element ,O',
    'index 0', 'orca 0', 'orca 6', 'index 5-2', 'index 1.5', 'index 1,', 'orca -1',
    'element O and', '(element O', 'element O)', 'within -1 of selected',
    'within nan of selected', 'within 1e999 of selected', 'within 3 of element O',
    'distance', 'distance < -2', 'all; none', 'not ' * 40 + 'all',
    "__import__('os').system('echo unsafe')", 'element O || element H'])
def test_invalid_input_is_rejected_without_modification(text):
    frame = molecule();positions = frame.positions.copy();reference = [0]
    with pytest.raises(ValueError):select(frame, text, reference)
    np.testing.assert_array_equal(frame.positions, positions)
    assert reference == [0]


def test_distance_requires_reference_even_in_short_circuited_branch():
    with pytest.raises(ValueError, match='reference atom'):
        select(molecule(), 'all or distance < 3', [])
    with pytest.raises(ValueError, match='outside'):
        select(molecule(), 'selected', [99])


def brute_nearest(frame, references, ranges):
    shifts = np.asarray(list(product(*ranges)), dtype=float) @ frame.cell
    return [min(float(np.linalg.norm(point - frame.positions[j] + shifts, axis=1).min())
                for j in references) for point in frame.positions]


@pytest.mark.parametrize('pbc', [(True, True, True), (True, True, False)])
def test_skew_nonreduced_cell_matches_independent_periodic_enumeration(pbc):
    cell = np.array([[2., 0, 0], [21., 1.8, 0], [9., 8., 3.]])
    frame = Frame(['H'] * 6, np.array([[.04, .06, .1], [.98, .96, .1], [.5, .5, .1],
                  [.02, .02, .9], [.7, .1, .3], [.1, .8, .8]]) @ cell, cell, pbc)
    ranges = (range(-30, 31), range(-8, 9), range(-3, 4) if pbc[2] else (0,))
    expected = np.array(brute_nearest(frame, [0, 3], ranges))
    for radius in (.2, .7, 1., 1.5, 2., 3.):
        assert select(frame, f'distance <= {radius}', [0, 3]) == np.flatnonzero(expected <= radius).tolist()
    # Images are disabled when the structure is nonperiodic.
    frame.pbc = (False, False, False)
    direct = np.linalg.norm(frame.positions[:, None] - frame.positions[[0, 3]][None], axis=2).min(axis=1)
    assert select(frame, 'within 1 of selected', [0, 3]) == np.flatnonzero(direct <= 1).tolist()


def test_periodic_distance_blocks_never_allocate_all_atom_pairs():
    import ase.geometry
    random = np.random.default_rng(123)
    frame = Frame(['H'] * 256, random.random((256, 3)) * 10, np.eye(3) * 10, (True,) * 3)
    sizes = [];original = ase.geometry.find_mic
    def tracked(vectors, *args, **kwargs):
        sizes.append(len(vectors))
        assert len(vectors) <= DISTANCE_PAIR_BLOCK
        return original(vectors, *args, **kwargs)
    with patch('ase.geometry.find_mic', side_effect=tracked):
        result = select(frame, 'distance < 2 and distance > .1', list(range(128)))
    assert len(sizes) >= 2 and max(sizes) <= DISTANCE_PAIR_BLOCK
    assert all(i >= 128 for i in result)


def test_cancelled_expression_returns_no_partial_selection():
    with pytest.raises(LoadCancelled):
        select(molecule(), 'all', [0], cancelled=lambda: True)


def test_expression_enter_uses_current_selection_and_invalid_input_keeps_undo(gui):
    gui.attach(molecule());window = gui.window;gui.select([0])
    panel = window.atoms_selection_panel
    previous = len(window.undo_stack)
    panel.expression_input.setText('element O and within 1.1 of selected')
    QTest.keyClick(panel.expression_input, Qt.Key.Key_Return)
    assert window.selection == [1] and len(window.undo_stack) == previous + 1
    window.undo_edit();assert window.selection == [0]
    previous = len(window.undo_stack)
    panel.expression_input.setText('index 99')
    QTest.keyClick(panel.expression_input, Qt.Key.Key_Return)
    assert window.selection == [0] and len(window.undo_stack) == previous
    assert not panel.expression_error.isHidden() and 'between 1 and 6' in panel.expression_error.text()
    panel.expression_input.setText('none')
    panel.expression_apply.click()
    assert window.selection == [] and panel.expression_error.isHidden()
    assert window.select_by_expression('distance < 3') is False
    assert window.selection == [] and 'reference atom' in panel.expression_error.text()


def test_expression_help_is_readonly_modeless_and_owned(gui):
    dialog = gui.window.show_selection_expression_help()
    gui.addCleanup(dialog.close)
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert not (dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    from PySide6.QtWidgets import QPlainTextEdit
    text = dialog.findChild(QPlainTextEdit)
    assert text.isReadOnly() and 'within 3.5 of selected' in text.toPlainText()
    assert 'index starts at 1' in text.toPlainText()
    assert 'orca' not in text.toPlainText().lower()


def test_expression_does_not_commit_if_source_changes_during_evaluation(gui):
    gui.attach(molecule());window = gui.window;gui.select([0])
    previous = len(window.undo_stack)
    def changed_source(parent, title, function, **kwargs):
        answer = function()
        window.frame.positions[1] = [99, 0, 0]
        return answer
    with patch('lele.operations.run_data_task', side_effect=changed_source):
        assert window.select_by_expression('within 1.1 of selected') is False
    assert window.selection == [0] and len(window.undo_stack) == previous


def test_cancelled_gui_expression_retains_selection_and_undo(gui):
    gui.attach(molecule());window = gui.window;gui.select([0])
    previous = len(window.undo_stack)
    with patch('lele.operations.run_data_task', side_effect=LoadCancelled()):
        assert window.select_by_expression('all') is False
    assert window.selection == [0] and len(window.undo_stack) == previous
