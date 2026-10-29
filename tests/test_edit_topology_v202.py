"""Edits preserve connectivity; only explicit bond actions change the graph."""
from pathlib import Path
from itertools import product
from unittest.mock import patch
import numpy as np
import pytest

from lele.core import Frame, visible_bonds, freeze_bonds, toggle_selected_bonds, unit_cell_edges
from lele.periodic_geometry import (periodic_bonds, normalized_positions, minimum_image,
                                    short_contact_details)
from lele.atom_clipboard import copy_atoms, read_atoms, paste_atoms
from lele.supercell import make_supercell
from lele.boundary import boundary_view
from lele.renderer import MoleculeRenderer
from lele.trajectory_analysis import DisplayAlignment
from vtkmodules.vtkRenderingCore import vtkRenderer
from test_periodic_fragment_ui_v171 import gui


def three_atoms():
    return Frame(['C']*3, [[0,0,0],[1.4,0,0],[4,0,0]])


def test_alt_middle_drag_does_not_join_a_nearby_fragment_and_undo_restores_state(gui):
    from lele.fragment import selected_fragments
    gui.attach(three_atoms()); gui.select([0]); w = gui.window
    assert visible_bonds(w.frame) == [(0,1)]
    w._fragment_begin('pan',0,0)
    with patch('lele.fragment.screen_translation',return_value=np.array([1.8,0,0])):
        w._fragment_move('pan',10,0)
    w._fragment_end('pan')
    assert np.linalg.norm(w.frame.positions[1]-w.frame.positions[2]) == pytest.approx(.8)
    assert visible_bonds(w.frame) == [(0,1)]
    assert selected_fragments(w.frame,[0]) == [0,1]
    w._fragment_begin('pan',0,0)
    assert w._fragment_gesture['indices'] == [0,1]
    w._fragment_end('pan'); w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions,three_atoms().positions)
    assert w.frame.bond_snapshot is None


def test_coordinate_edit_keeps_long_bonds_and_does_not_add_new_short_bonds(gui):
    gui.attach(three_atoms()); w=gui.window
    w.atom_table.item(1,1).setText('8')
    assert visible_bonds(w.frame) == [(0,1)]
    w.atom_table.item(2,1).setText('.8')
    assert visible_bonds(w.frame) == [(0,1)]
    assert w.frame.bond_snapshot == frozenset({(0,1)})
    w.undo_edit(); w.undo_edit()
    assert w.frame.bond_snapshot is None
    np.testing.assert_array_equal(w.frame.positions,three_atoms().positions)


def test_manual_bond_toggle_still_changes_only_requested_connections(gui):
    gui.attach(three_atoms()); w=gui.window
    w.atom_table.item(1,1).setText('8'); gui.select([0,1]); w.toggle_bonds()
    assert visible_bonds(w.frame) == []
    gui.select([0,2]); w.toggle_bonds()
    assert visible_bonds(w.frame) == [(0,2)]
    w.atom_table.item(2,1).setText('20')
    assert visible_bonds(w.frame) == [(0,2)]
    w.undo_edit(); w.undo_edit()
    assert visible_bonds(w.frame) == []


def test_explicit_rebuild_and_undo_preserve_user_control(gui):
    frame=Frame(['C','C'],[[0,0,0],[5,0,0]])
    gui.attach(frame); w=gui.window
    w.atom_table.item(1,1).setText('1.4')
    assert visible_bonds(w.frame) == []
    w.rebuild_bonds(); assert visible_bonds(w.frame) == [(0,1)]
    w.undo_edit(); assert visible_bonds(w.frame) == []


def test_deleting_an_intermediate_atom_does_not_create_a_new_bridge(gui):
    gui.attach(Frame(['C']*3,[[0,0,0],[.8,0,0],[1.6,0,0]])); w=gui.window
    assert visible_bonds(w.frame) == [(0,1),(1,2)]
    gui.select([1]); w.delete_selected_atoms()
    assert len(w.frame.symbols)==2 and visible_bonds(w.frame)==[]
    w.undo_edit(); assert visible_bonds(w.frame)==[(0,1),(1,2)]


