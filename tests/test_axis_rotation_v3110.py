"""Axis edits preserve selected topology and fixed atoms, including cell images."""
from unittest.mock import patch

import numpy as np
import pytest

from lele.axis_rotation import plan_axis_rotation
from lele.core import Frame, measure
from test_periodic_fragment_ui_v171 import gui


def molecule():
    return Frame(['C'] * 6,
                 [[0, 1.4, 0], [0, 0, 0], [1.4, 0, 0],
                  [1.4, 1.4, 1], [2.8, 0, 0], [9, 9, 9]],
                 energy_ev=-20.,
                 bond_snapshot=frozenset({(0, 1), (1, 2), (2, 3), (2, 4)}))


def distances(frame, edges=None):
    edges = edges if edges is not None else [(i, j, (0, 0, 0)) for i, j in frame.bond_snapshot]
    return {(i, j): np.linalg.norm(frame.positions[j] + np.asarray(s) @ frame.cell - frame.positions[i])
            for i, j, s in edges}


@pytest.mark.parametrize('selection,moving', [([1, 2], [3, 4]), ([2, 1], [0]),
                                            ([0, 5, 3], [1, 2, 3, 4]),
                                            ([1, 2, 3, 5], [3, 5])])
def test_axis_branch_selection_preserves_all_bonds_and_fixed_coordinates(selection, moving):
    frame = molecule()
    original = frame.positions.copy()
    old_lengths = distances(frame)
    edit = plan_axis_rotation(frame, selection, 73.)
    assert edit.moving == moving
    np.testing.assert_array_equal(frame.positions, original)
    fixed = sorted(set(range(6)) - set(moving))
    np.testing.assert_array_equal(edit.positions[fixed], original[fixed])
    frame.positions = edit.positions
    for edge, length in distances(frame).items():
        assert length == pytest.approx(old_lengths[edge])


def test_positive_angle_follows_directed_axis_right_hand_rule():
    frame = molecule()
    before = measure(frame, [0, 1, 2, 3])[1]
    frame.positions = plan_axis_rotation(frame, [1, 2], 60).positions
    after = measure(frame, [0, 1, 2, 3])[1]
    assert (after - before + 180) % 360 - 180 == pytest.approx(60.)


def test_two_atom_ring_ambiguity_requires_explicit_moving_seed():
    frame = molecule()
    frame.bond_snapshot |= {(0, 3)}
    original = frame.positions.copy()
    with pytest.raises(ValueError, match='ring|bond path'):
        plan_axis_rotation(frame, [1, 2], 60.)
    np.testing.assert_array_equal(frame.positions, original)
    old_lengths = distances(frame)
    edit = plan_axis_rotation(frame, [1, 2, 3], 60.)
    assert edit.moving == [0, 3]
    frame.positions = edit.positions
    for edge, length in distances(frame).items():
        assert length == pytest.approx(old_lengths[edge])


def test_nonbonded_axis_uses_second_atoms_component_and_keeps_axis_fixed():
    frame = Frame(['He', 'C', 'H', 'H'],
                  [[0, 0, 0], [0, 0, 5], [1, 0, 5], [2, 0, 5]],
                  bond_snapshot=frozenset({(1, 2), (2, 3)}))
    edit = plan_axis_rotation(frame, [0, 1], 90)
    assert edit.moving == [2, 3]
    np.testing.assert_array_equal(edit.positions[:2], frame.positions[:2])
    np.testing.assert_allclose(edit.positions[2:], [[0, 1, 5], [0, 2, 5]], atol=1.e-12)


def test_explicit_branch_can_attach_to_both_ends_of_nonbonded_axis():
    frame = Frame(['C'] * 4, [[0, 0, 0], [0, 0, 3], [1, 0, 1.5], [1, 0, 4]],
                  bond_snapshot=frozenset({(0, 2), (1, 2), (1, 3)}))
    original = frame.positions.copy()
    lengths = distances(frame)
    with pytest.raises(ValueError, match='ring|bond path'):
        plan_axis_rotation(frame, [0, 1], 90)
    edit = plan_axis_rotation(frame, [0, 1, 2], 90)
    assert edit.moving == [2]
    np.testing.assert_array_equal(edit.positions[[0, 1, 3]], original[[0, 1, 3]])
    np.testing.assert_allclose(edit.positions[2], [0, 1, 1.5], atol=1.e-12)
    frame.positions = edit.positions
    assert distances(frame) == pytest.approx(lengths)


@pytest.mark.parametrize('selection,angle', [([1], 20), ([1, 1], 20), ([1, 6], 20),
                                            ([1, 2], float('nan')), ([5, 0], float('inf'))])
def test_bad_input_rejects_without_mutation(selection, angle):
    frame = molecule()
    original = frame.positions.copy()
    with pytest.raises(ValueError):
        plan_axis_rotation(frame, selection, angle)
    np.testing.assert_array_equal(frame.positions, original)


