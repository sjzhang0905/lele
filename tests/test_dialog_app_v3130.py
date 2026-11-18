"""Main-window controls remain available with help open; cancelled exports stay local."""
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from lele.core import Document, Frame
from test_periodic_fragment_ui_v171 import gui


def test_help_is_reused_modeless_owned_and_main_controls_remain_live(gui):
    window = gui.window
    window.show()
    help_window = window.help_dialog()
    gui.app.processEvents()
    assert help_window.isVisible()
    assert help_window.windowModality() == Qt.WindowModality.NonModal
    assert not (help_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert help_window.windowHandle().transientParent() is window.windowHandle()
    assert QApplication.activeModalWidget() is None
    assert window.help_dialog() is help_window
    original = window.cell_check.isChecked()
    window.cell_check.click()
    assert window.cell_check.isChecked() is not original
    assert window.render_options.unit_cell is not original
    QTest.mouseClick(window.vtk, Qt.MouseButton.LeftButton)
    window.activateWindow()
    window.vtk.setFocus()
    gui.app.processEvents()
    QTest.keyClick(window.vtk, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert window.selection == list(range(len(window.frame.symbols)))
    assert help_window.isVisible()
    help_window.close()
    gui.app.processEvents()
    assert window._help_window is None


def test_cancelled_png_does_not_restart_playback_on_new_document(gui):
    window = gui.window
    other = Document(Path(gui.temp.name) / 'other.xyz', 'XYZ', [Frame(['He'], [[0., 0., 0.]])])
    window.documents.append(other)
    window.playback.start(60000)
    def switch_then_cancel(*args, **kwargs):
        window.change_frame(0, switch_doc=1)
        return '', ''
    with patch('lele.app.QFileDialog.getSaveFileName', side_effect=switch_then_cancel):
        window.save_png()
    assert window.doc is other
    assert not window.playback.isActive()
    assert not window._png_exporting


def test_cancelled_png_restores_playback_when_source_unchanged(gui):
    window = gui.window
    window.playback.start(60000)
    with patch('lele.app.QFileDialog.getSaveFileName', return_value=('', '')):
        window.save_png()
    assert window.playback.isActive()
    window.playback.stop()
