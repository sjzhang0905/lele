"""Import a table of extrema into the file chosen in the Files tree."""
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from .color_controls import color_value, set_color_swatch
from .dialog_policy import QColorDialog, QDialog, QFileDialog
from .esp_extrema import read_extrema_points
from .operations import run_data_task
from .output_text import LoadCancelled


class EspExtremaDialog(QDialog):
    independent_files = True

    def __init__(self, document, display_name, text_color, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add ESP extrema')
        self.resize(495, 255)
        self.rows = None
        self.directory = str(document.path.parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        form.addRow('Target', QLabel(display_name))
        row = QHBoxLayout()
        self.path = QLineEdit()
        self.path.setReadOnly(True)
        self.path.setPlaceholderText('X Y Z value, one point per row')
        browse = QPushButton('Browse…')
        browse.clicked.connect(self.browse)
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        form.addRow('Extrema file', row)
        self.unit = QComboBox()
        self.unit.addItem('Angstrom (Å)', 'Å')
        self.unit.addItem('Bohr', 'Bohr')
        form.addRow('Coordinate unit', self.unit)
        self.height = QDoubleSpinBox()
        self.height.setDecimals(3)
        self.height.setRange(.001, 1000.)
        self.height.setSingleStep(.05)
        self.height.setValue(.35)
        self.height.setSuffix(' Å')
        form.addRow('Text size', self.height)
        self.color = QPushButton()
        set_color_swatch(self.color, text_color, 'Extremum text color')
        self.color.clicked.connect(self.choose_color)
        form.addRow('Text color', self.color)
        self.note = QLabel('The fourth column is displayed in its original units, rounded to one decimal place.')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.add_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.add_button.setText('Add extrema')
        self.add_button.setEnabled(False)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(color_value(self.color)), self, 'Extremum text color')
        if color.isValid():
            set_color_swatch(self.color, color.name(), 'Extremum text color')

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose ESP extrema', self.directory,
                                              'Point data (*.dat *.txt *.csv);;All files (*)')
        if path:
            self.load_file(path)

    def load_file(self, path):
        self.path.setText(str(path))
        self.directory = str(Path(path).parent)
        self.rows = None
        self.add_button.setEnabled(False)
        try:
            self.rows = run_data_task(self, 'Reading ESP extrema', lambda: read_extrema_points(path),
                                      cancellable=True)
        except LoadCancelled:
            self.note.setText('Import cancelled.')
            return
        except (ValueError, OSError) as exc:
            self.note.setText(str(exc))
            return
        values = self.rows[:, 3]
        self.note.setText(f'{len(values)} points · values from {values.min():.1f} to {values.max():.1f} '
                          'in the original units.')
        self.add_button.setEnabled(True)
