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
            def Initialize(self): pass
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
        self.enterContext(patch('lele.interaction.InteractiveVTKView', HeadlessCanvas))
        w._build_ui()
        w.playback = QTimer(w)
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

    def attach_vibrations(self):
        from lele.formats import load_document
        w = self.window
        path = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic_opt_freq.log'
        document = load_document(path)
        w.documents = [document]
        w.current_doc = 0
        w.selection = []
        w.files_tree.clear()
        w._add_document_tree(0, document)
        w.change_frame(0)
        return document

    def attach_properties(self):
        from lele.formats import load_document
        w=self.window;document=load_document(Path(__file__).resolve().parents[1]/'examples/synthetic_properties.log')
        w.documents=[document];w.current_doc=0;w.files_tree.clear();w._add_document_tree(0,document)
        w.change_frame(len(document.frames)-1)
        return document

    def test_restored_moment_sources_four_arrows_and_export_buttons(self):
        import csv
        from lele.gaussian_properties import AU_TO_DEBYE
        self.attach_properties();w=self.window
        for source,expected in [('permanent',[1,-2,2]),('permanent:1',[1.5,-.5,2.5]),('transition:0:1',np.array([1,-1,2.1915])*AU_TO_DEBYE)]:
            w._set_option('dipole_source',source);w._set_option('dipole_mode','Total + components')
            np.testing.assert_allclose(w.renderer.dipole_vector,expected)
            arrows=[a for a in w.renderer.dynamic if a.IsA('vtkActor') and a.GetUserMatrix()]
            self.assertEqual(len(arrows),4)
        w._set_option('dipole_mode','Off')
        def save(suffix):
            self.assertEqual(w.render_options.dipole_mode,'Total');self.assertIn('transition_0_1',suffix)
        with patch.object(w,'save_png',side_effect=save):w.dipole_panel.save_image.click()
        self.assertEqual(w.render_options.dipole_mode,'Off')
        for button,name,count in [(w.dipole_panel.export_data,'dipoles.csv',5),(w.dipole_panel.export_transitions,'td.csv',3)]:
            path=Path(self.temp.name)/name
            with patch('lele.restored_actions.QFileDialog.getSaveFileName',return_value=(str(path),'')):button.click()
            self.assertEqual(len(list(csv.DictReader(path.open(encoding='utf-8-sig')))),count)

    def test_restored_element_labels_stay_collapsed_triangle_expands(self):
        from PySide6.QtCore import QPoint,Qt
        from PySide6.QtTest import QTest
        w=self.window;w.show();w.sidebar_tabs.setCurrentWidget(w.atom_panel);self.app.processEvents()
        tree=w.atom_panel.tree;parent=tree.topLevelItem(0)
        self.assertFalse(parent.isExpanded())
        row=tree.visualItemRect(parent);position=QPoint(row.left()+65,row.center().y())
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,position)
        self.app.processEvents();self.assertFalse(parent.isExpanded());self.assertEqual(len(w.selection),4)
        QTest.mouseDClick(tree.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,position)
        self.app.processEvents();self.assertFalse(parent.isExpanded())
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPoint(6,row.center().y()))
        self.app.processEvents();self.assertTrue(parent.isExpanded())
        w.refresh_scene();self.assertTrue(parent.isExpanded());parent.setExpanded(False)
        self.select([1]);self.assertFalse(parent.isExpanded())

    def test_restored_boundary_source_picking_styles_and_real_supercell_coexist(self):
        from lele.atom_appearance import AtomAppearance
        f=Frame(['Si'],[[0,0,0]],np.eye(3)*2.2,(True,)*3,atom_appearance={0:AtomAppearance(opacity=.4)})
        self.attach(f);w=self.window;w.render_options.labels='Index (1..N)'
        bounds=((0,2),(0,2),(0,1));w._apply_boundary(True,bounds)
        self.assertEqual(len(w.renderer.boundary_display.source_indices),18)
        self.assertEqual(len(w.renderer.boundary_display.bonds),33)
        self.assertEqual({a.GetInput() for a in w.renderer._label_actors},{'1'})
        self.select([0]);self.assertEqual(len(w.renderer.atom_highlights),18)
        for i,p in w.renderer.displayed_atoms():
            w.scene.SetWorldPoint(*p,1.);w.scene.WorldToDisplay();x,y,_=w.scene.GetDisplayPoint()
            self.assertEqual(w.renderer.pick_index(x,y),0)
        with patch('lele.restored_actions.QMessageBox.warning') as message:w._apply_boundary(True,((0,0),)*3)
        self.assertTrue(message.called);self.assertEqual(w.render_options.boundary_bounds,bounds)
        self.assertIn('Atoms 1',w.summary_label.text());self.assertEqual(w.atom_table.rowCount(),1)
        w._apply_boundary(False,((0,1),)*3);self.assertTrue(w.apply_supercell((2,2,1)))
        self.assertEqual(len(w.frame.symbols),4);w.undo_edit();self.assertEqual(len(w.frame.symbols),1)

    def test_restored_spectrum_raw_table_and_broadened_csv_differ(self):
        from lele.spectrum_dialog import SpectrumDialog
        document=self.attach_properties();d=SpectrumDialog(document,'UV-Vis',self.window);self.addCleanup(d.deleteLater)
        self.assertEqual(d.table.rowCount(),3);self.assertEqual(d.table.columnCount(),10)
        for button,name,count in [(d.save_transitions,'raw.csv',4),(d.save_curve,'curve.csv',5001)]:
            path=Path(self.temp.name)/name
            with patch('lele.spectrum_dialog.QFileDialog.getSaveFileName',return_value=(str(path),'')):button.click()
            self.assertEqual(len(path.read_text(encoding='utf-8-sig').splitlines()),count)
        d.kind.setCurrentText('Raman');self.assertIsNotNone(d._curve)
        self.assertIn('Raman',d.table.horizontalHeaderItem(4).text())

    def test_restored_native_copy_paste_cross_file_click_and_undo(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from lele.atom_appearance import AtomAppearance
        self.addCleanup(lambda:self.app.clipboard().clear())
        self.attach(Frame(['O','H','H'],[[0,0,0],[1,0,0],[0,1,0]],atom_appearance={1:AtomAppearance(opacity=.3)}))
        w=self.window;w.show();w.vtk.setFocusPolicy(Qt.FocusPolicy.StrongFocus);w.vtk.setFocus();self.select([0,1]);self.app.processEvents()
        QTest.keyClick(w.vtk,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.app.clipboard().text().startswith('2\n'))
        target=Frame(['Si'],[[0,0,0]],np.eye(3)*6,(True,)*3,-7.)
        self.attach(target);w.vtk.GetRenderWindow().SetSize(600,400);w.refresh_scene(reset_camera=True);w.vtk.setFocus();self.app.processEvents()
        QTest.keyClick(w.vtk,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertIsNotNone(w._pending_paste)
        point=np.asarray(w.scene.GetActiveCamera().GetFocalPoint())
        w._pick_from_canvas(w.vtk.width()/2,w.vtk.height()/2)
        self.assertEqual(w.frame.symbols,['Si','O','H']);self.assertEqual(w.selection,[1,2])
        np.testing.assert_allclose(w.frame.positions[1:].mean(axis=0),point,atol=1e-7)
        self.assertEqual(w.frame.atom_appearance[2].opacity,.3);self.assertIsNone(w.frame.energy_ev)
        w.undo_edit();self.assertEqual(w.frame.symbols,['Si']);self.assertEqual(w.frame.energy_ev,-7.)

    def test_paste_detaches_obsolete_volume_and_undo_restores(self):
        volume = Volume(np.ones((2, 2, 2)), np.zeros(3), np.eye(3))
        self.attach(Frame(['C'], [[0, 0, 0]]), volume=volume)
        w = self.window
        w.vtk.GetRenderWindow().SetSize(600, 400)
        w.refresh_scene(reset_camera=True)
        w._pending_paste = Frame(['O'], [[0, 0, 0]])
        self.assertTrue(w._paste_at_click(w.vtk.width() / 2, w.vtk.height() / 2))
        self.assertEqual(w.frame.symbols, ['C', 'O'])
        self.assertIsNone(w.doc.volume)
        self.assertIsNone(w.renderer.volume)
        w.undo_edit()
        self.assertEqual(w.frame.symbols, ['C'])
        self.assertIs(w.doc.volume, volume)
        self.assertIs(w.renderer.volume, volume)

    def test_paste_updates_edit_element_choices(self):
        self.attach(Frame(['Si'], [[0, 0, 0]]))
        w = self.window
        w.vtk.GetRenderWindow().SetSize(600, 400)
        w.refresh_scene(reset_camera=True)
        w._pending_paste = Frame(['O'], [[0, 0, 0]])
        self.assertTrue(w._paste_at_click(w.vtk.width() / 2, w.vtk.height() / 2))
        self.assertEqual(w.frame.symbols, ['Si', 'O'])
        choices = [w.element_combo.itemText(i) for i in range(w.element_combo.count())]
        self.assertEqual(choices, ['O', 'Si'])

    def test_restored_rectangle_selection_ignores_hidden_atoms_and_appends(self):
        from lele.atom_appearance import AtomAppearance
        self.attach(Frame(['C']*3,[[-2,0,0],[0,0,0],[2,0,0]],atom_appearance={1:AtomAppearance(visible=False)}))
        w=self.window;w.vtk.GetRenderWindow().SetSize(600,400);w.refresh_scene(reset_camera=True)
        w.selection=[];w._rectangle_selected(0,0,w.vtk.width(),w.vtk.height())
        self.assertEqual(set(w.selection),{0,2})
        w.selection=[1];w._rectangle_selected(0,0,w.vtk.width(),w.vtk.height(),True)
        self.assertEqual(w.selection,[1,0,2])
        w.box_select_action.setChecked(True);self.assertTrue(w.box_select_button.isChecked())
        w.cancel_pointer_action();self.assertFalse(w.box_select_action.isChecked())

    def test_restored_box_gesture_uses_qt_rectangle_without_camera_motion(self):
        from PySide6.QtCore import Qt,QPointF,QEvent
        from PySide6.QtGui import QMouseEvent
        import importlib.util
        # The window harness replaces this class; load the original pointer
        # implementation separately to exercise its actual Qt event handlers.
        spec=importlib.util.spec_from_file_location('lele._real_box_interaction',Path(__file__).resolve().parents[1]/'lele/interaction.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        InteractiveVTKView=module.InteractiveVTKView
        view=InteractiveVTKView();self.addCleanup(view.deleteLater);view.set_box_selection(True)
        captured=[];view.rectangleSelected.connect(lambda *v:captured.append(v))
        for event_type,x,y,button in [(QEvent.Type.MouseButtonPress,10,20,Qt.MouseButton.LeftButton),
                                     (QEvent.Type.MouseMove,90,100,Qt.MouseButton.NoButton),
                                     (QEvent.Type.MouseButtonRelease,90,100,Qt.MouseButton.LeftButton)]:
            event=QMouseEvent(event_type,QPointF(x,y),QPointF(x,y),button,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier)
            if event_type==QEvent.Type.MouseButtonPress:view.mousePressEvent(event)
            elif event_type==QEvent.Type.MouseMove:view.mouseMoveEvent(event)
            else:view.mouseReleaseEvent(event)
        self.assertEqual(captured,[(10.,20.,90.,100.,True)])
        self.assertIsNone(view._left_start)

    def test_restored_source_save_paths_energy_units_and_edit_invalidation(self):
        d=self.attach_properties();w=self.window
        self.assertIn('kcal/mol',w.info_view.toPlainText())
        item=w._frame_tree_items[0,0];self.assertIn('kcal/mol',item.text(0))
        with patch('lele.app.QFileDialog.getSaveFileName',return_value=('','')) as dialog:w.save_png()
        self.assertEqual(Path(dialog.call_args.args[2]).parent,d.path.parent)
        with patch('lele.app.QInputDialog.getItem',return_value=('XYZ (.xyz)',True)),patch('lele.app.QFileDialog.getSaveFileName',return_value=('','')) as dialog:w.export_dialog()
        self.assertEqual(Path(dialog.call_args.args[2]).parent,d.path.parent)
        old=w.frame.energy_ev;self.assertIsNotNone(old)
        w.atom_table.item(0,1).setText('0.12345')
        self.assertIsNone(w.frame.energy_ev);self.assertNotIn('kcal/mol',w._frame_tree_items[0,1].text(0))
        w.undo_edit();self.assertEqual(w.frame.energy_ev,old)

    def test_supercell_changes_current_frame_exports_and_undo_restores(self):
        from lele.atom_appearance import AtomAppearance
        from lele.formats import export_frame, load_document
        first = Frame(['Si'], [[.2, .3, .4]], np.eye(3) * 3, (True,) * 3, -7.,
                      atom_appearance={0: AtomAppearance(opacity=.4, color='#aabbcc')})
        second = first.clone(); second.positions += .1
        volume = Volume(np.ones((2, 2, 2)), np.array([.1, .2, .3]), np.eye(3))
        self.attach(first, second_frame=second, volume=volume)
        w = self.window
        self.select([0]);w.playback.start(1000)
        self.assertTrue(w.supercell_action.isEnabled())
        self.assertTrue(w.apply_supercell((2, 3, 1)))
        self.assertEqual(len(w.frame.symbols), 6)
        self.assertEqual(w.atom_table.rowCount(), 6)
        self.assertIn('Atoms 6', w.summary_label.text())
        self.assertEqual(w.frame.atom_appearance[5], first.atom_appearance[0])
        self.assertIsNone(w.doc.volume); self.assertIsNone(w.frame.energy_ev)
        self.assertFalse(w.playback.isActive())
        self.assertEqual(w.selection, [])
        self.assertIs(w.doc.frames[1], second)
        self.assertEqual(len(w.doc.frames[1].symbols), 1)
        path = Path(self.temp.name) / 'supercell.vasp'
        export_frame(w.frame, path, 'poscar-direct')
        self.assertEqual(len(load_document(path).frames[0].symbols), 6)
        w.undo_edit()
        self.assertEqual(len(w.frame.symbols), 1)
        self.assertEqual(w.frame.energy_ev, -7.)
        self.assertIs(w.doc.volume, volume)
        self.assertEqual(w.selection, [0])
        np.testing.assert_allclose(w.frame.cell, first.cell)

    def test_supercell_invalid_input_is_atomic_and_unavailable_for_vibration(self):
        w = self.window
        original = w.frame
        with patch('lele.app.QMessageBox.warning') as warning:
            self.assertFalse(w.apply_supercell((0, 2, 1)))
        self.assertTrue(warning.called)
        self.assertIs(w.frame, original); self.assertEqual(w.undo_stack, [])
        self.attach(Frame(['H'], [[0, 0, 0]]))
        self.assertFalse(w.supercell_action.isEnabled())
        self.attach_vibrations(); w.select_vibration(0, 0, 0, autoplay=False)
        self.assertFalse(w.supercell_action.isEnabled())
        self.assertFalse(w.apply_supercell((2, 2, 2)))
        self.assertEqual(w.undo_stack, [])

    def test_supercell_dialog_uses_lattice_directions_and_preview_limit(self):
        from PySide6.QtWidgets import QDialogButtonBox
        from lele.supercell_dialog import SupercellDialog
        frame = Frame(['Si'], [[0, 0, 0]], np.eye(3) * 3, (True, True, False))
        dialog = SupercellDialog(frame)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.repeats(), (2, 2, 1))
        self.assertFalse(dialog.spins[2].isEnabled())
        self.assertIn('4 atoms', dialog.preview.text())
        button = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.assertTrue(button.isEnabled())
        for spin in dialog.spins:spin.setValue(1)
        self.assertFalse(button.isEnabled())
        dialog.spins[0].setValue(3)
        self.assertTrue(button.isEnabled())
        dialog._frame = Frame(['Si'] * 1000, np.zeros((1000, 3)), np.eye(3), (True,) * 3)
        dialog.spins[0].setValue(100)
        self.assertFalse(button.isEnabled())

    def test_actual_gif_export_preserves_live_pose_camera_and_resumes_vibration(self):
        from PIL import Image
        from lele.animation_export import GifSettings
        self.attach_vibrations()
        w = self.window
        w.select_vibration(0, 0, 0)
        w._vibration_phase = .4
        w._render_vibration()
        phase, pose = w._vibration_phase, w.renderer.frame.positions.copy()
        camera = w.scene.GetActiveCamera()
        state = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale(), camera.GetClippingRange())
        path = Path(self.temp.name) / 'mode.gif'
        self.assertTrue(w._save_gif_file(path, GifSettings(source='vibration', width=160, height=120, fps=8)))
        self.assertTrue(w.vibration_timer.isActive())
        self.assertEqual(w._vibration_phase, phase)
        np.testing.assert_array_equal(w.renderer.frame.positions, pose)
        self.assertEqual((camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale(), camera.GetClippingRange()), state)
        self.assertFalse(w._gif_exporting)
        self.assertEqual(w.undo_stack, [])
        self.assertFalse(w.doc.modified)
        with Image.open(path) as gif:
            self.assertEqual(gif.n_frames, 8)
            self.assertEqual(gif.size, (160, 120))
        w.stop_vibration()

    def test_gif_cancel_preserves_existing_file_and_restores_trajectory_playback(self):
        from PySide6.QtCore import QTimer
        from lele.animation_export import GifSettings
        self.attach_vibrations()
        w = self.window
        w.playback.start(1000)
        path = Path(self.temp.name) / 'existing.gif'
        path.write_bytes(b'original GIF')
        QTimer.singleShot(0, lambda: w._gif_progress.cancel())
        self.assertFalse(w._save_gif_file(path, GifSettings(width=160, height=120, last_frame=2)))
        self.assertEqual(path.read_bytes(), b'original GIF')
        self.assertTrue(w.playback.isActive())
        self.assertFalse(w._gif_exporting)
        self.assertIsNone(w._gif_progress)
        self.assertEqual(w.frame_index, 0)
        self.assertEqual([p.name for p in Path(self.temp.name).iterdir()], ['existing.gif'])
        w.playback.stop()

    def test_frequency_tree_lists_modes_and_keyboard_selection_starts_animation(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        doc = self.attach_vibrations()
        w = self.window
        head = w.files_tree.topLevelItem(0)
        self.assertIn('Geometry / optimization', head.child(0).text(0))
        frequencies = head.child(1)
        self.assertEqual(frequencies.childCount(), 3)
        self.assertIn('1 imaginary', frequencies.text(0))
        item = frequencies.child(0)
        self.assertIn('-250.0000 cm⁻¹', item.text(0))
        self.assertIn('imaginary', item.text(0))
        w.playback.start(1000)
        w.files_tree.setCurrentItem(item)
        self.assertEqual(w._active_vibration, (0, 0, 0))
        self.assertTrue(w.vibration_timer.isActive())
        self.assertFalse(w.playback.isActive())
        self.assertFalse(w.play_btn.isEnabled())
        self.assertIn('12.0000 km/mol', w.vibration_controls.description.text())
        np.testing.assert_allclose(w.renderer.frame.positions, doc.vibrations[0].reference.positions)
        QTest.keyClick(w.files_tree, Qt.Key.Key_Down)
        self.assertEqual(w._active_vibration, (0, 0, 1))
        self.assertIs(w.files_tree.currentItem(), frequencies.child(1))
        self.assertIn('1500.0000', w.vibration_controls.description.text())
        w.stop_vibration()

    def test_vibration_timer_pause_reset_amplitude_and_source_coordinates(self):
        from PySide6.QtTest import QTest
        from math import pi
        doc = self.attach_vibrations()
        w = self.window
        geometry = [frame.positions.copy() for frame in doc.frames]
        reference = doc.vibrations[0].reference.positions.copy()
        w.select_vibration(0, 0, 0)
        camera = w.scene.GetActiveCamera()
        camera_state = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale())
        # Wait for an actual animation update; a fixed short delay can expire
        # before Qt services timers on a busy software-rendering worker.
        import time
        deadline=time.monotonic()+2.
        while w._vibration_phase<=0. and time.monotonic()<deadline:QTest.qWait(25)
        self.assertGreater(w._vibration_phase, 0.)
        self.assertFalse(np.allclose(w.renderer.frame.positions, reference))
        w.vibration_controls.play_button.click()
        self.assertFalse(w.vibration_timer.isActive())
        paused = w.renderer.frame.positions.copy()
        QTest.qWait(80)
        np.testing.assert_array_equal(w.renderer.frame.positions, paused)
        w._vibration_phase = pi / 2
        w.vibration_controls.amplitude.setValue(.6)
        self.assertAlmostEqual(np.linalg.norm(w.renderer.frame.positions - reference, axis=1).max(), .6)
        self.assertEqual((camera.GetPosition(), camera.GetFocalPoint(), camera.GetParallelScale()), camera_state)
        self.assertEqual(w.atom_table.item(1, 1).text(), '0.960000')
        for frame, original in zip(doc.frames, geometry):
            np.testing.assert_array_equal(frame.positions, original)
        np.testing.assert_array_equal(doc.vibrations[0].reference.positions, reference)
        self.assertFalse(doc.modified)
        self.assertEqual(w.undo_stack, [])
        w.vibration_controls.stop_button.click()
        self.assertEqual(w._vibration_phase, 0.)
        np.testing.assert_array_equal(w.renderer.frame.positions, reference)
        self.assertFalse(w.vibration_timer.isActive())

    def test_leaving_frequency_restores_geometry_controls_and_stops_animation(self):
        from PySide6.QtCore import Qt
        self.attach_vibrations()
        w = self.window
        w.select_vibration(0, 0, 0)
        self.assertFalse(w.atom_table.item(1, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        w.files_tree.setCurrentItem(w._frame_tree_items[0, 0])
        self.assertIsNone(w._active_vibration)
        self.assertFalse(w.vibration_timer.isActive())
        self.assertIsNone(w.renderer.fixed_bonds)
        self.assertTrue(w.vibration_controls.isHidden())
        self.assertTrue(w.play_btn.isEnabled())
        self.assertTrue(w.fps_spin.isEnabled())
        self.assertEqual(w.frame_index, 0)
        self.assertEqual(w.atom_table.item(1, 1).text(), '1.100000')
        self.assertTrue(w.atom_table.item(1, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        w._step_next()
        self.assertEqual(w.frame_index, 1)
        self.assertIs(w.files_tree.currentItem(), w._frame_tree_items[0, 1])

    def test_frequency_reference_cannot_be_edited_and_atom_display_undo_targets_it(self):
        from lele.atom_appearance import appearance
        doc = self.attach_vibrations()
        w = self.window
        w.select_vibration(0, 0, 0, autoplay=False)
        self.select([0, 1])
        original = w.frame.positions.copy()
        w.delete_selected_atoms()
        w.toggle_bonds()
        w.align_selected_pair()
        w._fragment_begin('pan', 0., 0.)
        self.assertIsNone(w._fragment_gesture)
        w.atom_table.item(1, 1).setText('99.99')
        np.testing.assert_array_equal(w.frame.positions, original)
        self.assertEqual(w.atom_table.item(1, 1).text(), '0.960000')
        self.assertEqual(w.undo_stack, [])
        w._change_atom_appearance([1], {'color': '#ff00aa', 'opacity': .4})
        self.assertAlmostEqual(appearance(w.frame, 1).opacity, .4)
        self.assertAlmostEqual(doc.vibrations[0].reference.atom_appearance[1].opacity, .4)
        w.change_frame(0)
        w.select_vibration(0, 0, 1, autoplay=False)
        self.assertAlmostEqual(appearance(w.frame, 1).opacity, .4)
        w.change_frame(0)
        w.undo_edit()
        self.assertEqual(w._active_vibration, (0, 0, 0))
        self.assertEqual(w.frame.atom_appearance, {})
        self.assertEqual(doc.frames[0].atom_appearance, {})
        np.testing.assert_array_equal(w.frame.positions, original)
        self.assertFalse(doc.modified)

    def test_missing_mode_vectors_are_listed_but_animation_stays_disabled(self):
        doc = self.attach_vibrations()
        w = self.window
        doc.vibrations[0].modes[0].displacements = None
        w.select_vibration(0, 0, 0)
        self.assertFalse(w.vibration_timer.isActive())
        self.assertFalse(w.vibration_controls.play_button.isEnabled())
        self.assertIn('animation unavailable', w.vibration_controls.description.text())
        w.toggle_vibration()
        self.assertFalse(w.vibration_timer.isActive())
        w.change_frame(0)

    def test_multiple_frequency_jobs_and_document_switch_use_their_own_references(self):
        from copy import deepcopy
        doc = self.attach_vibrations()
        w = self.window
        second_analysis = deepcopy(doc.vibrations[0])
        second_analysis.reference.positions += [4., 2., 1.]
        doc.vibrations.append(second_analysis)
        w.files_tree.clear()
        w._add_document_tree(0, doc)
        w.files_tree.setCurrentItem(w._vibration_tree_items[0, 1, 0])
        self.assertEqual(w._active_vibration, (0, 1, 0))
        np.testing.assert_allclose(w.frame.positions, second_analysis.reference.positions)
        second_doc = Document(Path(self.temp.name) / 'other.xyz', 'XYZ',
                              [Frame(['He'], [[20., 0., 0.]])])
        w.documents.append(second_doc)
        w._add_document_tree(1, second_doc)
        w.files_tree.setCurrentItem(w._frame_tree_items[1, 0])
        self.assertIsNone(w._active_vibration)
        self.assertFalse(w.vibration_timer.isActive())
        self.assertEqual(w.current_doc, 1)
        self.assertEqual(w.frame.symbols, ['He'])
        w.files_tree.setCurrentItem(w._vibration_tree_items[0, 0, 0])
        self.assertEqual(w._active_vibration, (0, 0, 0))
        self.assertEqual(w.frame.symbols, ['O', 'H', 'H'])
        np.testing.assert_allclose(w.frame.positions, doc.vibrations[0].reference.positions)
        w.stop_vibration()

    def test_atom_browser_groups_elements_and_selection_matches_coordinate_indices(self):
        from PySide6.QtCore import Qt
        self.attach(Frame(['O', 'H', 'H', 'C'], [[0, 0, 0], [1, 0, 0], [-1, 0, 0], [4, 0, 0]]))
        w, panel = self.window, self.window.atom_panel
        self.assertEqual([panel.tree.topLevelItem(i).text(0) for i in range(3)],
                         ['O (1)', 'H (2)', 'C (1)'])
        self.assertIn('#3', panel._items[2].text(0))
        panel.tree.setCurrentItem(panel._items[2])
        self.assertEqual(w.selection, [2])
        self.assertEqual([i.row() for i in w.atom_table.selectionModel().selectedRows()], [2])
        self.select([0, 1])
        self.assertEqual(panel.selected_indices(), [0, 1])
        panel._groups['H'].setCheckState(0, Qt.CheckState.Unchecked)
        self.assertFalse(w.frame.atom_appearance[1].visible)
        self.assertFalse(w.frame.atom_appearance[2].visible)
        self.assertEqual(len(w.frame.symbols), 4)
        w.undo_edit()
        self.assertEqual(w.frame.atom_appearance, {})

    def test_single_atom_editor_changes_labels_colour_transparency_and_resets(self):
        from PySide6.QtGui import QColor
        from lele.atom_appearance import appearance
        w, panel = self.window, self.window.atom_panel
        coords = w.frame.positions.copy()
        self.select([1])
        panel.label_combo.setCurrentIndex(panel.label_combo.findData('Index (1..N)'))
        self.assertEqual([a.GetInput() for a in w.renderer._label_actors], ['2', '2'])
        panel.label_combo.setCurrentIndex(panel.label_combo.findData('Custom'))
        panel.label_text.setText('site B')
        panel.label_text.editingFinished.emit()
        self.assertEqual([a.GetInput() for a in w.renderer._label_actors], ['site B', 'site B'])
        with patch('lele.atom_panel.QColorDialog.getColor', return_value=QColor('#aabbcc')):
            panel.color_button.click()
        panel.transparency_spin.setValue(70)
        self.assertEqual(appearance(w.frame, 1).color, '#aabbcc')
        self.assertAlmostEqual(appearance(w.frame, 1).opacity, .3)
        self.assertEqual(appearance(w.frame, 0).color, None)
        self.assertEqual(panel._items[1].text(2), '70')
        self.assertFalse(w.doc.modified)
        np.testing.assert_array_equal(w.frame.positions, coords)
        panel.reset_button.click()
        self.assertEqual(w.frame.atom_appearance, {})
        self.assertEqual(w.renderer._label_actors, [])
        w.undo_edit()
        self.assertEqual(appearance(w.frame, 1).label_text, 'site B')
        self.assertAlmostEqual(appearance(w.frame, 1).opacity, .3)

    def test_atom_settings_stay_with_frame_and_survive_delete_undo(self):
        from lele.atom_appearance import appearance
        w = self.window
        second = w.frame.clone()
        w.doc.frames.append(second)
        w._change_atom_appearance([1], {'visible': False})
        w._change_atom_appearance([3], {'color': '#ff00aa', 'label_mode': 'Custom', 'label_text': 'last'})
        w.change_frame(1)
        self.assertFalse(appearance(w.frame, 1).visible)
        self.assertEqual(appearance(w.frame, 3).label_text, 'last')
        w.change_frame(0)
        self.select([0])
        w.delete_selected_atoms()
        self.assertFalse(appearance(w.frame, 0).visible)
        self.assertEqual(appearance(w.frame, 2).label_text, 'last')
        self.assertEqual(w.atom_panel._items[2].text(1), '#ff00aa')
        w.undo_edit()
        self.assertEqual(len(w.frame.symbols), 4)
        self.assertFalse(appearance(w.frame, 1).visible)
        self.assertEqual(appearance(w.frame, 3).label_text, 'last')

    def test_lower_panel_is_evenly_split_with_settings_left_coordinates_right(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QWidget
        w = self.window
        w.resize(1380, 850)
        w.show()
        self.app.processEvents()
        self.assertEqual(w.lower_splitter.orientation(), Qt.Orientation.Horizontal)
        self.assertIs(w.lower_splitter.widget(0), w.bottom_control_tabs)
        self.assertIs(w.lower_splitter.widget(1), w.tabs)
        sizes = w.lower_splitter.sizes()
        self.assertLess(abs(sizes[0] - sizes[1]), sum(sizes) * .08)
        self.assertEqual([w.bottom_control_tabs.tabText(i) for i in range(w.bottom_control_tabs.count())], ['Axes','Labels','Field','Boundary'])
        self.assertTrue(w.atom_table.verticalHeader().isHidden())
        self.assertLessEqual(w.atom_table.verticalHeader().defaultSectionSize(),
                             max(24, w.atom_table.fontMetrics().height() + 4))
        self.assertFalse(w.atom_table.horizontalHeader().stretchLastSection())
        self.assertTrue(w.atom_table.item(0, 1).flags() & Qt.ItemFlag.ItemIsEditable)
        w.hide()

    def test_isovalue_accepts_precise_keyboard_input_and_updates_only_after_enter(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w = self.window
        volume = Volume(np.linspace(-.1, .1, 64).reshape(4, 4, 4), [0, 0, 0], np.eye(3))
        self.attach(w.frame, volume=volume)
        page = next(i for i in range(w.bottom_control_tabs.count()) if w.bottom_control_tabs.tabText(i) == 'Field')
        w.bottom_control_tabs.setCurrentIndex(page)
        w.show()
        w.iso_spin.setFocus()
        self.app.processEvents()
        with patch.object(w, 'refresh_scene', wraps=w.refresh_scene) as render:
            w.iso_spin.selectAll()
            QTest.keyClicks(w.iso_spin, '0.01234567')
            self.assertAlmostEqual(w.render_options.volume_iso, .035)
            render.assert_not_called()
            QTest.keyClick(w.iso_spin, Qt.Key.Key_Return)
            self.assertAlmostEqual(w.iso_spin.value(), .01234567, places=12)
            self.assertAlmostEqual(w.render_options.volume_iso, .01234567, places=12)
            render.assert_called_once()
        contours = [resources[0] for resources in w.renderer._keepalive
                    if isinstance(resources, tuple) and resources[0].IsA('vtkContourFilter')]
        self.assertEqual(len(contours), 2)
        np.testing.assert_allclose(sorted(c.GetValue(0) for c in contours),
                                   [-.01234567, .01234567], rtol=0, atol=1e-12)
        w.hide()

    def test_isovalue_scientific_paste_apply_arrows_and_invalid_input(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        w = self.window
        page = next(i for i in range(w.bottom_control_tabs.count()) if w.bottom_control_tabs.tabText(i) == 'Field')
        w.bottom_control_tabs.setCurrentIndex(page)
        w.show()
        w.iso_spin.setFocus()
        self.app.processEvents()
        editor = w.iso_spin.lineEdit()
        editor.selectAll()
        self.app.clipboard().setText('1.2345e-5')
        editor.paste()
        self.assertEqual(editor.text(), '1.2345e-5')
        self.assertAlmostEqual(w.render_options.volume_iso, .035)
        QTest.mouseClick(w.iso_apply_button, Qt.MouseButton.LeftButton)
        self.assertAlmostEqual(w.render_options.volume_iso, .000012345, places=12)
        self.assertEqual(w.iso_spin.text(), '0.000012345')
        w.iso_spin.setFocus()
        QTest.keyClick(w.iso_spin, Qt.Key.Key_Up)
        self.assertAlmostEqual(w.render_options.volume_iso, .005012345, places=12)
        self.assertEqual(len(w.frame.symbols), 4)
        editor.selectAll()
        QTest.keyClick(editor, Qt.Key.Key_Delete)
        self.assertEqual(len(w.frame.symbols), 4)
        QTest.keyClicks(editor, '0')
        QTest.keyClick(editor, Qt.Key.Key_Return)
        self.assertGreater(w.iso_spin.value(), 0)
        self.assertAlmostEqual(w.render_options.volume_iso, .005012345, places=12)
        w.hide()

    def test_plane_only_fits_on_request_and_selection_changes_clear_it(self):
        w = self.window
        from lele.selection_geometry import fit_selection_plane
        with patch('lele.selection_geometry.fit_selection_plane', wraps=fit_selection_plane) as fit:
            self.select([0, 1, 2])
            w.refresh_scene()
            fit.assert_not_called()
            self.assertIsNone(w.renderer.fitted_plane)
            self.assertTrue(w.fit_plane_btn.isEnabled())
            self.assertFalse(w.plane_align_btn.isEnabled())
            w.fit_plane_btn.click()
            fit.assert_called_once()
            self.assertIsNotNone(w.renderer.fitted_plane)
            self.assertTrue(w.plane_align_btn.isEnabled())
            self.assertIn('RMS distance', w.plane_label.text())
            for actor in w.renderer.dynamic[-2:]:
                self.assertEqual(actor.GetPickable(), 0)
            w.show_plane_check.setChecked(False)
            self.assertIsNone(w.renderer.fitted_plane)
            self.assertTrue(w.plane_align_btn.isEnabled())
            w.show_plane_check.setChecked(True)
            self.assertIsNotNone(w.renderer.fitted_plane)
            fit.assert_called_once()
            self.select([0, 1, 3])
            self.assertIsNone(w.renderer.fitted_plane)
            self.assertFalse(w.plane_align_btn.isEnabled())
            fit.assert_called_once()
            w.fit_plane_action.trigger()
            self.assertEqual(fit.call_count, 2)
            self.assertIsNotNone(w.renderer.fitted_plane)
        self.select([0, 1])
        self.assertIsNone(w.renderer.fitted_plane)
        self.assertFalse(w.plane_align_btn.isEnabled())
        self.assertFalse(w.fit_plane_btn.isEnabled())

    def test_plane_requires_refit_after_coordinates_periodic_options_or_frame_change(self):
        w = self.window
        w.doc.frames.append(w.frame.clone())
        self.select([0, 1, 2])
        w.fit_plane_btn.click()
        w.frame.positions[0, 2] += .5
        w.refresh_scene()
        self.assertIsNone(w.renderer.fitted_plane)
        w.fit_plane_btn.click()
        self.assertIsNotNone(w.renderer.fitted_plane)
        w.plane_images_check.setChecked(False)
        self.assertIsNone(w.renderer.fitted_plane)
        w.fit_plane_btn.click()
        self.assertIsNotNone(w.renderer.fitted_plane)
        w.change_frame(1)
        self.assertEqual(w.selection, [0, 1, 2])
        self.assertIsNone(w.renderer.fitted_plane)
        self.assertTrue(w.fit_plane_btn.isEnabled())

    def test_collinear_plane_error_is_reported_on_fit_without_geometry_changes(self):
        w = self.window
        w.frame.positions[:3] = [[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]]
        before = w.frame.clone()
        self.select([0, 1, 2])
        self.assertNotIn('collinear;', w.plane_label.text())
        w.fit_plane_btn.click()
        self.assertIn('collinear;', w.plane_label.text())
        self.assertIsNone(w.renderer.fitted_plane)
        self.assertFalse(w.plane_align_btn.isEnabled())
        self.assertEqual(w.undo_stack, [])
        np.testing.assert_array_equal(w.frame.positions, before.positions)
        np.testing.assert_array_equal(w.frame.cell, before.cell)

    def test_view_menu_axes_and_projection_preserve_atomic_geometry(self):
        w = self.window
        from PySide6.QtWidgets import QToolBar
        self.assertEqual([a.text().replace('&', '') for a in w.menuBar().actions()],
                         ['File', 'Edit', 'View', 'Analysis', 'Help'])
        self.assertEqual(w.findChildren(QToolBar), [])
        self.assertIn(w.invert_action, w.edit_menu.actions())
        self.assertIn(w.delete_action, w.edit_menu.actions())
        before = w.frame.clone()
        for axis, direction in zip(('X', 'Y', 'Z'), np.eye(3)):
            with self.subTest(axis=axis):
                w.projection_actions['Perspective'].trigger()
                self.assertEqual(w.scene.GetActiveCamera().GetParallelProjection(), 0)
                w.axis_actions[axis].trigger()
                camera = w.scene.GetActiveCamera()
                offset = np.asarray(camera.GetPosition()) - np.asarray(camera.GetFocalPoint())
                np.testing.assert_allclose(offset / np.linalg.norm(offset), direction, atol=1e-12)
                self.assertAlmostEqual(np.dot(direction, camera.GetViewUp()), 0.)
                self.assertEqual(camera.GetParallelProjection(), 1)
                self.assertTrue(w.projection_actions['Orthographic'].isChecked())
                w.projection_actions['Perspective'].trigger()
                w.projection_actions['Orthographic'].trigger()
                np.testing.assert_allclose(-np.asarray(camera.GetDirectionOfProjection()), direction,
                                           atol=1e-12)
        np.testing.assert_array_equal(w.frame.positions, before.positions)
        np.testing.assert_array_equal(w.frame.cell, before.cell)

    def test_plane_alignment_and_undo_restore_cell_volume_and_selection(self):
        w = self.window
        volume = Volume(np.ones((2, 2, 2)), [1., 2., 3.], np.diag([.1, .2, .3]))
        w.doc.volume = volume
        before = w.frame.clone()
        old_origin, old_vectors = volume.origin.copy(), volume.voxel_vectors.copy()
        self.select([0, 1, 2])
        w.fit_plane_btn.click()
        w.plane_align_btn.click()
        self.assertEqual(len(w.undo_stack), 1)
        np.testing.assert_allclose(w.frame.positions[:3, 2], 0., atol=1.e-12)
        self.assertFalse(np.allclose(w.frame.cell, before.cell))
        np.testing.assert_allclose(w.renderer.fitted_plane.normal, [0., 0., 1.], atol=1.e-12)
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
        self.assertTrue(w.summary_label.text().startswith('Atoms 4  |  Composition C4'))
        self.assertIn('electrons even', w.summary_label.text())
        self.assertNotRegex(w.summary_label.text(), r'\d+ electrons')
        self.select([0, 2])
        self.assertTrue(w.summary_label.text().startswith('Atoms 4'))
        w.delete_btn.click()
        self.assertEqual(len(w.frame.symbols), 2)
        self.assertEqual(w.frame.bond_added, {(0, 1)})
        self.assertEqual(w.atom_table.rowCount(), 2)
        self.assertEqual(w.selection, [])
        self.assertTrue(w.summary_label.text().startswith('Atoms 2  |  Composition C2'))
        self.assertIsNone(w.doc.volume)
        self.assertEqual(len(w.doc.frames[1].symbols), 4)
        w.undo_edit()
        self.assertEqual(w.selection, [0, 2])
        self.assertEqual(w.frame.bond_added, {(0, 2), (1, 3)})
        self.assertIs(w.doc.volume, volume)
        self.assertTrue(w.summary_label.text().startswith('Atoms 4  |  Composition C4'))

    def test_electron_parity_tracks_net_charge_and_frame_without_showing_total(self):
        w = self.window
        first = Frame(['O', 'H'], [[0., 0., 0.], [1., 0., 0.]])
        second = first.clone()
        second.info['converter_charge'] = -1
        self.attach(first, second_frame=second)
        self.assertEqual(w.charge_spin.value(), 0)
        self.assertIn('electrons odd', w.summary_label.text())
        self.assertNotRegex(w.summary_label.text(), r'\d+ electrons')
        w.charge_spin.setValue(1)
        self.assertEqual(w.frame.info['charge_override'], 1)
        self.assertIn('electrons even', w.summary_label.text())
        w.change_frame(1)
        self.assertEqual(w.charge_spin.value(), -1)
        self.assertNotIn('charge_override', w.frame.info)
        self.assertIn('electrons even', w.summary_label.text())
        self.assertNotRegex(w.summary_label.text(), r'\d+ electrons')
        w.change_frame(0)
        self.assertEqual(w.charge_spin.value(), 1)
        self.assertIn('electrons even', w.summary_label.text())

    def test_delete_all_leaves_an_empty_editable_frame_and_undo_restores(self):
        w = self.window
        self.select(range(4))
        w.delete_selected_atoms()
        self.assertEqual(w.frame.symbols, [])
        self.assertEqual(w.atom_table.rowCount(), 0)
        self.assertFalse(w.delete_btn.isEnabled())
        w.align_camera('Z')
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
