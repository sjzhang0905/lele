#!/usr/bin/env python3
"""Parity, periodic close contacts, hydrogen bonds and finite-fragment previews."""
import unittest
import numpy as np

from lele.core import Frame
from lele.chemical_analysis import electron_parity, detect_hydrogen_bonds, short_contact_summary
from lele.periodic_geometry import periodic_fragment, periodic_bonds, short_contacts


class ChemicalPresentationTests(unittest.TestCase):
    def test_electron_parity_uses_net_charge(self):
        frame = Frame(['O', 'H'], [[0, 0, 0], [1, 0, 0]])
        self.assertIn('Odd (9 electrons', electron_parity(frame))
        frame.info['charge_override'] = 1
        self.assertIn('Even (8 electrons', electron_parity(frame))
        frame.info['charge_override'] = -1
        self.assertIn('Even (10 electrons', electron_parity(frame))

    def test_neutral_charge_assumption(self):
        frame = Frame(['H'], [[0, 0, 0]])
        self.assertIn('assumed charge 0', electron_parity(frame))

    def test_hbond_linear_three_atoms(self):
        frame = Frame(['O', 'H', 'O'], [[0, 0, 0], [.97, 0, 0], [2.83, 0, 0]])
        bonds = detect_hydrogen_bonds(frame)
        self.assertEqual(len(bonds), 1)
        self.assertEqual((bonds[0].donor, bonds[0].hydrogen, bonds[0].acceptor), (0, 1, 2))
        self.assertAlmostEqual(bonds[0].angle_deg, 180.0)

    def test_bent_non_hbond(self):
        frame = Frame(['O', 'H', 'O'], [[0, 0, 0], [.97, 0, 0], [.97, 2.2, 0]])
        self.assertEqual(detect_hydrogen_bonds(frame), [])

    def test_hbond_cross_boundary(self):
        frame = Frame(['O', 'H', 'O'], [[8.1, 0, 0], [9.07, 0, 0], [0.93, 0, 0]],
                      cell=np.eye(3) * 10, pbc=(True, True, True))
        bonds = detect_hydrogen_bonds(frame)
        self.assertEqual(len(bonds), 1)
        self.assertAlmostEqual(bonds[0].distance, 1.86)

    def test_short_contact_periodic(self):
        frame = Frame(['O', 'O'], [[9.88, 1, 1], [.18, 1, 1]],
                      cell=np.eye(3) * 10, pbc=(True, True, True))
        number, closest = short_contacts(frame)
        self.assertEqual(number, 1)
        self.assertAlmostEqual(closest[2], .30)
        self.assertIn('0.300', short_contact_summary(frame))

    def test_close_contacts_do_not_count_atom_own_images(self):
        frame = Frame(['H'], [[0, 0, 0]], cell=np.eye(3) * .5, pbc=(True, True, True))
        self.assertEqual(short_contacts(frame), (0, None))


class PeriodicFragmentTests(unittest.TestCase):
    def test_unwraps_water_crossing_boundary_without_changing_coordinates(self):
        frame = Frame(['O', 'H', 'H', 'O'],
                      [[9.7, 1, 1], [.58, 1, 1], [9.4, 1.89, 1], [5, 5, 5]],
                      cell=np.eye(3) * 10, pbc=(True, True, True))
        coords = frame.positions.copy()
        preview = periodic_fragment(frame, [0])
        self.assertEqual(preview.indices, [0, 1, 2])
        self.assertIn((1, 0, 0), preview.extra_tiles)
        self.assertAlmostEqual(np.linalg.norm(preview.image_positions[1] - preview.image_positions[0]), .88)
        np.testing.assert_array_equal(frame.positions, coords)

    def test_detects_infinite_periodic_network(self):
        frame = Frame(['O', 'O'], [[.5, 0, 0], [1.5, 0, 0]],
                      cell=np.eye(3) * 2, pbc=(True, True, True))
        with self.assertRaisesRegex(ValueError, 'infinite periodic network'):
            periodic_fragment(frame, [0])

    def test_manual_bond_removal_disconnects_periodic_fragment(self):
        frame = Frame(['O', 'H'], [[9.65, 0, 0], [.52, 0, 0]],
                      cell=np.eye(3) * 10, pbc=(True, True, True))
        self.assertEqual(periodic_fragment(frame, [0]).indices, [0, 1])
        frame.bond_removed.add((0, 1))
        self.assertEqual(periodic_fragment(frame, [0]).indices, [0])

    def test_nonperiodic_selection(self):
        frame = Frame(['O', 'H', 'He'], [[0,0,0], [.95,0,0], [4,0,0]])
        self.assertEqual(periodic_fragment(frame, [0]).indices, [0,1])


if __name__ == '__main__':
    unittest.main()

class PeriodicBondEditingTests(unittest.TestCase):
    def test_ctrl_b_respects_periodic_bond_then_removes_it(self):
        from lele.core import toggle_selected_bonds
        frame = Frame(['O', 'H'], [[9.65, 0, 0], [.52, 0, 0]],
                      cell=np.eye(3)*10, pbc=(True, True, True))
        self.assertEqual(toggle_selected_bonds(frame, [0,1])[0], 'removed')
        self.assertEqual(periodic_fragment(frame, [0]).indices, [0])
        self.assertEqual(toggle_selected_bonds(frame, [0,1])[0], 'added')
        self.assertEqual(periodic_fragment(frame, [0]).indices, [0, 1])

    def test_multi_atom_restore_periodic_bonds(self):
        from lele.core import toggle_selected_bonds
        frame = Frame(['O','H','H'], [[9.7,1,1],[.6,1,1],[9.4,1.9,1]],
                      cell=np.eye(3)*10, pbc=(True,True,True))
        self.assertEqual(periodic_fragment(frame,[0]).indices,[0,1,2])
        self.assertEqual(toggle_selected_bonds(frame,[0,1,2])[0],'removed')
        self.assertEqual(periodic_fragment(frame,[0]).indices,[0])
        self.assertEqual(toggle_selected_bonds(frame,[0,1,2])[0],'restored')
        self.assertEqual(periodic_fragment(frame,[0]).indices,[0,1,2])
