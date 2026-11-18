"""Interactive forward powder-XRD simulation for the current crystal frame."""
from copy import deepcopy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from .dialog_policy import QDialog, QFileDialog, QMessageBox

from .operations import run_data_task
from .output_text import LoadCancelled
from .xrd import export_pattern_csv, simulate_powder_xrd


class XrdDialog(QDialog):
    def __init__(self, frame, source_path=None, parent=None):
        super().__init__(parent)
        self.frame = deepcopy(frame)
        self.source_path = Path(source_path) if source_path is not None else Path('structure')
        self.pattern = None
        self.setWindowTitle('Powder XRD — ' + self.source_path.name)
        self.resize(1100, 850)
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from .figure_export import FigureExportToolbar
        layout = QVBoxLayout(self)
        form = QGridLayout()
        layout.addLayout(form)
        self.radiation = QComboBox()
        for label, value in [('Cu Kα1', 1.54056), ('Mo Kα1', .70930),
                              ('Co Kα1', 1.78896), ('Cr Kα1', 2.28970), ('Custom', None)]:
            self.radiation.addItem(label, value)
        self.wavelength = self._spin(.05, 10., 1.54056, 6, ' Å')
        self.minimum = self._spin(0., 178., 5., 3, '°')
        self.maximum = self._spin(.01, 179.9, 90., 3, '°')
        self.fwhm = self._spin(.001, 10., .15, 3, '°')
        self.step = self._spin(.001, 2., .02, 3, '°')
        self.b_iso = self._spin(0., 100., 0., 3, ' Å²')
        self.profile = QComboBox()
        self.profile.addItems(['Gaussian', 'Lorentzian'])
        self.lp = QCheckBox('Lorentz–polarization (unpolarized powder)')
        self.lp.setChecked(True)
        self.sticks = QCheckBox('Reflection markers')
        self.sticks.setChecked(True)
        self.labels = QCheckBox('Label strongest peaks')
        controls = [('Radiation', self.radiation), ('Wavelength', self.wavelength),
                    ('2θ minimum', self.minimum), ('2θ maximum', self.maximum),
                    ('Profile', self.profile), ('FWHM', self.fwhm),
                    ('Angular step', self.step), ('Isotropic B', self.b_iso)]
        for index, (label, widget) in enumerate(controls):
            row, col = divmod(index, 4)
            form.addWidget(QLabel(label), row * 2, col)
            form.addWidget(widget, row * 2 + 1, col)
        form.addWidget(self.lp, 4, 0, 1, 2)
        form.addWidget(self.sticks, 4, 2)
        form.addWidget(self.labels, 4, 3)
        self.calculate_button = QPushButton('Calculate pattern')
        self.calculate_button.setAutoDefault(False)
        form.addWidget(self.calculate_button, 5, 0, 1, 4)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(split, 1)
        plot_page = QWidget()
        plot_layout = QVBoxLayout(plot_page)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(9, 4), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.get_default_filename = lambda: str(self.source_path.with_name(self.source_path.stem + '_xrd.svg'))
        plot_layout.addWidget(FigureExportToolbar(self.canvas, self))
        plot_layout.addWidget(self.canvas)
        split.addWidget(plot_page)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['2θ (°)', 'd (Å)', 'Intensity (max 100)',
                                              'Reciprocal vectors', 'hkl (one per Friedel pair)'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        split.addWidget(self.table)
        split.setSizes([430, 220])
        notice = QLabel('Calculated from the current unit cell, including mixed occupancies. '
            'This simulates a powder pattern; it does not refine a structure against experimental data. '
            'Single wavelength, neutral-atom scattering and one isotropic B; no texture or anomalous scattering. '
            'Slab vacuum repeats as part of the 3D crystal. Parameters apply after “Calculate pattern”.')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.save_plot = QPushButton('Save plot SVG / PNG…')
        self.save_curve = QPushButton('Export curve CSV…')
        self.save_reflections = QPushButton('Export reflections CSV…')
        for button in (self.save_plot, self.save_curve, self.save_reflections):
            button.setAutoDefault(False)
            button.setEnabled(False)
            row.addWidget(button)
        self.radiation.currentIndexChanged.connect(self._radiation_changed)
        self.calculate_button.clicked.connect(self.calculate)
        self.sticks.toggled.connect(self.draw)
        self.labels.toggled.connect(self.draw)
        self.save_plot.clicked.connect(self.export_plot)
        self.save_curve.clicked.connect(lambda: self.export_csv(False))
        self.save_reflections.clicked.connect(lambda: self.export_csv(True))
        self.calculate()

    @staticmethod
    def _spin(minimum, maximum, value, decimals, suffix):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(decimals)
        widget.setValue(value)
        widget.setSuffix(suffix)
        widget.setKeyboardTracking(False)
        return widget

    def _radiation_changed(self):
        value = self.radiation.currentData()
        if value is not None:
            self.wavelength.setValue(value)

    def calculate(self):
        parameters = dict(wavelength=self.wavelength.value(),
            two_theta_range=(self.minimum.value(), self.maximum.value()),
            fwhm=self.fwhm.value(), step=self.step.value(),
            lorentz_polarization=self.lp.isChecked(), b_iso=self.b_iso.value(),
            profile=self.profile.currentText())
        try:
            pattern = run_data_task(self, 'Calculating powder XRD',
                lambda: simulate_powder_xrd(self.frame, **parameters), cancellable=True)
        except LoadCancelled:
            self.status.setText('Calculation cancelled; the previous result is retained.')
            return
        except (ValueError, TypeError) as exc:
            self.status.setText(str(exc) + ' The previous result, if any, is retained.')
            return
        self.pattern = pattern
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(pattern.peaks))
        for row, peak in enumerate(pattern.peaks):
            for col, value in enumerate((peak.two_theta, peak.d_spacing, peak.intensity,
                                          peak.multiplicity, peak.label)):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, round(value, 6) if isinstance(value, float) else value)
                if col == 4:
                    item.setToolTip(str(value))
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(4, 330)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.status.setText(f'{len(pattern.peaks)} distinct peak positions · λ {pattern.wavelength:.6f} Å · '
            f'{pattern.profile} FWHM {pattern.fwhm:g}° · B {pattern.b_iso:g} Å² · '
            f'Lorentz–polarization {"on" if pattern.lorentz_polarization else "off"}. '
            'Both reflection sticks and the broadened curve are independently normalized to 100.')
        if parameters['step'] > pattern.fwhm / 5:
            self.status.setText(self.status.text() + ' Use an angular step ≤ FWHM/5 to resolve narrow peaks well.')
        for button in (self.save_plot, self.save_curve, self.save_reflections):
            button.setEnabled(True)
        self.draw()

    def draw(self, *_):
        if self.pattern is None:
            return
        pattern = self.pattern
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        axes.plot(pattern.two_theta, pattern.intensity, color='#285b93', lw=1.4)
        if self.sticks.isChecked():
            axes.vlines([p.two_theta for p in pattern.peaks], -7, -2, colors='#c76545', linewidths=.9)
        if self.labels.isChecked():
            for peak in sorted(pattern.peaks, key=lambda p: p.intensity, reverse=True)[:12]:
                import numpy as np
                height = float(np.interp(peak.two_theta, pattern.two_theta, pattern.intensity))
                representative = max(peak.hkls)
                axes.annotate('(' + ' '.join(map(str, representative)) + ')',
                    (peak.two_theta, height), xytext=(0, 5), textcoords='offset points',
                    ha='center', va='bottom', rotation=90, fontsize=8)
        if not pattern.peaks:
            axes.text(.5, .5, 'No allowed reflections in this angular range.',
                      ha='center', va='center', transform=axes.transAxes)
        axes.set_xlim(pattern.two_theta[0], pattern.two_theta[-1])
        axes.set_ylim(-10 if self.sticks.isChecked() else 0, 125 if self.labels.isChecked() else 108)
        axes.set_xlabel('2θ (°)')
        axes.set_ylabel('Relative intensity')
        axes.set_title(f'Simulated powder XRD · λ = {pattern.wavelength:.6f} Å')
        axes.spines[['top', 'right']].set_visible(False)
        self.canvas.draw_idle()

    def export_plot(self):
        if self.pattern is None:
            return
        from .figure_export import save_figure_dialog
        return save_figure_dialog(self, self.figure,
                                 self.source_path.with_name(self.source_path.stem + '_xrd'))

    def export_csv(self, reflections=False):
        if self.pattern is None:
            return
        stem = self.source_path.stem + ('_xrd_reflections' if reflections else '_xrd_curve')
        filename, _ = QFileDialog.getSaveFileName(self, 'Export XRD data',
            str(self.source_path.with_name(stem + '.csv')), 'CSV (*.csv)')
        if not filename:
            return
        try:
            return export_pattern_csv(self.pattern, filename, reflections=reflections)
        except OSError as exc:
            QMessageBox.warning(self, 'Could not export XRD', str(exc))
