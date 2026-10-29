"""Persistent geometric monitors over the current, stage-local trajectory."""
import csv
import re
import numpy as np
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QCheckBox, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QFileDialog, QMessageBox)

from .trajectory_analysis import GeometryParameter, PARAMETER_KINDS, parameter_values


def parse_atoms(text):
    fields = re.split(r'[\s,;]+', text.strip())
    if not text.strip(): return ()
    result = []
    for field in fields:
        if not field.isdigit() or int(field) < 1:
            raise ValueError('Enter atom numbers starting at 1, separated by spaces or commas')
        result.append(int(field) - 1)
    return tuple(result)


class GeometryCurveDialog(QDialog):
    def __init__(self, document, window):
        super().__init__(window)
        self.document, self.window = document, window
        self.symbols = tuple(window.frame.symbols)
        self.parameters = window._geometry_parameters.setdefault(id(document), [])
        self.line_frames = {}
        self.setWindowTitle('Geometry parameter curves — ' + document.path.name)
        self.resize(1050, 860)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        layout = QVBoxLayout(self)
        top = QHBoxLayout(); layout.addLayout(top)
        self.sequence_combo = QComboBox(); top.addWidget(self.sequence_combo, 1)
        self.use_trajectory_button = QPushButton('Use current trajectory')
        self.use_trajectory_button.clicked.connect(self.use_trajectory); top.addWidget(self.use_trajectory_button)
        self.unwrap_check = QCheckBox('Unwrap dihedrals'); top.addWidget(self.unwrap_check)
        self.sequence_label = QLabel(); self.sequence_label.setWordWrap(True); layout.addWidget(self.sequence_label)
        add = QHBoxLayout(); layout.addLayout(add)
        self.add_selection_button = QPushButton('Add current selection (2 / 3 / 4 atoms)')
        self.add_selection_button.clicked.connect(self.add_selection); add.addWidget(self.add_selection_button)
        self.remove_button = QPushButton('Remove selected monitor'); self.remove_button.clicked.connect(self.remove_parameter)
        add.addWidget(self.remove_button)
        self.nearest_check = QCheckBox('Use nearest periodic images for new monitors'); add.addWidget(self.nearest_check)
        custom = QHBoxLayout(); layout.addLayout(custom)
        self.kind_combo = QComboBox(); self.kind_combo.addItems(PARAMETER_KINDS); custom.addWidget(self.kind_combo)
        self.first_edit = QLineEdit(); self.first_edit.setPlaceholderText('First group: atom numbers, e.g. 1 2 3')
        self.second_edit = QLineEdit(); self.second_edit.setPlaceholderText('Second group: planes / vectors only')
        custom.addWidget(self.first_edit, 1); custom.addWidget(self.second_edit, 1)
        self.add_custom_button = QPushButton('Add'); self.add_custom_button.clicked.connect(self.add_custom); custom.addWidget(self.add_custom_button)
        help_text = QLabel('Distance / angle / dihedral: 2 / 3 / 4 atoms. Plane angle: ≥3 atoms per group. '
                           'Vector angle: 2 + 2. Point–plane: 1 + ≥3. Point–line: 1 + 2. Vector–plane: 2 + ≥3. '
                           'Plane angles use 0–90°. Calculations use source coordinates.')
        help_text.setWordWrap(True); layout.addWidget(help_text)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Monitor', 'Images', 'Valid points', 'Min', 'Max', 'Mean', 'Std dev'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMaximumHeight(185); layout.addWidget(self.table)
        self.figure = Figure(figsize=(9, 5), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.canvas, self)); layout.addWidget(self.canvas, 1)
        self.note = QLabel('Click a curve point to display its source frame. Undefined values leave gaps.')
        self.note.setWordWrap(True); layout.addWidget(self.note)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        self.refresh_button = QPushButton('Refresh source geometry'); self.refresh_button.clicked.connect(self.redraw)
        self.export_button = QPushButton('Export all monitor values CSV…'); self.export_button.clicked.connect(self.export_csv)
        buttons.addWidget(self.refresh_button); buttons.addWidget(self.export_button)
        self.canvas.mpl_connect('pick_event', self.pick_point)
        self.sequence_combo.currentIndexChanged.connect(self.redraw)
        self.unwrap_check.toggled.connect(self.redraw)
        self.use_trajectory()
        if not self.parameters and 2 <= len(window.selection) <= 4: self.add_selection()

    def use_trajectory(self):
        from .workflow_ui import sequence_for
        if self.window.doc is not self.document or self.window.frame is None:
            self.note.setText('Select a geometry of this file before capturing its current trajectory.'); return
        current = sequence_for(self.window) if self.window.doc is self.document else []
        if not current:
            current = list(range(len(self.document.frames)))
        context = getattr(self.window, '_result_sequence', None)
        if context is not None and (context[0] is not self.document or self.window.frame_index not in context[1]):
            context = None
        label = context[2] if context is not None and context[0] is self.document else 'Current trajectory'
        # Older output readers may identify jobs without stage records.
        if context is None and self.window.doc is self.document:
            job = self.window.frame.info.get('calculation_index')
            if job is not None and 'stage_index' not in self.window.frame.info:
                current = [i for i in current if self.document.frames[i].info.get('calculation_index') == job]
                label = f'Job {job+1} trajectory'
        groups = [(label, tuple(current))]
        # A computed job's stages stay separate. NEB profiles and per-image
        # histories are selected by the NEB browser and captured above.
        keys = []
        for i, frame in enumerate(self.document.frames):
            key = ('series', frame.info['series_key']) if 'series_key' in frame.info else (
                ('stage', frame.info['stage_index']) if 'stage_index' in frame.info else
                (('job', frame.info['calculation_index']) if 'calculation_index' in frame.info else ('other', 0)))
            if key not in keys: keys.append(key)
        for key in keys:
            indices = tuple(i for i, f in enumerate(self.document.frames)
                            if (('series', f.info['series_key']) if 'series_key' in f.info else
                                (('stage', f.info['stage_index']) if 'stage_index' in f.info else
                                 (('job', f.info['calculation_index']) if 'calculation_index' in f.info else ('other', 0)))) == key)
            if indices == tuple(current): continue
            frame = self.document.frames[indices[0]]
            label = frame.info.get('series_label', 'Geometry trajectory')
            if key[0] == 'stage' and self.document.calculation_results is not None:
                label = next((s.name for s in self.document.calculation_results.stages if s.index == key[1]), label)
            if key[0] == 'job': label = f'Job {key[1]+1} trajectory'
            groups.append((label, indices))
        with QSignalBlocker(self.sequence_combo):
            self.sequence_combo.clear()
            for label, indices in groups: self.sequence_combo.addItem(f'{label} ({len(indices)} frames)', indices)
        self.redraw()

    def add_parameter(self, parameter):
        parameter.validate(len(self.symbols))
        if parameter not in self.parameters: self.parameters.append(parameter)
        self.redraw()

    def add_selection(self):
        if self.window.doc is not self.document or self.window.frame is None or tuple(self.window.frame.symbols) != self.symbols:
            self.note.setText('Select atoms in a compatible frame of this file.'); return
        atoms = tuple(self.window.selection)
        if len(atoms) not in (2, 3, 4):
            self.note.setText('Select 2, 3 or 4 atoms in order, then add a monitor.'); return
        self.add_parameter(GeometryParameter({2: 'Distance', 3: 'Angle', 4: 'Dihedral'}[len(atoms)],
                                            atoms, nearest_images=self.nearest_check.isChecked()))

    def add_custom(self):
        try:
            self.add_parameter(GeometryParameter(self.kind_combo.currentText(), parse_atoms(self.first_edit.text()),
                                               parse_atoms(self.second_edit.text()), self.nearest_check.isChecked()))
        except ValueError as exc: self.note.setText(str(exc))

    def remove_parameter(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.parameters): self.parameters.pop(row); self.redraw()

    def redraw(self, *_):
        self.sequence = tuple(self.sequence_combo.currentData() or ())
        self.values = [parameter_values(self.document, self.sequence, parameter, self.symbols,
                       unwrap=self.unwrap_check.isChecked()) for parameter in self.parameters]
        self.figure.clear(); self.line_frames = {}
        units = list(dict.fromkeys(p.unit for p in self.parameters)) or ['Å']
        axes = {unit: self.figure.add_subplot(len(units), 1, i+1) for i, unit in enumerate(units)}
        self.table.setRowCount(len(self.parameters))
        colors = ('#1675b8', '#d64c3b', '#339768', '#9653b8', '#ba861f', '#2b9baa')
        for row, (parameter, values) in enumerate(zip(self.parameters, self.values)):
            valid = values[np.isfinite(values)]
            stats = [f'{func(valid):.5f} {parameter.unit}' if len(valid) else '—'
                     for func in (np.min, np.max, np.mean, np.std)]
            cells = [parameter.label, 'Nearest' if parameter.nearest_images else 'As printed', str(len(valid)), *stats]
            for column, value in enumerate(cells): self.table.setItem(row, column, QTableWidgetItem(value))
            # NaNs intentionally break lines between undefined geometries.
            line, = axes[parameter.unit].plot(np.arange(1, len(values)+1), values, '.-',
                        label=parameter.label, color=colors[row % len(colors)], picker=7)
            self.line_frames[line] = self.sequence
        for unit, ax in axes.items():
            ax.set_xlabel('Position in selected trajectory'); ax.set_ylabel('Distance (Å)' if unit == 'Å' else 'Angle (°)')
            ax.grid(True, alpha=.2)
            if ax.lines: ax.legend(fontsize=8)
            else: ax.text(.5, .5, 'Add a geometry monitor', ha='center', transform=ax.transAxes)
            if self.window.doc is self.document and self.window.frame_index in self.sequence:
                ax.axvline(self.sequence.index(self.window.frame_index)+1, color='#777777', linestyle=':', alpha=.5)
        self.sequence_label.setText(f'{len(self.sequence)} source frames. Atom correspondence follows the printed atom order; '
                                    'frames with a different atom sequence or undefined geometry leave gaps.')
        self.canvas.draw()

    def pick_point(self, event):
        sequence = self.line_frames.get(event.artist)
        if sequence is None or not len(event.ind): return
        k = int(event.ind[0])
        if 0 <= k < len(sequence) and np.isfinite(event.artist.get_ydata()[k]):
            self.window._jump_to_result_sequence(self.document, sequence[k], sequence, self.sequence_combo.currentText())
            self.redraw()

    def write_csv(self, path):
        with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['trajectory_position', 'source_frame_1based', 'stage_index', 'neb_iteration', 'neb_image',
                             *[p.label + ' (' + p.unit + ')' + (' [unwrapped]' if self.unwrap_check.isChecked() and p.kind == 'Dihedral' else '')
                               for p in self.parameters]])
            for k, index in enumerate(self.sequence):
                info = self.document.frames[index].info
                writer.writerow([k+1, index+1, info.get('stage_index'), info.get('neb_iteration'), info.get('neb_image'),
                                 *[float(values[k]) if np.isfinite(values[k]) else None for values in self.values]])

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export geometry monitor data',
                        str(self.document.path.with_name(self.document.path.stem + '_geometry_curves.csv')), 'CSV (*.csv)')
        if path: self.write_csv(path)
