"""Polyhedron summaries, periodic ligand identities and trajectory curves."""
from copy import deepcopy
import csv
import numpy as np
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QSplitter, QFileDialog, QComboBox, QProgressDialog, QApplication)
from .polyhedron_analysis import (METRIC_COLUMNS, analyze_polyhedra, summary_rows,
                                  ligand_rows, polyhedron_series)
from .operations import gui_operation,run_data_task
from .output_text import progress_items


def fill_table(table, headings, rows):
    with QSignalBlocker(table):
        table.clear();table.setColumnCount(len(headings));table.setHorizontalHeaderLabels(headings)
        table.setRowCount(len(rows))
        for i, row in enumerate(progress_items(rows,'Building coordination table')):
            for j, value in enumerate(row):
                text = '—' if value is None else f'{value:.7g}' if isinstance(value, (float, np.floating)) else str(value)
                table.setItem(i, j, QTableWidgetItem(text))
        table.resizeColumnsToContents()


def table_widget():
    table = QTableWidget();table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    return table


def write_csv(path, columns, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream);writer.writerow(columns);writer.writerows(progress_items(rows,'Writing coordination CSV'))


class PolyhedronDialog(QDialog):
    def __init__(self, document, window):
        super().__init__(window);self.document = document;self.window = window
        self.options = deepcopy(window.render_options);self.records = []
        self.setWindowTitle('Coordination / polyhedron analysis — '+document.path.name);self.resize(1180, 760)
        layout = QVBoxLayout(self);controls = QHBoxLayout();layout.addLayout(controls)
        controls.addWidget(QLabel('Structure frame'))
        self.frame_spin = QSpinBox();self.frame_spin.setRange(1, len(document.frames))
        self.frame_spin.setValue(window.frame_index+1);controls.addWidget(self.frame_spin)
        self.selected_only = QCheckBox('Selected centers only');controls.addWidget(self.selected_only)
        self.refresh_button = QPushButton('Refresh with current rules');controls.addWidget(self.refresh_button)
        self.curve_button = QPushButton('Selected center trajectory…');controls.addWidget(self.curve_button)
        self.summary = QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        split = QSplitter(Qt.Orientation.Vertical);layout.addWidget(split, 1)
        self.table = table_widget();self.ligands = table_widget();split.addWidget(self.table);split.addWidget(self.ligands)
        split.setSizes([390, 200])
        buttons = QHBoxLayout();layout.addLayout(buttons)
        self.export_summary_button = QPushButton('Export summary CSV…');self.export_ligands_button = QPushButton('Export ligand CSV…')
        buttons.addWidget(self.export_summary_button);buttons.addWidget(self.export_ligands_button)
        self.note = QLabel('Source coordinates and current coordination rules, before Boundary repeats and HKL cuts. '
            'Hidden source atoms are excluded. CN=0 is retained; blank metrics have no applicable geometry.\n'
            'D is mean relative bond-length deviation; ECoN uses Hoppe distance weights. '
            'Quadratic elongation / edge-angle variance are reported only for recognized tetrahedra and octahedra containing the center.')
        self.note.setWordWrap(True);layout.addWidget(self.note)
        self.frame_spin.valueChanged.connect(self.refresh)
        self.selected_only.toggled.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh_rules)
        self.table.itemSelectionChanged.connect(self.select_record)
        self.curve_button.clicked.connect(self.show_curve)
        self.export_summary_button.clicked.connect(self.export_summary)
        self.export_ligands_button.clicked.connect(self.export_ligands)
        self.refresh()

    @property
    def frame_index(self):return self.frame_spin.value()-1

    def refresh_rules(self):
        if self.window.doc is self.document:self.options = deepcopy(self.window.render_options)
        self.refresh()

    def refresh(self, *_):
        frame = self.document.frames[self.frame_index]
        selected = tuple(self.window.selection) if self.window.doc is self.document else ()
        from .operations import run_data_task
        centers=selected if self.selected_only.isChecked() else None
        self.records = run_data_task(self,'Analyzing coordination polyhedra',lambda:analyze_polyhedra(frame,self.options,centers))
        columns, rows = summary_rows(self.records)
        headings = ['Center', 'Element']+[label+(' ('+unit+')' if unit else '') for _, label, unit in METRIC_COLUMNS]+['Geometry']
        fill_table(self.table, headings, rows)
        self.summary.setText(f'{self.document.path.name} · frame {self.frame_index+1} · {len(rows)} center(s) · '
            f'{len(self.options.element_pair_rules)} element-pair rule(s)')
        self.curve_button.setEnabled(bool(rows));self.export_summary_button.setEnabled(bool(rows));self.export_ligands_button.setEnabled(bool(rows))
        preferred = next((i for i, (shell, _) in enumerate(self.records) if shell.center in selected), 0)
        if rows:self.table.selectRow(preferred)
        else:fill_table(self.ligands, ['Ligands'], [])

    def select_record(self):
        index = self.table.currentRow()
        if not 0 <= index < len(self.records):return
        shell, _ = self.records[index];frame = self.document.frames[self.frame_index]
        columns, rows = ligand_rows(frame, [self.records[index]])
        fill_table(self.ligands, columns, rows)
        self.window._jump_to_result_frame(self.document, self.frame_index)
        self.window.selection = list(dict.fromkeys([shell.center]+shell.ligand_indices.tolist()))
        self.window._sync_selection_to_table();self.window.refresh_scene()

    def export_summary(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export polyhedron summary',
            str(self.document.path.with_name(self.document.path.stem+'_polyhedra.csv')), 'CSV (*.csv)')
        if path:run_data_task(self,'Exporting coordination summary',lambda:write_csv(path,*summary_rows(self.records)))

    def export_ligands(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export ligand distances',
            str(self.document.path.with_name(self.document.path.stem+'_polyhedron_ligands.csv')), 'CSV (*.csv)')
        if path:
            frame=self.document.frames[self.frame_index]
            run_data_task(self,'Exporting ligand distances',lambda:write_csv(path,*ligand_rows(frame,self.records)))

    def show_curve(self):
        index = self.table.currentRow()
        if not 0 <= index < len(self.records):return
        center = self.records[index][0].center
        indices = (self.window._navigation_indices() if self.window.doc is self.document
                   else list(range(len(self.document.frames))))
        from .operations import run_data_task
        from .output_text import LoadCancelled
        reference=self.document.frames[self.frame_index]
        try:rows=run_data_task(self,'Analyzing trajectory coordination',lambda:polyhedron_series(
            self.document,self.options,center,indices,reference=reference),cancellable=True)
        except LoadCancelled:return
        if rows is None:return
        return self.window._show_analysis_window(PolyhedronCurveDialog(self.document, rows, self.window))


