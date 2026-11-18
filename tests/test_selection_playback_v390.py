"""Typing an element selection must not race trajectory playback."""
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from lele.core import Frame
from test_periodic_fragment_ui_v171 import gui


def test_element_editor_focus_pauses_frame_playback(gui):
    frame = Frame(['O', 'H', 'H'], [[0, 0, 0], [1, 0, 0], [0, 1, 0]])
    gui.attach(frame, second_frame=frame.clone())
    window = gui.window
    window.show()
    window.selection_tabs.setCurrentWidget(window.atoms_selection_panel)
    gui.app.processEvents()
    window.vtk.setFocus()
    gui.app.processEvents()
    window.playback.start(50000)
    window.play_btn.setText('Pause')
    editor = window.atoms_selection_panel.inputs['H']
    QTest.mouseClick(editor, Qt.MouseButton.LeftButton)
    gui.app.processEvents()
    assert not window.playback.isActive()
    assert window.play_btn.text() == 'Play'
    QTest.keyClicks(editor, '1-2')
    QTest.keyClick(editor, Qt.Key.Key_Return)
    assert window.selection == [1, 2]
    assert window.frame_index == 0
    assert window.atoms_selection_panel.inputs['H'] is editor
