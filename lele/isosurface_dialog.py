"""Edit independent signed isosurface layers without changing the source field."""
from math import isfinite
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QComboBox, QCheckBox, QDoubleSpinBox, QColorDialog,
    QDialogButtonBox, QMessageBox, QHeaderView)
from .numeric_controls import IsovalueSpinBox


def basic_surface_layers(options):
    """Mirror the signed basic settings; values stay in source field units."""
    layers=[]
    for negative, sign in ((False,'Positive'), (True,'Negative')):
        if options.volume_signs not in ('Both',sign):continue
        magnitude=(options.volume_negative_iso if negative and options.volume_independent_negative else options.volume_iso)
        layers.append(dict(value=-abs(magnitude) if negative else abs(magnitude),
            color=options.volume_negative_color if negative else options.volume_positive_color,
            opacity=options.volume_negative_opacity if negative and options.volume_independent_opacity else options.volume_opacity,
            style=options.volume_representation,visible=True))
    return layers


class IsosurfaceLayersDialog(QDialog):
    """Accepted result replaces layer settings; cancellation leaves them intact."""
    def __init__(self,options,parent=None,*,fields=None,active_index=-1):
        super().__init__(parent)
        self.setWindowTitle('Surface layers and color mapping');self.resize(1120,480)
        self.layers=None;self.options=options
        self.fields=list(fields or []);self.active_index=active_index
        layout=QVBoxLayout(self)
        note=QLabel('Each row is a signed isovalue in its source field’s units. '
                    'Custom layers replace the basic +/− controls. Out-of-range levels draw no surface. '
                    'Choose different source fields to overlay surfaces; Color mapping applies another field to a surface (for example ESP on density). '
                    'No data smoothing or density normalization is performed.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['Show','Signed isovalue','Color','Opacity','Style','','Source field','Color mapping'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table,1)
        for layer in (options.volume_surfaces or basic_surface_layers(options)):
            # Newly promoted basic layers bind to the current source. Legacy
            # custom layers without a dataset keep their active-field behavior.
            if not options.volume_surfaces and self.fields:layer={**layer,'dataset':active_index}
            self.add_layer(layer)
        row=QHBoxLayout();layout.addLayout(row)
        self.add_button=QPushButton('Add layer');self.add_button.clicked.connect(lambda:self.add_layer())
        row.addWidget(self.add_button)
        self.basic_button=QPushButton('Use basic +/− controls');self.basic_button.clicked.connect(self.use_basic)
        row.addWidget(self.basic_button);row.addStretch(1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def add_layer(self,layer=None):
        if self.table.rowCount()>=32:
            QMessageBox.information(self,'Layer limit','Use up to 32 layers to keep rendering manageable.');return
        layer=layer or dict(value=self.options.volume_iso,color=self.options.volume_positive_color,
                            opacity=self.options.volume_opacity,style='Surface',visible=True,dataset=self.active_index)
        row=self.table.rowCount();self.table.insertRow(row)
        enabled=QCheckBox();enabled.setChecked(bool(layer.get('visible',True)))
        value=IsovalueSpinBox();value.setRange(-10000,10000);value.setValue(float(layer['value']))
        value.setToolTip('Signed decimal or scientific isovalue. Zero draws the nodal surface.')
        color=QPushButton(str(layer.get('color','#EC6B46')));self._color_style(color)
        color.clicked.connect(lambda _,b=color:self.pick_color(b))
        opacity=QDoubleSpinBox();opacity.setRange(0,1);opacity.setDecimals(2);opacity.setSingleStep(.05)
        opacity.setValue(float(layer.get('opacity',.65)))
        style=QComboBox();style.addItems(['Surface','Wireframe','Points']);style.setCurrentText(layer.get('style','Surface'))
        remove=QPushButton('Remove');remove.clicked.connect(lambda _,b=remove:self.remove_layer(b))
        for col,widget in enumerate((enabled,value,color,opacity,style,remove)):self.table.setCellWidget(row,col,widget)
        from .field_mapping_dialog import field_title
        source=QComboBox();source.addItem('Active Dataset',-1)
        for i,field in enumerate(self.fields):source.addItem(field_title(i,field),i)
        selection=layer.get('dataset',-1)
        if source.findData(selection)<0:source.addItem(f'Missing field {selection+1}',selection)
        source.setCurrentIndex(source.findData(selection));self.table.setCellWidget(row,6,source)
        mapping=QPushButton();mapping.settings={key:layer[key] for key in ('map_dataset','map_palette','map_range','map_legend') if key in layer}
        self.mapping_label(mapping);mapping.clicked.connect(lambda _,b=mapping:self.edit_mapping(b))
        self.table.setCellWidget(row,7,mapping)

    def mapping_label(self,button):
        index=button.settings.get('map_dataset',-1)
        button.setText('Uniform color…' if index<0 else f'Field {index+1} colors…')

    def edit_mapping(self,button):
        from .field_mapping_dialog import FieldMappingDialog
        dialog=FieldMappingDialog(self.fields,button.settings,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            button.settings=dialog.settings;self.mapping_label(button)

    @staticmethod
    def _color_style(button):
        color=QColor(button.text())
        if color.isValid():button.setStyleSheet('border: 3px solid '+color.name()+'; padding: 3px;')

    def pick_color(self,button):
        color=QColorDialog.getColor(QColor(button.text()),self,'Layer color')
        if color.isValid():button.setText(color.name());self._color_style(button)

    def remove_layer(self,button):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,5) is button:self.table.removeRow(row);return

    def use_basic(self):
        self.layers=[];self.accept()

    def commit(self):
        if self.table.rowCount()==0:
            QMessageBox.information(self,'No custom layers',
                'Add a layer, or choose “Use basic +/− controls” to return to the basic surfaces. '
                'To hide all custom surfaces, uncheck Show on each row.')
            return
        layers=[]
        for row in range(self.table.rowCount()):
            widgets=[self.table.cellWidget(row,col) for col in range(8)]
            widgets[1].interpretText();value=widgets[1].value()
            if not isfinite(value):
                QMessageBox.warning(self,'Invalid level','Each isovalue must be finite.');return
            layer=dict(visible=widgets[0].isChecked(),value=value,color=widgets[2].text(),
                       opacity=widgets[3].value(),style=widgets[4].currentText())
            if widgets[6].currentData()!=-1:layer['dataset']=widgets[6].currentData()
            layer.update(widgets[7].settings)
            layers.append(layer)
        self.layers=layers;self.accept()
