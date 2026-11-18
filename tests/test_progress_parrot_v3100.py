"""Truthful parrot progress, cancellation cleanup and all three entry paths."""
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest.mock import patch

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QPushButton

from lele.progress_dialog import LeleProgressDialog
from lele.welcome import POSE_INTERVAL_MS
from test_periodic_fragment_ui_v171 import gui


def progress_dialog():
    QApplication.instance() or QApplication([])
    dialog = LeleProgressDialog('Reading a calculation file\nProcessing data', 'Cancel', 0, 100)
    dialog.setMinimumDuration(2_000_000_000)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)
    dialog.resize(520, 220)
    return dialog


def test_progress_module_keeps_first_paint_free_of_scientific_imports():
    code = '''
import sys
from lele.progress_dialog import LeleProgressDialog
assert not ({'numpy','scipy','ase','vtkmodules','matplotlib'} & {n.split('.')[0] for n in sys.modules})
'''
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


def test_known_progress_positions_are_independent_of_gait_and_close_at_right(gui):
    dialog = progress_dialog()
    try:
        dialog.show();gui.app.processEvents()
        bird = dialog.parrot_walk
        assert bird.pose_timer.interval() == POSE_INTERVAL_MS
        assert len(bird.poses) == 4
        dialog.setRange(20, 40)
        dialog.setValue(20);left = bird.bird_rect().x()
        dialog.setValue(40);right = bird.bird_rect().x()
        assert right > left and bird.bird_rect().right() <= bird.width()
        assert not bird.pose_timer.isActive()
        dialog.setValue(30)
        assert bird.fraction == .5
        assert bird.bird_rect().x() == pytest.approx((left+right)/2)
        before = bird.bird_rect()
        bird._next_pose()
        assert bird.bird_rect() == before
        assert bird.pose_timer.isActive()
        assert dialog.label.geometry().bottom() < bird.geometry().top()
        assert bird.geometry().bottom() < dialog.progress_bar.geometry().top()
        assert dialog.progress_bar.geometry().bottom() < dialog.findChild(QPushButton).geometry().top()
        dialog.mark_complete()
        assert bird.fraction == 1. and bird.bird_rect().x() == right
        assert not bird.pose_timer.isActive()
    finally:
        dialog.close();dialog.deleteLater()


def test_unknown_busy_progress_walks_in_place_without_percentage(gui):
    dialog = progress_dialog()
    try:
        dialog.setRange(0, 0);dialog.show();gui.app.processEvents()
        assert dialog.parrot_walk.fraction is None
        assert not dialog.progress_bar.isTextVisible()
        initial = dialog.parrot_walk.bird_rect()
        dialog.parrot_walk._next_pose()
        assert dialog.parrot_walk.bird_rect() == initial
        assert dialog.parrot_walk.pose_timer.isActive()
    finally:
        dialog.close();dialog.deleteLater()


def test_hidden_progress_reuses_welcome_artwork_without_reading_or_cropping(gui):
    with patch('lele.welcome.QPixmap', side_effect=AssertionError('Repeated artwork read')):
        dialog = progress_dialog()
    try:
        assert dialog.parrot_walk.poses is gui.window.welcome_page.parrot_walk.poses
        assert not dialog.parrot_walk.pose_timer.isActive()
    finally:
        dialog.close();dialog.deleteLater()


def test_frequent_reports_do_not_restart_the_pose_clock(gui):
    dialog = progress_dialog()
    timer = QTimer()
    try:
        dialog.show();dialog.setValue(25)
        timer.setInterval(20)
        timer.timeout.connect(lambda: dialog.setValue(25))
        timer.start()
        QTest.qWait(POSE_INTERVAL_MS+120)
        assert dialog.parrot_walk.pose_index == 1
        assert dialog.parrot_walk.fraction == .25
    finally:
        timer.stop();dialog.close();dialog.deleteLater()


@pytest.mark.parametrize('method', ['button', 'escape', 'window'])
def test_cancel_stops_all_owned_timers_and_signals_once(gui, method):
    dialog = progress_dialog()
    extra_timer = QTimer(dialog);extra_timer.start(50)
    spy = QSignalSpy(dialog.canceled)
    try:
        dialog.show();gui.app.processEvents()
        if method == 'button':dialog.findChild(QPushButton).click()
        elif method == 'escape':QTest.keyClick(dialog, Qt.Key.Key_Escape)
        else:
            event = QCloseEvent();QApplication.sendEvent(dialog, event)
            assert event.isAccepted()
        assert dialog.wasCanceled() and spy.count() == 1
        assert not any(timer.isActive() for timer in dialog.findChildren(QTimer))
        dialog.cancel()
        assert spy.count() == 1
    finally:
        dialog.close();dialog.deleteLater()


def test_noncancellable_operation_ignores_user_close_and_finishes_silently(gui):
    from lele.operations import OperationProgress
    dialog = OperationProgress(gui.window, 'Rendering')
    spy = QSignalSpy(dialog.canceled)
    dialog.show();gui.app.processEvents()
    event = QCloseEvent();QApplication.sendEvent(dialog, event)
    assert not event.isAccepted() and dialog.isVisible()
    dialog.reject()
    assert not dialog.wasCanceled() and dialog.isVisible()
    dialog.finish()
    assert spy.count() == 0
    assert not any(timer.isActive() for timer in dialog.findChildren(QTimer))


