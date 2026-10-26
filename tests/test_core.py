#!/usr/bin/env python3
import math
import unittest
import numpy as np
from lele.core import Frame, find_bonds, unit_cell_edges, measure

class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.water = Frame(['O', 'H', 'H'], [[0,0,0], [.76,.59,0], [-.76,.59,0]])

    def test_geometry(self):
        self.assertEqual(len(find_bonds(self.water)), 2)
        name, d = measure(self.water, [0, 1])
        self.assertEqual(name, 'distance')
        self.assertAlmostEqual(d, math.hypot(.76, .59))
        name, a = measure(self.water, [1, 0, 2])
        self.assertTrue(100 < a < 105)

    def test_cell_edges(self):
        c = np.array([[3,0,0],[1,4,0],[0,0,6]], dtype=float)
        edges = unit_cell_edges(c)
        self.assertEqual(len(edges), 12)

    def test_dihedral(self):
        f = Frame(['C']*4, [[0,1,0], [0,0,0], [1,0,0], [1,0,1]])
        k, v = measure(f, [0,1,2,3])
        self.assertEqual(k, 'dihedral')
        self.assertAlmostEqual(abs(v), 90.0)

    def test_errors(self):
        with self.assertRaises(ValueError):
            measure(self.water, [0,0])
        with self.assertRaises(ValueError):
            Frame(['H'], [[1,2,3], [4,5,6]])

if __name__ == '__main__':
    unittest.main()
