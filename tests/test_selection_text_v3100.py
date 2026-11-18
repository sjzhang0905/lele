"""Copyable aligned selection text and deferred hidden-panel formatting."""
import os
import subprocess
import sys
from time import monotonic
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTableView, QTabWidget, QWidget

from lele.core import Frame
from lele.selection_panel import SelectionPanel, SelectionTableModel, selection_plain_text
from test_periodic_fragment_ui_v171 import gui


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def frame():
    result = Frame(['Cu', 'O'], [[123.4, -.2, 7.], [-1234.567, 3., 4.]],
                   np.eye(3) * 5, (True, True, True))
    result.info.update(site_occupancies=[{'Cu': .75, 'Fe': .25}, {'O': 1.}],
                       fixed_axes=[[True, False, None], [False, False, False]],
                       fixed_axes_basis='cartesian',
                       constraint_notes=['Bond 1–2 constrained.'])
    return result


def test_plain_text_has_aligned_columns_mixed_occupancy_and_all_existing_fields(app):
    model = SelectionTableModel()
    model.set_frame(frame(), [0, 1])
    output = selection_plain_text(model)
    lines = output.splitlines()
    assert len(lines) == 4
    widths = [max(len(model.headers[column]), *(len(model.cell_text(row, column))
               for row in range(model.rowCount()))) for column in range(model.columnCount())]
    for row, line in enumerate(lines[1:]):
        start = 0
        for column, width in enumerate(widths):
            assert line[start:start + width].strip() == model.cell_text(row, column)
            start += width + 2
    assert 'Occ. %' in lines[0] and 'Cartesian X' in lines[0] and 'Direct Z' in lines[0]
    assert 'ORCA index' not in lines[0]
    assert 'Fixed X' in lines[0]
    assert 'Cu' in lines[1] and '75' in lines[1]
    assert 'Fe' in lines[2] and '25' in lines[2]
    assert '-246.91340000' in lines[3]  # Direct coordinates remain unwrapped.
    assert '—' in lines[1]
    assert '\t' not in output and '|' not in output