class PolyhedronCurveDialog(QDialog):
    def __init__(self, document, rows, window):
        super().__init__(window);self.document = document;self.rows = rows;self.window = window
        self.setWindowTitle('Polyhedron trajectory — '+document.path.name);self.resize(940, 670)
        layout = QVBoxLayout(self);self.metric_combo = QComboBox()
        for key, label, unit in METRIC_COLUMNS:self.metric_combo.addItem(label+(' ('+unit+')' if unit else ''), key)
        layout.addWidget(self.metric_combo)
        self.summary = QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        self.figure = Figure(figsize=(8, 5), tight_layout=True);self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename = lambda:str(document.path.with_name(document.path.stem+'_polyhedron_trajectory.png'))
        layout.addWidget(NavigationToolbar2QT(self.canvas, self));layout.addWidget(self.canvas, 1)
        self.export_button = QPushButton('Export all trajectory metrics CSV…');layout.addWidget(self.export_button)
        self.export_button.clicked.connect(self.export_data);self.metric_combo.currentIndexChanged.connect(self.redraw)
        self.canvas.mpl_connect('pick_event', self.pick_point);self.redraw()

    @gui_operation('Preparing result display')
    def redraw(self, *_):
        self.figure.clear();axes = self.figure.add_subplot(111);key = self.metric_combo.currentData()
        xs = [row['frame']+1 for row in self.rows]
        ys = [np.nan if row[key] is None else row[key] for row in self.rows]
        self.line, = axes.plot(xs, ys, '.-', picker=7)
        axes.set_xlabel('Source frame');axes.set_ylabel(self.metric_combo.currentText());axes.grid(True, alpha=.2)
        finite = [y for y in ys if np.isfinite(y)]
        description = f'{len(self.rows)} source frames'
        if self.rows:description += f' · center {self.rows[0]["center"]+1} {self.rows[0]["element"]}'
        if finite:description += f' · mean {np.mean(finite):.7g} · min {min(finite):.7g} · max {max(finite):.7g}'
        self.summary.setText(description+'\nCN=0 is retained. Missing/undefined metrics and changed atom sequences are gaps. Click a point to display its source frame.')
        self.canvas.draw()

    def pick_point(self, event):
        if event.artist is not self.line or not len(event.ind):return
        row = self.rows[int(event.ind[0])]
        if row['status'] != 'OK':return
        self.window._jump_to_result_frame(self.document, row['frame'])
        self.window.selection = [row['center']];self.window._sync_selection_to_table();self.window.refresh_scene()

    def export_data(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export polyhedron trajectory',
            str(self.document.path.with_name(self.document.path.stem+'_polyhedron_trajectory.csv')), 'CSV (*.csv)')
        if not path:return
        columns = ['frame', 'center', 'element', *[key for key, _, _ in METRIC_COLUMNS], 'shape', 'status']
        run_data_task(self,'Exporting coordination trajectory',lambda:write_csv(path, columns,
            [[r['frame']+1,r['center']+1,r['element'],*[r[key] for key,_,_ in METRIC_COLUMNS],
              r.get('shape',''),r['status']] for r in self.rows]))
