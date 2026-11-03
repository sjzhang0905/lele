"""Find normal modes involving the current atom selection."""
import csv
from .operations import gui_operation,run_data_task
from .output_text import progress_items
from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QCheckBox, QDoubleSpinBox, QPushButton, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QFileDialog)

from .trajectory_analysis import displacement_share


class VibrationAnalysisDialog(QDialog):
    def __init__(self, document, window):
        super().__init__(window)
        self.document, self.window = document, window
        self.selected = ()
        self.setWindowTitle('Find vibrations by selected atoms — ' + document.path.name)
        self.resize(960, 670)
        layout = QVBoxLayout(self)
        top = QHBoxLayout(); layout.addLayout(top)
        self.analysis_combo = QComboBox()
        for i, analysis in enumerate(document.vibrations):
            self.analysis_combo.addItem(analysis.purpose or f'Frequencies {i + 1}', i)
        active = window._active_vibration
        if active is not None and window.doc is document:
            self.analysis_combo.setCurrentIndex(active[1])
        top.addWidget(self.analysis_combo, 1)
        self.use_selection_button = QPushButton('Use current atom selection')
        self.use_selection_button.clicked.connect(self.use_selection); top.addWidget(self.use_selection_button)
        self.selection_label = QLabel(); self.selection_label.setWordWrap(True); layout.addWidget(self.selection_label)
        controls = QHBoxLayout(); layout.addLayout(controls)
        self.selected_only = QCheckBox('Filter by selected-atom share ≥')
        controls.addWidget(self.selected_only)
        self.threshold = QDoubleSpinBox(); self.threshold.setRange(0, 100)
        self.threshold.setDecimals(1); self.threshold.setValue(1); self.threshold.setSuffix(' %')
        controls.addWidget(self.threshold)
        self.imaginary_only = QCheckBox('Imaginary modes only'); controls.addWidget(self.imaginary_only)
        self.sort_combo = QComboBox(); self.sort_combo.addItems(['Selected-atom share ↓', 'Frequency ↑', 'Mode number ↑'])
        controls.addWidget(self.sort_combo)
        self.note = QLabel('Share = Σ selected |Cartesian displacement|² / Σ all |displacement|². '
                           'This is a displacement measure, not an energy contribution. Missing vectors are shown as —.')
        self.note.setWordWrap(True); layout.addWidget(self.note)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Mode', 'Frequency (cm⁻¹)', 'Selected share (%)',
                                              'IR intensity', 'IR unit', 'Raman (Å⁴/amu)', 'Displacements'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True); layout.addWidget(self.table, 1)
        buttons = QHBoxLayout(); layout.addLayout(buttons)
        self.play_button = QPushButton('Play selected mode'); self.play_button.clicked.connect(lambda: self.open_mode(True))
        self.arrows_button = QPushButton('Show static displacement arrows'); self.arrows_button.clicked.connect(self.show_arrows)
        self.export_button = QPushButton('Export shown modes CSV…'); self.export_button.clicked.connect(self.export_csv)
        for button in (self.play_button, self.arrows_button, self.export_button): buttons.addWidget(button)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_mode(True))
        self.analysis_combo.currentIndexChanged.connect(self.use_selection)
        for widget in (self.selected_only, self.imaginary_only): widget.toggled.connect(self.redraw)
        self.threshold.valueChanged.connect(self.redraw); self.sort_combo.currentIndexChanged.connect(self.redraw)
        self.use_selection()

    def use_selection(self, *_):
        analysis = self.document.vibrations[self.analysis_combo.currentIndex()]
        frame = self.window.frame
        from .atom_indices import atom_mapping
        mapping=atom_mapping(frame,analysis.reference,allow_partial=True) if self.window.doc is self.document and frame is not None else None
        self.selected=tuple(mapping[i] for i in self.window.selection if mapping[i] is not None) if mapping is not None else ()
        text = ', '.join(f'{analysis.reference.symbols[i]}{i+1}' for i in self.selected)
        self.selection_label.setText('Selected atoms: ' + text if self.selected else
                                     'No compatible atoms selected. Select atoms in the molecule, then click Use current atom selection.')
        self.selected_only.setEnabled(bool(self.selected)); self.threshold.setEnabled(bool(self.selected))
        with QSignalBlocker(self.selected_only): self.selected_only.setChecked(bool(self.selected))
        self.redraw()

    @gui_operation('Analyzing vibrational modes')
    def redraw(self, *_):
        analysis = self.document.vibrations[self.analysis_combo.currentIndex()]
        self.rows = []
        selected=self.selected
        shares=run_data_task(self,'Calculating mode participation',lambda:[displacement_share(m,selected,len(analysis.reference.symbols))
            for m in progress_items(analysis.modes,'Analyzing mode participation')])
        for i, (mode,share) in enumerate(zip(analysis.modes,shares)):
            if self.imaginary_only.isChecked() and not mode.imaginary: continue
            if self.selected_only.isChecked() and (share is None or share * 100 < self.threshold.value()): continue
            self.rows.append((i, mode, share))
        if self.sort_combo.currentIndex() == 0:
            self.rows.sort(key=lambda row: (row[2] is None, -(row[2] or 0), row[1].number))
        elif self.sort_combo.currentIndex() == 1: self.rows.sort(key=lambda row: row[1].frequency_cm1)
        else: self.rows.sort(key=lambda row: row[1].number)
        self.table.setRowCount(len(self.rows))
        for r, (_, mode, share) in enumerate(progress_items(self.rows,'Building mode table')):
            values = [mode.number, f'{mode.frequency_cm1:.4f}', '—' if share is None else f'{share*100:.3f}',
                      '—' if mode.ir_intensity is None else f'{mode.ir_intensity:.5g}', mode.ir_intensity_unit,
                      '—' if mode.raman_activity is None else f'{mode.raman_activity:.5g}',
                      'Available' if mode.can_animate else 'Not available']
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value)); self.table.setItem(r, c, item)
                if mode.imaginary: item.setForeground(Qt.GlobalColor.darkRed)
        if self.rows: self.table.selectRow(0)
        self.update_buttons()

    def current_mode(self):
        row = self.table.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def update_buttons(self):
        row = self.current_mode()
        enabled = row is not None and row[1].can_animate
        self.play_button.setEnabled(enabled); self.arrows_button.setEnabled(enabled)

    def open_mode(self, autoplay=False):
        row = self.current_mode()
        if row is None: return
        index = next((i for i, d in enumerate(self.window.documents) if d is self.document), None)
        if index is not None:
            self.window.select_vibration(index, self.analysis_combo.currentIndex(), row[0], autoplay=autoplay)

    def show_arrows(self):
        self.open_mode(False)
        self.window.vibration_controls.arrows_check.setChecked(True)
        self.window.stop_vibration()

    @gui_operation('Exporting vibration results')
    def write_csv(self, path):
        with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            qe=any(hasattr(m,'qpoint') for _,m,_ in self.rows)
            writer.writerow(['analysis', 'mode', 'frequency_cm-1', 'selected_atoms_1based',
                             'selected_cartesian_displacement_share', 'IR_intensity', 'IR_unit',
                             'Raman_activity_A4_amu', 'displacements_available']+(['q_x','q_y','q_z','q_units'] if qe else []))
            for _, mode, share in progress_items(self.rows,'Writing mode CSV'):
                writer.writerow([self.analysis_combo.currentIndex()+1, mode.number, mode.frequency_cm1,
                                 ' '.join(str(i+1) for i in self.selected), share, mode.ir_intensity,
                                 mode.ir_intensity_unit, mode.raman_activity, mode.can_animate]+
                                ([*mode.qpoint,'Cartesian 2pi/alat'] if qe else []))

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export selected vibration results',
                    str(self.document.path.with_name(self.document.path.stem + '_selected_modes.csv')), 'CSV (*.csv)')
        if path: self.write_csv(path)