def test_real_qt_readonly_monospace_select_copy_and_preserve_selection(app):
    panel = SelectionPanel()
    try:
        panel.set_frame(frame(), [0, 1])
        panel.resize(400, 230)
        panel.show(); panel.activateWindow(); app.processEvents()
        assert isinstance(panel.text, QPlainTextEdit)
        assert panel.findChildren(QTableView) == []
        assert panel.text.isReadOnly()
        assert panel.text.lineWrapMode() == QPlainTextEdit.LineWrapMode.NoWrap
        assert panel.text.font().fixedPitch()
        assert panel.text.font().styleHint() == QFont.StyleHint.Monospace
        assert 'Bond 1–2' in panel.note_label.text()
        original = panel.text.toPlainText()
        panel.text.setFocus()
        QTest.keyClicks(panel.text, 'cannot edit')
        assert panel.text.toPlainText() == original
        QTest.keyClick(panel.text, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClick(panel.text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        assert app.clipboard().text() == original
        cursor = panel.text.textCursor()
        before = (cursor.anchor(), cursor.position())
        panel.set_frame(panel.model.frame, [0, 1])
        cursor = panel.text.textCursor()
        assert (cursor.anchor(), cursor.position()) == before
    finally:
        panel.close(); panel.deleteLater(); app.processEvents()


def test_hidden_large_selection_does_not_format_text_until_tab_is_shown(app):
    host = QTabWidget()
    panel = SelectionPanel()
    host.addTab(QWidget(), 'Other')
    host.addTab(panel, 'Current selection')
    host.show(); app.processEvents()
    large = Frame(['H'] * 100_000, np.zeros((100_000, 3)))
    try:
        with patch('lele.selection_panel.selection_plain_text', wraps=selection_plain_text) as formatter:
            for step in range(3):
                large.positions[0, 0] = step
                panel.set_frame(large, list(range(100_000)))
            assert formatter.call_count == 0
            assert panel.text.toPlainText() == ''
            assert panel.model.rowCount() == 100_000
            # Opening the tab renders only the latest pending state, not any
            # of the stale hidden trajectory frames.
            panel.set_frame(large, [0, 99_999])
            host.setCurrentWidget(panel); app.processEvents()
            assert formatter.call_count == 1
            assert '2.00000000' in panel.text.toPlainText()
            assert '100000' in panel.text.toPlainText()
    finally:
        host.close(); host.deleteLater(); app.processEvents()


def wait_for_text(app, panel, timeout=20):
    deadline = monotonic() + timeout
    while panel._text_dirty and monotonic() < deadline:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        QTest.qWait(1)
    assert not panel._text_dirty, 'The latest complete selection text was not committed.'


def test_large_visible_selection_returns_before_formatting_and_newest_generation_wins(app):
    panel = SelectionPanel()
    panel.show(); app.processEvents()
    source = Frame(['C'] * 100_000, np.full((100_000, 3), 22.25))
    indices = list(range(100_000))
    formatted_cells = []
    original_cell_text = panel.model.cell_text
    def count_cell_text(row, column):
        if len(formatted_cells) < 2:
            formatted_cells.append((row, column))
        return original_cell_text(row, column)
    panel.model.cell_text = count_cell_text
    probe = QTimer(panel)
    probe.setInterval(1)
    ticks = []
    probe.timeout.connect(lambda: ticks.append(True))
    try:
        panel.set_frame(source, indices)
        assert not formatted_cells  # No full/partial formatting inside set_frame.
        assert panel.text.toPlainText() == 'Updating…'
        assert panel.summary_label.text() == 'Atoms 1-100000'
        probe.start()
        QTest.qWait(140)
        assert ticks and formatted_cells
        assert panel._text_dirty  # The first large frame is still unfinished.
        first_generation = panel._text_generation
        following = source.clone()
        following.positions[:] = -99.125
        panel.set_frame(following, indices)
        assert panel._text_generation > first_generation
        assert panel.text.toPlainText() == 'Updating…'
        wait_for_text(app, panel)
        lines = panel.text.toPlainText().splitlines()
        assert len(lines) == 100_001
        assert lines[1].split() == ['1', 'C', '100', '-99.12500000', '-99.12500000', '-99.12500000']
        assert lines[-1].split() == ['100000', 'C', '100', '-99.12500000', '-99.12500000', '-99.12500000']
        assert '22.25000000' not in panel.text.toPlainText()
        assert len(ticks) > 2  # Other Qt timers ran while text was formatting.
        assert panel._text_job is None and not panel._text_timer.isActive()
    finally:
        probe.stop(); panel.close(); panel.deleteLater(); app.processEvents()


def test_large_chunked_output_matches_small_formatter_and_preserves_scroll(app):
    panel = SelectionPanel()
    panel.resize(300, 160)
    panel.set_frame(frame(), [0, 1])
    panel.show(); app.processEvents()
    panel.text.horizontalScrollBar().setValue(120)
    scroll = panel.text.horizontalScrollBar().value()
    source = Frame(['O'] * 2000, np.zeros((2000, 3)), np.eye(3) * 5, (True,) * 3,
                   info={'fixed_axes': [[False, True, None]] * 2000})
    source.positions[:, 0] = np.arange(2000) / 10
    try:
        panel.set_frame(source, list(range(2000)))
        assert panel.text.toPlainText() == 'Updating…'
        wait_for_text(app, panel)
        assert panel.text.toPlainText() == selection_plain_text(panel.model)
        assert panel.text.horizontalScrollBar().value() == scroll
    finally:
        panel.close(); panel.deleteLater(); app.processEvents()


def test_hiding_or_closing_cancels_pending_chunks_and_small_selection_is_immediate(app):
    panel = SelectionPanel()
    panel.show(); app.processEvents()
    source = Frame(['H'] * 10_000, np.zeros((10_000, 3)))
    try:
        panel.set_frame(source, list(range(10_000)))
        assert panel._text_timer.isActive()
        panel.hide()
        assert not panel._text_timer.isActive() and panel._text_job is None
        assert panel._text_dirty
        panel.show(); app.processEvents()
        assert panel._text_timer.isActive()
        panel.set_frame(source, [0, 9999])
        assert not panel._text_dirty and panel._text_job is None
        assert not panel._text_timer.isActive()
        assert panel.text.toPlainText().splitlines()[-1].split()[0] == '10000'
        panel.set_frame(source, list(range(10_000)))
        panel.close()
        assert not panel._text_timer.isActive() and panel._text_job is None
    finally:
        panel.close(); panel.deleteLater(); app.processEvents()


def test_main_window_selection_coordinate_chemistry_undo_and_trajectory_text(gui):
    original = frame()
    gui.attach(original, second_frame=original.clone())
    window = gui.window
    window.show(); gui.app.processEvents()
    window.selection_tabs.setCurrentWidget(window.selection_panel)
    gui.select([0])
    panel = window.selection_panel
    assert 'Cu' in panel.text.toPlainText() and 'Fe' in panel.text.toPlainText()
    window.atom_table.item(0, 1).setText('8.25')
    assert '8.25000000' in panel.text.toPlainText()
    assert window.apply_atom_species(0, [('Ni', 1.)])
    assert 'Ni' in panel.text.toPlainText() and 'Cu' not in panel.text.toPlainText()
    window.undo_edit()
    assert 'Cu' in panel.text.toPlainText() and '8.25000000' in panel.text.toPlainText()
    window.undo_edit()
    assert '123.40000000' in panel.text.toPlainText()
    window.doc.frames[1].positions[0, 0] = -55.
    window.change_frame(1)
    gui.select([0])
    assert '-55.00000000' in panel.text.toPlainText()
    window.clear_selection()
    assert panel.text.toPlainText() == ''
    window.hide()


def test_empty_panel_startup_is_qt_only():
    code = '''
import sys
from PySide6.QtWidgets import QApplication
from lele.selection_panel import SelectionPanel
app = QApplication([])
panel = SelectionPanel()
panel.show()
app.processEvents()
assert not ({'numpy', 'scipy', 'ase', 'vtkmodules', 'matplotlib'} & set(sys.modules))
'''
    result = subprocess.run([sys.executable, '-c', code], text=True, capture_output=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=20)
    assert result.returncode == 0, result.stderr
