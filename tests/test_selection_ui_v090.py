#!/usr/bin/env python3
"""Live Qt selection workflows with a headless canvas and real VTK scene."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from lele.core import Document, Frame, Volume


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class SelectionWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(['SelectionTests'])

    def setUp(self):
        from PySide6.QtCore import Signal, QTimer
        from PySide6.QtWidgets import QWidget, QMainWindow
        from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderWindowInteractor
        from lele.app import LELEWindow

        class HeadlessCanvas(QWidget):
            atomClick = Signal(float, float)
            clearSelectionClick = Signal()
            fragmentGestureBegin = Signal(str, float, float)
            fragmentGestureMove = Signal(str, float, float)
            fragmentGestureEnd = Signal(str)

            def __init__(self):
                super().__init__()
                self.window = vtkRenderWindow()
                self.interactor = vtkRenderWindowInteractor()
                self.interactor.SetRenderWindow(self.window)
                self.window.Render = lambda: None

            def GetRenderWindow(self): return self.window
            def TerminateApp(self): pass

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        w = LELEWindow.__new__(LELEWindow)
        QMainWindow.__init__(w)
        w.documents = []
        w.current_doc = -1
        w.frame_index = 0
        w.selection = []
        w.undo_stack = []
        w._ignore_table = w._ignore_tree = False
        w._fragment_gesture = None
        w._user_style_presets = {}
        with patch('lele.app.InteractiveVTKView', HeadlessCanvas):
            w._build_ui()
        w.playback = QTimer(w)
        w.axes_widget = SimpleNamespace(GetEnabled=lambda: False)
        w._sync_corner_axes = lambda: None
        self.addCleanup(w.deleteLater)
        self.window = w
        self.attach(Frame(['C'] * 4, [[0., 0., 3.], [1., 0., 4.], [0., 1., 5.], [4., 3., 2.]],
                          np.eye(3) * 15, (True, True, True)))

    def attach(self, frame, *, volume=None, second_frame=None):
        w = self.window
        frames = [frame] + ([] if second_frame is None else [second_frame])
        w.documents = [Document(Path(self.temp.name) / 'input.xyz', 'XYZ', frames, volume)]
        w.current_doc = 0
        w.frame_index = 0
        w.selection = []
        w.change_frame(0)

    def select(self, indices):
        self.window.selection = list(indices)
        self.window._sync_selection_to_table()
        self.window.refresh_scene()

    def test_plane_appears_updates_and_hides_with_selection(self):
        w = self.window
        self.select([0, 1, 2])
        self.assertIsNotNone(w.renderer.fitted_plane)
        self.assertTrue(w.plane_align_btn.isEnabled())
        self.assertIn('RMS distance', w.plane_label.text())
        for actor in w.renderer.dynamic[-2:]:
            self.assertEqual(actor.GetPickable(), 0)
        w.show_plane_check.setChecked(False)
        self.assertIsNone(w.renderer.fitted_plane)
        self.assertTrue(w.plane_align_btn.isEnabled())
        self.select([0, 1])
        self.assertFalse(w.plane_align_btn.isEnabled())

    def test_plane_alignment_and_undo_restore_cell_volume_and_selection(self):
        w = self.window
        volume = Volume(np.ones((2, 2, 2)), [1., 2., 3.], np.diag([.1, .2, .3]))
        w.doc.volume = volume
        before = w.frame.clone()
        old_origin, old_vectors = volume.origin.copy(), volume.voxel_vectors.copy()
        self.select([0, 1, 2])
        w.plane_align_btn.click()
        self.assertEqual(len(w.undo_stack), 1)
        np.testing.assert_allclose(w.frame.positions[:3, 2], 0., atol=1.e-12)
        self.assertFalse(np.allclose(w.frame.cell, before.cell))
        self.assertIn('Last plane alignment', w.info_view.toPlainText())
        w.undo_edit()
        np.testing.assert_array_equal(w.frame.positions, before.positions)
        np.testing.assert_array_equal(w.frame.cell, before.cell)
        np.testing.assert_array_equal(w.doc.volume.origin, old_origin)
        np.testing.assert_array_equal(w.doc.volume.voxel_vectors, old_vectors)
        self.assertEqual(w.selection, [0, 1, 2])

    def test_invert_complements_selection_and_updates_coordinate_table(self):
        w = self.window
        self.select([0, 2])
        w.invert_btn.click()
        self.assertEqual(w.selection, [1, 3])
        self.assertEqual([i.row() for i in w.atom_table.selectionModel().selectedRows()], [1, 3])
        w.invert_action.trigger()
        self.assertEqual(w.selection, [0, 2])
        w.clear_selection()
        w.invert_selection()
        self.assertEqual(w.selection, [0, 1, 2, 3])
        w.invert_selection()
        self.assertEqual(w.selection, [])
        self.assertEqual(w.undo_stack, [])

    def test_delete_is_frame_local_and_undo_restores_bonds_and_field(self):
        w = self.window
        first = w.frame.clone()
        first.bond_added = {(0, 2), (1, 3)}
        second = first.clone()
        volume = Volume(np.ones((2, 2, 2)), [0., 0., 0.], np.eye(3))
        self.attach(first, volume=volume, second_frame=second)
        self.select([0, 2])
        w.delete_btn.click()
        self.assertEqual(len(w.frame.symbols), 2)
        self.assertEqual(w.frame.bond_added, {(0, 1)})
        self.assertEqual(w.atom_table.rowCount(), 2)
        self.assertEqual(w.selection, [])
        self.assertIsNone(w.doc.volume)
        self.assertEqual(len(w.doc.frames[1].symbols), 4)
        w.undo_edit()
        self.assertEqual(w.selection, [0, 2])
        self.assertEqual(w.frame.bond_added, {(0, 2), (1, 3)})
        self.assertIs(w.doc.volume, volume)

    def test_delete_all_leaves_an_empty_editable_frame_and_undo_restores(self):
        w = self.window
        self.select(range(4))
        w.delete_selected_atoms()
        self.assertEqual(w.frame.symbols, [])
        self.assertEqual(w.atom_table.rowCount(), 0)
        self.assertFalse(w.delete_btn.isEnabled())
        w.align_camera('front')
        w.undo_edit()
        self.assertEqual(len(w.frame.symbols), 4)
        self.assertEqual(w.selection, list(range(4)))

    def test_real_delete_key_does_not_delete_atoms_while_editing_a_coordinate(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QLineEdit
        w = self.window
        w.resize(1100, 800)
        w.show()
        w.activateWindow()
        self.app.processEvents()
        self.select([0, 2])
        w.atom_table.setFocus()
        self.app.processEvents()
        QTest.keyClick(w.atom_table, Qt.Key.Key_Delete)
        self.assertEqual(len(w.frame.symbols), 2)
        w.undo_edit()
        item = w.atom_table.item(0, 1)
        w.atom_table.setCurrentItem(item)
        w.atom_table.editItem(item)
        editor = w.atom_table.findChild(QLineEdit)
        self.assertIsNotNone(editor)
        editor.setText('12.34')
        editor.setCursorPosition(0)
        editor.setFocus()
        self.app.processEvents()
        QTest.keyClick(editor, Qt.Key.Key_Delete)
        self.assertEqual(editor.text(), '2.34')
        self.assertEqual(len(w.frame.symbols), 4)
        w.hide()


if __name__ == '__main__':
    unittest.main()
