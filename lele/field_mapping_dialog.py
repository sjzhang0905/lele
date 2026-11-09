"""Choose an existing scalar grid and its displayed color scale."""
from copy import deepcopy
from PySide6.QtWidgets import (QDialog,QFormLayout,QComboBox,QCheckBox,QLineEdit,
                              QLabel,QDialogButtonBox,QMessageBox)
from .field_mapping import PALETTES,validate_layer_mapping


def field_title(index,field):
    return f'{index+1} · {field.label or "Field"} [{field.unit or "source units"}]'


class FieldMappingDialog(QDialog):
    def __init__(self,fields,settings=None,parent=None):
        super().__init__(parent);self.settings=None;self.fields=fields
        self.setWindowTitle('Color surface by another field');self.resize(610,360)
        settings=deepcopy(settings or {})
        layout=QFormLayout(self)
        self.source=QComboBox();self.source.addItem('Uniform layer color',-1)
        for i,field in enumerate(fields):self.source.addItem(field_title(i,field),i)
        self.source.setCurrentIndex(max(0,self.source.findData(settings.get('map_dataset',-1))))
        layout.addRow('Color field',self.source)
        self.palette=QComboBox();self.palette.addItems(PALETTES)
        self.palette.setCurrentText(settings.get('map_palette','Red-white-blue'))
        layout.addRow('Palette (low → high)',self.palette)
        self.automatic=QCheckBox('Automatic symmetric range from surface samples')
        self.automatic.setChecked(settings.get('map_range') is None);layout.addRow(self.automatic)
        low,high=settings.get('map_range') or (-.05,.05)
        self.minimum=QLineEdit(f'{low:.12g}');self.maximum=QLineEdit(f'{high:.12g}')
        layout.addRow('Min (color-field units)',self.minimum);layout.addRow('Max (color-field units)',self.maximum)
        self.legend=QCheckBox('Show color scale');self.legend.setChecked(settings.get('map_legend',True));layout.addRow(self.legend)
        self.note=QLabel();self.note.setWordWrap(True);layout.addRow(self.note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit);buttons.rejected.connect(self.reject);layout.addRow(buttons)
        self.automatic.toggled.connect(self.update_controls);self.source.currentIndexChanged.connect(self.update_controls)
        self.update_controls()

    def update_controls(self,*_):
        mapped=self.source.currentData()>=0
        self.minimum.setEnabled(mapped and not self.automatic.isChecked())
        self.maximum.setEnabled(mapped and not self.automatic.isChecked())
        for control in (self.palette,self.automatic,self.legend):control.setEnabled(mapped)
        index=self.source.currentData()
        unit=(self.fields[index].unit or 'source units') if mapped else 'source units'
        self.note.setText(f'Values are sampled at the surface vertices in {unit}. '
            'Different grid spacings and oblique grids are supported. Outside-grid samples are gray. '
            'Red-white-blue uses red below zero, white at zero and blue above zero; fixed diverging ranges must span zero. '
            'Import an ESP/potential grid to display ESP. This does not calculate electrostatic potential.')

    def commit(self):
        value=dict(map_dataset=self.source.currentData(),map_palette=self.palette.currentText(),map_legend=self.legend.isChecked(),map_range=None)
        try:
            if value['map_dataset']>=0 and not self.automatic.isChecked():
                value['map_range']=[float(self.minimum.text()),float(self.maximum.text())]
            validate_layer_mapping(value)
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid color mapping',str(exc));return
        self.settings=value;self.accept()