def test_connectivity_lock_remains_local_to_the_edited_frame(gui):
    a=three_atoms(); b=a.clone(); gui.attach(a,second_frame=b);w=gui.window
    w.atom_table.item(1,1).setText('8')
    assert w.doc.frames[0].bond_snapshot is not None
    assert w.doc.frames[1].bond_snapshot is None
    w.change_frame(1);np.testing.assert_array_equal(w.frame.positions,three_atoms().positions)
    assert visible_bonds(w.frame)==[(0,1)]


def test_paste_preserves_internal_links_without_bonding_to_the_destination():
    target=Frame(['C'],[[0,0,0]])
    fragment=Frame(['C','C'],[[0,0,0],[1.4,0,0]])
    paste_atoms(target,fragment,[.8,0,0])
    assert visible_bonds(target)==[(1,2)]
    assert target.bond_snapshot==frozenset({(1,2)})


def test_clipboard_retains_an_intentionally_unbonded_close_pair():
    frame=Frame(['C','C'],[[0,0,0],[5,0,0]])
    freeze_bonds(frame);frame.positions[1,0]=1.4
    text,metadata=copy_atoms(frame,[0,1]);fragment=read_atoms(text,metadata)
    target=Frame(['He'],[[20,0,0]]);paste_atoms(target,fragment,[0,0,0])
    assert visible_bonds(fragment)==[] and visible_bonds(target)==[]


def test_periodic_edit_keeps_the_original_image_connection():
    frame=Frame(['C','C'],[[.1,0,0],[9,0,0]],np.eye(3)*10,(True,True,True))
    freeze_bonds(frame)
    assert frame.periodic_bond_snapshot==((0,1,(-1,0,0)),)
    for x in (4.,20.2,-8.):
        frame.positions[1,0]=x
        _,floors=normalized_positions(frame)
        i,j,shift=periodic_bonds(frame)[0]
        np.testing.assert_array_equal(np.asarray(shift)+floors[i]-floors[j],[-1,0,0])
        assert len(periodic_bonds(frame))==1
    toggle_selected_bonds(frame,[0,1]);assert periodic_bonds(frame)==[]
    toggle_selected_bonds(frame,[0,1]);assert len(periodic_bonds(frame))==1
    assert frame.periodic_bond_snapshot[0][2]==minimum_image(frame.positions[1]-frame.positions[0],frame)[1]


def test_supercell_repeats_a_locked_graph_without_inventing_connections():
    frame=Frame(['C','C'],[[0,0,0],[5,0,0]],np.eye(3)*10,(True,)*3)
    freeze_bonds(frame);frame.positions[1,0]=1.4
    expanded=make_supercell(frame,(2,1,1))
    assert len(expanded.symbols)==4
    assert visible_bonds(expanded)==[] and periodic_bonds(expanded)==[]
    assert len(frame.symbols)==2 and frame.bond_snapshot==frozenset()


def test_supercell_does_not_retarget_a_moved_manual_periodic_bond():
    frame=Frame(['C','C'],[[.1,0,0],[9,0,0]],np.eye(3)*10,(True,)*3,
                bond_added={(0,1)})
    freeze_bonds(frame);frame.positions[1,0]=4
    expanded=make_supercell(frame,(2,1,1))
    assert periodic_bonds(expanded)==[(0,3,(-1,0,0)),(1,2,(0,0,0))]
    assert expanded.bond_added=={(0,3),(1,2)}


