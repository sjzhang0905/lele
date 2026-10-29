"""Real Qt buttons, frontier units, energy-only points and CSV navigation."""
from pathlib import Path
from shutil import copy2
from unittest.mock import patch
from types import SimpleNamespace
import csv
import numpy as np
from ase.units import Hartree
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


def attach(gui,path):
    w=gui.window;d=load_document(path)
    w.documents=[d];w.current_doc=0;w.frame_index=0;w.selection=[];w.files_tree.clear()
    w._add_document_tree(0,d);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w,d


def test_frontiers_open_only_on_button_click_and_keep_source_labels_and_units(gui):
    w,d=attach(gui,EXAMPLES/'synthetic_xtb_v1110.out')
    assert not w._analysis_windows and w.orbital_btn.isEnabled()
    w.orbital_btn.click();dialog=w._analysis_windows[-1]
    assert dialog.unit.currentText()=='eV'
    assert dialog.summary.item(0,1).text()=='2' and dialog.summary.item(0,3).text()=='3'
    assert float(dialog.summary.item(0,5).text())==1.632683
    dialog.unit.setCurrentText('Hartree')
    assert np.isclose(float(dialog.summary.item(0,2).text()),-8.1634/Hartree,atol=1e-6)
    assert 'explicit source' in dialog.note.text() and dialog.grab().width()>700


def test_curve_cycle_pick_changes_to_the_matched_structure(gui):
    w,d=attach(gui,EXAMPLES/'synthetic_xtb_v1110.out');curve=w.show_energy_curve()
    assert len(curve.points())==3 and curve.unit.currentText()=='kcal/mol'
    line=curve.energy_axes.lines[0]
    np.testing.assert_allclose(line.get_xdata(),[1,2,3])
    event=SimpleNamespace(artist=line,ind=[1])
    curve.canvas.callbacks.process('pick_event',event)
    assert w.frame_index==1 and w.frame is d.frames[1]
    assert len(curve.figure.axes)==1 and not curve.metric_combo.isVisible()


def test_energy_only_cycles_stay_visible_and_do_not_jump_to_final_geometry(gui,tmp_path):
    source=EXAMPLES/'synthetic_xtb_v1110.out';p=tmp_path/source.name;copy2(source,p)
    w,d=attach(gui,p);curve=w.show_energy_curve()
    assert [r['frame'] for r in curve.points()]==[None,None,0]
    assert len(curve.energy_axes.lines[0].get_xdata())==3
    with patch.object(w,'_jump_to_result_frame') as jump:
        curve.pick_point(SimpleNamespace(artist=curve.energy_axes.lines[0],ind=[0]));jump.assert_not_called()
        assert 'No matched geometry' in curve.note.text()
        curve.pick_point(SimpleNamespace(artist=curve.energy_axes.lines[0],ind=[2]));jump.assert_called_once_with(d,0)


def test_curve_csv_keeps_all_cycles_blank_missing_frames_and_absolute_energy(gui,tmp_path):
    w,d=attach(gui,EXAMPLES/'synthetic_gxtb_v1110.out');curve=w.show_energy_curve()
    output=tmp_path/'energy.csv'
    with patch('lele.convergence_dialog.QFileDialog.getSaveFileName',return_value=(str(output),'')):
        curve.export_data()
    rows=list(csv.DictReader(output.open(encoding='utf-8-sig')))
    assert len(rows)==2 and rows[0]['geometry_frame']=='' and rows[1]['geometry_frame']=='1'
    assert float(rows[0]['energy_Eh'])==-20 and float(rows[1]['energy_Eh'])==-20.100000000123


def test_gxtb_channel_rows_and_missing_initial_eigenvalues_are_explicit(gui):
    w,d=attach(gui,EXAMPLES/'synthetic_gxtb_v1110.out');dialog=w.show_orbital_energies()
    assert dialog.summary.rowCount()==2
    assert [dialog.summary.item(i,0).text() for i in range(2)]==['Alpha','Beta']
    assert [float(dialog.summary.item(i,5).text()) for i in range(2)]==[8.1634,6.2586]
    assert '8.163415807' in dialog.note.text()
    dialog.calculation.setCurrentIndex(0)
    assert dialog.summary.rowCount()==0 and '7.000000000' in dialog.note.text()


def test_raw_trajectory_exposes_energy_and_playback_without_inventing_orbitals(gui):
    w,d=attach(gui,EXAMPLES/'synthetic_xtb_v1110.xtbopt.log')
    assert not w.orbital_btn.isEnabled() and w.frame_spin.maximum()==3
    w._step_next();assert w.frame_index==1
    curve=w.show_energy_curve()
    assert len(curve.points())==3 and curve.energy_axes.get_xlabel()=='Trajectory record'
