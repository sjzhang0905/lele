"""Relaxed-scan endpoints and printed scan coordinates, separate from cycles."""
import csv
from math import isfinite

import numpy as np
from ase.units import Hartree
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QPushButton, QStyledItemDelegate
from .dialog_policy import QDialog, QFileDialog

from .operations import gui_operation, run_data_task
from .output_text import progress_items
from .orca_analysis_dialogs import table, fill, selected_row, figure


class ScanNumberDelegate(QStyledItemDelegate):
    """Keep numeric sorting while showing chemically useful energy precision."""
    def displayText(self, value, locale):
        if isinstance(value, float):
            return f'{value:.10f}'
        return super().displayText(value, locale)


class ScanDialog(QDialog):
    def __init__(self, document, jump, parent=None):
        super().__init__(parent)
        self.document, self.jump = document, jump
        self.scans = list(getattr(document.calculation_results, 'scans', ()))
        self.links = {}
        self._points = []
        self._headers = []
        self._rows = []
        self.setWindowTitle('ORCA relaxed scan — ' + document.path.name)
        self.resize(1120, 840)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout(); layout.addLayout(controls)
        self.run = QComboBox()
        for i, scan in enumerate(self.scans):
            self.run.addItem(f'Scan {i + 1} · Job {scan.job_index + 1}', i)
        self.x_axis = QComboBox()
        self.unit = QComboBox(); self.unit.addItems(['kcal/mol', 'eV', 'Hartree'])
        self.include_incomplete = QCheckBox('Show incomplete points')
        self.include_incomplete.setToolTip('Include the last available energy of unconverged scan steps, marked by hollow orange circles.')
        for widget in (self.run, self.x_axis, self.unit, self.include_incomplete):
            controls.addWidget(widget)
        self.note = QLabel(); self.note.setWordWrap(True); layout.addWidget(self.note)
        self.fig, self.canvas = figure(layout)
        self.canvas.get_default_filename = lambda: str(document.path.with_name(document.path.stem + '_scan.png'))
        self.table = table(self, []); layout.addWidget(self.table, 1)
        self.table.setItemDelegate(ScanNumberDelegate(self.table))
        self.export_button = QPushButton('Export all scan points CSV…')
        layout.addWidget(self.export_button)
        self.canvas.mpl_connect('pick_event', self.pick)
        self.table.itemSelectionChanged.connect(self.select_table)
        self.export_button.clicked.connect(self.export_data)
        self.run.currentIndexChanged.connect(self.prepare)
        self.x_axis.currentIndexChanged.connect(self.redraw)
        self.unit.currentIndexChanged.connect(self.redraw)
        self.include_incomplete.toggled.connect(self.redraw)
        self.prepare()

    def prepare(self, *_):
        with QSignalBlocker(self.x_axis):
            self.x_axis.clear()
            self.x_axis.addItem('Scan step', None)
            if self.run.currentIndex() >= 0:
                scan = self.scans[self.run.currentIndex()]
                for i, coordinate in enumerate(scan.coordinates):
                    self.x_axis.addItem(f'{coordinate.label} ({coordinate.unit})', i)
                # A simultaneous scan is a path through two or more coordinates.
                # Its step number is the unambiguous common path parameter.
                if len(scan.coordinates) == 1:
                    self.x_axis.setCurrentIndex(1)
        self.redraw()

    def _x(self, point):
        coordinate = self.x_axis.currentData()
        if coordinate is None:
            return float(point.number)
        return (point.values[coordinate] if coordinate < len(point.values) else None)

    @gui_operation('Preparing scan curve')
    def redraw(self, *_):
        if not hasattr(self, 'canvas'):
            return
        self.fig.clear(); self.links = {}; self._points = []; self._rows = []; self._headers = []
        self.axes = self.fig.add_subplot(111)
        if self.run.currentIndex() < 0:
            self.note.setText('No relaxed-scan records in this file.')
            self.canvas.draw()
            return
        scan = self.scans[self.run.currentIndex()]
        self._points = list(scan.points)
        completed = [p for p in self._points if p.converged and p.energy_ev is not None and isfinite(p.energy_ev)]
        available = [p for p in self._points if p.energy_ev is not None and isfinite(p.energy_ev)]
        baseline = min((p.energy_ev for p in completed or available), default=0.)
        factor = {'kcal/mol': 23.0605478306, 'eV': 1., 'Hartree': 1. / Hartree}[self.unit.currentText()]
        x = [self._x(p) for p in self._points]
        y = [(p.energy_ev - baseline) * factor if p.energy_ev is not None and isfinite(p.energy_ev) else None
             for p in self._points]
        # NaNs leave holes at absent/unconverged scan steps rather than joining
        # unrelated endpoints across a failed geometry optimization.
        good_x = [float(v) if v is not None and isfinite(v) else np.nan for v in x]
        good_y = [v if p.converged and v is not None else np.nan for p, v in zip(self._points, y)]
        if any(np.isfinite(good_y)):
            line, = self.axes.plot(good_x, good_y, 'o-', color='#286d9a', markersize=5,
                                   picker=6, label='Converged scan endpoints')
            self.links[line] = self._points
        if self.include_incomplete.isChecked():
            # Only connect adjacent available points when at least one endpoint
            # is incomplete; do not draw a solid final-profile segment there.
            for i in range(1, len(self._points)):
                if (not self._points[i - 1].converged or not self._points[i].converged) and all(
                        v is not None and isfinite(v) for v in (x[i - 1], x[i], y[i - 1], y[i])):
                    self.axes.plot(x[i - 1:i + 1], y[i - 1:i + 1], '--', color='#b87526', alpha=.65)
            indices = [i for i, p in enumerate(self._points) if not p.converged and y[i] is not None
                       and x[i] is not None and isfinite(x[i])]
            if indices:
                line, = self.axes.plot([x[i] for i in indices], [y[i] for i in indices], 'o',
                    markerfacecolor='none', markeredgecolor='#b87526', markersize=7,
                    picker=6, label='Incomplete step: last printed energy')
                self.links[line] = [self._points[i] for i in indices]
        self.axes.set_xlabel(self.x_axis.currentText())
        self.axes.set_ylabel(f'Relative energy ({self.unit.currentText()})')
        self.axes.grid(True, alpha=.2)
        if self.links:
            self.axes.legend(fontsize=9)
        else:
            self.axes.text(.5, .5, 'No converged scan endpoint energies yet', ha='center', transform=self.axes.transAxes)
        # Always retain all printed points in the table/export, including an
        # unfinished tail whose last energy is not a relaxed endpoint.
        self._headers = ['Scan step', *[f'{c.label} ({c.unit})' for c in scan.coordinates],
                         'Status', 'Energy (Hartree)', 'Energy (eV)',
                         f'Relative energy ({self.unit.currentText()})', 'Geometry frame', 'Source line']
        for point, relative in zip(self._points, y):
            values = [point.values[i] if i < len(point.values) else None for i in range(len(scan.coordinates))]
            self._rows.append([point.number, *values, 'Converged' if point.converged else 'Incomplete / not converged',
                               None if point.energy_ev is None else point.energy_ev / Hartree,
                               point.energy_ev, relative,
                               None if point.frame_index is None else point.frame_index + 1, point.source_line])
        with QSignalBlocker(self.table):
            fill(self.table, self._headers, self._rows)
        expected = f' / {scan.expected_points} planned' if scan.expected_points else ''
        notes = [f'{len(self._points)} printed scan steps{expected} · {len(completed)} converged endpoint energies. '
                 'The table includes incomplete steps; the curve excludes them unless enabled.']
        if len(scan.coordinates) > 1:
            if scan.simultaneous:
                notes.append('Simultaneous scan: the coordinates change together along one path. Select either coordinate or scan step for the x-axis.')
            else:
                notes.append('Multiple scan coordinates: points follow the printed scan order; this plot does not interpolate a two-dimensional surface.')
        notes.append('Coordinate values are read from ORCA; displayed atom indices start at 1. '
                     'Relative energy uses the minimum converged endpoint energy' +
                     (' (no converged energies available: minimum available energy)' if not completed else '') +
                     '. Click a curve point or table row to show its source geometry.')
        self.note.setText('\n'.join(notes))
        self.canvas.draw()

    def navigate(self, point):
        if point.frame_index is None:
            self.note.setText(self.note.text().split('\nNo matched coordinates')[0] + '\nNo matched coordinates for this point.')
            return
        self.jump(point.frame_index)

    def pick(self, event):
        points = self.links.get(event.artist)
        if points is not None and len(event.ind):
            index = int(event.ind[0])
            if 0 <= index < len(points):
                self.navigate(points[index])

    def select_table(self):
        row = selected_row(self.table)
        if row is not None and 0 <= row < len(self._points):
            self.navigate(self._points[row])

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export all scan points',
            str(self.document.path.with_name(self.document.path.stem + '_scan.csv')), 'CSV (*.csv)')
        if path:
            headers, rows = list(self._headers), [list(r) for r in self._rows]
            run_data_task(self, 'Exporting scan points', lambda: self._write_csv(path, headers, rows))

    @staticmethod
    def _write_csv(path, headers, rows):
        with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(headers)
            writer.writerows(progress_items(rows, 'Writing scan points CSV'))
