import os
import sys
import unittest

if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from lele.gif_dialog import GifExportDialog


class GifDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['GIF options tests'])

    def test_trajectory_range_step_ping_pong_and_aspect_ratio(self):
        dialog = GifExportDialog(total_frames=8, view_size=(800, 400), trajectory_fps=6)
        self.addCleanup(dialog.deleteLater)
        self.assertEqual(dialog.settings().source, 'trajectory')
        self.assertFalse(dialog.source_combo.model().item(1).isEnabled())
        dialog.first_spin.setValue(2)
        dialog.last_spin.setValue(6)
        dialog.step_spin.setValue(2)
        dialog.ping_pong.setChecked(True)
        dialog.width_spin.setValue(512)
        settings = dialog.settings()
        self.assertEqual(settings.trajectory_indices(8), [1, 3, 5, 3])
        self.assertEqual((settings.width, settings.height), (512, 256))
        self.assertIn('4 frames', dialog.details_label.text())
        dialog.last_spin.setValue(1)
        self.assertFalse(dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())

    def test_selected_mode_uses_amplitude_and_cycle_and_preserves_sufficient_samples(self):
        dialog = GifExportDialog(total_frames=1, mode_label='Mode 1 · -195.4374 cm⁻¹',
                                  amplitude=.65, cycle_seconds=.2)
        self.addCleanup(dialog.deleteLater)
        settings = dialog.settings()
        self.assertEqual(settings.source, 'vibration')
        self.assertAlmostEqual(settings.amplitude, .65)
        self.assertEqual(settings.vibration_frame_count(), 8)
        self.assertEqual(settings.fps, 40)
        self.assertFalse(dialog.source_combo.model().item(0).isEnabled())
        self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
        dialog.period_spin.setValue(2.)
        dialog.fps_spin.setValue(12)
        self.assertEqual(dialog.settings().vibration_frame_count(), 24)
        self.assertIn('2.00 s', dialog.details_label.text())
