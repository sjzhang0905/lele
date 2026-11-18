"""Nonmodal dialogs keep the main window live and reject stale source edits."""
import gc
import os
import weakref
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6 import QtWidgets
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton
from shiboken6 import isValid

# Keep these before importing policy: project adapters must not patch Qt itself.
NativeDialog = QtWidgets.QDialog
NativeMessageBox = QtWidgets.QMessageBox
NativeFileDialog = QtWidgets.QFileDialog
NativeInputDialog = QtWidgets.QInputDialog
NativeColorDialog = QtWidgets.QColorDialog

from lele import dialog_policy as policy
from lele.atom_appearance import AtomAppearance
from lele.core import Document, Frame


@pytest.fixture
def app():
    instance = QApplication.instance() or QApplication([])
    before = set(instance.topLevelWidgets())
    quit_on_close = instance.quitOnLastWindowClosed()
    instance.setQuitOnLastWindowClosed(False)
    yield instance
    for widget in instance.topLevelWidgets():
        if widget not in before and isValid(widget):
            widget.close(); widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    instance.processEvents()
    instance.setQuitOnLastWindowClosed(quit_on_close)


class Owner(QMainWindow):
    def __init__(self):
        super().__init__()
        self.documents = [Document(Path('/tmp/source.xyz'), 'XYZ',
            [Frame(['C', 'H'], [[0., 0., 0.], [1., 0., 0.]])])]
        self.current_doc = 0
        self.frame_index = 0
        self.selection = [0]
        self.camera = {'azimuth': 0.}
        self.style = 'Ball and stick'
        self._closing = False
        self.button = QPushButton('Main canvas control', self)
        self.setCentralWidget(self.button)
        self.clicks = 0
        self.button.clicked.connect(self.count_click)

    @property
    def doc(self):
        return self.documents[self.current_doc]

    @property
    def frame(self):
        return self.doc.frames[self.frame_index]

    def count_click(self):
        self.clicks += 1


@pytest.fixture
def owner(app):
    window = Owner(); window.show(); app.processEvents()
    yield window
    if isValid(window):
        window.close(); window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def run_dialog(app, dialog, action):
    """Exercise a nested loop without letting a regression hang the test run."""
    errors = []; expired = []
    timer = QTimer(); timer.setSingleShot(True)

    def expire():
        expired.append(True)
        for widget in list(app.topLevelWidgets()):
            if isValid(widget) and isinstance(widget, NativeDialog):
                widget.reject()

    def exercise():
        try:
            action()
        except BaseException as exc:
            errors.append(exc)
            if isValid(dialog):
                dialog.reject()

    timer.timeout.connect(expire); timer.start(2500)
    QTimer.singleShot(0, exercise)
    try:
        result = dialog.exec()
    finally:
        timer.stop()
    assert not expired, 'Dialog wait did not finish after its completion/owner event.'
    if errors:
        raise errors[0]
    return result


