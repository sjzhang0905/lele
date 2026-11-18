"""Resizable atom columns and compact color swatches in a real Qt tree."""
import os

import numpy as np
import pytest

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QHeaderView

from lele.atom_panel import AtomPanel
from lele.color_controls import color_value
from lele.core import Frame


@pytest.fixture
def panel():
    app = QApplication.instance() or QApplication(['atom columns'])
    widget = AtomPanel()
    widget.resize(295, 720)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def frame():
    return Frame(['Cl'] * 110, np.zeros((110, 3)))


def test_all_columns_resize_and_keep_user_width_on_refresh_and_reload(panel):
    source = frame()
    panel.set_frame(source)
    header = panel.tree.header()
    assert panel.tree.columnCount() == 4
    assert all(header.sectionResizeMode(i) == QHeaderView.ResizeMode.Interactive for i in range(4))
    assert panel.tree.columnWidth(0) >= 140
    assert panel.tree.columnWidth(3) == 50
    assert panel.tree.headerItem().text(3) == 'Occ. %'
    panel.reveal_atom(99)
    QApplication.processEvents()
    assert '#100' in panel._items[99].text(0)
    needed = panel.tree.fontMetrics().horizontalAdvance(panel._items[99].text(0)) + 60
    assert panel.tree.columnWidth(0) >= needed
    widths = (188, 60, 48, 70)
    for column, width in enumerate(widths):
        header.resizeSection(column, width)
    QApplication.processEvents()
    # All columns remain reachable in a narrow sidebar without shrinking
    # their contents or losing their user-controlled widths.
    scroll = panel.tree.horizontalScrollBar()
    assert scroll.maximum() > 0
    scroll.setValue(scroll.maximum())
    rect = panel.tree.visualRect(panel.tree.indexFromItem(panel._items[99], 3))
    assert 0 <= rect.left() < rect.right() < panel.tree.viewport().width()
    assert panel._items[99].text(3) == '100%'
    panel.set_frame(source, selection=[99])
    panel.set_frame(source.clone(), selection=[99], document_key='next file')
    assert tuple(panel.tree.columnWidth(i) for i in range(4)) == widths


def test_swatch_color_value_survives_selection_and_has_no_hex_label(panel):
    source = frame()
    colors = ['#439ea5'] * 110
    panel.set_frame(source, colors)
    panel.reveal_atom(99)
    item = panel._items[99]
    assert item.text(1) == ''
    assert item.data(1, Qt.ItemDataRole.DecorationRole).name() == '#439ea5'
    assert panel.color_button.text() == ''
    assert color_value(panel.color_button) == '#439ea5'
    assert panel.color_button.width() == panel.color_button.height() == 26
    # Paint the delegate as part of the real widget to catch invalid style
    # options without constructing hundreds of per-cell button widgets.
    assert not panel.grab().isNull()
