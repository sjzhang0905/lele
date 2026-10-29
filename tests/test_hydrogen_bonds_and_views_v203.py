"""Manual dashed bonds and document-switch round trips through real Qt actions."""
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import Frame, Document, visible_bonds
from lele.fragment import selected_fragments
from lele.hydrogen_bonds import hydrogen_bond_links, toggle_hydrogen_bond
from lele.renderer import MoleculeRenderer
from lele.boundary import boundary_view
from lele.supercell import make_supercell
from lele.atom_clipboard import copy_atoms, read_atoms, paste_atoms
from lele.selection_geometry import delete_selected_atoms
from lele.trajectory_analysis import DisplayAlignment
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui

ROOT = Path(__file__).resolve().parents[1]


def water_pair():
    return Frame(['O','H','O','H'],[[0,0,0],[1,0,0],[2.8,0,0],[3.8,0,0]])


def test_manual_dashed_bond_never_joins_the_covalent_fragment_graph():
    frame = water_pair(); before = visible_bonds(frame)
    assert toggle_hydrogen_bond(frame,[1,2]) == 'added'
    assert len(hydrogen_bond_links(frame,False)) == 1
    assert visible_bonds(frame) == before
    assert selected_fragments(frame,[0]) == [0,1]
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.bonds = renderer.options.unit_cell = False
    renderer.options.axes_position = 'Off'
    with patch.object(renderer,'_tube_segments') as draw:
        renderer.set_scene(frame)
    segments = draw.call_args.args[0]
    assert len(segments) == 6 and {c for _,_,c in segments} == {'#23A9C4'}


def test_ctrl_h_can_suppress_an_automatic_candidate_without_duplicate_lines():
    frame = water_pair()
    assert len(hydrogen_bond_links(frame)) == 1
    assert toggle_hydrogen_bond(frame,[1,2],automatic=True) == 'removed'
    assert hydrogen_bond_links(frame) == []
    assert toggle_hydrogen_bond(frame,[1,2],automatic=True) == 'added'
    assert len(hydrogen_bond_links(frame)) == 1
    assert hydrogen_bond_links(frame)[0].manual


def test_ctrl_h_and_ctrl_b_are_independent_and_undoable(gui):
    gui.attach(water_pair()); w = gui.window
    w.show();w.vtk.setFocusPolicy(Qt.FocusPolicy.StrongFocus);w.vtk.setFocus()
    gui.select([1,2]);gui.app.processEvents()
    QTest.keyClick(w.vtk,Qt.Key.Key_H,Qt.KeyboardModifier.ControlModifier)
    assert (1,2) in w.frame.hbond_added and (1,2) not in visible_bonds(w.frame)
    QTest.keyClick(w.vtk,Qt.Key.Key_B,Qt.KeyboardModifier.ControlModifier)
    assert (1,2) in w.frame.hbond_added and (1,2) in visible_bonds(w.frame)
    QTest.keyClick(w.vtk,Qt.Key.Key_H,Qt.KeyboardModifier.ControlModifier)
    assert not w.frame.hbond_added and (1,2) in visible_bonds(w.frame)
    w.undo_edit();assert (1,2) in w.frame.hbond_added
    w.undo_edit();assert (1,2) not in visible_bonds(w.frame)
    w.undo_edit();assert not w.frame.hbond_added


def test_manual_periodic_image_survives_movement_and_cloning():
    frame = Frame(['H','O'],[[.1,0,0],[9,0,0]],np.eye(3)*10,(True,)*3)
    toggle_hydrogen_bond(frame,[1,0])
    assert frame.hbond_added == {(0,1):(-1,0,0)}
    frame.positions[1,0] = 4
    link, = hydrogen_bond_links(frame,False)
    np.testing.assert_allclose(link.end,[-6,0,0])
    other=frame.clone();toggle_hydrogen_bond(other,[0,1])
    assert frame.hbond_added and not other.hbond_added


@pytest.mark.parametrize('boundary',[False,True])
def test_manual_dashes_follow_display_alignment_and_boundary_images(boundary):
    reference=Frame(['H','O','N'],[[.1,1,1],[9,1,1],[.1,2,1]],np.eye(3)*10,(True,)*3)
    toggle_hydrogen_bond(reference,[0,1])
    source=reference.clone();rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    source.positions=source.positions@rotation+[4,3,0];source.cell=source.cell@rotation
    renderer=MoleculeRenderer(vtkRenderer())
    renderer.options.bonds=renderer.options.unit_cell=False;renderer.options.axes_position='Off'
    renderer.options.boundary_enabled=boundary;renderer.options.boundary_bounds=((0,2),(0,1),(0,1))
    renderer.alignment=DisplayAlignment(reference,(0,1,2))
    with patch.object(renderer,'_tube_segments') as draw:renderer.set_scene(source)
    display=boundary_view(source,renderer.options.boundary_bounds).frame if boundary else source
    expected=[]
    for link in hydrogen_bond_links(display,False):
        for k in range(6):
            f0=.11+k*.145;f1=min(f0+.077,.97)
            expected.append([link.start+(link.end-link.start)*f0,link.start+(link.end-link.start)*f1])
    expected=np.asarray(expected)@renderer.display_rotation+renderer.display_translation
    actual=np.asarray([[p,q] for call in draw.call_args_list for p,q,_ in call.args[0]])
    assert len(actual)>0
    np.testing.assert_allclose(actual,expected,atol=1e-12)


