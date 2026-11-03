#!/usr/bin/env python3
"""Regression contract: camera-only view vs. explicit coordinate edits."""
import ast
import unittest
from pathlib import Path

import numpy as np

from lele.core import Frame, align_pair_to_axis, move_atom_to_origin
from lele.fragment import apply_fragment_rotation, apply_fragment_translation


class CoordinateFrameContractTests(unittest.TestCase):
    def test_xyz_rotates_complete_crystal_and_abc_is_explicit_fixed_cell_edit(self):
        cell = np.array([[4., 0., 0.], [1., 5., 0.], [0.5, 0.7, 6.]])
        points = np.array([[2., 1., 1.], [3., 3., 2.], [3., 4., 6.]])
        for axis in ('X', 'Y', 'Z', 'a', 'b', 'c'):
            with self.subTest(axis=axis):
                f = Frame(['C', 'O', 'H'], points.copy(), cell.copy(),
                          (True, True, True))
                old = f.clone()
                rot, pivot, changed_cell = align_pair_to_axis(f, 0, 1, axis)
                self.assertEqual(changed_cell,axis.isupper())
                np.testing.assert_allclose(f.cell,old.cell@rot.T if axis.isupper() else old.cell,atol=1.e-11)
                np.testing.assert_array_equal(f.positions[0], pivot)
                self.assertAlmostEqual(np.linalg.det(rot), 1., places=12)
                self.assertAlmostEqual(np.linalg.norm(f.positions[2]-f.positions[1]),
                                       np.linalg.norm(old.positions[2]-old.positions[1]))
                fractional = f.positions @ np.linalg.inv(f.cell)
                np.testing.assert_allclose(fractional @ f.cell, f.positions,
                                           atol=1e-11)
                target = np.eye(3)[('X','Y','Z').index(axis)] if axis.isupper() else cell['abc'.index(axis)]
                vec = f.positions[1] - f.positions[0]
                np.testing.assert_allclose(vec / np.linalg.norm(vec),
                                           target / np.linalg.norm(target), atol=1e-11)

    def test_origin_only_translates_atoms_and_preserves_cell(self):
        cell = np.array([[3.1, 0., 0.], [0.5, 4.2, 0.], [0., 0., 5.3]])
        f = Frame(['Fe','O'], [[2,3,4], [3,4,5]], cell, (True,True,True))
        old_cell = f.cell.copy()
        move_atom_to_origin(f, 1)
        np.testing.assert_array_equal(f.cell, old_cell)
        np.testing.assert_allclose(f.positions[1], [0,0,0])

    def test_fragment_transform_changes_only_fragment_positions(self):
        cell = np.diag([10., 11., 12.])
        f = Frame(['O','H','O'], [[2,2,2],[3,2,2],[7,7,7]],cell,(True,True,True))
        frozen_cell = f.cell.copy()
        frozen_other = f.positions[2].copy()
        R = np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
        apply_fragment_rotation(f,[0,1],R,[2.,2.,2.])
        apply_fragment_translation(f,[0,1],[1.,2.,0.])
        np.testing.assert_array_equal(f.cell, frozen_cell)
        np.testing.assert_array_equal(f.positions[2], frozen_other)

    def test_view_methods_do_not_modify_frame_geometry(self):
        # Check API-level separation: camera controls must not invoke geometry editors.
        app = Path(__file__).resolve().parents[1] / 'lele' / 'app.py'
        tree = ast.parse(app.read_text(encoding='utf-8'))
        window = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                      and x.name == 'LELEWindow')
        controls = ('reset_camera','align_camera','isometric_view')
        geometry_methods = {'align_pair_to_axis','move_atom_to_origin',
                            'apply_fragment_rotation','apply_fragment_translation'}
        for method in controls:
            func = next(x for x in window.body if isinstance(x, ast.FunctionDef)
                        and x.name == method)
            called = {x.func.id for x in ast.walk(func)
                      if isinstance(x, ast.Call) and isinstance(x.func, ast.Name)}
            self.assertTrue(called.isdisjoint(geometry_methods), method)

    def test_alignment_blocks_volume_grids_in_all_six_modes(self):
        app = Path(__file__).resolve().parents[1] / 'lele' / 'app.py'
        tree = ast.parse(app.read_text(encoding='utf-8'))
        cls = next(x for x in tree.body if isinstance(x, ast.ClassDef)
                   and x.name == 'LELEWindow')
        fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef)
                  and x.name == 'align_selected_pair')
        guards = [x for x in ast.walk(fn) if isinstance(x, ast.If)]
        self.assertTrue(any('self.doc.volume is not None' in ast.unparse(x.test)
                            for x in guards))


if __name__ == '__main__':
    unittest.main()
