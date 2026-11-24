"""Regression coverage for inline ESP controls and independent density layers."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QWidget, QDialog, QLabel
from PySide6.QtTest import QTest
from PySide6.QtCore import QCoreApplication, QEvent
from lele.core import Volume, Document, Frame
from lele.render_options import RenderOptions
from lele.field_mapping import mapping_limits, suggested_isovalue, validate_layer_mapping
from lele.field_mapping_dialog import FieldMappingWidget
from lele.isosurface_dialog import IsosurfaceLayersDialog
from lele.surface_rendering import color_lookup, update_mapping_colors

@pytest.fixture(scope='module')
def app():
    application=QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(autouse=True)
def clean_widgets(app):
    import gc
    before={id(widget) for widget in app.topLevelWidgets()}
    yield
    for widget in app.topLevelWidgets():
        if id(widget) not in before:
            widget.close();widget.deleteLater()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents();gc.collect()


def fields():
    data=np.linspace(0,.02,5**3).reshape((5,)*3)
    return [Volume(data,[0,0,0],np.eye(3),name,'e/Bohr³') for name in ('electron','hole')]


def test_vmd_primary_colors_and_midpoint_do_not_require_zero():
    lut=color_lookup('VMD RWB',(2.,8.))
    np.testing.assert_allclose(lut.GetColor(2.),[1,0,0])
    np.testing.assert_allclose(lut.GetColor(5.),[1,1,1])
    np.testing.assert_allclose(lut.GetColor(8.),[0,0,1])
    reverse=color_lookup('VMD BWR',(-2.,4.))
    np.testing.assert_allclose(reverse.GetColor(1.),[1,1,1])
    assert mapping_limits({'map_palette':'VMD RWB'},[.1,.2],[-5,12])==(-5.,12.)
    assert mapping_limits({'map_palette':'VMD RWB','map_range':[2,8]},[.1])==(2.,8.)
    validate_layer_mapping({'map_palette':'VMD RWB','map_range':[2,8]})
    with pytest.raises(ValueError):
        validate_layer_mapping({'map_palette':'Red-white-blue','map_range':[2,8]})


def test_positive_density_source_gets_an_interior_positive_level():
    data=fields()[0].data
    assert suggested_isovalue(data,-.005)==.005
    assert suggested_isovalue(data,-.035)==pytest.approx(.002)
    assert suggested_isovalue(data,.003)==.003
    signed=np.linspace(-1,2,50)
    assert suggested_isovalue(signed,-.5)==-.5


def test_source_switch_recovers_second_layer_and_exposes_both_rows(app):
    dialog=IsosurfaceLayersDialog(RenderOptions(),fields=fields(),active_index=0)
    dialog.show();app.processEvents()
    assert dialog.table.rowCount()==2
    assert dialog.table.rowHeight(1)>=36
    second_source=dialog.table.cellWidget(1,6)
    assert dialog.table.cellWidget(1,1).value()<0
    second_source.setCurrentIndex(second_source.findData(1))
    assert dialog.table.cellWidget(1,1).value()==pytest.approx(.002)
    assert dialog._mapping_row==1
    assert isinstance(dialog.table.cellWidget(1,7),QLabel)
    assert 'no surface' not in dialog.source_note.text()
    dialog.close()


def test_inline_controls_update_live_from_numbers_and_sliders():
    calls=[]
    dialog=IsosurfaceLayersDialog(RenderOptions(),fields=fields(),active_index=0,preview=calls.append)
    editor=dialog.mapping_editor
    editor.source.setCurrentIndex(editor.source.findData(1))
    editor.minimum.setText('.002')
    editor.maximum.setText('.015')
    QTest.qWait(50)
    assert calls[-1][0]['map_range']==[.002,.015]
    assert calls[-1][0]['map_palette']=='VMD RWB'
    editor.min_slider.setValue(2000)
    QTest.qWait(50)
    assert calls[-1][0]['map_range'][0]==pytest.approx(.004)
    assert not editor.automatic.isChecked()
    assert calls[-1][0]['map_range'][1]==.015
    dialog.reject()


def test_invalid_numeric_edit_does_not_push_an_invalid_range():
    widget=FieldMappingWidget(fields(),{'map_dataset':0,'map_range':[.002,.018]})
    changes=[];widget.changed.connect(changes.append)
    widget.minimum.setText('.02')
    assert not changes and widget.error.text()
    widget.minimum.setText('.004')
    assert changes[-1]['map_range']==[.004,.018] and not widget.error.text()
    widget.close()


def test_recolor_reuses_mesh_and_material_follows_main_finish():
    from test_field_mapping_v340 import analytic_pair, draw_pair, options
    doc=analytic_pair();opts=options()
    opts.surface_finish='Matte'
    opts.volume_surfaces[0]['map_palette']='VMD RWB'
    draw,_=draw_pair(doc,opts)
    actor=draw.field_actors[0];mapper=actor.GetMapper();poly=mapper.GetInput()
    before=deepcopy(opts.volume_surfaces);after=deepcopy(before)
    after[0]['map_range']=[-.1,.3]
    assert update_mapping_colors(draw,before,after)
    assert actor is draw.field_actors[0] and mapper.GetInput() is poly
    np.testing.assert_allclose(mapper.GetLookupTable().GetColor(.1),[1,1,1])
    assert actor.GetProperty().GetSpecular()==pytest.approx(.05 * 47 / 50)
    assert draw.field_scalar_bars[0].GetTitle()=='Hartree'
    assert 'Layer' not in draw.field_scalar_bars[0].GetTitle()
    after[0]['value']*=2
    assert not update_mapping_colors(draw,before,after)


def test_out_of_range_layer_has_explicit_warning():
    from test_field_mapping_v340 import analytic_pair, draw_pair, options
    doc=analytic_pair();opts=options();opts.volume_surfaces[0]['value']=1e5
    draw,_=draw_pair(doc,opts)
    assert not draw.field_actors
    assert any('Layer 1:' in warning and 'outside source range' in warning for warning in draw.field_warnings)


def test_cancel_restores_originating_options_even_after_document_switch(monkeypatch):
    from lele.field_actions import FieldActions
    class Host(FieldActions,QWidget):
        def __init__(self):
            super().__init__();self.render_options=RenderOptions();self.renderer=None
            self.doc=Document(Path('density.cube'),'density',[Frame(['H'],[[0,0,0]])],fields()[0])
        def _set_surface_option(self,key,value):setattr(self.render_options,key,value)
    host=Host();origin=host.render_options;original=deepcopy(origin.volume_surfaces)
    def run(dialog):
        layers=dialog._collect_layers();dialog._preview(layers)
        assert origin.volume_surfaces==layers
        host.doc=Document(Path('other.xyz'),'other',[Frame(['He'],[[0,0,0]])])
        host.render_options=RenderOptions()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(IsosurfaceLayersDialog,'exec',run)
    host._edit_surface_layers()
    assert origin.volume_surfaces==original
    assert host.render_options.volume_surfaces==[]
    host.close()
