#!/usr/bin/env python3
"""Integration tests run on the target Windows environment after ASE install."""
import importlib.util
import unittest
from pathlib import Path

HAS_ASE = importlib.util.find_spec('ase') is not None

@unittest.skipUnless(HAS_ASE, 'Requires ASE package (installed by start_windows.bat)')
class ParserIntegration(unittest.TestCase):
    examples = Path(__file__).resolve().parents[1] / 'examples'

    def test_xyz_trajectory(self):
        from lele.formats import load_document
        doc = load_document(self.examples / 'water_trajectory.xyz')
        self.assertEqual(len(doc.frames), 3)
        self.assertEqual(len(doc.frames[0].symbols), 3)

    def test_gaussian_input(self):
        from lele.formats import load_document
        doc = load_document(self.examples / 'water.gjf')
        self.assertEqual(len(doc.frames[0].symbols), 3)

    def test_poscar(self):
        from lele.formats import load_document
        doc = load_document(self.examples / 'Si_POSCAR')
        self.assertEqual(len(doc.frames[0].symbols), 8)

    def test_cube(self):
        from lele.formats import load_document
        doc = load_document(self.examples / 'artificial_signed_field.cube')
        self.assertIsNotNone(doc.volume, doc.note)
        self.assertEqual(doc.volume.data.shape, (24,24,24))

if __name__ == '__main__':
    unittest.main()
