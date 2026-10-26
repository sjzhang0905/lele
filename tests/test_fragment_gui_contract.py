#!/usr/bin/env python3
"""Application gesture-handler tests without GUI dependencies."""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
import numpy as np
from lele.core import Frame
from lele.periodic_geometry import periodic_basis, periodic_fragment
from lele.fragment import (
    selected_fragments, apply_fragment_rotation, apply_fragment_translation,
    screen_rotation, screen_translation)


class Camera:
    def GetDirectionOfProjection(self): return (0.,0.,-1.)
    def GetViewUp(self): return (0.,1.,0.)
    def GetParallelProjection(self): return True
    def GetParallelScale(self): return 5.


class Dummy:
    def __init__(self):
        self.frame = Frame(['O','H','H','O','H','H'],
                           [[0,0,0],[.96,0,0],[-.24,.92,0],
                            [10,0,0],[10.96,0,0],[9.76,.92,0]])
        self.selection = [0]
        self.doc = SimpleNamespace(modified=False)
        self.renderer = SimpleNamespace(options=SimpleNamespace(bond_cutoff=1.18))
        self.scene = SimpleNamespace(GetActiveCamera=lambda: Camera())
        self.vtk = SimpleNamespace(height=lambda: 500)
        self._fragment_gesture = None
        self.undo_count = 0
        self.scene_count = 0
        self.table_count = 0
        self.selection_count = 0
        self._bar = SimpleNamespace(showMessage=lambda *_: None)
    def statusBar(self): return self._bar
    def _record_undo(self): self.undo_count += 1
    def _sync_selection_to_table(self): self.selection_count += 1
    def refresh_scene(self): self.scene_count += 1
    def _refresh_after_geometry_edit(self): self.table_count += 1


def handlers():
    app = Path(__file__).resolve().parents[1] / 'lele' / 'app.py'
    tree = ast.parse(app.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == 'LELEWindow')
    names = {'_fragment_begin','_fragment_move','_fragment_end','select_connected_fragment'}
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in names]
    space = {'selected_fragments': selected_fragments,
             'apply_fragment_rotation': apply_fragment_rotation,
             'apply_fragment_translation': apply_fragment_translation,
             'screen_rotation': screen_rotation,
             'screen_translation': screen_translation, 'periodic_basis': periodic_basis,
             'periodic_fragment': periodic_fragment, '__package__': 'lele'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), str(app), 'exec'),space)
    return space


class GestureApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name, method in handlers().items():
            if name in ('_fragment_begin','_fragment_move','_fragment_end','select_connected_fragment'):
                setattr(Dummy, name, method)

    def test_alt_rotation_changes_only_one_molecule_and_undo_once(self):
        win = Dummy()
        other = win.frame.positions[3:].copy()
        win._fragment_begin('orbit', 20, 20)
        win._fragment_move('orbit', 10, 0)
        win._fragment_move('orbit', 10, 0)
        win._fragment_end('orbit')
        self.assertEqual(win.selection,[0,1,2])
        self.assertEqual(win.undo_count,1)
        self.assertEqual(win.table_count,1)
        self.assertTrue(win.doc.modified)
        np.testing.assert_array_equal(win.frame.positions[3:],other)

    def test_middle_pan_preserves_other_molecule(self):
        win = Dummy()
        previous = win.frame.positions.copy()
        win._fragment_begin('pan', 20, 20)
        win._fragment_move('pan', 50, 0)
        win._fragment_end('pan')
        np.testing.assert_allclose(win.frame.positions[:3],previous[:3] + [1,0,0])
        np.testing.assert_array_equal(win.frame.positions[3:], previous[3:])

    def test_right_roll_and_no_drag_creates_no_undo(self):
        win = Dummy()
        win._fragment_begin('roll', 20, 20)
        win._fragment_end('roll')
        self.assertEqual(win.undo_count,0)
        win._fragment_begin('roll', 20, 20)
        win._fragment_move('roll', 90, 0)
        win._fragment_end('roll')
        self.assertEqual(win.undo_count,1)
        self.assertEqual(win.table_count,1)
        np.testing.assert_allclose(win.frame.positions[3:],
                                   [[10,0,0],[10.96,0,0],[9.76,.92,0]])

    def test_ctrl_g_expands_bond_components(self):
        win = Dummy()
        win.select_connected_fragment()
        self.assertEqual(win.selection,[0,1,2])
        self.assertEqual(win.undo_count,0)
        win.selection=[0,3]
        win.select_connected_fragment()
        self.assertEqual(win.selection,list(range(6)))