def test_clipboard_and_deletion_remap_manual_hydrogen_bonds():
    frame=water_pair();toggle_hydrogen_bond(frame,[1,2]);frame.hbond_removed={(0,2)}
    text,metadata=copy_atoms(frame,[2,1,0]);fragment=read_atoms(text,metadata)
    target=Frame(['He'],[[20,0,0]]);paste_atoms(target,fragment,[0,0,0])
    assert target.hbond_added=={(1,2):(0,0,0)}
    assert target.hbond_removed=={(1,3)}
    delete_selected_atoms(frame,[0])
    assert frame.hbond_added=={(0,1):(0,0,0)} and not frame.hbond_removed
    delete_selected_atoms(frame,[0]);assert not frame.hbond_added


@pytest.mark.parametrize('wrap',[True,False])
def test_supercell_retains_manual_hydrogen_bond_paths(wrap):
    frame=Frame(['H','O'],[[10.1,0,0],[9,0,0]],np.eye(3)*10,(True,)*3)
    toggle_hydrogen_bond(frame,[0,1])
    expanded=make_supercell(frame,(2,1,1),wrap=wrap)
    links=hydrogen_bond_links(expanded,False)
    assert len(links)==2
    for link in links:assert np.linalg.norm(link.end-link.start)==pytest.approx(1.1)
    assert frame.hbond_added=={(0,1):(0,0,0)}


def test_coordinate_edit_and_delete_undo_retain_manual_hydrogen_bonds(gui):
    frame=water_pair();toggle_hydrogen_bond(frame,[1,2]);gui.attach(frame);w=gui.window
    w.atom_table.item(2,1).setText('9')
    assert w.frame.hbond_added=={(1,2):(0,0,0)}
    gui.select([1]);w.delete_selected_atoms();assert not w.frame.hbond_added
    w.undo_edit();assert w.frame.hbond_added=={(1,2):(0,0,0)}
    w.undo_edit();np.testing.assert_allclose(w.frame.positions,water_pair().positions)
    assert w.frame.hbond_added=={(1,2):(0,0,0)}


def install_documents(gui,documents):
    w=gui.window;w.files_tree.clear();w.documents=documents
    for i,doc in enumerate(documents):w._add_document_tree(i,doc)
    w.change_frame(0,switch_doc=0,reset_camera=True)
    return w


def camera_values(w,clipping=True):
    camera=w.scene.GetActiveCamera()
    names=['Position','FocalPoint','ViewUp','ParallelProjection','ParallelScale','ViewAngle','WindowCenter']
    if clipping:names.append('ClippingRange')
    return {name:getattr(camera,'Get'+name)() for name in names}


def set_camera(w,first=True):
    cam=w.scene.GetActiveCamera()
    cam.SetPosition(*( (11,-7,21) if first else (-8,17,6) ))
    cam.SetFocalPoint(1,2,3);cam.SetViewUp(.2,1,.3)
    cam.SetParallelProjection(not first);cam.SetParallelScale(7.3 if first else 2.7)
    cam.SetViewAngle(42 if first else 31);cam.SetWindowCenter(.12,-.17)
    cam.SetClippingRange(.4,500)


def geometry_documents(gui):
    frame=Frame(['O','H','C'],[[0,0,0],[1,0,0],[0,2,0]],np.eye(3)*10,(True,)*3)
    return [Document(Path(gui.temp.name)/'a.xyz','XYZ',[frame,frame.clone()]),
            Document(Path(gui.temp.name)/'b.xyz','XYZ',[Frame(['C'],[[8,3,1]])])]


