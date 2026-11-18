import copy
from pathlib import Path
import numpy as np
from PySide6.QtWidgets import QApplication,QWidget,QFormLayout,QDialog
from lele.field_actions import FieldActions
from lele.isosurface_dialog import IsosurfaceLayersDialog,basic_surface_layers
from lele.render_options import RenderOptions
from lele.core import Document,Frame,Volume

APP=QApplication.instance() or QApplication([])

class Host(FieldActions,QWidget):
    def __init__(self):
        super().__init__();self.doc=None;self.render_options=RenderOptions()
        self._build_field_controls(QFormLayout(self))
    def _set_option(self,key,value):
        setattr(self.render_options,key,value);self.refresh_scene()
    def refresh_scene(self):self._refresh_field_controls()

def test_basic_signed_defaults_and_independent_controls():
    opts=RenderOptions();a,b=basic_surface_layers(opts)
    assert a['value']==.035 and b['value']==-.035
    assert a['color']=='#80E666' and b['color']=='#00C2FF'
    opts.volume_independent_negative=True;opts.volume_negative_iso=.02
    opts.volume_independent_opacity=True;opts.volume_negative_opacity=.3
    assert basic_surface_layers(opts)[1]['value']==-.02
    assert basic_surface_layers(opts)[1]['opacity']==.3

def test_custom_dialog_accept_cancel_and_basic():
    opts=RenderOptions();before=copy.deepcopy(opts)
    dialog=IsosurfaceLayersDialog(opts)
    assert dialog.table.rowCount()==2
    dialog.table.cellWidget(0,1).setValue(.1)
    dialog.reject();assert opts==before
    dialog=IsosurfaceLayersDialog(opts)
    dialog.table.cellWidget(0,1).setValue(-.007)
    dialog.table.cellWidget(0,4).setCurrentText('Wireframe')
    dialog.table.cellWidget(1,0).setChecked(False)
    dialog.commit()
    assert dialog.result()==QDialog.DialogCode.Accepted
    assert dialog.layers[0]['value']==-.007
    assert dialog.layers[0]['style']=='Wireframe'
    assert dialog.layers[0]['color'].lower()==opts.volume_positive_color.lower()
    assert dialog.layers[1]['color'].lower()==opts.volume_negative_color.lower()
    assert dialog.layers[1]['visible'] is False
    assert opts.volume_surfaces==[]
    dialog.use_basic();assert dialog.layers==[]

def test_layer_add_remove_zero_and_ui_restore():
    opts=RenderOptions();dialog=IsosurfaceLayersDialog(opts)
    dialog.add_layer(dict(value=0,color='#123456',opacity=.2,visible=True,style='Points'))
    dialog.remove_layer(dialog.table.cellWidget(0,5));dialog.commit()
    assert len(dialog.layers)==2 and dialog.layers[-1]['value']==0
    assert dialog.layers[-1]['color']=='#123456'
    host=Host();host._refresh_field_controls()
    assert not host.slice_button.isEnabled()
    v=Volume(np.indices((3,3,3))[0]-1.,[0,0,0],np.eye(3))
    host.doc=Document(Path('test.cube'),'test',[Frame(['H'],[[0,0,0]])],v)
    host.render_options.volume_surfaces=dialog.layers
    host._refresh_field_controls()
    # None remains available as a master hide even with independent layers.
    assert host.field_signs.isEnabled()
    assert host.field_signs.findText('None')>=0
    assert not host.negative_independent.isEnabled()
    assert host.slice_button.isEnabled() and host.field_export_button.isEnabled()
    assert 'active dataset' in host.layers_note.text()
    host.render_options=RenderOptions(volume_independent_negative=True,volume_negative_iso=.08)
    host._refresh_field_controls()
    assert host.negative_independent.isChecked()
    assert host.negative_iso.value()==.08 and host.negative_iso.isEnabled()
    host.doc.volume=None;host._refresh_field_controls()
    assert not host.slice_button.isEnabled() and not host.field_export_button.isEnabled()
    host.close()

