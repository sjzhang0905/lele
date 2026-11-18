"""Numbered fragments retain frame identities and canvas-only key handling."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QVBoxLayout, QWidget

from lele.atom_indices import reorder_atoms
from lele.core import Document, Frame
from lele.fragment_shortcuts import fragment_key_request
from lele.interaction import InteractiveVTKView
from lele.saved_fragments import add_fragment, fragments, get_fragment, save_fragment_slot
from lele.selection_geometry import delete_selected_atoms
from test_periodic_fragment_ui_v171 import gui


def structure():
    return Frame(['C', 'N', 'O', 'H'], [[0, 0, 0], [4, 0, 0], [8, 0, 0], [12, 0, 0]], energy_ev=-5.)


def test_slot_replace_append_and_empty_selection_preserve_snapshot_and_next_name():
    frame = structure()
    record, changed = save_fragment_slot(frame, 2, [2, 0, 2])
    assert changed and record == {'name': 'fragment2', 'indices': [0, 2]}
    snapshot = frame.clone()
    record, changed = save_fragment_slot(frame, 2, [1, 2], append=True)
    assert changed and record['indices'] == [0, 1, 2]
    assert fragments(snapshot) == [{'name': 'fragment2', 'indices': [0, 2]}]
    info = frame.info
    assert save_fragment_slot(frame, 2, [0], append=True)[1] is False
    assert save_fragment_slot(frame, 2, [], append=False)[1] is False
    assert frame.info is info
    assert save_fragment_slot(frame, 9, [3])[1]
    assert add_fragment(frame, [0])['name'] == 'fragment10'
    assert save_fragment_slot(frame, 2, [3])[0]['indices'] == [3]
    with pytest.raises(ValueError):
        save_fragment_slot(frame, 0, [0])
    with pytest.raises(ValueError):
        save_fragment_slot(frame, 1, [99])


def test_slot_names_use_existing_reorder_and_delete_identity_mapping():
    frame = structure()
    save_fragment_slot(frame, 1, [0, 2])
    reorder_atoms(frame, [2, 3, 0, 1])
    assert get_fragment(frame, 'fragment1')['indices'] == [0, 2]
    delete_selected_atoms(frame, [0])
    assert get_fragment(frame, 'fragment1')['indices'] == [1]
    assert frame.symbols[1] == 'C'


def key_event(key, modifiers=Qt.KeyboardModifier.NoModifier, *, scan=0, native=0, text='', repeat=False):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers, scan, native, 0, text, repeat)


@pytest.mark.parametrize('number', range(1, 10))
def test_digit_modifier_combinations_and_shift_symbols(number):
    key = int(Qt.Key.Key_0) + number
    assert fragment_key_request(key_event(key)) == ('select', number)
    assert fragment_key_request(key_event(key, Qt.KeyboardModifier.ControlModifier)) == ('save', number)
    assert fragment_key_request(key_event(key, Qt.KeyboardModifier.ShiftModifier)) == ('append', number)
    symbol = '!@#$%^&*('[number - 1]
    assert fragment_key_request(key_event(ord(symbol), Qt.KeyboardModifier.ShiftModifier)) == ('append', number)
    assert fragment_key_request(key_event(key, Qt.KeyboardModifier.AltModifier)) is None
    assert fragment_key_request(key_event(key, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)) is None
    assert fragment_key_request(key_event(Qt.Key.Key_0)) is None


def test_native_shifted_digit_layouts_do_not_steal_other_punctuation_keys():
    shift = Qt.KeyboardModifier.ShiftModifier
    assert fragment_key_request(key_event(Qt.Key.Key_QuoteDbl, shift, native=0x32), platform='windows') == ('append', 2)
    assert fragment_key_request(key_event(Qt.Key.Key_At, shift, native=0xde), platform='windows') is None
    assert fragment_key_request(key_event(Qt.Key.Key_section, shift, scan=12, native=0xa7), platform='xcb') == ('append', 3)
    assert fragment_key_request(key_event(Qt.Key.Key_At, shift, scan=48, native=0x40), platform='xcb') is None
    assert fragment_key_request(key_event(Qt.Key.Key_Exclam, shift, native=18), platform='cocoa') == ('append', 1)


@pytest.fixture
def canvas():
    app = QApplication.instance() or QApplication([])
    container = QWidget()
    layout = QVBoxLayout(container)
    view = InteractiveVTKView(container)
    view.GetRenderWindow().Render = lambda: None
    layout.addWidget(view)
    text = QLineEdit()
    number = QDoubleSpinBox()
    layout.addWidget(text)
    layout.addWidget(number)
    container.resize(400, 300)
    container.show()
    container.activateWindow()
    view.setFocus()
    app.processEvents()
    try:
        yield app, container, view, text, number
    finally:
        container.close()
        container.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_real_qt_keys_fire_once_only_on_canvas_and_leave_existing_actions(canvas):
    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    app, container, view, text, number = canvas
    events = []
    view.fragmentSlotRequested.connect(lambda operation, slot: events.append((operation, slot)))
    assert view.hasFocus()
    stereo = view.GetRenderWindow().GetStereoRender()
    with patch.object(QVTKRenderWindowInteractor, 'keyPressEvent') as vtk_press, \
         patch.object(QVTKRenderWindowInteractor, 'keyReleaseEvent') as vtk_release:
        QTest.keyClick(view, Qt.Key.Key_3)
        assert not vtk_press.called and not vtk_release.called
    assert view.GetRenderWindow().GetStereoRender() == stereo
    QTest.keyClick(view, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(view, Qt.Key.Key_2, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClick(view, Qt.Key.Key_At, Qt.KeyboardModifier.ShiftModifier)
    app.sendEvent(view, key_event(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, repeat=True))
    assert events == [('select', 3), ('save', 1), ('append', 2), ('append', 2)]
    original_shortcuts = []
    action = QAction(container)
    action.setShortcut(QKeySequence('Ctrl+G'))
    action.triggered.connect(lambda: original_shortcuts.append('Ctrl+G'))
    container.addAction(action)
    QTest.keyClick(view, Qt.Key.Key_G, Qt.KeyboardModifier.ControlModifier)
    assert original_shortcuts == ['Ctrl+G']
    text.setFocus()
    QTest.keyClicks(text, '123')
    assert text.text() == '123' and len(events) == 4
    number.setFocus()
    number.lineEdit().selectAll()
    QTest.keyClicks(number.lineEdit(), '42')
    QTest.keyClick(number, Qt.Key.Key_Return)
    assert number.value() == 42 and len(events) == 4
    app.sendEvent(view, key_event(Qt.Key.Key_1))  # even a misrouted event needs focus
    assert len(events) == 4


def test_shortcut_overrides_conflicting_widget_action_only_with_canvas_focus(canvas):
    app, container, view, text, _number = canvas
    actions, requests = [], []
    action = QAction(container)
    action.setShortcut(QKeySequence('Ctrl+1'))
    action.triggered.connect(lambda: actions.append('action'))
    container.addAction(action)
    view.fragmentSlotRequested.connect(lambda *args: requests.append(args))
    QTest.keyClick(view, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert requests == [('save', 1)] and not actions
    text.setFocus()
    QTest.keyClick(text, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert actions == ['action'] and requests == [('save', 1)]


def test_slot_actions_undo_metadata_and_selection_without_altering_geometry(gui):
    gui.attach(structure())
    w = gui.window
    gui.select([0, 2])
    before = w.frame.clone()
    w.doc.modified = False
    count = len(w.undo_stack)
    w.fragment_slot_shortcut('save', 1)
    assert w.doc.modified and len(w.undo_stack) == count + 1
    assert w.fragment_panel.list_widget.count() == 1
    assert get_fragment(w.frame, 'fragment1')['indices'] == [0, 2]
    w.fragment_slot_shortcut('append', 1)
    assert len(w.undo_stack) == count + 1
    w.selection = []
    w.fragment_slot_shortcut('save', 1)
    assert get_fragment(w.frame, 'fragment1')['indices'] == [0, 2]
    assert len(w.undo_stack) == count + 1
    w.selection = [1]
    w.fragment_slot_shortcut('append', 1)
    assert get_fragment(w.frame, 'fragment1')['indices'] == [0, 1, 2]
    w.undo_edit()
    assert get_fragment(w.frame, 'fragment1')['indices'] == [0, 2]
    w.doc.modified = False
    w.fragment_slot_shortcut('select', 1)
    assert w.selection == [0, 2] and not w.doc.modified
    w.undo_edit()
    assert w.selection == [1]
    w.undo_edit()
    assert fragments(w.frame) == []
    np.testing.assert_array_equal(w.frame.positions, before.positions)
    assert w.frame.energy_ev == before.energy_ev
    assert w.frame.bond_snapshot is before.bond_snapshot


def test_real_canvas_keys_drive_fragment_actions_and_ignore_repeat(gui, canvas):
    app, _container, view, _text, _number = canvas
    gui.attach(structure())
    window = gui.window
    view.fragmentSlotRequested.connect(window.fragment_slot_shortcut)
    gui.select([0, 2])
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    assert get_fragment(window.frame, 'fragment1')['indices'] == [0, 2]
    gui.select([1])
    count = len(window.undo_stack)
    app.sendEvent(view, key_event(Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier, repeat=True))
    assert get_fragment(window.frame, 'fragment1')['indices'] == [0, 2]
    assert len(window.undo_stack) == count
    QTest.keyClick(view, Qt.Key.Key_Exclam, Qt.KeyboardModifier.ShiftModifier)
    assert get_fragment(window.frame, 'fragment1')['indices'] == [0, 1, 2]
    QTest.keyClick(view, Qt.Key.Key_1)
    assert window.selection == [0, 1, 2]
    assert window.fragment_panel.list_widget.count() == 1


def test_slot_actions_are_document_local_and_survive_project_roundtrip(gui, tmp_path):
    gui.attach(structure())
    w = gui.window
    gui.select([1, 3])
    w.fragment_slot_shortcut('save', 2)
    other = Document(Path('second.xyz'), 'XYZ', [structure()])
    w._attach_loaded_document(other)
    gui.select([0])
    w.fragment_slot_shortcut('select', 2)
    assert w.selection == [0] and fragments(w.frame) == []
    w.fragment_slot_shortcut('append', 2)
    assert get_fragment(w.frame, 'fragment2')['indices'] == [0]
    w.change_frame(0, switch_doc=0)
    w.fragment_slot_shortcut('select', 2)
    assert w.selection == [1, 3]
    path = tmp_path / 'slots.lele'
    assert w.save_project_to(path)
    assert w._load_project_path(path)
    w.fragment_slot_shortcut('select', 2)
    assert w.selection == [1, 3]
    w.change_frame(0, switch_doc=1)
    assert get_fragment(w.frame, 'fragment2')['indices'] == [0]
