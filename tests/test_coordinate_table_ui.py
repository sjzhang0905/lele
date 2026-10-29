#!/usr/bin/env python3
"""Coordinate rendering and geometry-edit UI logic without a display server."""
from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path
import unittest
import numpy as np
from lele.core import Frame, coordinate_table_rows, move_atom_to_origin, align_pair_to_axis


APP_PATH = Path(__file__).resolve().parents[1] / 'lele' / 'app.py'


class FakeItem:
    def __init__(self, value=''):
        self.value = value
        self.bits = 7

    def setText(self, value):
        self.value = value

    def text(self):
        return self.value

    def flags(self):
        return self.bits

    def setFlags(self, value):
        self.bits = value


class FakeTable:
    def __init__(self):
        self.cells = {}
        self.row_count = 0
        self.updates = True
        self.scrolled_to = None
        self.paint_count = 0

    def setUpdatesEnabled(self, value):
        self.updates = value

    def setRowCount(self, count):
        self.row_count = count
        self.cells = {k: v for k, v in self.cells.items() if k[0] < count}

    def item(self, row, column):
        return self.cells.get((row, column))

    def setItem(self, row, column, item):
        self.cells[row, column] = item

    def viewport(self):
        return self

    def update(self):
        self.paint_count += 1

    def scrollToItem(self, item):
        self.scrolled_to = item

    def values(self):
        return [tuple(self.item(i, j).text() for j in range(4)) for i in range(self.row_count)]


class FakeTabs:
    def __init__(self):
        self.current = None

    def setCurrentWidget(self, item):
        self.current = item


class FakeQt:
    class ItemFlag:
        ItemIsEditable = 1


class FakeCombo:
    def __init__(self):
        self.items = []
        self.current = ''

    def currentText(self): return self.current
    def clear(self): self.items = []; self.current = ''
    def addItems(self, items): self.items.extend(items)
    def setCurrentText(self, text): self.current = text


class DummyWindow:
    def _alignment_enabled(self):
        return False

    def __init__(self, frame):
        self.frame = frame
        self.atom_table = FakeTable()
        self.tabs = FakeTabs()
        self.selection = []
        self.scene_updates = 0
        self.info_updates = 0
        self._ignore_table = False
        self._active_vibration = None
        self.element_combo = FakeCombo()

    def _sync_selection_to_table(self):
        self.selection_synced = list(self.selection)

    def refresh_scene(self):
        self.scene_updates += 1

    def _refresh_info(self):
        self.info_updates += 1


def extracted_methods():
    tree = ast.parse(APP_PATH.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LELEWindow')
    wanted = {'_refresh_coordinates', '_refresh_after_geometry_edit', '_refresh_element_choices'}
    methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert len(methods) == len(wanted)
    namespace = {'__name__': 'lele.app', '__package__': 'lele',
                 'QSignalBlocker': lambda obj: nullcontext(), 'QTableWidgetItem': FakeItem, 'Qt': FakeQt}
    compiled = compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), str(APP_PATH), 'exec')
    exec(compiled, namespace)
    return namespace


class CoordinateUIRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        methods = extracted_methods()
        for name in ('_refresh_coordinates', '_refresh_after_geometry_edit', '_refresh_element_choices'):
            setattr(DummyWindow, name, methods[name])

    def test_translation_updates_coordinate_cells_and_keeps_selection(self):
        frame = Frame(['O', 'H', 'H'], [[3, -1, 2], [4, 1, 2], [1, -2, 7]])
        win = DummyWindow(frame)
        win.selection = [0]
        win._refresh_coordinates()
        self.assertEqual(win.atom_table.values()[0], ('1 O', '3.000000', '-1.000000', '2.000000'))
        original = frame.clone()
        move_atom_to_origin(frame, 0)
        win._refresh_after_geometry_edit()
        self.assertEqual(win.atom_table.values()[0], ('1 O', '0.000000', '0.000000', '0.000000'))
        self.assertEqual(win.atom_table.values()[1], ('2 H', '1.000000', '2.000000', '0.000000'))
        self.assertEqual(win.selection_synced, [0])
        self.assertIs(win.tabs.current, win.atom_table)
        self.assertIs(win.atom_table.scrolled_to, win.atom_table.item(0, 0))
        self.assertEqual((win.scene_updates, win.info_updates), (1, 1))
        win.frame = original
        win._refresh_coordinates()
        self.assertEqual(win.atom_table.values()[0], ('1 O', '3.000000', '-1.000000', '2.000000'))

    def test_axis_alignment_updates_both_xyz_rows(self):
        frame = Frame(['O', 'C', 'H'], [[1, 2, 3], [1, 4, 3], [2, 2, 3]], cell=np.eye(3) * 15)
        win = DummyWindow(frame)
        win.selection = [0, 1]
        win._refresh_coordinates()
        align_pair_to_axis(frame, 0, 1, 'X')
        win._refresh_after_geometry_edit()
        rows = win.atom_table.values()
        self.assertEqual(rows[0][1:], ('1.000000', '2.000000', '3.000000'))
        self.assertEqual(rows[1][1:], ('3.000000', '2.000000', '3.000000'))
        self.assertEqual(win.selection_synced, [0, 1])
        self.assertIs(win.tabs.current, win.atom_table)

    def test_nonorthogonal_lattice_alignment_updates_table(self):
        cell = np.array([[3, 0, 0], [1, 4, 0], [1, 1, 4]], dtype=float)
        frame = Frame(['O', 'H'], [[0, 0, 0], [0, 0, 2]], cell=cell, pbc=(True, True, True))
        win = DummyWindow(frame)
        win.selection = [0, 1]
        align_pair_to_axis(frame, 0, 1, 'b')
        win._refresh_after_geometry_edit()
        displayed = np.array([float(v) for v in win.atom_table.values()[1][1:]])
        np.testing.assert_allclose(displayed / np.linalg.norm(displayed), cell[1] / np.linalg.norm(cell[1]), atol=1e-6)

    def test_edit_handlers_use_same_table_refresh(self):
        tree = ast.parse(APP_PATH.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LELEWindow')
        functions = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        for name in ('move_selected_to_origin', 'align_selected_pair', '_coordinate_edited'):
            calls = [n for n in ast.walk(functions[name]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
            self.assertIn('_refresh_after_geometry_edit', [n.func.attr for n in calls])
        self.assertIn('self.change_frame(frame_idx, switch_doc=doc_idx)', ast.get_source_segment(APP_PATH.read_text(encoding='utf-8'), functions['undo_edit']))

    def test_layout_has_one_sidebar_with_six_tabs_and_no_right_panel(self):
        tree = ast.parse(APP_PATH.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LELEWindow')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_build_ui')
        code = ast.get_source_segment(APP_PATH.read_text(encoding='utf-8'), method)
        self.assertEqual(code.count('root.addWidget('), 2)
        self.assertIn('root.addWidget(sidebar_tabs)', code)
        self.assertIn('root.addWidget(centre)', code)
        self.assertIn("sidebar_tabs.addTab(files_page, 'Files')", code)
        for name in ('Style', 'Axes', 'Labels', 'Field', 'Edit'):
            self.assertIn(f"control_page('{name}')", code)
        self.assertNotIn('root.addWidget(panel)', code)


if __name__ == '__main__':
    unittest.main()
