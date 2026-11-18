"""Embedded, live scalar-color controls shared by the surface layer editor."""
from copy import deepcopy
from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QFormLayout, QHBoxLayout, QComboBox,
    QCheckBox, QLineEdit, QLabel, QDialogButtonBox, QSlider, QVBoxLayout)
from .dialog_policy import QDialog, QMessageBox
from .field_mapping import PALETTES, DEFAULT_PALETTE, field_data_limits, validate_layer_mapping


def field_title(index, field):
    return f'{index+1} · {field.label or "Field"} [{field.unit or "source units"}]'


class FieldMappingWidget(QWidget):
    """No dialog or Apply step: every complete valid input emits settings."""
    changed = Signal(object)

    def __init__(self, fields, settings=None, parent=None):
        super().__init__(parent)
        self.fields = list(fields)
        self._loading = False
        self._slider_bounds = (-.05, .05)
        self._field_bounds = {}
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.source = QComboBox()
        self.source.setMinimumContentsLength(28)
        self.source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.source.addItem('Uniform layer color', -1)
        for i, field in enumerate(fields):
            self.source.addItem(field_title(i, field), i)
        layout.addRow('Color field', self.source)
        self.palette = QComboBox(); self.palette.addItems(PALETTES)
        layout.addRow('Palette (low → high)', self.palette)
        self.automatic = QCheckBox('Automatic range from color-field grid (VMD)')
        layout.addRow(self.automatic)
        self.minimum = QLineEdit(); self.maximum = QLineEdit()
        self.min_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_slider = QSlider(Qt.Orientation.Horizontal)
        for label, entry, slider in (('Min', self.minimum, self.min_slider), ('Max', self.maximum, self.max_slider)):
            entry.setMaximumWidth(180)
            slider.setRange(0, 10000)
            slider.setTracking(True)
            row = QHBoxLayout(); row.addWidget(entry); row.addWidget(slider, 1)
            layout.addRow(label + ' (color-field units)', row)
        self.legend = QCheckBox('Show color scale'); layout.addRow(self.legend)
        self.note = QLabel(); self.note.setWordWrap(True); layout.addRow(self.note)
        self.error = QLabel(); self.error.setWordWrap(True)
        self.error.setStyleSheet('color: #b34728;'); layout.addRow(self.error)
        self.source.currentIndexChanged.connect(self._source_changed)
        self.palette.currentIndexChanged.connect(self._palette_changed)
        self.automatic.toggled.connect(self._auto_changed)
        self.legend.toggled.connect(self._emit_changed)
        self.minimum.textChanged.connect(self._numeric_changed)
        self.maximum.textChanged.connect(self._numeric_changed)
        self.min_slider.valueChanged.connect(lambda value: self._slider_changed(True, value))
        self.max_slider.valueChanged.connect(lambda value: self._slider_changed(False, value))
        self.set_settings(settings or {})

    def _bounds(self):
        index = self.source.currentData()
        if index is None or not 0 <= index < len(self.fields):
            return (-.05, .05)
        if index not in self._field_bounds:
            try: self._field_bounds[index] = field_data_limits(self.fields[index].data)
            except ValueError: self._field_bounds[index] = (-.05, .05)
        return self._field_bounds[index]

    def _automatic_limits(self):
        low, high = self._bounds()
        if not self.palette.currentText().startswith('VMD '):
            # The legacy renderer uses the surface sample range. The grid range
            # is only an initial manual-control suggestion until edited.
            bound = max(abs(low), abs(high), 1e-12)
            return -bound, bound
        return low, high

    def set_settings(self, settings):
        self._loading = True
        try:
            settings = deepcopy(settings or {})
            index = settings.get('map_dataset', -1)
            selected = self.source.findData(index)
            if selected < 0:
                self.source.addItem(f'Missing field {index+1}', index)
                selected = self.source.count()-1
            self.source.setCurrentIndex(selected)
            self.palette.setCurrentText(settings.get('map_palette', DEFAULT_PALETTE))
            self.automatic.setChecked(settings.get('map_range') is None)
            low, high = settings.get('map_range') or self._automatic_limits()
            self.minimum.setText(f'{low:.12g}'); self.maximum.setText(f'{high:.12g}')
            self.legend.setChecked(settings.get('map_legend', True))
            self._sync_sliders()
            self.update_controls()
            self.error.clear()
        finally: self._loading = False

    def settings_value(self):
        value = dict(map_dataset=self.source.currentData(), map_palette=self.palette.currentText(),
                     map_legend=self.legend.isChecked(), map_range=None)
        if value['map_dataset'] >= 0 and not self.automatic.isChecked():
            try: value['map_range'] = [float(self.minimum.text()), float(self.maximum.text())]
            except ValueError: raise ValueError('Enter finite Min and Max values with Min < Max.') from None
        validate_layer_mapping(value)
        return value

    def _sync_sliders(self):
        try: low, high = float(self.minimum.text()), float(self.maximum.text())
        except ValueError: return
        import math
        if not (math.isfinite(low) and math.isfinite(high) and low < high): return
        field_low, field_high = self._bounds()
        self._slider_bounds = min(low, field_low), max(high, field_high)
        start, end = self._slider_bounds
        for slider, value in ((self.min_slider, low), (self.max_slider, high)):
            with QSignalBlocker(slider): slider.setValue(round((value-start)/(end-start)*10000))

    def _set_auto_numbers(self):
        low, high = self._automatic_limits()
        with QSignalBlocker(self.minimum), QSignalBlocker(self.maximum):
            self.minimum.setText(f'{low:.12g}'); self.maximum.setText(f'{high:.12g}')
        self._sync_sliders()

    def _source_changed(self, *_):
        if self._loading: return
        if self.automatic.isChecked(): self._set_auto_numbers()
        else: self._sync_sliders()
        self.update_controls(); self._emit_changed()

    def _palette_changed(self, *_):
        if self._loading: return
        if self.automatic.isChecked(): self._set_auto_numbers()
        self.update_controls(); self._emit_changed()

    def _auto_changed(self, *_):
        if self._loading: return
        if self.automatic.isChecked(): self._set_auto_numbers()
        self.update_controls(); self._emit_changed()

    def _numeric_changed(self, *_):
        if self._loading: return
        # Editing either value switches from autoscale to explicit limits.
        with QSignalBlocker(self.automatic): self.automatic.setChecked(False)
        self._sync_sliders(); self._emit_changed()

    def _slider_changed(self, minimum, position):
        if self._loading: return
        start, end = self._slider_bounds
        value = start + (end-start)*position/10000
        try:
            other = float(self.maximum.text() if minimum else self.minimum.text())
        except ValueError: return
        epsilon = max((end-start)/10000, 1e-12)
        value = min(value, other-epsilon) if minimum else max(value, other+epsilon)
        with QSignalBlocker(self.automatic): self.automatic.setChecked(False)
        entry = self.minimum if minimum else self.maximum
        with QSignalBlocker(entry): entry.setText(f'{value:.12g}')
        self._sync_sliders(); self._emit_changed()

    def update_controls(self, *_):
        index = self.source.currentData()
        mapped = index is not None and 0 <= index < len(self.fields)
        for control in (self.minimum, self.maximum, self.min_slider, self.max_slider,
                        self.palette, self.automatic, self.legend):
            control.setEnabled(mapped)
        vmd = self.palette.currentText().startswith('VMD ')
        self.automatic.setText('Automatic range from color-field grid (VMD)' if vmd else
                              'Automatic symmetric range from surface samples (legacy)')
        unit = (self.fields[index].unit or 'source units') if mapped else 'source units'
        low, high = self._bounds()
        scale = ('VMD RWB/BWR uses pure red and blue endpoints with white halfway between Min and Max. '
                 if vmd else 'Legacy red/white/blue palettes keep white at zero. ')
        self.note.setText(f'Grid range: {low:.6g} to {high:.6g} {unit}. ' + scale +
            'Drag a slider or type a value to update the canvas. Outside-grid samples are gray.')

    def _emit_changed(self, *_):
        if self._loading: return
        try: value = self.settings_value()
        except ValueError as exc:
            self.error.setText(str(exc)); return
        self.error.clear(); self.changed.emit(value)


class FieldMappingDialog(QDialog):
    """Compatibility wrapper; the surface editor embeds FieldMappingWidget."""
    def __init__(self, fields, settings=None, parent=None):
        super().__init__(parent); self.settings = None; self.fields = fields
        self.setWindowTitle('Color surface by another field'); self.resize(650, 400)
        layout = QVBoxLayout(self)
        self.editor = FieldMappingWidget(fields, settings, self); layout.addWidget(self.editor)
        for name in ('source', 'palette', 'automatic', 'minimum', 'maximum', 'legend', 'note', 'min_slider', 'max_slider'):
            setattr(self, name, getattr(self.editor, name))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def update_controls(self, *_): self.editor.update_controls()

    def commit(self):
        try: value = self.editor.settings_value()
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid color mapping', str(exc)); return
        self.settings = value; self.accept()
