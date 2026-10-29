"""Geometry, topology and export checks for real periodic supercells."""
from itertools import product
from pathlib import Path
import tempfile
import unittest

import numpy as np

from lele.atom_appearance import AtomAppearance
from lele.core import Frame
from lele.periodic_geometry import periodic_bonds
from lele.supercell import make_supercell, validate_repeats


class SupercellTests(unittest.TestCase):
    def test_skew_lattice_fractional_coordinates_and_density(self):
        cell = np.array([[3., 0, 0], [.7, 4, 0], [.5, .9, 5]])
        fractional = np.array([[.1, .2, .3], [.8, .6, .5]])
        source = Frame(['Si', 'O'], fractional @ cell, cell, (True, True, True), -12.)
        expanded = make_supercell(source, (2, 3, 1))
        self.assertEqual(expanded.symbols, source.symbols * 6)
        np.testing.assert_allclose(expanded.cell, np.diag([2, 3, 1]) @ cell)
        actual = expanded.positions @ np.linalg.inv(expanded.cell)
        expected = np.concatenate([(fractional + tile) / [2, 3, 1]
                                   for tile in product(range(2), range(3), range(1))])
        np.testing.assert_allclose(actual, expected, atol=1e-14)
        self.assertAlmostEqual(abs(np.linalg.det(expanded.cell)), abs(np.linalg.det(cell)) * 6)
        self.assertIsNone(expanded.energy_ev)
        np.testing.assert_allclose(source.positions, fractional @ cell)
        self.assertEqual(source.energy_ev, -12.)

    def test_wrapping_only_periodic_directions_and_optional_unwrapped_input(self):
        source = Frame(['C'], [[-1., 8., 13.]], np.diag([4., 5., 10.]), (True, True, False))
        wrapped = make_supercell(source, (2, 1, 1))
        np.testing.assert_allclose(wrapped.positions, [[3, 3, 13], [7, 3, 13]])
        unwrapped = make_supercell(source, (2, 1, 1), wrap=False)
        np.testing.assert_allclose(unwrapped.positions, [[-1, 8, 13], [3, 8, 13]])
        self.assertEqual(wrapped.pbc, source.pbc)
        with self.assertRaises(ValueError):make_supercell(source, (1, 1, 2))

    def test_per_atom_styles_group_order_charge_and_independent_metadata(self):
        style = AtomAppearance(color='#126abc', opacity=.35, label_mode='Custom', label_text='site')
        source = Frame(['Li', 'O'], [[0, 0, 0], [2, 0, 0]], np.eye(3) * 5, (True,) * 3,
                       -9., {'converter_charge': 1, 'converter_mult': 2,
                             'poscar_groups': [('Li', 1), ('O', 1)], 'nested': {'x': [1]}},
                       atom_appearance={1: style})
        result = make_supercell(source, (2, 2, 1))
        self.assertEqual(result.atom_appearance, {i: style for i in (1, 3, 5, 7)})
        self.assertEqual(result.info['converter_charge'], 4)
        self.assertNotIn('converter_mult', result.info)
        self.assertEqual(result.info['poscar_groups'], source.info['poscar_groups'] * 4)
        result.info['nested']['x'].append(2)
        self.assertEqual(source.info['nested']['x'], [1])
        result.atom_appearance.clear()
        self.assertEqual(source.atom_appearance, {1: style})

    def test_cross_boundary_manual_bonds_map_to_image_not_same_tile(self):
        source = Frame(['H', 'H'], [[.1, 0, 0], [3.9, 0, 0]], np.eye(3) * 4,
                       (True,) * 3, bond_added={(0, 1)})
        result = make_supercell(source, (2, 1, 1))
        self.assertEqual(result.bond_added, {(0, 3), (1, 2)})
        self.assertEqual(source.bond_added, {(0, 1)})
        # Translating a source atom by a whole cell must preserve the actual
        # image path even when the caller chooses not to wrap coordinates.
        source.positions[1, 0] += 4.
        raw = make_supercell(source, (2, 1, 1), wrap=False)
        self.assertEqual(raw.bond_added, {(0, 1), (2, 3)})

    def test_removed_bonds_remain_removed_across_supercell_seams(self):
        source = Frame(['C', 'C'], [[.4, 0, 0], [3.6, 0, 0]], np.eye(3) * 4,
                       (True,) * 3, bond_removed={(0, 1)})
        result = make_supercell(source, (3, 1, 1))
        self.assertTrue({(0, 5), (1, 2), (3, 4)}.issubset(result.bond_removed))
        self.assertEqual(periodic_bonds(result), [])

    def test_validation_and_identity_repeat(self):
        frame = Frame(['Si'], [[0, 0, 0]], np.eye(3) * 3, (True,) * 3, -3.)
        for repeat in [(0, 1, 1), (-1, 2, 1), (1.5, 1, 1), (True, 1, 1), (2, 2), (100, 100, 100)]:
            with self.subTest(repeat=repeat), self.assertRaises(ValueError):make_supercell(frame, repeat)
        self.assertEqual(validate_repeats(frame, (np.int64(2), 1, 1)), (2, 1, 1))
        same = make_supercell(frame, (1, 1, 1))
        self.assertIsNot(same, frame)
        self.assertEqual(same.energy_ev, -3.)
        for bad in [Frame(['H'], [[0, 0, 0]]), Frame(['H'], [[0, 0, 0]], np.zeros((3, 3)), (True,) * 3)]:
            with self.assertRaises(ValueError):make_supercell(bad, (2, 1, 1))

    def test_export_poscar_and_cif_roundtrip_has_real_supercell(self):
        from lele.formats import export_frame, load_document
        cell = np.array([[3., 0, 0], [.5, 4, 0], [.2, .3, 5]])
        source = Frame(['Si', 'Si'], [[.1, .2, .3], [1.7, 2.1, 3.2]], cell, (True,) * 3)
        expanded = make_supercell(source, (2, 3, 1))
        with tempfile.TemporaryDirectory() as directory:
            for name, target in [('POSCAR', 'poscar-direct'), ('supercell.cif', 'cif')]:
                with self.subTest(target=target):
                    path = Path(directory) / name
                    export_frame(expanded, path, target)
                    loaded = load_document(path).frames[0]
                    self.assertEqual(len(loaded.symbols), 12)
                    np.testing.assert_allclose(loaded.cell @ loaded.cell.T, expanded.cell @ expanded.cell.T,
                                               rtol=2e-7, atol=2e-7)
                    self.assertAlmostEqual(abs(np.linalg.det(loaded.cell)), abs(np.linalg.det(cell)) * 6, places=5)


if __name__ == '__main__':
    unittest.main()
