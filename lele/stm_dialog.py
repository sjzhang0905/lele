"""Interactive constant-height / constant-current STM maps from PARCHG."""
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, QSpinBox, QLabel, QPushButton, QLineEdit, QCheckBox
from .dialog_policy import QDialog, QFileDialog, QMessageBox
from .operations import run_data_task
from .output_text import LoadCancelled
from .stm import simulate_stm, slab_geometry, export_stm_csv


class STMDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from .figure_export import FigureExportToolbar
        self.document = document
        self.result = None
        self.setWindowTitle('Simulated STM — ' + document.path.name)
        self.resize(1040, 870)
        layout = QVBoxLayout(self)
        intro = QLabel('PARCHG partial density · constant height or constant-current isodensity approximation. '
            'The energy window is fixed by the source VASP calculation; the filename alone does not determine the bias.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        controls = QHBoxLayout()
        layout.addLayout(controls)
        left, right = QFormLayout(), QFormLayout()
        controls.addLayout(left)
        controls.addLayout(right)
        self.mode = QComboBox()
        self.mode.addItem('Constant height', 'height')
        self.mode.addItem('Constant current (isodensity)', 'current')
        left.addRow('Mode', self.mode)
        self.axis = QComboBox()
        self.axis.addItems(['Normal to b–c', 'Normal to a–c', 'Normal to a–b'])
        self.axis.setCurrentIndex(2)
        left.addRow('Surface plane', self.axis)
        self.side = QComboBox()
        self.side.addItem('Upper (+ normal)', 1)
        self.side.addItem('Lower (− normal)', -1)
        left.addRow('Surface', self.side)
        self.height = QDoubleSpinBox()
        self.height.setRange(0., 1000.)
        self.height.setDecimals(3)
        self.height.setSuffix(' Å')
        self.height.setValue(2.)
        left.addRow('Tip above outermost atom', self.height)
        self.setpoint = QLineEdit('1e-4')
        self.setpoint.setToolTip('Partial-density setpoint in e/Å³. There is no absolute current calibration in PARCHG.')
        left.addRow('Density setpoint (e/Å³)', self.setpoint)
        self.minimum = QDoubleSpinBox()
        self.minimum.setRange(0., 1000.)
        self.minimum.setDecimals(3)
        self.minimum.setSuffix(' Å')
        left.addRow('Minimum scan height', self.minimum)
        self.spin = QComboBox()
        self.spin.addItem('Total', 'total')
        if len(document.volumes) == 2:
            self.spin.addItem('Spin up', 'up')
            self.spin.addItem('Spin down', 'down')
        right.addRow('Density', self.spin)
        self.repeat_u, self.repeat_v = QSpinBox(), QSpinBox()
        for spin in (self.repeat_u, self.repeat_v):
            spin.setRange(1, 12)
            spin.setValue(1)
        repeats = QHBoxLayout()
        repeats.addWidget(self.repeat_u)
        repeats.addWidget(QLabel('×'))
        repeats.addWidget(self.repeat_v)
        right.addRow('In-plane repeats', repeats)
        self.smoothing = QDoubleSpinBox()
        self.smoothing.setRange(0., 10.)
        self.smoothing.setDecimals(2)
        self.smoothing.setSingleStep(.25)
        self.smoothing.setToolTip('Periodic Gaussian smoothing of the density before sampling, in grid-index units. Zero keeps the original density.')
        right.addRow('Density smoothing σ (grid points)', self.smoothing)
        self.colormap = QComboBox()
        self.colormap.addItems(['afmhot', 'gray', 'viridis', 'magma', 'copper'])
        right.addRow('Color map', self.colormap)
        self.reverse = QCheckBox('Reverse colors')
        right.addRow(self.reverse)
        self.log = QCheckBox('Log color scale (density only)')
        right.addRow(self.log)
        update = QPushButton('Calculate / update map')
        update.clicked.connect(self.calculate)
        layout.addWidget(update)
        self.figure = Figure(figsize=(8, 5), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        layout.addWidget(FigureExportToolbar(self.canvas, self))
        layout.addWidget(self.canvas, 1)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.save_image = QPushButton('Export image…')
        self.save_image.clicked.connect(self.export_image)
        self.save_data = QPushButton('Export samples CSV…')
        self.save_data.clicked.connect(self.export_csv)
        row.addWidget(self.save_image)
        row.addWidget(self.save_data)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.colormap.currentIndexChanged.connect(self.redraw)
        self.reverse.toggled.connect(self.redraw)
        self.log.toggled.connect(self.redraw)
        self._mode_changed()
        try:
            geometry = slab_geometry(document.frames[0])
            self.height.setValue(min(2., geometry.vacuum*.25))
        except ValueError:
            pass
        self.calculate()
        if self.result is not None:
            positive = self.result.values[self.result.values > 0]
            if positive.size:
                self.setpoint.setText(f'{np.median(positive):.6g}')

    def _mode_changed(self, *_):
        is_height = self.mode.currentData() == 'height'
        self.height.setEnabled(is_height)
        self.setpoint.setEnabled(not is_height)
        self.minimum.setEnabled(not is_height)
        self.log.setEnabled(is_height)

    def calculate(self, *_):
        try:
            mode = self.mode.currentData()
            try:
                setpoint = float(self.setpoint.text())
            except ValueError:
                raise ValueError('Enter a positive finite density setpoint, for example 1e-4.') from None
            arguments = dict(mode=mode, axis=self.axis.currentIndex(), side=self.side.currentData(),
                height=self.height.value(), setpoint=setpoint, spin=self.spin.currentData(),
                repeat=(self.repeat_u.value(), self.repeat_v.value()), smoothing=self.smoothing.value(),
                minimum_height=self.minimum.value())
            result = run_data_task(self, 'Calculating STM map',
                lambda: simulate_stm(self.document, **arguments), cancellable=True)
        except LoadCancelled:
            return
        except (ValueError, OSError, MemoryError) as exc:
            self.note.setText(str(exc))
            return
        self.result = result
        self.redraw()

    def redraw(self, *_):
        self.save_image.setEnabled(self.result is not None)
        self.save_data.setEnabled(self.result is not None)
        if self.result is None:
            return
        from matplotlib.colors import LogNorm
        result = self.result
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        values = np.ma.masked_invalid(result.values)
        cmap = self.colormap.currentText() + ('_r' if self.reverse.isChecked() else '')
        norm = None
        if result.mode == 'height' and self.log.isChecked():
            values = np.ma.masked_less_equal(values, 0.)
            if values.count():
                lo, hi = float(values.min()), float(values.max())
                norm = LogNorm(lo, max(hi, lo*(1+1e-6)))
        if values.count():
            # Pixel values remain the exact computed samples. Rasterizing the
            # heat map keeps SVG manageable; axes and text remain vectors.
            mesh = ax.pcolormesh(result.x, result.y, values, shading='nearest',
                                 cmap=cmap, norm=norm, rasterized=True)
            self.figure.colorbar(mesh, ax=ax, label=result.unit)
        else:
            ax.text(.5, .5, 'No isodensity crossing in the vacuum scan range.\nAdjust the density setpoint or scan height.',
                    ha='center', va='center', transform=ax.transAxes)
        ax.set_aspect('equal')
        ax.set_xlabel('In-plane u (Å)')
        ax.set_ylabel('In-plane v (Å)')
        p = result.parameters
        title = (f'Constant height · {p["height"]:.3g} Å above surface' if result.mode == 'height'
                 else f'Constant current · ρ = {p["setpoint"]:.5g} e/Å³')
        ax.set_title(title + f' · {p["spin"]}')
        note = (f'Grid {result.values.shape[0]} × {result.values.shape[1]}; '
                f'atom-free gap {p["vacuum_gap"]:.4g} Å; '
                f'normal {np.array2string(result.normal, precision=4)}. ')
        if result.mode == 'current':
            note += (f'Valid crossings {result.valid_fraction:.1%}. Heights are measured outward from the outermost atom. '
                'Scanning starts at the vacuum midpoint; missing crossings remain blank / NaN. '
                'The setpoint is density, not a calibrated current in nA. ')
        else:
            note += 'Color represents partial density, proportional to the tunnelling-current contrast in the simple tip approximation. '
        if p['smoothing']:
            note += f'Density Gaussian σ = {p["smoothing"]:g} grid points. '
        self.note.setText(note)
        self.canvas.draw_idle()

    def export_image(self):
        if self.result is None:
            return
        from .figure_export import save_figure_dialog
        save_figure_dialog(self, self.figure, str(self.document.path.with_name(self.document.path.name + '_STM')))

    def export_csv(self):
        if self.result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export STM samples',
            str(self.document.path.with_name(self.document.path.name + '_STM.csv')), 'CSV (*.csv)')
        if not path:
            return
        if Path(path).suffix.lower() != '.csv':
            path += '.csv'
        try:
            result = self.result
            run_data_task(self, 'Exporting STM samples', lambda: export_stm_csv(result, path), cancellable=True)
        except LoadCancelled:
            return
        except OSError as exc:
            QMessageBox.warning(self, 'Could not export STM samples', str(exc))