def test_run_data_task_uses_reported_position_and_finishes_at_right(gui, monkeypatch):
    import lele.operations as operations
    from lele.output_text import load_progress
    original = operations.OperationProgress
    captured, final = [], []
    ready, release = threading.Event(), threading.Event()
    class TrackingProgress(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs);captured.append(self)
        def finish(self, completed=True):
            super().finish(completed)
            final.append((self.parrot_walk.fraction, self.parrot_walk.pose_timer.isActive()))
    monkeypatch.setattr(operations, 'OperationProgress', TrackingProgress)
    monkeypatch.setattr(operations, 'DELAY_MS', 0)
    observations = []
    timer = QTimer()
    def inspect():
        if ready.is_set() and captured and captured[0].parrot_walk.fraction == .25:
            observations.append((captured[0].isVisible(), captured[0].parrot_walk.pose_timer.isActive()))
            release.set()
    timer.timeout.connect(inspect);timer.start(10)
    def work():
        report = load_progress('Processing', 4)
        # The shared reporter deliberately coalesces updates inside 50 ms.
        threading.Event().wait(.08)
        report(1);ready.set()
        assert release.wait(3), 'Progress report did not reach the GUI'
        report(4)
        return 42
    try:
        assert operations.run_data_task(gui.window, 'Calculation', work) == 42
    finally:
        release.set();timer.stop()
    assert observations and observations[0] == (True, True)
    assert final == [(1., False)]


def test_file_loader_uses_same_animation_and_cancellation_cleanup(gui, tmp_path, monkeypatch):
    from lele.output_text import LoadCancelled
    from test_large_files_v250 import wait_until
    window = gui.window
    window._closing = False;window._backend_state = 'ready'
    path = tmp_path/'input.out';path.write_text('placeholder')
    entered = threading.Event()
    def slow_read(path, *, cancelled=None, progress=None):
        progress('Reading', 1, 4);entered.set()
        while not cancelled():
            threading.Event().wait(.005)
        raise LoadCancelled()
    monkeypatch.setattr('lele.formats.load_document', slow_read)
    window.open_path(path)
    wait_until(gui, lambda: entered.is_set() and window._file_load_progress.parrot_walk.fraction == .25)
    dialog = window._file_load_progress
    assert isinstance(dialog, LeleProgressDialog)
    dialog.show();gui.app.processEvents()
    assert dialog.parrot_walk.pose_timer.isActive()
    dialog.cancel()
    assert not any(timer.isActive() for timer in dialog.findChildren(QTimer))
    wait_until(gui, lambda: window._file_load_active is None)
    wait_until(gui, lambda: not gui.app._lele_file_loaders)


def test_parent_close_during_import_delay_cannot_resurrect_progress(gui, tmp_path, monkeypatch):
    from lele.output_text import LoadCancelled
    from test_large_files_v250 import wait_until
    window = gui.window
    window._closing = False;window._backend_state = 'ready'
    path = tmp_path/'input.out';path.write_text('placeholder')
    entered, release = threading.Event(), threading.Event()
    def slow_read(path, *, cancelled=None, progress=None):
        entered.set()
        release.wait(3)
        raise LoadCancelled()
    monkeypatch.setattr('lele.formats.load_document', slow_read)
    window.open_path(path)
    wait_until(gui, entered.is_set)
    dialog = window._file_load_progress
    try:
        window._closing = True
        window._cancel_file_imports()
        assert window._file_load_active.isInterruptionRequested()
        assert not any(timer.isActive() for timer in dialog.findChildren(QTimer))
        QTest.qWait(400)
        assert not dialog.isVisible()
        dialog._show_if_active()
        assert not dialog.isVisible()
    finally:
        release.set()
        wait_until(gui, lambda: window._file_load_active is None)
        wait_until(gui, lambda: not gui.app._lele_file_loaders)
        window._closing = False


def test_gif_path_uses_common_dialog_and_actual_frame_count(gui, tmp_path):
    from lele.animation_export import GifSettings
    from lele.core import Frame
    frame = Frame(['H'], [[0., 0., 0.]])
    gui.attach(frame, second_frame=frame.clone())
    window = gui.window;seen = []
    def fake_export(path, document, settings, options, **kwargs):
        dialog = window._gif_progress
        assert isinstance(dialog, LeleProgressDialog)
        kwargs['progress'](1, 2)
        seen.append(dialog.parrot_walk.fraction)
        kwargs['progress'](2, 2)
        seen.append(dialog.parrot_walk.fraction)
        assert not dialog.parrot_walk.pose_timer.isActive()
        return 2
    with patch('lele.animation_export.export_animation_gif', side_effect=fake_export):
        assert window._save_gif_file(tmp_path/'test.gif', GifSettings(last_frame=2))
    assert seen == [.5, 1.] and window._gif_progress is None
