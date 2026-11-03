#!/usr/bin/env python3
"""Regression cases for frame-local bond/coordinate editing (no Qt required)."""
import unittest
import numpy as np
from lele.core import (
    Frame, visible_bonds, toggle_selected_bonds, move_atom_to_origin,
    rotation_between_vectors, align_pair_to_axis,
)


class EditorTests(unittest.TestCase):
    def test_pair_bond_toggle_without_distance_limit(self):
        f = Frame(['C', 'C', 'H'], [[0, 0, 0], [20, 0, 0], [20.8, 0, 0]])
        external = (1, 2)
        self.assertIn(external, visible_bonds(f))
        self.assertNotIn((0, 1), visible_bonds(f))
        self.assertEqual(toggle_selected_bonds(f, [0, 1]), ('added', 1))
        self.assertIn((0, 1), visible_bonds(f))
        self.assertIn(external, visible_bonds(f))
        self.assertEqual(toggle_selected_bonds(f, [1, 0]), ('removed', 1))
        self.assertNotIn((0, 1), visible_bonds(f))
        self.assertIn(external, visible_bonds(f))

    def test_multi_toggle_removes_all_internal_and_restores_distances_only(self):
        f = Frame(['C'] * 5, [[0, 0, 0], [1.2, 0, 0], [0, 1.2, 0],
                              [3.5, 0, 0], [3.5, 1.2, 0]])
        original = set(visible_bonds(f))
        subset = {0, 1, 2}
        internal = {p for p in original if set(p) <= subset}
        external = original - internal
        self.assertEqual(len(internal), 3)
        self.assertEqual(toggle_selected_bonds(f, [0, 1, 2]), ('removed', 3))
        self.assertEqual(set(visible_bonds(f)), external)
        self.assertEqual(toggle_selected_bonds(f, [0, 1, 2]), ('restored', 3))
        self.assertEqual(set(visible_bonds(f)), original)
        # Force a far bond within selection, then clear; it won't be
        # automatically recreated unless within default bond cutoff.
        f.positions[2] = [12, 0, 0]
        toggle_selected_bonds(f, [0, 2])
        self.assertIn((0, 2), visible_bonds(f))
        toggle_selected_bonds(f, [0, 1, 2])
        self.assertNotIn((0, 2), visible_bonds(f))
        toggle_selected_bonds(f, [0, 1, 2])
        self.assertNotIn((0, 2), visible_bonds(f))

    def test_clone_isolates_bonds_and_positions_for_undo(self):
        f = Frame(['C', 'H'], [[3, 4, 5], [4, 4, 5]])
        old = f.clone()
        toggle_selected_bonds(f, [0, 1])
        move_atom_to_origin(f, 0)
        self.assertFalse(np.array_equal(f.positions, old.positions))
        self.assertNotEqual(visible_bonds(f), visible_bonds(old))
        self.assertFalse(old.bond_added or old.bond_removed)

    def test_origin_translation_and_distances(self):
        f = Frame(['H', 'O', 'H'], [[1, 2, 3], [4, 5, 6], [9, 8, 7]],
                  cell=np.diag([12., 13., 14.]), pbc=(True, True, True))
        original_positions = f.positions.copy()
        original_cell = f.cell.copy()
        move = move_atom_to_origin(f, 1)
        np.testing.assert_allclose(f.positions[1], np.zeros(3), atol=1e-12)
        np.testing.assert_allclose(move, -original_positions[1])
        np.testing.assert_allclose(f.positions[2] - f.positions[0],
                                   original_positions[2] - original_positions[0])
        np.testing.assert_allclose(f.cell, original_cell)

    def test_xyz_alignment_preserves_distances_and_rotates_lattice(self):
        cell = np.array([[3., 0., 0.], [1., 4., 0.], [0., 0., 5.]])
        f = Frame(['O', 'C', 'H'], [[2, 3, 1], [2, 4, 1], [3, 5, 6]],
                  cell=cell, pbc=(True, True, True))
        original = f.positions.copy()
        pivot_before = f.positions[0].copy()
        R, pivot, rotated_cell = align_pair_to_axis(f, 0, 1, 'X')
        self.assertTrue(rotated_cell)
        np.testing.assert_allclose(pivot, pivot_before)
        np.testing.assert_allclose(f.positions[0], pivot_before)
        np.testing.assert_allclose((f.positions[1] - f.positions[0]) / 1., [1., 0., 0.], atol=1e-11)
        self.assertAlmostEqual(np.linalg.det(R), 1., places=11)
        np.testing.assert_allclose(f.cell, cell@R.T,atol=1.e-12)
        self.assertAlmostEqual(np.linalg.norm(f.positions[2] - f.positions[1]),
                               np.linalg.norm(original[2] - original[1]))

    def test_abc_alignment_uses_nonorthogonal_lattice_direction_and_keeps_cell(self):
        cell = np.array([[3, 0, 0], [1, 4, 0], [1, 2, 5]], float)
        f = Frame(['O', 'O'], [[0, 0, 0], [0, 0, 2]], cell=cell, pbc=(True, True, True))
        R, pivot, rotated_cell = align_pair_to_axis(f, 0, 1, 'b')
        self.assertFalse(rotated_cell)
        np.testing.assert_allclose(f.cell, cell)
        direction = f.positions[1] - f.positions[0]
        np.testing.assert_allclose(direction / np.linalg.norm(direction),
                                   cell[1] / np.linalg.norm(cell[1]), atol=1e-12)

    def test_antiparallel_rotation_is_proper(self):
        R = rotation_between_vectors([1, 0, 0], [-2, 0, 0])
        np.testing.assert_allclose(R @ [1, 0, 0], [-1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(R), 1.0)

    def test_invalid_cases_and_no_external_bond_changes(self):
        f = Frame(['H', 'H', 'H'], [[0, 0, 0], [0, 0, 0], [2, 2, 2]])
        for selection in ([], [0]):
            with self.assertRaises(ValueError):
                toggle_selected_bonds(f, selection)
        with self.assertRaises(ValueError):
            toggle_selected_bonds(f, [1, 1])
        with self.assertRaises(ValueError):
            align_pair_to_axis(f, 0, 1, 'Z')
        with self.assertRaises(ValueError):
            align_pair_to_axis(f, 0, 2, 'a')
        with self.assertRaises(ValueError):
            rotation_between_vectors([0, 0, 0], [1, 0, 0])
