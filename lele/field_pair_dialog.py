"""Two local file selectors with explicit scientific roles and per-surface levels."""
from pathlib import Path

from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)

from .dialog_policy import QDialog, QFileDialog
from .field_pair import ROLES, TITLES, make_field_pair, proposed_level, read_pair_source, source_channels
from .operations import run_data_task
from .output_text import LoadCancelled


class FieldPairDialog(QDialog):
    independent_files = True

    def __init__(self, mode, directory, parent=None):
        super().__init__(parent)
        self.mode = mode
        self.directory = str(directory)
        self.sources = [None, None]
        self.result_pair = None
        self.paths, self.channels, self.levels, self.ranges = [], [], [], []
        self.setWindowTitle(TITLES[mode])
        self.resize(650, 390)
        layout = QVBoxLayout(self)
        help_text = ('Choose an electron-density surface and the ESP grid used to color it. '
                     'For VASP use CHGCAR (or CHG) and an ionic + Hartree LOCPOT from LVHAR = .TRUE. '
                     'LOCPOT is converted to the potential for a positive test charge. ESP CUBE values are used as supplied.'
                     if mode == 'esp' else
                     'Choose the electron (lime) and hole (cyan) density grids for the same geometry and excitation. '
                     'Each isovalue uses its own dataset’s units.')
        intro = QLabel(help_text)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        for i, role in enumerate(ROLES[mode]):
            box = QGroupBox(role)
            form = QFormLayout(box)
            row = QHBoxLayout()
            path = QLineEdit()
            path.setReadOnly(True)
            path.setPlaceholderText('Choose local file…')
            browse = QPushButton('Browse…')
            browse.clicked.connect(lambda _checked=False, i=i: self.browse(i))
            row.addWidget(path, 1)
            row.addWidget(browse)
            form.addRow('File', row)
            channel = QComboBox()
            channel.currentIndexChanged.connect(lambda _index, i=i: self.update_level(i))
            form.addRow('Dataset', channel)
            level = QLineEdit() if mode == 'electron_hole' or i == 0 else None
            detail = QLabel() if level is not None else None
            if level is not None:
                form.addRow('Signed isovalue' if mode == 'electron_hole' else 'Density isovalue', level)
                form.addRow(detail)
            self.paths.append(path)
            self.channels.append(channel)
            self.levels.append(level)
            self.ranges.append(detail)
            layout.addWidget(box)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #a32626')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.plot_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.plot_button.setText('Plot')
        self.plot_button.setEnabled(False)
        buttons.accepted.connect(self.plot)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self, i):
        role = ROLES[self.mode][i]
        filters = ('Field files (*.cube *.cub CHGCAR* CHG LOCPOT*);;All files (*)'
                   if self.mode == 'esp' else 'Gaussian CUBE (*.cube *.cub);;All files (*)')
        path, _ = QFileDialog.getOpenFileName(self, 'Choose ' + role + ' file', self.directory, filters)
        if path:
            self.load_source(i, path)

    def load_source(self, i, path):
        role = ROLES[self.mode][i]
        try:
            source = run_data_task(self, 'Reading ' + role + ' field',
                                   lambda: read_pair_source(path, role), cancellable=True)
            choices = source_channels(source)
        except LoadCancelled:
            return
        except (ValueError, OSError, RuntimeError, MemoryError, IndexError) as exc:
            self.error.setText(str(exc))
            return
        self.directory = str(Path(path).parent)
        self.paths[i].setText(str(source.path))
        self.paths[i].setToolTip(str(source.path))
        self.sources[i] = source
        channel = self.channels[i]
        channel.clear()
        for label, indices in choices:
            channel.addItem(label, list(indices))
        self.update_level(i)
        self.error.clear()
        self.plot_button.setEnabled(all(source is not None for source in self.sources))

    def update_level(self, i):
        data = self.channels[i].currentData()
        if not data or self.levels[i] is None:
            return
        field = self.sources[i].volumes[data[0]]
        low, high = float(field.data.min()), float(field.data.max())
        value = proposed_level(field, ROLES[self.mode][i], (low, high))
        self.levels[i].setText(f'{value:.10g}')
        self.ranges[i].setText(f'Range {low:.7g} to {high:.7g}  ·  {field.unit}')

    def plot(self):
        if not all(self.sources):
            return
        try:
            choices = [tuple(box.currentData()) for box in self.channels]
            levels = [float(edit.text()) for edit in self.levels if edit is not None]
            self.result_pair = run_data_task(self, 'Preparing ' + TITLES[self.mode],
                lambda: make_field_pair(self.mode, self.sources, choices, levels), cancellable=True)
        except LoadCancelled:
            return
        except (ValueError, OSError, RuntimeError, MemoryError, IndexError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()