def assert_live(app, owner, dialog):
    assert dialog.isVisible()
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert not (dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert dialog.windowHandle().transientParent() is dialog.parentWidget().window().windowHandle()
    assert app.activeModalWidget() is None
    assert owner.isEnabled() and owner.button.isEnabled()
    before = owner.clicks
    QTest.mouseClick(owner.button, Qt.MouseButton.LeftButton)
    assert owner.clicks == before + 1


def test_project_policy_does_not_monkeypatch_global_qt():
    assert QtWidgets.QDialog is NativeDialog
    assert QtWidgets.QMessageBox is NativeMessageBox
    assert QtWidgets.QFileDialog is NativeFileDialog
    assert QtWidgets.QInputDialog is NativeInputDialog
    assert QtWidgets.QColorDialog is NativeColorDialog
    assert policy.QDialog is not NativeDialog


def test_configure_and_exec_leave_main_canvas_interactive(app, owner):
    dialog = policy.QDialog(owner); dialog.setWindowTitle('Rotate around axis')
    policy.configure_dialog(dialog)
    assert dialog.windowModality() == Qt.WindowModality.NonModal
    assert not (dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def action():
        assert_live(app, owner, dialog)
        dialog.accept()

    assert run_dialog(app, dialog, action) == NativeDialog.DialogCode.Accepted
    assert not dialog.isVisible()


def test_nested_owned_dialog_still_keeps_main_window_enabled(app, owner):
    first = policy.QDialog(owner); first.setWindowTitle('Structure settings')

    def action():
        second = policy.QDialog(first); second.setWindowTitle('Nested numeric entry')
        def inner():
            assert_live(app, owner, second)
            assert first.isEnabled()
            second.accept()
        assert run_dialog(app, second, inner) == NativeDialog.DialogCode.Accepted
        first.accept()

    assert run_dialog(app, first, action) == NativeDialog.DialogCode.Accepted


def mutate_positions(owner):
    owner.frame.positions[0, 0] += .25


def switch_document(owner):
    owner.documents.append(Document(Path('/tmp/other.xyz'), 'XYZ',
        [Frame(['O'], [[2., 0., 0.]])]))
    owner.current_doc = 1


def mutate_selection(owner):
    owner.selection.append(1)


def mutate_annotations(owner):
    owner.doc.annotations.append({'kind': 'text', 'text': 'changed'})


def mutate_volumes(owner):
    owner.doc.volumes.append(SimpleNamespace(data=np.ones((2, 2, 2)),
        origin=np.zeros(3), axes=np.eye(3)))


@pytest.mark.parametrize('mutation', [mutate_positions, switch_document, mutate_selection,
                                     mutate_annotations, mutate_volumes],
                         ids=['in_place_coordinates', 'document_switch', 'selection',
                              'annotations', 'volumes'])
def test_source_changes_reject_stale_accept_with_visible_reason(app, owner, mutation):
    dialog = policy.QDialog(owner); dialog.setWindowTitle('Edit captured source')

    def action():
        assert_live(app, owner, dialog)
        mutation(owner)
        dialog.accept()

    assert run_dialog(app, dialog, action) == NativeDialog.DialogCode.Rejected
    reason = getattr(dialog, '_lele_context_rejection', '')
    assert reason
    app.processEvents()
    messages = [w for w in app.topLevelWidgets() if isinstance(w, NativeMessageBox)
                and w.isVisible() and w.windowTitle() == 'Source changed']
    assert reason in owner.statusBar().currentMessage()
    assert messages and reason in messages[0].text()
    assert app.activeModalWidget() is None


def test_camera_and_style_changes_do_not_reject_source_edit(app, owner):
    dialog = policy.QDialog(owner); dialog.setWindowTitle('Edit while viewing')

    def action():
        owner.camera['azimuth'] = 45.
        owner.style = 'Space filling'
        owner.frame.atom_appearance[0] = AtomAppearance(color='#1a2b3c', representation='Space filling')
        dialog.accept()

    assert run_dialog(app, dialog, action) == NativeDialog.DialogCode.Accepted
    assert not getattr(dialog, '_lele_context_rejection', '')


def test_duplicate_dialog_is_rejected_without_dismissing_existing_one(app, owner):
    first = policy.QDialog(owner); first.setWindowTitle('Same operation')

    def action():
        duplicate = policy.QDialog(owner); duplicate.setWindowTitle('Same operation')
        assert duplicate.exec() == NativeDialog.DialogCode.Rejected
        assert first.isVisible() and not duplicate.isVisible()
        assert_live(app, owner, first)
        first.accept()

    assert run_dialog(app, first, action) == NativeDialog.DialogCode.Accepted


@pytest.mark.parametrize('event', ['close', 'destroy', 'quit'])
def test_owner_lifecycle_events_release_dialog_wait(app, owner, event):
    dialog = policy.QDialog(owner); dialog.setWindowTitle('Pending decision')

    def action():
        if event == 'close':
            owner.close()
        elif event == 'destroy':
            owner.deleteLater()
        else:
            # Emitting the shutdown signal tests its connection without
            # terminating the QApplication shared with the remaining tests.
            app.aboutToQuit.emit()

    assert run_dialog(app, dialog, action) == NativeDialog.DialogCode.Rejected


def test_information_is_async_nonmodal_and_retained_until_closed(app, owner):
    result = policy.QMessageBox.information(owner, 'Async information', 'Ready to continue')
    assert result == NativeMessageBox.StandardButton.Ok
    gc.collect(); app.processEvents()
    boxes = [w for w in app.topLevelWidgets() if isinstance(w, NativeMessageBox)
             and w.isVisible() and w.windowTitle() == 'Async information']
    assert len(boxes) == 1
    assert_live(app, owner, boxes[0])
    boxes[0].accept(); app.processEvents()
    assert not boxes[0].isVisible() if isValid(boxes[0]) else True


def test_show_dialog_retains_parentless_window_until_completion(app):
    dialog = policy.QDialog(); dialog.setWindowTitle('Detached result')
    reference = weakref.ref(dialog)
    policy.show_dialog(dialog)
    del dialog
    gc.collect(); app.processEvents()
    assert reference() is not None and reference().isVisible()
    reference().reject()
    app.processEvents()
    assert reference() is None or not reference().isVisible()


def run_static(app, owner, native_class, title, invoke, choose):
    errors = []; handled = []; expired = []
    timer = QTimer(); watchdog = QTimer(); watchdog.setSingleShot(True)

    def poll():
        dialogs = [w for w in app.topLevelWidgets() if isinstance(w, native_class)
                   and w.isVisible() and w.windowTitle() == title]
        if not dialogs:
            return
        timer.stop(); dialog = dialogs[0]; handled.append(True)
        try:
            assert_live(app, owner, dialog)
            choose(dialog)
        except BaseException as exc:
            errors.append(exc); dialog.reject()

    def timeout():
        expired.append(True)
        for widget in list(app.topLevelWidgets()):
            if isValid(widget) and isinstance(widget, NativeDialog):
                widget.reject()

    timer.timeout.connect(poll); timer.start(1)
    watchdog.timeout.connect(timeout); watchdog.start(2500)
    try:
        result = invoke()
    finally:
        timer.stop(); watchdog.stop()
    assert handled and not expired
    if errors:
        raise errors[0]
    return result


def test_question_waits_for_choice_without_blocking_main_window(app, owner):
    result = run_static(app, owner, NativeMessageBox, 'Confirm operation',
        lambda: policy.QMessageBox.question(owner, 'Confirm operation', 'Apply?',
            NativeMessageBox.StandardButton.Yes | NativeMessageBox.StandardButton.No),
        lambda dialog: dialog.button(NativeMessageBox.StandardButton.Yes).click())
    assert result == NativeMessageBox.StandardButton.Yes


def test_file_picker_is_nonnative_nonmodal_and_returns_selected_path(app, owner, tmp_path):
    source = tmp_path / 'sample.xyz'; source.write_text('1\n\nH 0 0 0\n')

    def choose(dialog):
        assert dialog.testOption(NativeFileDialog.Option.DontUseNativeDialog)
        dialog.selectFile(str(source)); dialog.accept()

    result = run_static(app, owner, NativeFileDialog, 'Choose structure',
        lambda: policy.QFileDialog.getOpenFileName(owner, 'Choose structure', str(tmp_path), 'XYZ (*.xyz)'),
        choose)
    assert Path(result[0]) == source


def test_text_input_waits_nonmodally_and_returns_updated_value(app, owner):
    def choose(dialog):
        dialog.setTextValue('72.5'); dialog.accept()

    value, accepted = run_static(app, owner, NativeInputDialog, 'Rotation angle',
        lambda: policy.QInputDialog.getText(owner, 'Rotation angle', 'Degrees', text='0'),
        choose)
    assert accepted and value == '72.5'


def test_item_input_waits_nonmodally_and_returns_updated_choice(app, owner):
    def choose(dialog):
        dialog.setTextValue('Blue'); dialog.accept()

    value, accepted = run_static(app, owner, NativeInputDialog, 'Display choice',
        lambda: policy.QInputDialog.getItem(owner, 'Display choice', 'Color',
            ['Red', 'Blue'], 0, False), choose)
    assert accepted and value == 'Blue'


def test_color_picker_is_nonnative_nonmodal_and_returns_selected_color(app, owner):
    def choose(dialog):
        assert dialog.testOption(NativeColorDialog.ColorDialogOption.DontUseNativeDialog)
        dialog.setCurrentColor(QColor('#1a2b3c')); dialog.accept()

    color = run_static(app, owner, NativeColorDialog, 'Atom color',
        lambda: policy.QColorDialog.getColor(QColor('#ffffff'), owner, 'Atom color'), choose)
    assert color.isValid() and color.name() == '#1a2b3c'


@pytest.mark.parametrize('changed',[False,True])
def test_custom_accept_button_zero_result_cannot_bypass_source_guard(app,owner,changed):
    from lele.structure_edit_dialogs import confirm_maximum_occupancy_export
    def choose(dialog):
        if changed:owner.frame.positions[0,0]+=.5
        button=next(b for b in dialog.buttons() if b.text()=='Use highest-occupancy element')
        button.click()
    accepted=run_static(app,owner,NativeMessageBox,'Mixed / partial occupancy export',
                       lambda:confirm_maximum_occupancy_export(owner),choose)
    assert accepted is (not changed)


def test_async_popup_closes_when_owner_accepts_close(app,owner):
    dialog=policy.show_dialog(policy.QDialog(owner))
    owner.close();app.processEvents()
    assert not dialog.isVisible()
    assert id(dialog) not in policy._live_dialogs


def test_async_popup_stays_open_when_owner_ignores_close(app):
    class BusyOwner(Owner):
        def closeEvent(self,event):event.ignore()
    owner=BusyOwner();owner.show()
    dialog=policy.show_dialog(policy.QDialog(owner))
    owner.close();app.processEvents()
    assert owner.isVisible() and dialog.isVisible()
    dialog.reject();owner.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def test_parent_form_completion_releases_nested_child_wait(app,owner):
    parent=policy.show_dialog(policy.QDialog(owner))
    child=policy.QDialog(parent);child.setWindowTitle('Nested decision')
    assert run_dialog(app,child,parent.reject)==NativeDialog.DialogCode.Rejected
    assert not child.isVisible() and owner.isEnabled()


def test_reorientation_rejects_atom_deletion_before_indexing_stale_plan(app,owner):
    from lele.reorientation_dialog import ReorientationDialog
    dialog=ReorientationDialog(owner.frame,parent=owner)
    dialog.origin.setValue(2)
    def action():
        owner.frame.positions=owner.frame.positions[:1].copy()
        owner.frame.symbols=owner.frame.symbols[:1]
        dialog._accept_plan()
    assert run_dialog(app,dialog,action)==NativeDialog.DialogCode.Rejected
    assert dialog._lele_context_rejection
