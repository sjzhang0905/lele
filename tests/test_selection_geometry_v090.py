#!/usr/bin/env python3
"""Geometry invariants for fitted planes, rigid alignment and atom deletion."""
import unittest
import numpy as np

from lele.core import Frame, Volume, atom_label_texts
from lele.periodic_geometry import minimum_image
from lele.selection_geometry import (
    fit_selection_plane, align_plane_to_xy, delete_selected_atoms,
)


class PlaneGeometryTests(unittest.TestCase):
    def test_three_atoms_define_plane_without_changing_input(self):
        points = np.array([[0., 0., 2.], [2., 0., 4.], [0., 3., 8.]])
        frame = Frame(['C'] * 3, points.copy())
        plane = fit_selection_plane(frame, [0, 1, 2])
        expected = np.array([-1., -2., 1.]) / np.sqrt(6.)
        self.assertAlmostEqual(abs(plane.normal @ expected), 1., places=12)
        self.assertLess(plane.rms, 1.e-12)
        np.testing.assert_allclose((plane.corners - plane.center) @ plane.normal, 0., atol=1.e-12)
        np.testing.assert_array_equal(frame.positions, points)

    def test_nonplanar_fit_minimizes_orthogonal_residual_and_does_not_flatten(self):
        points = np.array([[-2., -2., .1], [2., -2., -.1],
                           [2., 2., .1], [-2., 2., -.1]]) + [1., 2., 3.]
        frame = Frame(['C'] * 4, points)
        plane = fit_selection_plane(frame, range(4))
        np.testing.assert_allclose(plane.normal, [0., 0., 1.], atol=1.e-12)
        self.assertAlmostEqual(plane.rms, .1)
        before_distances = np.linalg.norm(frame.positions[:, None] - frame.positions, axis=-1)
        rotation, _ = align_plane_to_xy(frame, plane)
        np.testing.assert_allclose(frame.positions[:, 2], [.1, -.1, .1, -.1], atol=1.e-12)
        np.testing.assert_allclose(np.linalg.norm(frame.positions[:, None] - frame.positions, axis=-1), before_distances)
        self.assertAlmostEqual(np.linalg.det(rotation), 1.)

    def test_periodic_boundary_fit_uses_nearest_images(self):
        cell = np.array([[10., 0., 0.], [1., 9., 0.], [.5, 1., 12.]])
        unwrapped = np.array([[9.5, 1., 1.], [10.5, 1., 2.], [9.5, 2., 3.], [10.5, 2., 4.]])
        wrapped = unwrapped.copy()
        wrapped[[1, 3]] -= cell[0]
        frame = Frame(['C'] * 4, wrapped, cell, (True, True, True))
        plane = fit_selection_plane(frame, range(4))
        np.testing.assert_allclose(plane.points, unwrapped, atol=1.e-12)
        self.assertLess(plane.rms, 1.e-12)
        raw = fit_selection_plane(frame, range(4), nearest_images=False)
        self.assertLess(abs(raw.normal @ plane.normal), .99)

    def test_alignment_rotates_periodic_cell_and_volume_and_preserves_geometry(self):
        frame = Frame(['C'] * 4, [[2., 1., 3.], [3., 1., 4.], [2., 2., 5.], [6., 3., 2.]],
                      [[10., 0., 0.], [1., 11., 0.], [1., 2., 12.]], (True, True, True))
        volume = Volume(np.ones((2, 2, 2)), [1., 2., 3.], np.diag([.1, .2, .3]))
        points, cell = frame.positions.copy(), frame.cell.copy()
        origin, voxels = volume.origin.copy(), volume.voxel_vectors.copy()
        old_delta = minimum_image(points[3] - points[0], frame)[0]
        plane = fit_selection_plane(frame, [0, 1, 2])
        rotation, translation = align_plane_to_xy(frame, plane, volume=volume)
        np.testing.assert_allclose(rotation @ rotation.T, np.eye(3), atol=1.e-12)
        self.assertAlmostEqual(np.linalg.det(rotation), 1., places=12)
        np.testing.assert_allclose(frame.positions[:3, 2], 0., atol=1.e-12)
        np.testing.assert_allclose(frame.cell @ frame.cell.T, cell @ cell.T, atol=1.e-11)
        np.testing.assert_allclose(frame.positions, points @ rotation.T + translation)
        np.testing.assert_allclose(volume.origin, origin @ rotation.T + translation)
        np.testing.assert_allclose(volume.voxel_vectors, voxels @ rotation.T)
        new_delta = minimum_image(frame.positions[3] - frame.positions[0], frame)[0]
        np.testing.assert_allclose(new_delta, old_delta @ rotation.T, atol=1.e-12)
        self.assertLess(fit_selection_plane(frame, [0, 1, 2]).rms, 1.e-12)

    def test_alignment_without_translation_uses_only_rotation(self):
        frame = Frame(['C'] * 3, [[0., 0., 5.], [1., 0., 6.], [0., 1., 7.]])
        points = frame.positions.copy()
        plane = fit_selection_plane(frame, range(3))
        rotation, translation = align_plane_to_xy(frame, plane, place_at_zero=False)
        np.testing.assert_array_equal(translation, np.zeros(3))
        np.testing.assert_allclose(frame.positions, points @ rotation.T)
        self.assertAlmostEqual(np.ptp(frame.positions[:, 2]), 0.)

    def test_collinear_selection_has_no_unique_plane(self):
        frame = Frame(['C'] * 4, [[0., 0., 0.], [1., 1., 1.], [2., 2., 2.], [0., 2., 0.]])
        for selection in ([0, 1], [0, 1, 1], [0, 1, 2]):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    fit_selection_plane(frame, selection)


class AtomDeletionTests(unittest.TestCase):
    def test_deletion_remaps_manual_bonds_and_preserves_poscar_block_numbering(self):
        frame = Frame(['Li'] * 4 + ['O'], np.arange(15.).reshape(5, 3), np.eye(3) * 20,
                      (True, True, True), -12., {'poscar_groups': [('Li', 2), ('Li', 2), ('O', 1)]},
                      bond_added={(0, 2), (1, 3), (3, 4)}, bond_removed={(2, 4)})
        old = frame.clone()
        self.assertEqual(delete_selected_atoms(frame, [0, 2]), 2)
        self.assertEqual(frame.symbols, ['Li', 'Li', 'O'])
        np.testing.assert_array_equal(frame.positions, old.positions[[1, 3, 4]])
        np.testing.assert_array_equal(frame.cell, old.cell)
        self.assertEqual(frame.bond_added, {(0, 1), (1, 2)})
        self.assertEqual(frame.bond_removed, set())
        self.assertEqual(frame.info['poscar_groups'], [('Li', 1), ('Li', 1), ('O', 1)])
        self.assertEqual(atom_label_texts(frame.symbols, 'VESTA (POSCAR groups)', frame.info['poscar_groups']), ['Li1', 'Li1', 'O1'])
        self.assertIsNone(frame.energy_ev)
        self.assertEqual(old.info['poscar_groups'], [('Li', 2), ('Li', 2), ('O', 1)])

    def test_delete_all_and_empty_selection(self):
        frame = Frame(['H', 'H'], [[0., 0., 0.], [1., 0., 0.]])
        self.assertEqual(delete_selected_atoms(frame, []), 0)
        self.assertEqual(delete_selected_atoms(frame, [0, 1]), 2)
        self.assertEqual(frame.positions.shape, (0, 3))
        self.assertEqual(frame.symbols, [])
        self.assertEqual(frame.clone().symbols, [])


if __name__ == '__main__':
    unittest.main()
