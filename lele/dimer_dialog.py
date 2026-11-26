"""Inspect a VTST dimer search without assigning rotations their own centre geometry."""
import csv
from pathlib import Path

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
                               QLabel, QPushButton, QTableView, QVBoxLayout)
from .dialog_policy import QDialog, QFileDialog, QMessageBox
from .vtst_dimer import records

COLUMNS = (('job', 'Run'), ('step', 'Translation'), ('rotation', 'Rotation'), ('frame', 'Centre frame'),
           ('centre_energy', 'Centre energy (eV)'), ('e0', 'Centre E0 (eV)'),
           ('force', 'Centre force F0 (eV/Å)'), ('torque', 'Rotational force FN (eV/Å²)'),
           ('curvature', 'Curvature (eV/Å²)'), ('angle', 'Angle (°)'), ('line', 'Source line'))


class DimerTable(QAbstractTableModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][1]
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and index.isValid():
            key = COLUMNS[index.column()][0]
            value = self.rows[index.row()].get(key)
            if value is not None:
                return str(value+1 if key == 'frame' else value)
        return None


class DimerDialog(QDialog):
    def __init__(self, document, jump, parent=None):
        super().__init__(parent)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        from .figure_export import FigureExportToolbar

        self.jump = jump
        self.document = document
        self.all_rows = list(records(document.calculation_results))
        self.setWindowTitle('VTST dimer convergence — ' + document.path.name)
        self.resize(1000, 750)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.job = QComboBox()
        for job in dict.fromkeys(r['job'] for r in self.all_rows):
            self.job.addItem(f'Run {job}', job)
        self.energy = QComboBox()
        self.metric_combo = QComboBox()
        for key, label in COLUMNS[4:10]:
            if any(r.get(key) is not None for r in self.all_rows):
                (self.energy if key in ('centre_energy', 'e0') else self.metric_combo).addItem(label, key)
        if self.energy.findData('e0') >= 0:
            self.energy.setCurrentIndex(self.energy.findData('e0'))
        self.export = QPushButton('Export CSV…')
        for widget in (self.job,self.energy,self.metric_combo,self.export):
            controls.addWidget(widget)
        layout.addLayout(controls)
        note = QLabel('Select a record to view its centre when coordinates are available. Each rotation retains its translation step.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.figure = Figure(tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.subplots(2, 1, sharex=True)
        layout.addWidget(FigureExportToolbar(self.canvas,self))
        layout.addWidget(self.canvas, 2)
        self.table = QTableView()
        self.model = DimerTable(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        layout.addWidget(self.table, 1)
        self.table.selectionModel().currentRowChanged.connect(self._selected)
        self.canvas.mpl_connect('pick_event', self._picked)
        self.export.clicked.connect(self.export_csv)
        self.job.currentIndexChanged.connect(self._change_job)
        self.energy.currentIndexChanged.connect(self.redraw)
        self.metric_combo.currentIndexChanged.connect(self.redraw)
        self._change_job()

    def _change_job(self, *_):
        self.model.beginResetModel()
        self.model.rows = [r for r in self.all_rows if r['job'] == self.job.currentData()]
        self.model.endResetModel()
        self.redraw()

    def redraw(self, *_):
        rows = self.model.rows
        self.lines = []
        for axis, combo in zip(self.axes, (self.energy, self.metric_combo)):
            axis.clear()
            key = combo.currentData()
            values = [row.get(key, np.nan) for row in rows]
            line, = axis.plot(np.arange(1,len(rows)+1), values, '.-', picker=5)
            self.lines.append(line)
            axis.set_ylabel(combo.currentText())
            if key == 'curvature':
                axis.axhline(0, color='grey', linestyle='--', linewidth=.8)
            axis.grid(alpha=.25)
        self.axes[-1].set_xlabel('Record in calculation order')
        self.canvas.draw_idle()

    def _selected(self, index, previous):
        if index.isValid():
            frame = self.model.rows[index.row()]['frame']
            if frame is not None:
                self.jump(frame)

    def _picked(self, event):
        if event.artist in self.lines and len(event.ind):
            self.table.selectRow(int(event.ind[0]))

    def _write_csv(self, path):
        with Path(path).open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.writer(stream)
            writer.writerow([label for _, label in COLUMNS])
            for row in self.model.rows:
                values = dict(row)
                if row['frame'] is not None:
                    values['frame'] += 1
                writer.writerow([values.get(key) for key, _ in COLUMNS])

    def export_csv(self):
        filename, _ = QFileDialog.getSaveFileName(self, 'Export dimer records',
            str(self.document.path.with_name(self.document.path.name+'_dimer.csv')), 'CSV (*.csv)')
        if filename:
            try:
                self._write_csv(filename)
            except OSError as exc:
                QMessageBox.warning(self, 'Could not export dimer records', str(exc))
