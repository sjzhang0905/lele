"""Energy/geometry data load independently without phantom structures or curves."""
from pathlib import Path
from shutil import copy2
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from ase.units import Hartree
from lele.core import Document
from lele.formats import load_document
from lele.result_availability import has_curve_data
from test_periodic_fragment_ui_v171 import gui

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'
ENERGY=EXAMPLES/'synthetic_xtb_energy_only_v1111.out'
GEOMETRY=EXAMPLES/'synthetic_xtb_geometry_only_v1111.xyz'


def attach(gui,path):
    w=gui.window;d=load_document(path)
    w.documents=[d];w.current_doc=0;w.frame_index=0;w.selection=[];w.files_tree.clear()
    w._add_document_tree(0,d);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w,d


def test_energy_only_document_has_no_geometry_and_does_not_require_companion():
    d=load_document(ENERGY)
    assert d.frames==[] and has_curve_data(d)
    assert len(d.calculation_results.steps)==3
    assert all(s.geometry is None and s.frame_index is None for s in d.calculation_results.steps)
    np.testing.assert_allclose([s.energy_ev/Hartree for s in d.calculation_results.steps],[-10,-10.05,-10.1])


def test_nearby_trajectory_cannot_supply_coordinates_not_present_in_energy_only_file(tmp_path):
    p=tmp_path/ENERGY.name;copy2(ENERGY,p)
    copy2(EXAMPLES/'synthetic_xtb_v1110.xtbopt.log',tmp_path/'xtbopt.log')
    assert load_document(p).frames==[]


def test_structure_only_document_keeps_frames_without_energy_or_curve():
    d=load_document(GEOMETRY)
    assert len(d.frames)==3 and not has_curve_data(d)
    assert all(f.energy_ev is None for f in d.frames)
    assert all(s.energy_ev is None for s in d.calculation_results.steps)
    assert not d.calculation_results.orbitals


def test_single_point_energy_without_geometry_is_a_real_result(tmp_path):
    p=tmp_path/'single.out';p.write_text(' * xtb version 6.7.0\n | TOTAL ENERGY -5.0 Eh |\n')
    d=load_document(p)
    assert d.frames==[] and has_curve_data(d)
    assert d.calculation_results.jobs[0].energy_ev/Hartree==-5


def test_energy_only_page_has_no_frame_coordinates_or_3d_view(gui):
    w,d=attach(gui,ENERGY)
    assert w.frame is None and w.canvas_stack.currentWidget() is w.results_only_page
    assert w.frame_count_label.text()=='No structure' and w.frame_spin.value()==0
    assert w.atom_table.rowCount()==0 and not w.play_btn.isEnabled() and not w.gif_action.isEnabled()
    assert w.energy_curve_action.isEnabled() and w.results_energy_button.isEnabled()
    assert 'Total energy:' in w.results_only_info.toPlainText()
    assert 'Atoms:' not in w.info_view.toPlainText()
    group=w.files_tree.topLevelItem(0).child(0)
    assert group.childCount()==3 and 'energies without coordinates' in group.text(0)
    assert w.results_only_page.grab().width()>400


def test_energy_only_plot_keeps_all_points_and_never_jumps_to_a_structure(gui):
    w,d=attach(gui,ENERGY);curve=w.show_energy_curve()
    assert len(curve.points())==3 and all(r['frame'] is None for r in curve.points())
    with patch.object(w,'_jump_to_result_frame') as jump:
        for i in range(3):curve.pick_point(SimpleNamespace(artist=curve.energy_axes.lines[0],ind=[i]))
        jump.assert_not_called()
    overview=w.show_calculation_overview()
    assert 'No structure' in overview.header.text()
    assert float(overview.table.item(0,6).text())<0


def test_structure_only_page_disables_empty_curve_but_keeps_navigation(gui):
    w,d=attach(gui,GEOMETRY)
    assert w.frame is d.frames[0] and w.canvas_stack.currentWidget() is w.structure_page
    assert not w.energy_curve_action.isEnabled() and not w.orbital_btn.isEnabled()
    assert w.show_energy_curve() is None and not w._analysis_windows
    assert not any('Energy:' in line for line in w.info_view.toPlainText().splitlines())
    w._step_next();assert w.frame_index==1


def test_switching_documents_does_not_reuse_previous_geometry_or_energy(gui):
    w,d=attach(gui,GEOMETRY)
    w._open_path_now(ENERGY);assert w.frame is None and w.canvas_stack.currentWidget() is w.results_only_page
    w.toggle_play();w._step_next();assert not w.playback.isActive()
    w._open_path_now(GEOMETRY)
    assert w.frame is not None and w.frame.energy_ev is None
    assert w.canvas_stack.currentWidget() is w.structure_page and not w.energy_curve_action.isEnabled()


def test_energy_only_can_load_without_constructing_the_native_canvas(gui):
    w=gui.window
    with patch.object(w,'renderer',None),patch.object(w,'vtk',None),patch.object(w,'_ensure_3d_view',side_effect=AssertionError('3D should not be requested')):
        attach(gui,ENERGY)
    assert w.frame is None


def test_orbitals_remain_available_without_a_geometry(gui,tmp_path):
    source=(EXAMPLES/'synthetic_gxtb_v1110.out').read_text()
    start=source.index(' ================\n final structure:')
    end=source.index(' :: total energy -20.100',start)
    p=tmp_path/'orbitals.out';p.write_text(source[:start]+source[end:])
    w,d=attach(gui,p)
    assert d.frames==[] and w.results_orbital_button.isEnabled()
    w.results_orbital_button.click();dialog=w._analysis_windows[-1]
    assert dialog.summary.rowCount()==2 and dialog.unit.currentText()=='eV'