def test_each_file_restores_camera_colours_and_all_render_controls(gui):
    docs=geometry_documents(gui);w=install_documents(gui,docs)
    w.preset_combo.setCurrentIndex(w.preset_combo.findData('Dark presentation'))
    w._set_option('element_colors',{'O':'#123456'})
    w.hbond_check.setChecked(True);w.atom_slider.setValue(82);w.cutoff_slider.setValue(130)
    w.axes_basis_combo.setCurrentIndex(w.axes_basis_combo.findData('abc'))
    w.axes_position_combo.setCurrentIndex(w.axes_position_combo.findData('Origin'))
    w.axes_length_spin.setValue(4.25);w.label_combo.setCurrentText('Index (1..N)')
    w.label_size_spin.setValue(24);w.label_font_combo.setCurrentText('Times');w.label_bold_check.setChecked(False)
    w.volume_check.setChecked(False);w.iso_spin.setValue(1.25e-5);w.opacity_slider.setValue(35)
    w._set_option('dipole_mode','Total');w._set_option('dipole_scale',.75)
    w._apply_boundary(True,((0,2),(0,1),(0,1)))
    w._change_atom_appearance([0],{'color':'#ABCDEF'})
    set_camera(w);a_camera=camera_values(w);a_options=asdict(w.render_options)
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(1))
    assert w.current_doc==1 and camera_values(w)!=a_camera
    w.preset_combo.setCurrentIndex(w.preset_combo.findData('Soft pastel'))
    w._set_option('element_colors',{'C':'#FEDCBA'});w.hbond_check.setChecked(False)
    w.cell_check.setChecked(False);w.label_size_spin.setValue(13);w.volume_check.setChecked(True)
    set_camera(w,False);b_camera=camera_values(w);b_options=asdict(w.render_options)
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(0))
    assert camera_values(w)==a_camera and asdict(w.render_options)==a_options
    assert w.renderer.options is w.render_options
    assert w.atom_slider.value()==82 and w.cutoff_slider.value()==130
    assert w.hbond_check.isChecked() and w.axes_basis_combo.currentData()=='abc'
    assert w.axes_position_combo.currentData()=='Origin' and w.axes_length_spin.value()==4.25
    assert w.label_size_spin.value()==24 and w.label_font_combo.currentText()=='Times'
    assert not w.label_bold_check.isChecked() and not w.volume_check.isChecked()
    assert w.iso_spin.value()==pytest.approx(1.25e-5) and w.opacity_slider.value()==35
    assert w.dipole_panel.mode.currentText()=='Total' and w.dipole_panel.scale.value()==.75
    assert w.boundary_panel.enabled.isChecked() and w.boundary_panel.bounds()==((0,2),(0,1),(0,1))
    assert docs[0].frames[0].atom_appearance[0].color=='#ABCDEF'
    assert docs[1].frames[0].atom_appearance=={}
    assert w.projection_actions['Perspective'].isChecked()
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(1))
    assert camera_values(w)==b_camera and asdict(w.render_options)==b_options
    assert w.projection_actions['Orthographic'].isChecked()


def test_opening_another_file_preserves_the_previous_view(gui):
    w=install_documents(gui,geometry_documents(gui)[:1])
    set_camera(w);before=camera_values(w);w._set_option('element_colors',{'O':'#123456'})
    path=Path(gui.temp.name)/'new.xyz';path.write_text('2\nnew\nC 0 0 0\nH 1 0 0\n')
    w._open_path_now(path);assert w.current_doc==1
    w._set_option('element_colors',{'H':'#654321'})
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(0))
    assert camera_values(w)==before and w.render_options.element_colors=={'O':'#123456'}


def energy_item(head):
    queue=[head]
    while queue:
        item=queue.pop(0);data=item.data(0,Qt.ItemDataRole.UserRole)
        if data and len(data)>1 and data[1]=='energy':return item
        queue.extend(item.child(i) for i in range(item.childCount()))
    raise AssertionError('No energy-only item')


@pytest.mark.parametrize('mixed',[False,True])
def test_energy_only_switches_do_not_overwrite_a_geometry_camera(gui,mixed):
    docs=geometry_documents(gui)[:1]
    energies=load_document(ROOT/'examples/synthetic_xtb_energy_only_v1111.out')
    if mixed:docs[0].calculation_results=deepcopy(energies.calculation_results)
    docs.append(energies);w=install_documents(gui,docs)
    w._set_option('background','#123456');set_camera(w);before=camera_values(w)
    if mixed:
        w.files_tree.setCurrentItem(energy_item(w.files_tree.topLevelItem(0)))
        assert w.frame is None and w.current_doc==0
    w.files_tree.setCurrentItem(energy_item(w.files_tree.topLevelItem(1)))
    assert w.frame is None and w.current_doc==1
    w._set_option('background','#FFFFFF')
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(0))
    assert w.current_doc==0 and w.frame is not None
    assert camera_values(w)==before and w.render_options.background=='#123456'


def test_frequency_tree_switch_restores_view_without_a_second_camera_reset(gui):
    vibr=load_document(ROOT/'examples/synthetic_opt_freq.log')
    docs=[vibr,geometry_documents(gui)[1]];w=install_documents(gui,docs)
    w.select_vibration(0,0,0,autoplay=False);set_camera(w);before=camera_values(w,False)
    w._set_option('element_colors',{'O':'#123456'})
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(1));set_camera(w,False)
    w.files_tree.setCurrentItem(w._vibration_tree_items[0,0,0])
    w.vibration_timer.stop()
    assert w._active_vibration==(0,0,0) and camera_values(w,False)==before
    assert w.render_options.element_colors=={'O':'#123456'}


def test_analysis_result_navigation_restores_file_view(gui):
    docs=geometry_documents(gui);w=install_documents(gui,docs);set_camera(w)
    before=camera_values(w);w._set_option('element_colors',{'O':'#123456'})
    w.files_tree.setCurrentItem(w.files_tree.topLevelItem(1));set_camera(w,False)
    w._jump_to_result_frame(docs[0],1)
    assert w.current_doc==0 and w.frame_index==1 and camera_values(w)==before
    assert w.render_options.element_colors=={'O':'#123456'}