@pytest.mark.parametrize('boundary',[False,True])
def test_cell_outlines_and_atoms_share_rotation_and_translation_with_boundary(boundary):
    reference=Frame(['C','N','O'],[[1,1,1],[2,1,1],[1,2,1]],np.diag([10.,8,6]),(True,)*3)
    source=reference.clone();rot=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    source.positions=source.positions@rot+[4,3,0];source.cell=source.cell@rot
    renderer=MoleculeRenderer(vtkRenderer());renderer.options.bonds=False;renderer.options.axes_position='Off'
    renderer.options.boundary_enabled=boundary;renderer.options.boundary_bounds=((0,2),(0,1),(0,1))
    renderer.alignment=DisplayAlignment(reference,(0,1,2))
    with patch.object(renderer,'_tube_segments') as capture:renderer.set_scene(source)
    rotation,translation=renderer.display_rotation,renderer.display_translation
    if boundary:
        base=boundary_view(source,renderer.options.boundary_bounds)
        expected_lines=np.asarray(base.cell_lines)@rotation+translation
        np.testing.assert_allclose(renderer.boundary_display.frame.positions,base.frame.positions@rotation+translation,atol=1e-12)
    else:expected_lines=np.asarray(unit_cell_edges(source.cell))@rotation+translation
    actual=np.asarray([[p,q] for p,q,_ in capture.call_args.args[0]])
    np.testing.assert_allclose(actual,expected_lines,atol=1e-12)
    np.testing.assert_allclose(renderer.frame.positions,reference.positions,atol=1e-12)


def test_large_shear_shift_is_mapped_back_to_the_input_basis():
    cell=np.array([[3.,0,0],[240.,3,0],[0,0,8.]])
    frame=Frame(['C','O'],[[0,0,0],[60.15,.45,0]],cell,(True,)*3)
    contact,=short_contact_details(frame)
    assert contact.image_shift==(-20,0,0)
    assert contact.distance==pytest.approx(np.hypot(.15,.45))
    vector,shift=minimum_image(frame.positions[1],frame)
    np.testing.assert_allclose(vector,[.15,.45,0],atol=1e-12)
    assert shift==(-20,0,0)


def test_partial_periodicity_does_not_translate_nonperiodic_axes():
    cell=np.array([[3.,0,0],[24.,3,0],[0,0,8.]])
    frame=Frame(['C','O'],[[0,0,0],[6.15,.45,0]],cell,(True,False,False))
    vector,shift=minimum_image(frame.positions[1],frame)
    assert shift==(-2,0,0)
    np.testing.assert_allclose(vector,[.15,.45,0],atol=1e-12)
    vector,shift=minimum_image([240,30,0],frame)
    assert shift==(-80,0,0)
    np.testing.assert_allclose(vector,[0,30,0],atol=1e-12)


def test_windows_launcher_has_no_hardcoded_old_version():
    content=(Path(__file__).resolve().parents[1]/'start_windows.bat').read_text()
    assert 'LELE needs 64-bit CPython 3.12' in content
    assert 'v1.7.0' not in content


@pytest.mark.parametrize('pbc',[mask for mask in product((False,True),repeat=3) if any(mask)])
def test_minimum_image_matches_independent_enumeration_with_partial_periodicity(pbc):
    cell=np.array([[3.,0,0],[24.,3,0],[5.,7.,8.]])
    frame=Frame(['C'],[[0,0,0]],cell,pbc)
    ranges=[range(-45,46),range(-6,7),range(-3,4)]
    shifts=np.asarray(list(product(*[r if use else [0] for r,use in zip(ranges,pbc)])))
    rng=np.random.default_rng(202)
    for delta in rng.uniform(-.6,.6,size=(5,3))@cell:
        vector,shift=minimum_image(delta,frame)
        expected=np.linalg.norm(delta+shifts@cell,axis=1).min()
        assert np.linalg.norm(vector)==pytest.approx(expected,abs=1e-10)
        assert all(use or s==0 for use,s in zip(pbc,shift))
        np.testing.assert_allclose(vector,delta+np.asarray(shift)@cell,atol=1e-12)
