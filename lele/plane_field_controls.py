"""Startup-safe shared controls for HKL and selected-atom field slices."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QWidget,QFormLayout,QHBoxLayout,QCheckBox,
                              QComboBox,QDoubleSpinBox,QSpinBox,QLabel)
from .panel_controls import PanelComboBox
from .numeric_controls import IsovalueSpinBox


class SliceRangeSpinBox(IsovalueSpinBox):
    def __init__(self):
        super().__init__();self.setRange(-1e20,1e20);self.setFixedWidth(140)
        self.setToolTip('Signed decimal or scientific field value, e.g. -0.01 or 1e-5.')

    def textFromValue(self,value):
        return f'{value:.10g}'


class PlaneFieldControls(QWidget):
    valuesChanged = Signal(object)

    def __init__(self, *, include_opacity=False):
        super().__init__();self._loading=False;self._values={};self.include_opacity=include_opacity
        form=QFormLayout(self);form.setContentsMargins(0,0,0,0)
        self.field=QCheckBox('Color plane by active field');self.field.setChecked(True)
        self.field.setToolTip('Samples the active Dataset on this plane; independent of Isosurface signs and Show isosurfaces.')
        form.addRow(self.field)
        self.palette=PanelComboBox();self.palette.addItems(['Auto','Blue-white-red','Viridis']);form.addRow('Slice colors',self.palette)
        self.fixed=QCheckBox('Fixed slice color range');form.addRow(self.fixed)
        self.minimum=SliceRangeSpinBox();self.maximum=SliceRangeSpinBox()
        for spin in (self.minimum,self.maximum):
            spin.setKeyboardTracking(False);spin.setSingleStep(.01)
        self.minimum.setValue(-.1);self.maximum.setValue(.1)
        form.addRow('Slice min',self.minimum);form.addRow('Slice max',self.maximum)
        self.contours=QCheckBox('Slice contour lines');self.legend=QCheckBox('Slice color scale');self.legend.setChecked(True)
        form.addRow(self.contours);form.addRow(self.legend)
        self.resolution=QSpinBox();self.resolution.setRange(16,1024);self.resolution.setValue(256);self.resolution.setKeyboardTracking(False)
        self.resolution.setFixedWidth(90)
        self.resolution.setToolTip('Maximum samples per in-plane axis. Original field values are retained.')
        form.addRow('Slice resolution',self.resolution)
        self.opacity=None
        if include_opacity:
            self.opacity=QDoubleSpinBox();self.opacity.setRange(0.,1.);self.opacity.setDecimals(2)
            self.opacity.setSingleStep(.05);self.opacity.setValue(.22);self.opacity.setKeyboardTracking(False)
            self.opacity.setFixedWidth(90)
            self.opacity.setToolTip('0 = invisible, 1 = opaque. Applies to the plane and its scalar-field slice.')
            form.addRow('Plane opacity',self.opacity);self.opacity.valueChanged.connect(self._edited)
        for check in (self.field,self.fixed,self.contours,self.legend):check.toggled.connect(self._edited)
        self.palette.currentTextChanged.connect(self._edited)
        self.minimum.valueChanged.connect(self._edited);self.maximum.valueChanged.connect(self._edited)
        self.resolution.valueChanged.connect(self._edited)
        self._update_enabled()

    def values(self):
        values=dict(self._values,field=self.field.isChecked(),field_palette=self.palette.currentText(),
            field_range=([self.minimum.value(),self.maximum.value()] if self.fixed.isChecked() else None),
            field_contours=self.contours.isChecked(),field_legend=self.legend.isChecked(),
            field_resolution=self.resolution.value())
        if self.opacity is not None:values['opacity']=self.opacity.value()
        return values

    def set_values(self, values):
        values=values or {}
        self._loading=True;self._values=dict(values)
        self.field.setChecked(values.get('field',True));self.palette.setCurrentText(values.get('field_palette','Auto'))
        limits=values.get('field_range');self.fixed.setChecked(limits is not None)
        if limits is not None:self.minimum.setValue(limits[0]);self.maximum.setValue(limits[1])
        self.contours.setChecked(values.get('field_contours',False));self.legend.setChecked(values.get('field_legend',True))
        self.resolution.setValue(values.get('field_resolution',256))
        if self.opacity is not None:self.opacity.setValue(values.get('opacity',.22))
        self._loading=False;self._update_enabled()

    def _update_enabled(self):
        for widget in (self.palette,self.fixed,self.contours,self.legend,self.resolution):widget.setEnabled(self.field.isChecked())
        self.minimum.setEnabled(self.field.isChecked() and self.fixed.isChecked())
        self.maximum.setEnabled(self.field.isChecked() and self.fixed.isChecked())

    def _edited(self,*_):
        self._update_enabled()
        if not self._loading:self.valuesChanged.emit(self.values())
