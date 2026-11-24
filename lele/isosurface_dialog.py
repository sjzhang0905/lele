"""Independent surface layers with inline, live scalar-color controls."""
from copy import deepcopy
from math import isfinite
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from shiboken6 import isValid
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QComboBox, QCheckBox, QDoubleSpinBox, QDialogButtonBox,
    QHeaderView, QAbstractItemView, QGroupBox, QScrollArea, QWidget)
from .dialog_policy import QDialog, QColorDialog, QMessageBox, ensure_source_current
from .numeric_controls import IsovalueSpinBox
from .color_controls import set_color_swatch, color_value
from .field_mapping import suggested_isovalue


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
    """Changes preview in the owner; the caller restores its snapshot on Cancel."""
    def __init__(self,options,parent=None,*,fields=None,active_index=-1,preview=None):
        super().__init__(parent)
        self.setWindowTitle('Surface layers and color mapping');self.resize(1120,720)
        self.layers=None;self.options=options
        self.fields=list(fields or []);self.active_index=active_index
        self._source_bounds={}
        self._preview=preview;self._building=True;self._preview_busy=False
        self._mapping_row=-1
        self._preview_timer=QTimer(self);self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._apply_preview)
        self.finished.connect(lambda *_:self._preview_timer.stop())
        layout=QVBoxLayout(self)
        note=QLabel('Choose a surface row to edit its color mapping below. Changes update the canvas immediately; '
                    'Cancel restores the original layers. Each signed isovalue uses its source field’s units.')
        note.setWordWrap(True);layout.addWidget(note)
        self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['Show','Signed isovalue','Color','Opacity','Style','','Source field','Color field'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6,QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(150)
        self.table.currentCellChanged.connect(self._select_mapping)
        layout.addWidget(self.table,2)
        from .field_mapping_dialog import FieldMappingWidget
        self.mapping_group=QGroupBox('Color mapping — select a surface layer')
        mapping_layout=QVBoxLayout(self.mapping_group)
        self.mapping_editor=FieldMappingWidget(self.fields,parent=self.mapping_group)
        self.mapping_editor.changed.connect(self._mapping_changed)
        mapping_layout.addWidget(self.mapping_editor)
        self.source_note=QLabel();self.source_note.setWordWrap(True)
        mapping_layout.addWidget(self.source_note)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(self.mapping_group)
        scroll.setMinimumHeight(280);layout.addWidget(scroll,3)
        for layer in (options.volume_surfaces or basic_surface_layers(options)):
            if not options.volume_surfaces and self.fields:layer={**layer,'dataset':active_index}
            self.add_layer(layer)
        row=QHBoxLayout();layout.addLayout(row)
        self.add_button=QPushButton('Add layer');self.add_button.clicked.connect(lambda:self.add_layer())
        row.addWidget(self.add_button)
        self.basic_button=QPushButton('Use basic +/− controls');self.basic_button.clicked.connect(self.use_basic)
        row.addWidget(self.basic_button);row.addStretch(1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.commit);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self._building=False
        if self.table.rowCount():self.table.setCurrentCell(0,1);self._select_mapping(0,1,-1,-1)

    def add_layer(self,layer=None):
        if self.table.rowCount()>=32:
            QMessageBox.information(self,'Layer limit','Use up to 32 layers to keep rendering manageable.');return
        fresh=layer is None
        layer=layer or dict(value=self.options.volume_iso,color=self.options.volume_positive_color,
                            opacity=self.options.volume_opacity,style='Surface',visible=True,dataset=self.active_index)
        row=self.table.rowCount();self.table.insertRow(row)
        enabled=QCheckBox();enabled.setChecked(bool(layer.get('visible',True)))
        value=IsovalueSpinBox();value.setRange(-10000,10000);value.setValue(float(layer['value']))
        value.setMinimumWidth(152)
        value.setToolTip('Signed decimal or scientific isovalue. Zero draws the nodal surface.')
        color=QPushButton();set_color_swatch(color, str(layer.get('color','#80E666')), 'Layer color')
        color.clicked.connect(lambda _,b=color:self.pick_color(b))
        opacity=QDoubleSpinBox();opacity.setRange(0,1);opacity.setDecimals(2);opacity.setSingleStep(.05)
        opacity.setValue(float(layer.get('opacity', self.options.volume_opacity)))
        style=QComboBox();style.addItems(['Surface','Wireframe','Points']);style.setCurrentText(layer.get('style','Surface'))
        remove=QPushButton('Remove');remove.clicked.connect(lambda _,b=remove:self.remove_layer(b))
        for col,widget in enumerate((enabled,value,color,opacity,style,remove)):self.table.setCellWidget(row,col,widget)
        from .field_mapping_dialog import field_title
        source=QComboBox();source.addItem('Active Dataset',-1)
        source.setMinimumContentsLength(18)
        source.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        for i,field in enumerate(self.fields):source.addItem(field_title(i,field),i)
        selection=layer.get('dataset',-1)
        if source.findData(selection)<0:source.addItem(f'Missing field {selection+1}',selection)
        source.setCurrentIndex(source.findData(selection));self.table.setCellWidget(row,6,source)
        mapping=QLabel();mapping.setMargin(4)
        mapping.settings={key:deepcopy(layer[key]) for key in ('map_dataset','map_palette','map_range','map_legend') if key in layer}
        self.mapping_label(mapping);self.table.setCellWidget(row,7,mapping)
        source.currentIndexChanged.connect(lambda _,s=source:self._source_changed(s))
        for signal in (enabled.toggled,value.valueChanged,opacity.valueChanged,style.currentIndexChanged):
            signal.connect(self._schedule_preview)
        if fresh:self._source_changed(source)
        if not self._building:
            self.table.setCurrentCell(row,1);self._select_mapping(row,1,-1,-1);self._schedule_preview()

    def mapping_label(self,widget):
        index=widget.settings.get('map_dataset',-1)
        widget.setText('Uniform color' if index<0 else f'Field {index+1}')
        widget.setToolTip('Select this row to edit the color controls below.')

    def _select_mapping(self,row,*_):
        if self._building:return
        self._mapping_row=row
        valid=0<=row<self.table.rowCount() and self.table.cellWidget(row,7) is not None
        self.mapping_group.setEnabled(valid)
        if not valid:return
        self.mapping_group.setTitle(f'Color mapping — layer {row+1}')
        self.mapping_editor.set_settings(self.table.cellWidget(row,7).settings)
        self._update_source_note(row)

    def edit_mapping(self,widget):
        """Compatibility entry point; select inline controls, never open a popup."""
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,7) is widget:
                self.table.setCurrentCell(row,7);self._select_mapping(row);return

    def _mapping_changed(self,settings):
        row=self._mapping_row
        if not 0<=row<self.table.rowCount():return
        widget=self.table.cellWidget(row,7);widget.settings=deepcopy(settings)
        self.mapping_label(widget);self._schedule_preview()

    def _source_index(self,row):
        index=self.table.cellWidget(row,6).currentData()
        return self.active_index if index<0 else index

    def _source_changed(self,source):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,6) is not source:continue
            index=self._source_index(row)
            if 0<=index<len(self.fields):
                value=self.table.cellWidget(row,1)
                value.setValue(suggested_isovalue(self.fields[index].data,value.value()))
            self.table.setCurrentCell(row,6);self._select_mapping(row)
            self._schedule_preview();return

    def _update_source_note(self,row):
        import numpy as np
        index=self._source_index(row)
        if not 0<=index<len(self.fields):
            self.source_note.setText('Source field is unavailable.');return
        if index not in self._source_bounds:
            data=np.asarray(self.fields[index].data);finite=data[np.isfinite(data)]
            self._source_bounds[index]=(float(finite.min()),float(finite.max())) if finite.size else None
        if self._source_bounds[index] is None:
            self.source_note.setText('Source field contains no finite values.');return
        low,high=self._source_bounds[index];value=self.table.cellWidget(row,1).value()
        warning='' if low<value<high else ' — this level draws no surface; choose an interior value.'
        self.source_note.setText(f'Source range: {low:.6g} to {high:.6g}; isovalue: {value:.6g}'+warning)
        self.source_note.setStyleSheet('color: #b34728;' if warning else '')

    def pick_color(self,button):
        color=QColorDialog.getColor(QColor(color_value(button)),self,'Layer color')
        if color.isValid() and isValid(button):
            set_color_swatch(button,color.name(),'Layer color');self._schedule_preview()

    def remove_layer(self,button):
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row,5) is button:
                self.table.removeRow(row)
                selected=min(row,self.table.rowCount()-1)
                if selected>=0:self.table.setCurrentCell(selected,1)
                self._select_mapping(selected);self._schedule_preview();return

    def _collect_layers(self):
        layers=[]
        for row in range(self.table.rowCount()):
            widgets=[self.table.cellWidget(row,col) for col in range(8)]
            if any(widget is None for widget in widgets):return None
            value=widgets[1].value()
            if not isfinite(value):raise ValueError('Each isovalue must be finite.')
            layer=dict(visible=widgets[0].isChecked(),value=value,color=color_value(widgets[2]),
                       opacity=widgets[3].value(),style=widgets[4].currentText())
            if widgets[6].currentData()!=-1:layer['dataset']=widgets[6].currentData()
            layer.update(deepcopy(widgets[7].settings));layers.append(layer)
        return layers

    def _schedule_preview(self,*_):
        if self._building:return
        if 0<=self._mapping_row<self.table.rowCount():self._update_source_note(self._mapping_row)
        if self._preview is not None:self._preview_timer.start(25)

    def _apply_preview(self):
        if self._preview_busy:
            self._preview_timer.start(25);return
        if not ensure_source_current(self):return
        layers=self._collect_layers()
        if not layers:return
        self._preview_busy=True
        try:self._preview(deepcopy(layers))
        finally:self._preview_busy=False

    def use_basic(self):
        self._preview_timer.stop();self.layers=[];self.accept()

    def commit(self):
        if self.table.rowCount()==0:
            QMessageBox.information(self,'No custom layers','Add a layer, or choose “Use basic +/− controls”. '
                'To hide all custom surfaces, uncheck Show on each row.');return
        for row in range(self.table.rowCount()):self.table.cellWidget(row,1).interpretText()
        if self.mapping_editor.error.text():
            QMessageBox.warning(self,'Invalid color mapping',self.mapping_editor.error.text());return
        try:self.layers=self._collect_layers()
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid level',str(exc));return
        self._preview_timer.stop();self.accept()