def test_layers_project_roundtrip_and_old_defaults(tmp_path):
    from lele.project_file import save_project,load_project
    import zipfile,json
    doc=Document(Path('test.cube'),'test',[Frame(['H'],[[0,0,0]])])
    options=RenderOptions(volume_independent_negative=True,volume_negative_iso=.17,
        volume_positive_color='#112233',volume_negative_color='#445566',
        volume_surfaces=[dict(value=.1,color='#778899',opacity=.3,style='Wireframe',visible=True)])
    state=dict(documents=[dict(document=doc,options=options,frame_index=0)],current_document=0,selection=[])
    file=tmp_path/'layers.lele';save_project(file,state)
    restored=load_project(file)['documents'][0]['options'];assert restored==options
    with zipfile.ZipFile(file) as z:payload={name:z.read(name) for name in z.namelist()}
    manifest=json.loads(payload['manifest.json'])
    added=['volume_independent_negative','volume_negative_iso','volume_positive_color','volume_negative_color',
           'volume_independent_opacity','volume_negative_opacity','volume_representation','volume_line_width',
           'volume_smooth_normals','volume_surfaces']
    for node in manifest['nodes']:
        if node.get('type')=='lele.render_options:RenderOptions':
            for name in added:node['attributes'].pop(name,None)
    payload['manifest.json']=json.dumps(manifest).encode()
    old=tmp_path/'old.lele'
    with zipfile.ZipFile(old,'w') as z:
        for name,data in payload.items():z.writestr(name,data)
    legacy=load_project(old)['documents'][0]['options']
    assert legacy.volume_surfaces==[] and legacy.volume_positive_color=='#80E666'
    assert not legacy.volume_independent_negative

def test_color_swatches_edit_and_restore_without_hex_labels(monkeypatch):
    from PySide6.QtGui import QColor
    from lele.dialog_policy import QColorDialog
    from lele.color_controls import color_value
    from lele.crystal_panel import LatticePlanePanel,PolyhedraPanel

    dialog=IsosurfaceLayersDialog(RenderOptions())
    button=dialog.table.cellWidget(0,2)
    assert button.text()=='' and button.width()==button.height()==26
    initial=[]
    def pick(color,*args):
        initial.append(color.name())
        return QColor('#439ea5')
    monkeypatch.setattr(QColorDialog,'getColor',pick)
    dialog.pick_color(button);dialog.commit()
    assert initial==['#80e666']
    assert dialog.layers[0]['color']=='#439ea5'
    assert color_value(button)=='#439ea5' and button.text()==''

    planes=LatticePlanePanel();planes.add_plane();planes.choose_color()
    assert planes.selected_plane()['color']=='#439ea5'
    planes.set_values(planes.records)
    assert color_value(planes.color)=='#439ea5' and planes.color.text()==''
    polyhedra=PolyhedraPanel();polyhedra.choose_edge_color()
    assert polyhedra.values()['polyhedra_edge_color']=='#439ea5'
    polyhedra.set_values(RenderOptions(polyhedra_edge_color='#123456'))
    assert color_value(polyhedra.edge_color)=='#123456'
    assert polyhedra.edge_color.text()==''

    host=Host();host.render_options.volume_positive_color='#439ea5';host._refresh_field_controls()
    assert color_value(host.positive_color)=='#439ea5' and host.positive_color.text()==''
    assert host.positive_color.width()==host.positive_color.height()==26
    for widget in (dialog,planes,polyhedra,host):widget.close()

def test_empty_custom_commit_does_not_silently_restore_basic(monkeypatch):
    from lele.dialog_policy import QMessageBox
    notices=[];monkeypatch.setattr(QMessageBox,'information',lambda *args:notices.append(args))
    dialog=IsosurfaceLayersDialog(RenderOptions())
    dialog.table.setRowCount(0);dialog.commit()
    assert dialog.layers is None and dialog.result()!=QDialog.DialogCode.Accepted
    assert notices
