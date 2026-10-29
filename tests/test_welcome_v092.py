#!/usr/bin/env python3
"""Startup and file-opening workflows without a native OpenGL dependency."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl, Signal, QObject, QTimer
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderWindowInteractor

from lele import APP_CONTACT_EMAIL, APP_FULL_NAME, APP_NAME, APP_REPOSITORY_URL, __version__
from lele.app import LELEWindow
from lele.welcome import WelcomePage, WALK_STEP_COUNT


class HeadlessCanvas(QWidget):
    atomClick = Signal(float, float)
    clearSelectionClick = Signal()
    fragmentGestureBegin = Signal(str, float, float)
    fragmentGestureMove = Signal(str, float, float)
    fragmentGestureEnd = Signal(str)

    def __init__(self):
        super().__init__()
        self.initialize_count = 0
        self.window = vtkRenderWindow()
        self.interactor = vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.window)
        self.window.Render = lambda: None

    def GetRenderWindow(self): return self.window
    def Initialize(self): self.initialize_count += 1
    def TerminateApp(self): pass


class ControlledLoader(QObject):
    finished = Signal()

    def __init__(self, *, auto_finish=True):
        super().__init__()
        self.loaded = False
        self.error = ''
        self.start_count = 0
        self.auto_finish = auto_finish

    def ensure_started(self):
        self.start_count += 1
        if self.auto_finish:
            QTimer.singleShot(0, self.complete)

    def complete(self, error=''):
        self.error = error
        self.loaded = not error
        self.finished.emit()


class WelcomeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['WelcomeTests'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'water.xyz'
        self.path.write_text('3\nwater\nO 0 0 0\nH .76 .59 0\nH -.76 .59 0\n')

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(5)
        self.assertTrue(predicate())

    def window(self, initial_files=(), *, loader=None, wait_ready=True):
        loader = loader or ControlledLoader()
        self.enterContext(patch('lele.app.get_backend_loader', return_value=loader))
        self.enterContext(patch('lele.interaction.InteractiveVTKView', HeadlessCanvas))
        with patch.object(LELEWindow, '_read_user_style_presets', return_value={}), \
                patch.object(LELEWindow, '_sync_corner_axes'):
            window = LELEWindow(initial_files)
        window._sync_corner_axes = lambda: None
        self.assertIsNone(window.vtk)
        self.assertEqual(loader.start_count, 0)
        window.show()
        window.activateWindow()
        self.app.processEvents()
        self.addCleanup(window.close)
        if wait_ready:
            self.wait_for(lambda: window._backend_state == 'ready')
        return window

    def assert_loaded(self, window):
        self.assertEqual(window.files_tree.topLevelItemCount(), 1)
        self.assertEqual(window.doc.path, self.path)
        self.assertEqual(window.atom_table.rowCount(), 3)
        self.assertIs(window.canvas_stack.currentWidget(), window.structure_page)
        self.assertFalse(window.welcome_page.parrot_walk.pose_timer.isActive())
        self.assertEqual(window.vtk.initialize_count, 1)

    def test_empty_startup_is_white_welcome_with_no_fake_document_or_gl_init(self):
        window = self.window()
        page = window.welcome_page
        self.assertIs(window.canvas_stack.currentWidget(), page)
        self.assertEqual(window.files_tree.topLevelItemCount(), 0)
        self.assertIsNone(window.doc)
        self.assertEqual(window._backend_state, 'ready')
        self.assertEqual(window.vtk.initialize_count, 0)
        self.assertEqual(page.title_label.text(), APP_NAME)
        self.assertEqual(page.full_name_label.text(), APP_FULL_NAME)
        self.assertEqual(page.version_label.text(), f'Version {__version__}')
        self.assertIn(APP_CONTACT_EMAIL, page.contact_label.text())
        self.assertIn('mailto:' + APP_CONTACT_EMAIL, page.contact_label.text())
        self.assertTrue(page.contact_label.openExternalLinks())
        self.assertGreaterEqual(page.contact_label.geometry().top(), page.version_label.geometry().bottom())
        self.assertIn(APP_REPOSITORY_URL, page.repository_label.text())
        self.assertIn('href="' + APP_REPOSITORY_URL + '"', page.repository_label.text())
        self.assertTrue(page.repository_label.openExternalLinks())
        self.assertLess(page.contact_label.geometry().bottom(), page.repository_label.geometry().top())
        self.assertLess(page.repository_label.geometry().bottom(), page.open_button.geometry().top())
        self.assertFalse(window.windowIcon().isNull())
        self.assertFalse(window.windowIcon().pixmap(32, 32).isNull())
        self.assertEqual(page.parrot_walk.findChildren(QLabel), [])
        self.assertEqual(page.grab().toImage().pixelColor(1, 1).name(), '#ffffff')
        self.assertFalse(window.structure_page.isVisible())

    def test_open_button_loads_file_and_stops_welcome_animation(self):
        window = self.window()
        with patch('lele.app.QFileDialog.getOpenFileNames', return_value=([str(self.path)], '')):
            window.welcome_page.open_button.click()
        self.app.processEvents()
        self.assert_loaded(window)
        window.change_frame(0)
        self.assertEqual(window.vtk.initialize_count, 1)

    def test_ctrl_o_works_from_welcome_button_focus(self):
        window = self.window()
        window.welcome_page.open_button.setFocus()
        self.app.processEvents()
        with patch('lele.app.QFileDialog.getOpenFileNames', return_value=([str(self.path)], '')):
            QTest.keyClick(window.welcome_page.open_button, Qt.Key.Key_O,
                           Qt.KeyboardModifier.ControlModifier)
        self.assert_loaded(window)

    def test_drop_from_welcome_loads_file(self):
        window = self.window()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(self.path))])
        event = QDropEvent(QPointF(500, 200), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        window.dropEvent(event)
        self.assertTrue(event.isAccepted())
        self.assert_loaded(window)

    def test_command_line_file_opens_directly_and_failure_preserves_welcome(self):
        loaded = self.window([str(self.path)])
        self.assert_loaded(loaded)
        with patch('lele.app.QMessageBox.warning') as warning:
            empty = self.window([str(self.path.with_name('missing.xyz'))])
        warning.assert_called_once()
        self.assertIsNone(empty.doc)
        self.assertIs(empty.canvas_stack.currentWidget(), empty.welcome_page)
        self.assertEqual(empty.vtk.initialize_count, 0)

    def test_style_edits_before_first_file_are_kept_and_backend_is_reused(self):
        loader = ControlledLoader(auto_finish=False)
        window = self.window(loader=loader, wait_ready=False)
        self.wait_for(lambda: loader.start_count == 1)
        window.preset_combo.setCurrentIndex(window.preset_combo.findData('Soft pastel'))
        window._set_option('background', '#eeeeee')
        window._set_option('bond_cutoff', 1.3)
        self.assertIsNone(window.renderer)
        loader.complete()
        self.wait_for(lambda: window._backend_state == 'ready')
        window.open_path(self.path)
        self.assert_loaded(window)
        canvas, renderer = window.vtk, window.renderer
        self.assertIs(renderer.options, window.render_options)
        self.assertEqual(renderer.options.atom_palette, 'Pastel')
        self.assertEqual(renderer.options.background, '#eeeeee')
        self.assertEqual(renderer.options.bond_cutoff, 1.3)
        window.open_path(self.path)
        self.assertIs(window.vtk, canvas)
        self.assertIs(window.renderer, renderer)
        self.assertEqual(canvas.initialize_count, 1)

    def test_file_requested_while_loading_opens_automatically_when_ready(self):
        loader = ControlledLoader(auto_finish=False)
        window = self.window(loader=loader, wait_ready=False)
        self.wait_for(lambda: loader.start_count == 1)
        window.open_path(self.path)
        self.assertIsNone(window.doc)
        self.assertEqual(window._pending_open_paths, [self.path])
        self.assertTrue(window.welcome_page.parrot_walk.pose_timer.isActive())
        loader.complete()
        self.wait_for(lambda: window.doc is not None)
        self.assert_loaded(window)
        self.assertEqual(loader.start_count, 1)

    def test_closing_during_preload_does_not_create_canvas_or_open_queued_files(self):
        loader = ControlledLoader(auto_finish=False)
        window = self.window(loader=loader, wait_ready=False)
        self.wait_for(lambda: loader.start_count == 1)
        window.open_path(self.path)
        window.close()
        loader.complete()
        self.app.processEvents()
        self.assertIsNone(window.vtk)
        self.assertIsNone(window.doc)
        self.assertEqual(window._pending_open_paths, [])

    def test_preload_failure_keeps_welcome_and_file_open_can_retry(self):
        loader = ControlledLoader(auto_finish=False)
        window = self.window(loader=loader, wait_ready=False)
        self.wait_for(lambda: loader.start_count == 1)
        loader.complete('Test import failure')
        self.wait_for(lambda: window._backend_state == 'failed')
        self.assertIs(window.canvas_stack.currentWidget(), window.welcome_page)
        window.open_path(self.path)
        self.assertEqual(loader.start_count, 2)
        loader.complete()
        self.wait_for(lambda: window.doc is not None)
        self.assert_loaded(window)

    def test_pose_timer_holds_first_pose_for_800ms_and_pauses_when_hidden(self):
        page = WelcomePage()
        page.resize(1020, 798)
        page.show()
        self.addCleanup(page.close)
        self.app.processEvents()
        walk = page.parrot_walk
        self.assertEqual(len(walk.poses), 4)
        self.assertTrue(all(not pose.isNull() for pose in walk.poses))
        initial_x = walk.bird_rect().x()
        QTest.qWait(250)
        self.assertEqual(walk.pose_index, 0)
        self.assertEqual(walk.bird_rect().x(), initial_x)
        QTest.qWait(600)
        self.assertEqual(walk.pose_index, 1)
        self.assertGreater(walk.bird_rect().x(), initial_x)
        next_x = walk.bird_rect().x()
        QTest.qWait(200)
        self.assertEqual(walk.pose_index, 1)
        self.assertEqual(walk.bird_rect().x(), next_x)
        page.hide()
        self.assertFalse(walk.pose_timer.isActive())
        index = walk.pose_index
        QTest.qWait(850)
        self.assertEqual(walk.pose_index, index)
        self.assertEqual(walk.bird_rect().x(), next_x)

    def test_steps_cross_canvas_loop_and_stay_inside_after_resize(self):
        page = WelcomePage()
        page.resize(1020, 798)
        page.show()
        self.addCleanup(page.close)
        self.app.processEvents()
        walk = page.parrot_walk
        walk.pose_timer.stop()
        self.assertEqual(WALK_STEP_COUNT % 4, 0)
        # Cross both the four-pose boundary and the full-canvas boundary.
        sequence = []
        for _ in range(WALK_STEP_COUNT * 2):
            sequence.append(walk.pose_index)
            walk._next_pose()
        self.assertEqual(sequence, [0, 1, 2, 3] * (WALK_STEP_COUNT // 2))
        self.assertEqual(walk.step_index, 0)
        positions = []
        for step in range(WALK_STEP_COUNT):
            rect = walk.bird_rect()
            positions.append(rect.x())
            self.assertGreaterEqual(rect.left(), 0)
            self.assertLessEqual(rect.right(), walk.width())
            self.assertEqual(walk.pose_index, step % len(walk.poses))
            walk._next_pose()
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(positions[-1] - positions[0], walk.width() * .7)
        self.assertEqual(walk.step_index, 0)
        self.assertEqual(walk.bird_rect().x(), positions[0])
        walk.step_index = WALK_STEP_COUNT - 1
        for width, columns in ((760, 2), (510, 1), (1020, 3)):
            page.resize(width, 600)
            self.app.processEvents()
            self.assertEqual(page._columns, columns)
            self.assertLessEqual(walk.bird_rect().right(), walk.width())
            self.assertEqual(page.horizontalScrollBar().maximum(), 0)
            self.assertLessEqual(page.body.minimumSizeHint().width(), page.viewport().width())


if __name__ == '__main__':
    unittest.main()
