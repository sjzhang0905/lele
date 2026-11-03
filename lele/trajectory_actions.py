"""Lazy GUI integration for selection analysis and display-only alignment."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QPushButton, QHBoxLayout, QDialog,
    QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QLabel, QDialogButtonBox)


class TrajectoryAnalysisActions:
    def _install_trajectory_controls(self, layout):
        self._geometry_parameters = {}
        self._trajectory_alignments = {}
        self._aligned_documents = set()
        self._energy_only_context = None
        self.vibration_analysis_action = self._action(self.analysis_menu,
            'Find vibrations by selected atoms…', self.show_vibration_analysis)
        self.geometry_curve_action = self._action(self.analysis_menu,
            'Geometry parameter curves…', self.show_geometry_curves)
        self.alignment_action = self._action(self.analysis_menu,
            'Trajectory display alignment…', self.configure_trajectory_alignment)
        row = QHBoxLayout()
        self.trajectory_align_check = QCheckBox('Align trajectory for display')
        self.trajectory_align_check.setToolTip('Align to a reference frame without changing source coordinates. Disable before geometry editing.')
        self.trajectory_align_check.toggled.connect(self._toggle_trajectory_alignment)
        row.addWidget(self.trajectory_align_check)
        self.trajectory_align_button = QPushButton('Settings…')
        self.trajectory_align_button.clicked.connect(self.configure_trajectory_alignment)
        row.addWidget(self.trajectory_align_button); layout.addLayout(row)
        row = QHBoxLayout()
        self.geometry_curve_button = QPushButton('Geometry curves…')
        self.geometry_curve_button.clicked.connect(self.show_geometry_curves)
        self.vibration_analysis_button = QPushButton('Find vibrations…')
        self.vibration_analysis_button.clicked.connect(self.show_vibration_analysis)
        row.addWidget(self.geometry_curve_button); row.addWidget(self.vibration_analysis_button); layout.addLayout(row)
        self._refresh_trajectory_controls()

    def _alignment_enabled(self):
        return (self.doc is not None and self.frame is not None and id(self.doc) in self._aligned_documents
                and self._active_vibration is None)

    def _refresh_trajectory_controls(self):
        structure = self.frame is not None
        vibr = self.doc is not None and bool(self.doc.vibrations)
        for widget in (self.geometry_curve_button, self.geometry_curve_action): widget.setEnabled(structure)
        for widget in (self.vibration_analysis_button, self.vibration_analysis_action): widget.setEnabled(vibr)
        enabled = structure and self._active_vibration is None
        for widget in (self.trajectory_align_check, self.trajectory_align_button, self.alignment_action): widget.setEnabled(enabled)
        with QSignalBlocker(self.trajectory_align_check): self.trajectory_align_check.setChecked(self._alignment_enabled())

    def _prepare_analysis_scene(self):
        if self.renderer is None: return
        self.renderer.alignment = self._trajectory_alignments.get(id(self.doc)) if self._alignment_enabled() else None
        self.renderer.mode_vectors = None
        if self._active_vibration is not None and self.vibration_controls.arrows_check.isChecked():
            _, analysis, mode = self._active_vibration
            selected_mode=self.doc.vibrations[analysis].modes[mode]
            self.renderer.mode_vectors = selected_mode.arrow_vectors() if hasattr(selected_mode,'arrow_vectors') else selected_mode.displacements
            self.renderer.mode_vector_length = self.vibration_controls.arrow_length.value()
            self.renderer.mode_vector_indices = tuple(self.selection) if self.vibration_controls.selected_arrows_check.isChecked() else None

    def _toggle_trajectory_alignment(self, checked):
        if self.frame is None: return
        from .trajectory_analysis import DisplayAlignment
        key = id(self.doc)
        if checked:
            if key not in self._trajectory_alignments:
                self._trajectory_alignments[key] = DisplayAlignment(self.frame.clone(), tuple(range(len(self.frame.symbols))), self.frame_index)
            self._aligned_documents.add(key)
        else: self._aligned_documents.discard(key)
        self.renderer.periodic_preview = None
        self.refresh_scene(reset_camera=True); self._refresh_coordinates(); self._refresh_info()

    def configure_trajectory_alignment(self):
        if self.frame is None or self._active_vibration is not None: return
        dialog = AlignmentDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._trajectory_alignments[id(self.doc)] = dialog.spec
            self._aligned_documents.add(id(self.doc))
            self.renderer.periodic_preview = None
            self.refresh_scene(reset_camera=True); self._refresh_coordinates(); self._refresh_info()

    def show_vibration_analysis(self):
        if self.doc is None or not self.doc.vibrations: return
        from .vibration_analysis_dialog import VibrationAnalysisDialog
        return self._show_analysis_window(VibrationAnalysisDialog(self.doc, self))

    def show_geometry_curves(self):
        if self.frame is None: return
        from .geometry_curve_dialog import GeometryCurveDialog
        return self._show_analysis_window(GeometryCurveDialog(self.doc, self))


class AlignmentDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.document = window.doc
        self.sequence = tuple(window._navigation_indices())
        self.selection = tuple(window.selection)
        self.setWindowTitle('Trajectory display alignment'); self.resize(540, 260)
        layout = QVBoxLayout(self); form = QFormLayout(); layout.addLayout(form)
        self.reference_spin = QSpinBox(); self.reference_spin.setRange(1, len(self.sequence))
        self.reference_spin.setValue(self.sequence.index(window.frame_index)+1)
        form.addRow('Reference in current trajectory', self.reference_spin)
        self.atoms_combo = QComboBox(); self.atoms_combo.addItems(['All atoms', f'Current selection ({len(self.selection)} atoms)'])
        self.atoms_combo.model().item(1).setEnabled(bool(self.selection))
        form.addRow('Atoms used for fitting', self.atoms_combo)
        self.note = QLabel('The current trajectory is aligned by translation and proper rotation. '
            'Source coordinates, measurements and structure exports remain in their original frame. '
            'PNG/GIF use the displayed alignment. Disable alignment before geometry editing.')
        self.note.setWordWrap(True); layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def apply(self):
        from .trajectory_analysis import DisplayAlignment
        index = self.sequence[self.reference_spin.value()-1]
        reference = self.document.frames[index]
        indices = self.selection if self.atoms_combo.currentIndex() else tuple(range(len(reference.symbols)))
        spec = DisplayAlignment(reference.clone(), indices, index)
        try: spec.transform(self.window.frame)
        except ValueError as exc: self.note.setText(str(exc)); return
        self.spec = spec
        self.accept()
