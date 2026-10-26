#!/usr/bin/env python3
"""POSCAR block-aware VESTA labels, including repeated chemical symbols."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from lele.core import atom_label_texts
from lele.poscar_labels import read_poscar_groups


class PoscarBlockTests(unittest.TestCase):
    def test_repeated_identical_symbols_reset_at_group_boundary(self):
        syms = ['Li'] * 15 + ['Fe'] * 14 + ['Zr'] + ['P'] * 16 + ['O'] * 64
        groups = [('Li', 10), ('Li', 5), ('Fe', 14), ('Zr', 1), ('P', 16), ('O', 64)]
        labels = atom_label_texts(syms, 'VESTA (POSCAR groups)', groups)
        self.assertEqual(labels[:10], ['Li' + str(i) for i in range(1, 11)])
        self.assertEqual(labels[10:15], ['Li' + str(i) for i in range(1, 6)])
        self.assertEqual(labels[15], 'Fe1')
        self.assertEqual(labels[28], 'Fe14')
        self.assertEqual(labels[29], 'Zr1')
        self.assertEqual(labels[-1], 'O64')
        self.assertEqual(atom_label_texts(syms, 'Element + index (global)')[14], 'Li15')

    def test_read_user_example_poscar_header(self):
        syms = ['Li'] * 15 + ['Fe'] * 14 + ['Zr'] + ['P'] * 16 + ['O'] * 64
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'POSCAR'
            path.write_text('Synthetic example\n1.0\n1 0 0\n0 1 0\n0 0 1\nLi Li Fe Zr P O\n10 5 14 1 16 64\n')
            groups = read_poscar_groups(path, syms)
            self.assertEqual(groups, [('Li', 10), ('Li', 5), ('Fe', 14), ('Zr', 1), ('P', 16), ('O', 64)])
            self.assertIsNone(read_poscar_groups(path, syms[:-1]))

    def test_no_invented_crystal_sites_without_metadata(self):
        self.assertEqual(atom_label_texts(['O', 'O', 'O'], 'VESTA (POSCAR groups)'), ['O1', 'O2', 'O3'])
        with self.assertRaises(ValueError):
            atom_label_texts(['Li','Li'], 'VESTA (POSCAR groups)', [('Li',1)])


if __name__ == '__main__':
    unittest.main()
