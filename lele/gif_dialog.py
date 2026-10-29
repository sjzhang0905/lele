"""Animation export options, usable without importing the rendering backend."""
from math import ceil

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox,
                               QDoubleSpinBox, QCheckBox, QLabel, QDialogButtonBox, QWidget)

from .animation_export import GifSettings


class GifExportDialog(QDialog):
    def __init__(self, parent=None, *, total_frames, mode_label='', view_size=(960, 540),
                 trajectory_fps=6, amplitude=.35, cycle_seconds=1.):
        super().__init__(parent)
        self.setWindowTitle('Export animation GIF')
        self.resize(450, 420)
        self.total_frames = total_frames
        self.aspect = max(1, view_size[1]) / max(1, view_size[0])
        layout = QVBoxLayout(self)
        note = QLabel('Save the 3D view using the current camera, colours and labels.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItem('Geometry / optimization trajectory', 'trajectory')
        self.source_combo.addItem('Current vibration' + (f' · {mode_label}' if mode_label else ' · select a frequency first'), 'vibration')
        self.source_combo.model().item(0).setEnabled(total_frames > 1)
        self.source_combo.model().item(1).setEnabled(bool(mode_label))
        form.addRow('Animation', self.source_combo)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(160, min(2560, max(160, int(4096 / self.aspect))))
        self.width_spin.setValue(min(self.width_spin.maximum(), max(1280, view_size[0])))
        self.width_spin.setSuffix(' px')
        form.addRow('Width', self.width_spin)
        self.size_label = QLabel()
        form.addRow('Output size', self.size_label)
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 50)
        self.fps_spin.setValue(24 if mode_label else trajectory_fps)
        form.addRow('FPS', self.fps_spin)
        layout.addLayout(form)
        self.trajectory_page = QWidget()
        trajectory = QFormLayout(self.trajectory_page)
        trajectory.setContentsMargins(0, 0, 0, 0)
        self.first_spin = QSpinBox()
        self.first_spin.setRange(1, max(1, total_frames))
        self.last_spin = QSpinBox()
        self.last_spin.setRange(1, max(1, total_frames))
        self.last_spin.setValue(total_frames)
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, max(1, total_frames))
        trajectory.addRow('First frame', self.first_spin)
        trajectory.addRow('Last frame', self.last_spin)
        trajectory.addRow('Every N frames', self.step_spin)
        self.ping_pong = QCheckBox('Forward then backward')
        trajectory.addRow(self.ping_pong)
        layout.addWidget(self.trajectory_page)
        self.vibration_page = QWidget()
        vibration = QFormLayout(self.vibration_page)
        vibration.setContentsMargins(0, 0, 0, 0)
        self.period_spin = QDoubleSpinBox()
        self.period_spin.setRange(.2, 10.)
        self.period_spin.setDecimals(2)
        self.period_spin.setSingleStep(.1)
        self.period_spin.setValue(cycle_seconds)
        self.period_spin.setSuffix(' s')
        vibration.addRow('One cycle', self.period_spin)
        self.amplitude_spin = QDoubleSpinBox()
        self.amplitude_spin.setRange(.01, 2.)
        self.amplitude_spin.setDecimals(2)
        self.amplitude_spin.setSingleStep(.05)
        self.amplitude_spin.setValue(amplitude)
        self.amplitude_spin.setSuffix(' Å')
        self.amplitude_spin.setToolTip('Maximum atom displacement from the reference geometry.')
        vibration.addRow('Amplitude', self.amplitude_spin)
        layout.addWidget(self.vibration_page)
        self.loop_check = QCheckBox('Loop continuously')
        self.loop_check.setChecked(True)
        layout.addWidget(self.loop_check)
        self.quality_check=QCheckBox('High quality: 2× supersampling + Lanczos');self.quality_check.setChecked(True);layout.addWidget(self.quality_check)
        self.dither_check=QCheckBox('Dither GIF colours (shared animation palette)');self.dither_check.setChecked(True);layout.addWidget(self.dither_check)
        self.details_label = QLabel()
        self.details_label.setWordWrap(True)
        layout.addWidget(self.details_label)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for widget in [self.first_spin, self.last_spin, self.step_spin, self.width_spin,
                       self.fps_spin, self.period_spin, self.amplitude_spin]:
            widget.valueChanged.connect(self._update)
        self.source_combo.currentIndexChanged.connect(self._update)
        self.ping_pong.toggled.connect(self._update)
        self.source_combo.setCurrentIndex(1 if mode_label else 0)
        self._update()

    def settings(self):
        width = self.width_spin.value()
        return GifSettings(source=self.source_combo.currentData(), width=width,
                           height=max(1, min(4096, round(width * self.aspect))),
                           fps=self.fps_spin.value(), first_frame=self.first_spin.value(),
                           last_frame=self.last_spin.value(), stride=self.step_spin.value(),
                           ping_pong=self.ping_pong.isChecked(), cycle_seconds=self.period_spin.value(),
                           amplitude=self.amplitude_spin.value(), loop=self.loop_check.isChecked(),
                           supersample=2 if self.quality_check.isChecked() else 1,dither=self.dither_check.isChecked())

    def _update(self, *_):
        vibration = self.source_combo.currentData() == 'vibration'
        self.trajectory_page.setVisible(not vibration)
        self.vibration_page.setVisible(vibration)
        with QSignalBlocker(self.fps_spin):
            self.fps_spin.setMinimum(ceil(8 / self.period_spin.value()) if vibration else 1)
        settings = self.settings()
        self.size_label.setText(f'{settings.width} × {settings.height} px · same aspect ratio as the canvas')
        try:
            count = settings.vibration_frame_count() if vibration else len(settings.trajectory_indices(self.total_frames))
            duration = settings.cycle_seconds if vibration else count / settings.fps
            self.details_label.setText(f'{count} frames · {duration:.2f} s'
                                       + (' · one vibration cycle' if vibration else ''))
            enabled = self.source_combo.model().item(self.source_combo.currentIndex()).isEnabled()
        except ValueError as error:
            self.details_label.setText(str(error))
            enabled = False
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(enabled)
