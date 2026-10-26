#!/usr/bin/env python3
"""Regression fixtures for Siesta geometry optimization and chemistry summary."""
import tempfile
from pathlib import Path
import unittest
import numpy as np

from lele.siesta_trajectory import read_siesta_output, load_siesta_history, read_siesta_ani, read_siesta_mde
from lele.structure_summary import molecular_formula, spin_summary, summary_text
from lele.core import Frame


EXAMPLE = '''Welcome to SIESTA
Species number: 1 Atomic number: 1 Label: H
Species number: 2 Atomic number: 8 Label: O
outcell: Unit cell vectors (Ang):
outcell: 8.0 0.0 0.0
outcell: 0.0 8.0 0.0
outcell: 0.0 0.0 8.0
siesta: Etot = -100.12345
outcoor: Atomic coordinates (Ang):
outcoor: 0.0 0.0 0.0 1 1 H
outcoor: 0.0 0.0 1.1 2 8 O

siesta: E_KS(eV) = -99.7
siesta: Etot = -100.45678
outcoor: Atomic coordinates (Ang):
outcoor: 0.0 0.0 0.1 1 1 H
outcoor: 0.0 0.0 1.0 2 8 O

siesta: Final energy
'''


class SiestaHistory(unittest.TestCase):
    def test_out_geometry_energy_and_cell(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'job.out'
            path.write_text(EXAMPLE)
            frames, note = read_siesta_output(path)
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0].symbols, ['H', 'O'])
            self.assertAlmostEqual(frames[1].positions[0, 2], .1)
            self.assertAlmostEqual(frames[1].energy_ev, -100.45678)
            self.assertEqual([f.energy_ev for f in frames], [-100.12345, -100.45678])
            self.assertTrue(np.allclose(frames[0].cell, np.eye(3) * 8))
            self.assertEqual(note, '')

    def test_ani_multiple_structures(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'test.ANI'
            p.write_text('2\nstep 1\nH 0 0 0\nO 0 0 1\n2\nstep 2\nH 0 0 .2\nO 0 0 1.1\n')
            self.assertEqual(len(read_siesta_ani(p)), 2)

    def test_bad_energy_count_not_fabricated(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'job.out'
            p.write_text(EXAMPLE.replace('siesta: Etot = -100.45678', 'siesta: SCF done'))
            frames, note = read_siesta_output(p)
            self.assertEqual(len(frames), 2)
            self.assertIsNone(frames[0].energy_ev)
            self.assertIn('counts differ', note)

    def test_ani_fallback_when_out_has_one_frame(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'job.out').write_text('Welcome to SIESTA\n' + EXAMPLE.split('siesta: E_KS')[0])
            (root / 'job.ANI').write_text('2\nfirst\nH 0 0 0\nO 0 0 1\n2\nsecond\nH 0 0 .2\nO 0 0 1.1\n')
            frames, note = load_siesta_history(root / 'job.out')
            self.assertEqual(len(frames), 2)
            self.assertIn('ANI', note)

    def test_mde_energy_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'job.out').write_text(EXAMPLE.split('siesta: E_KS')[0])
            (root / 'job.ANI').write_text('2\na\nH 0 0 0\nO 0 0 1\n2\nb\nH 0 0 .2\nO 0 0 1.1\n')
            (root / 'job.MDE').write_text('# Step T (K) E_KS (eV)E_tot (eV) Vol (A^3) P (kBar)\n0 0.0 -10.1 -10.2 10.0 0.0\n1 0.0 -10.3 -10.4 10.0 0.0\n')
            frames, note = load_siesta_history(root / 'job.out')
            self.assertEqual([f.energy_ev for f in frames], [-10.2, -10.4])
            self.assertTrue(all(f.pbc for f in frames))
            self.assertIn('per-step energies', note)

    def test_single_unrelated_ani_is_not_assumed_when_many_choices(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'job.out').write_text(EXAMPLE)
            for name in ('other.ANI', 'another.ANI'):
                (root / name).write_text('1\ntest\nH 0 0 0\n')
            frames, note = load_siesta_history(root / 'job.out')
            self.assertEqual(len(frames), 2)
            self.assertEqual(note, '')

    def test_mde_requires_explicit_columns(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'run.MDE'
            p.write_text('0 0.0 -11.0 -10.0\n')
            self.assertEqual(read_siesta_mde(p), [])

    def test_molecular_formula_and_spin(self):
        self.assertEqual(molecular_formula(['Cl'] * 9 + ['C'] + ['H'] * 20), 'C1H20Cl9')
        self.assertEqual(molecular_formula(['Li'] * 2 + ['O']), 'Li2O1')
        self.assertIn('Unknown', spin_summary({}))
        self.assertIn('Yes', spin_summary({'converter_mult': '2'}))
        self.assertIn('open-shell singlet', spin_summary({'converter_mult': '1'}))
        self.assertIn('Cell composition', summary_text(Frame(['Li', 'O'], np.zeros((2, 3)), np.eye(3), (True,)*3)))


if __name__ == '__main__':
    unittest.main()
