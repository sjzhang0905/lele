"""PNG size and edge quality controls; no rendering imports during startup."""
from PySide6.QtCore import QSignalBlocker, QSettings
from PySide6.QtWidgets import QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QCheckBox, QLabel, QDialogButtonBox
from .dialog_policy import QDialog

from .png_export import MAX_OUTPUT_SIDE, PngSettings


class PngExportDialog(QDialog):
    def __init__(self, parent=None, *, view_size, title='PNG image quality', note=None, format_name='PNG', scene_image=True):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(420, 240)
        self.format_name = format_name
        self.source_size = (max(1, view_size[0]), max(1, view_size[1]))
        self.aspect = self.source_size[1] / self.source_size[0]
        layout = QVBoxLayout(self)
        note = QLabel(note or 'Save the current camera, colors, labels and arrows at a higher resolution.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.scale_combo = QComboBox()
        for value in (1, 2, 3, 4):
            self.scale_combo.addItem(f'{value}× canvas size', value)
        self.scale_combo.addItem('Custom width', None)
        form.addRow('Resolution', self.scale_combo)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, min(MAX_OUTPUT_SIDE, max(1, int(MAX_OUTPUT_SIDE / self.aspect))))
        self.width_spin.setSuffix(' px')
        form.addRow('Width', self.width_spin)
        self.size_label = QLabel()
        form.addRow('Output size', self.size_label)
        layout.addLayout(form)
        self.smooth_check = QCheckBox('Smooth edges (recommended)')
        self.smooth_check.setChecked(True)
        self.smooth_check.setToolTip('Use finer atom and bond meshes and render extra samples for smoother edges.')
        layout.addWidget(self.smooth_check)
        self.white_background_check = QCheckBox('White background')
        self.white_background_check.setChecked(True)
        self.white_background_check.setToolTip('Clear this to export the current background color.')
        layout.addWidget(self.white_background_check)
        self.crop_check = QCheckBox('Cropped image (remove empty margins' + (', omit coordinate axes)' if scene_image else ')'))
        self.crop_check.setChecked(QSettings('LELE', 'LELE').value('image_export/cropped', False, type=bool))
        self.crop_check.setToolTip('Keep the current view and trim empty margins. The saved image may be smaller than the requested canvas size. Your choice is remembered.')
        layout.addWidget(self.crop_check)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        layout.addWidget(self.details_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.scale_combo.currentIndexChanged.connect(self._set_scale)
        self.width_spin.valueChanged.connect(self._update)
        self.smooth_check.toggled.connect(self._update)
        self.crop_check.toggled.connect(self._update)
        self.scale_combo.setCurrentIndex(3)
        self._set_scale()

    def _set_scale(self, *_):
        factor = self.scale_combo.currentData()
        if factor is not None:
            self.width_spin.setValue(min(self.width_spin.maximum(), self.source_size[0] * factor))
        self._update()

    def settings(self):
        return PngSettings(self.width_spin.value(),
                           max(1, min(MAX_OUTPUT_SIDE, round(self.width_spin.value() * self.aspect))),
                           supersample=2 if self.smooth_check.isChecked() else 1,
                           cropped=self.crop_check.isChecked(),
                           white_background=self.white_background_check.isChecked())

    def accept(self):
        preferences = QSettings('LELE', 'LELE')
        preferences.setValue('image_export/cropped', self.crop_check.isChecked())
        preferences.sync()
        super().accept()

    def _update(self, *_):
        settings = self.settings()
        matches = next((i for i in range(4)
                        if settings.width == self.source_size[0] * self.scale_combo.itemData(i)), 4)
        with QSignalBlocker(self.scale_combo):
            self.scale_combo.setCurrentIndex(matches)
        self.size_label.setText(f'{settings.width} × {settings.height} px · ' +
                               ('before cropping' if settings.cropped else 'canvas aspect ratio'))
        try:
            settings.capture_scale(self.source_size)
            self.details_label.setText(('High-quality JPEG' if self.format_name == 'JPEG' else 'Lossless ' + self.format_name) + ' · 300 dpi print metadata')
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(True)
        except ValueError as exc:
            self.details_label.setText(str(exc))
            self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
