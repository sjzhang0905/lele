"""Clipboard coordinates must preserve the active structure, not recenter it."""
import os

import numpy as np
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from lele.atom_clipboard import coordinate_text
from lele.core import Frame
from lele.selection_panel import SelectionPanel


def test_xyz_body_preserves_unwrapped_cartesian_and_source_order():
    source = Frame(['O', 'C', 'H'], [[-2.3, 12.6, 0.], [4., 5., 6.], [3., 8., -9.]],
                   np.eye(3) * 10, (True,) * 3)
    rows = coordinate_text(source, [2, 0, 2]).splitlines()
    assert len(rows) == 2
    assert [row.split()[0] for row in rows] == ['O', 'H']
    np.testing.assert_allclose([[float(v) for v in row.split()[1:]] for row in rows],
                               source.positions[[0, 2]])
    with pytest.raises(ValueError):
        coordinate_text(source, [3])


def test_button_copies_latest_frame_once_per_site_and_disables_without_selection():
    app = QApplication.instance() or QApplication([])
    panel = SelectionPanel()
    source = Frame(['Cu', 'O'], [[1., 2., 3.], [5., 6., 7.]],
                   info={'site_occupancies': [{'Cu': .75, 'Fe': .25}, {'O': 1.}]})
    try:
        panel.set_frame(source, [0, 1])
        panel.copy_coordinates_button.click()
        assert len(app.clipboard().text().splitlines()) == 2
        assert app.clipboard().text().splitlines()[0].split() == ['Cu', '1.000000000000', '2.000000000000', '3.000000000000']
        assert 'ORCA index' not in panel.model.headers
        assert panel.model.cell_text(0, panel.model.headers.index('Index')) == '1'
        changed = source.clone()
        changed.positions[0] = [11., 12., 13.]
        panel.set_frame(changed, [0])
        panel.copy_coordinates_button.click()
        assert '11.000000000000' in app.clipboard().text()
        panel.set_frame(changed, [])
        assert not panel.copy_coordinates_button.isEnabled()
    finally:
        panel.close(); panel.deleteLater(); app.processEvents()
