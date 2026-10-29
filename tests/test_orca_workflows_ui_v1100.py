"""Actual result navigation, sortable ensemble rows and complex SOC UI."""
from pathlib import Path
from unittest.mock import patch
import csv
import numpy as np
from PySide6.QtCore import Qt
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


def attach(gui,name):
    w=gui.window;d=load_document(EXAMPLES/name)
    w.documents=[d];w.current_doc=0;w.frame_index=0;w.selection=[];w.files_tree.clear()
    w._add_document_tree(0,d);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w,d


def test_path_and_image_history_navigation_use_distinct_sequences(gui):
    w,d=attach(gui,'synthetic_neb_v1100.out');dialog=w.show_neb_results();gui.app.processEvents()
    linked=[i for i,p in enumerate(d.neb_runs[0].profiles) if p.source.endswith('.NEB.log')]
    dialog.profile.setCurrentIndex(linked[0]);dialog.table.setCurrentCell(1,0)
    assert w.frame.info['neb_image']==1 and w.frame.info['neb_iteration']==0
    assert w.frame_spin.maximum()==4
    w._step_next();assert w.frame.info['neb_image']==2 and w.frame.info['neb_iteration']==0
    dialog.view.setCurrentIndex(1);dialog.image.setCurrentIndex(1);dialog.table.setCurrentCell(0,0)
    assert w.frame.info['neb_image']==1 and w.frame_spin.maximum()==2
    w._step_next();assert w.frame.info['neb_image']==1 and w.frame.info['neb_iteration']==1
    w.frame_spin.setValue(1);assert w.frame.info['neb_iteration']==0
    assert dialog.grab().width()>800


def test_stage_curve_never_connects_endpoint_and_ts_steps(gui):
    w,d=attach(gui,'synthetic_neb_v1100.out');curve=w.show_energy_curve()
    assert curve.stage_combo.count()==3
    for i in range(curve.stage_combo.count()):
        curve.stage_combo.setCurrentIndex(i);points=curve.points()
        assert len({d.frames[p['frame']].info['stage_index'] for p in points})==1
    overview=w.show_calculation_overview()
    assert overview.stage_table.item(1,2).text()=='Not converged (cycle limit)'


def test_replacing_workflow_tree_with_single_geometry_drops_old_item_links(gui):
    w,_=attach(gui,'synthetic_goat_v1100.out')
    w.change_frame(0)
    w,d=attach(gui,'synthetic_soc_v1100.out')
    assert w.frame is d.frames[0] and w.files_tree.currentItem() is w.files_tree.topLevelItem(0)


def test_neb_gif_uses_only_active_image_history(gui,tmp_path):
    from lele.animation_export import GifSettings
    w,d=attach(gui,'synthetic_neb_v1100.out')
    profiles=[p for p in d.neb_runs[0].profiles if p.source.endswith('.NEB.log')]
    indices=[p.frame_indices[1] for p in profiles]
    w._jump_to_result_sequence(d,indices[0],indices,'Image 1 history')
    received=[]
    def capture(path,doc,*args,**kwargs):received.extend(doc.frames)
    with patch('lele.animation_export.export_animation_gif',side_effect=capture):
        assert w._save_gif_file(tmp_path/'history.gif',GifSettings(first_frame=1,last_frame=2))
    assert len(received)==2 and all(f.info['neb_image']==1 for f in received)


def test_goat_sorting_keeps_conformer_ids_temperature_and_frame_links(gui,tmp_path):
    w,d=attach(gui,'synthetic_goat_v1100.out');dialog=w.show_goat_results()
    dialog.table.sortItems(1,Qt.SortOrder.DescendingOrder);dialog.table.setCurrentCell(0,0)
    assert w.frame.info['goat_conformer']==3 and w.frame_spin.maximum()==4
    old=dialog.rows[-1][5];dialog.temperature.setValue(900)
    assert dialog.rows[-1][5]>old
    assert dialog.grab().width()>800


def test_soc_complex_components_mixed_states_and_single_csv(gui,tmp_path):
    w,d=attach(gui,'synthetic_soc_v1100.out');dialog=w.show_soc_results()
    assert dialog.table.rowCount()==3 and dialog.states.rowCount()==2
    dialog.states.setCurrentCell(0,0);dialog.state_selected();assert dialog.details.rowCount()==2
    dialog.component.setCurrentText('Im X');dialog.unit.setCurrentIndex(1)
    assert np.isclose(float(dialog.table.item(0,4).text()),4*1239.841984332/1.e7)
    output=tmp_path/'soc.csv'
    with patch('lele.orca_analysis_dialogs.QFileDialog.getSaveFileName',return_value=(str(output),'')) as choose:
        dialog.export_data();assert choose.call_count==1
    rows=list(csv.DictReader(output.open(encoding='utf-8-sig')))
    assert {r['record'] for r in rows}=={'coupling','mixed_state','SOC_absorption'}
    assert dialog.grab().width()>800
