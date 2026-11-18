"""Scan profiles link endpoints rather than inner optimization records."""
import csv
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

if not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from lele.orca_scan_dialog import ScanDialog
from lele.orca_scan import ScanCoordinate


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def document(two_coordinates=True):
    coordinates = [ScanCoordinate('Bond', (59, 17))]
    if two_coordinates:
        coordinates.append(ScanCoordinate('Bond', (130, 107)))
    points = [SimpleNamespace(number=i + 1, values=(3.858 - .1 * i, 1.91525 - .03 * i),
               energy_ev=-100. + .02 * i, converged=i != 2, frame_index=(i + 1) * 7,
               source_line=1000 * (i + 1)) for i in range(3)]
    scan = SimpleNamespace(job_index=0, coordinates=coordinates, points=points,
                           simultaneous=two_coordinates, expected_points=40)
    return SimpleNamespace(path=Path('/tmp/scan.log'), calculation_results=SimpleNamespace(scans=[scan]))


def test_simultaneous_curve_keeps_one_path_and_all_coordinate_columns(app, tmp_path):
    jumps = []
    dialog = ScanDialog(document(), jumps.append)
    try:
        assert dialog.x_axis.currentText() == 'Scan step'
        assert dialog.table.rowCount() == 3
        assert dialog.table.columnCount() == 9
        line = next(iter(dialog.links))
        assert np.array_equal(line.get_xdata(), [1., 2., 3.])
        assert np.isnan(line.get_ydata()[-1])
        assert 'Simultaneous scan' in dialog.note.text()
        assert 'displayed atom indices start at 1' in dialog.note.text()
        assert dialog.document.calculation_results.scans[0].coordinates[0].atoms == (59, 17)
        dialog.x_axis.setCurrentIndex(2)
        line = next(iter(dialog.links))
        assert np.allclose(line.get_xdata(), [1.91525, 1.88525, 1.85525])
        assert 'Bond (131, 108)' in dialog.axes.get_xlabel()
        dialog.include_incomplete.setChecked(True)
        incomplete = next(line for line in dialog.links if 'Incomplete' in line.get_label())
        assert incomplete.get_markerfacecolor() == 'none'
        dialog.pick(SimpleNamespace(artist=incomplete, ind=[0]))
        assert jumps[-1] == 21
        dialog.table.sortItems(0, Qt.SortOrder.DescendingOrder)
        dialog.table.setCurrentCell(0, 0)
        assert jumps[-1] == 21
        output = tmp_path / 'scan.csv'
        dialog._write_csv(output, dialog._headers, dialog._rows)
        rows = list(csv.DictReader(output.open(encoding='utf-8-sig')))
        assert len(rows) == 3
        assert rows[-1]['Status'] == 'Incomplete / not converged'
        assert float(rows[0]['Bond (131, 108) (Å)']) == 1.91525
        assert all('ORCA index' not in heading for heading in rows[0])
        assert rows[-1]['Geometry frame'] == '22'
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()


def test_single_coordinate_defaults_to_distance_and_no_endpoint_uses_no_curve(app):
    doc = document(False)
    for point in doc.calculation_results.scans[0].points:
        point.converged = False
    dialog = ScanDialog(doc, lambda _: None)
    try:
        assert dialog.x_axis.currentIndex() == 1
        assert not dialog.links
        assert 'No converged' in dialog.axes.texts[0].get_text()
        dialog.include_incomplete.setChecked(True)
        assert len(dialog.links) == 1
    finally:
        dialog.close(); dialog.deleteLater(); app.processEvents()