def periodic_molecule():
    return Frame(['C', 'C', 'H', 'He'],
                 [[.1, 0, 0], [9.5, 0, 0], [9.6, .8, 0], [5, 5, 5]],
                 np.eye(3) * 10, (True,) * 3,
                 bond_snapshot=frozenset({(0, 1), (1, 2)}),
                 periodic_bond_snapshot=((0, 1, (-1, 0, 0)), (1, 2, (0, 0, 0))),
                 hbond_added={(2, 3): (0, 0, 0)})


def test_periodic_axis_keeps_images_and_cell_consistent_across_successive_edits():
    frame = periodic_molecule()
    original = frame.clone()
    old_lengths = distances(frame, frame.periodic_bond_snapshot)
    for angle in (90, -32, 75):
        edit = plan_axis_rotation(frame, [0, 1], angle)
        assert edit.moving == [2]
        frame.positions = edit.positions
        frame.periodic_bond_snapshot = edit.periodic_edges
        frame.hbond_added = edit.hbond_added
        for edge, length in distances(frame, frame.periodic_bond_snapshot).items():
            assert length == pytest.approx(old_lengths[edge])
        np.testing.assert_array_equal(frame.positions[[0, 1, 3]], original.positions[[0, 1, 3]])
        np.testing.assert_array_equal(frame.cell, original.cell)
    assert frame.hbond_added[(2, 3)] == (-1, 0, 0)


def test_periodic_rebasing_is_independent_of_the_original_coordinate_wrapping():
    frame = periodic_molecule()
    original = frame.clone()
    # Shift only the first atom's stored representative by a lattice vector,
    # keeping the same physical edge. The rotation must be equivalent modulo
    # whole-cell translations and preserve annotation ownership/shifts.
    frame.positions[0] += [10, 0, 0]
    frame.periodic_bond_snapshot = ((0, 1, (0, 0, 0)), (1, 2, (0, 0, 0)))
    frame.hbond_added = {(0, 2): (0, 0, 0), (2, 3): (0, 0, 0)}
    edit = plan_axis_rotation(frame, [0, 1], 90)
    reference = plan_axis_rotation(original, [0, 1], 90)
    np.testing.assert_allclose(edit.positions[2], reference.positions[2] + [10, 0, 0], atol=1.e-12)
    assert edit.hbond_added == frame.hbond_added  # No rebasing required in this representation.
    assert reference.hbond_added[(2, 3)] == (-1, 0, 0)


@pytest.mark.parametrize('edge,message', [((2, 2, (1, 0, 0)), 'infinite periodic'),
                                        ((0, 1, (0, 0, 0)), 'multiple periodic images'),
                                        ((1, 2, (1, 0, 0)), 'different periodic images')])
def test_periodic_network_cannot_be_stretched(edge, message):
    frame = periodic_molecule()
    frame.periodic_bond_snapshot += (edge,)
    with pytest.raises(ValueError, match=message):
        plan_axis_rotation(frame, [0, 1], 60.)


def test_gui_axis_rotation_updates_one_frame_preserves_bonds_and_undo(gui):
    frame = molecule()
    other = frame.clone()
    gui.attach(frame, second_frame=other)
    w = gui.window
    gui.select([1, 2])
    original = frame.clone()
    assert w.apply_axis_rotation(90.)
    assert len(w.undo_stack) == 1 and w.doc.modified and w.frame.energy_ev is None
    assert w.frame.bond_snapshot == original.bond_snapshot
    np.testing.assert_array_equal(other.positions, original.positions)
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions, original.positions)
    assert w.frame.energy_ev == -20. and w.selection == [1, 2]
    assert not w.apply_axis_rotation(360.) and not w.undo_stack


def test_gui_dihedral_target_and_rejected_ring(gui):
    frame = molecule()
    gui.attach(frame)
    w = gui.window
    gui.select([0, 1, 2, 3])
    assert w.apply_selected_dihedral(-65.)
    assert measure(w.frame, [0, 1, 2, 3])[1] == pytest.approx(-65.)
    w.undo_edit()
    frame = w.frame
    frame.bond_snapshot |= {(0, 3)}
    original = frame.positions.copy()
    with patch('lele.selection_actions.QMessageBox.warning') as warning:
        assert not w.apply_selected_dihedral(50.)
    warning.assert_called_once()
    np.testing.assert_array_equal(frame.positions, original)
    assert not w.undo_stack


def test_index_editor_is_one_based_and_respects_readonly(gui):
    from lele.structure_edit_dialogs import AtomIndexDialog
    dialog = AtomIndexDialog(molecule(), 2, [1, 2], parent=gui.window)
    assert dialog.index.value() == 3 and not hasattr(dialog, 'orca_index')
    dialog.index.setValue(1)
    assert dialog.index.value() == 1
    dialog.index.setValue(6)
    assert dialog.index.value() == 6
    assert 'ORCA' not in dialog.swap_button.text()
    dialog.close()
    dialog = AtomIndexDialog(molecule(), 2, editable=False, parent=gui.window)
    assert not dialog.index.isEnabled()
    dialog.close()
