"""Whole-crystal rotations, image representatives and the actual POSCAR pair."""
from pathlib import Path
import ast
import math
import os
from unittest.mock import patch
import numpy as np
import pytest
from lele.core import Frame,Volume,align_pair_to_axis,freeze_bonds,visible_bonds
from lele.coordinate_reorientation import local_axis_rotation,proper_rotation,reorient_from_atoms,transform_complete_frame
from lele.periodic_geometry import minimum_image,periodic_bonds,normalized_positions
from lele.energy_units import rigid_equivalent
from lele.formats import load_document,export_frame
from lele.project_file import save_project,load_project
from lele.render_options import RenderOptions
from test_periodic_fragment_ui_v171 import gui


def crystal():
    cell=np.array([[4.,0,0],[3.7,1.1,0],[.8,.4,7.]])
    fractional=np.array([[.95,.1,.4],[.03,.2,.42],[.97,.11,.7],[.3,.6,.2]])
    return Frame(['Co','Se','S','Li'],fractional@cell,cell,(True,True,True),-12.,{'optimization_converged':True})


def distances(frame):
    from ase import Atoms
    return Atoms(frame.symbols,positions=frame.positions,cell=frame.cell,pbc=frame.pbc).get_all_distances(mic=True)


@pytest.mark.parametrize('axis',['X','Y','Z'])
@pytest.mark.parametrize('pbc',[(True,True,True),(True,False,True)])
def test_pair_alignment_preserves_all_periodic_distances_and_cell_metric(axis,pbc):
    f=crystal();f.pbc=pbc;old=f.clone()
    source,_=minimum_image(old.positions[1]-old.positions[0],old)
    rotation,pivot,changed=align_pair_to_axis(f,0,1,axis)
    assert changed and f.pbc==pbc
    np.testing.assert_allclose(f.cell,old.cell@rotation.T,atol=1.e-12)
    np.testing.assert_allclose(f.cell@f.cell.T,old.cell@old.cell.T,atol=1.e-12)
    np.testing.assert_allclose(source@rotation.T,np.eye(3)['XYZ'.index(axis)]*np.linalg.norm(source),atol=1.e-12)
    np.testing.assert_allclose(distances(f),distances(old),atol=2.e-12)
    np.testing.assert_allclose(f.positions[0],pivot,atol=1.e-12)
    assert rigid_equivalent(old,f) and f.energy_ev==old.energy_ev


def test_three_atom_convention_z_exact_and_x_projected_without_distortion():
    f=Frame(['Co','O','S','He'],[[2,3,4],[3,5,5],[2,4,5],[5,8,9]])
    old=f.clone();rotation,details=local_axis_rotation(f,0,1,2)
    z=np.array([0,1,1])/np.sqrt(2);x=np.array([1,.5,-.5])/np.sqrt(1.5);y=np.cross(z,x)
    np.testing.assert_allclose(rotation,np.stack([x,y,z]),atol=1.e-12)
    reorient_from_atoms(f,0,1,2)
    np.testing.assert_allclose(f.positions[0],0,atol=1.e-12)
    np.testing.assert_allclose(f.positions[2],[0,0,np.sqrt(2)],atol=1.e-12)
    assert f.positions[1,0]>0 and abs(f.positions[1,1])<1.e-12
    assert f.positions[1,2]>0  # A nonorthogonal hint cannot itself lie on X.
    np.testing.assert_allclose(distances(f),distances(old),atol=1.e-12)


def test_nearest_images_remap_frozen_bonds_and_hydrogen_bonds():
    f=Frame(['O','H','He'],[[9.8,0,0],[.2,.5,0],[9.8,0,1]],np.eye(3)*10,(True,True,True))
    f.bond_snapshot=frozenset();f.periodic_bond_snapshot=((0,1,(1,0,0)),)
    f.bond_added={(0,1)};f.hbond_added={(0,1):(1,0,0)}
    old=f.clone();reorient_from_atoms(f,0,1,2)
    assert f.periodic_bond_snapshot==((0,1,(0,0,0)),)
    assert f.hbond_added=={(0,1):(0,0,0)} and visible_bonds(f)==[(0,1)]
    assert f.bond_added==old.bond_added and f.symbols==old.symbols
    np.testing.assert_allclose(distances(f),distances(old),atol=1.e-12)
    assert rigid_equivalent(old,f)


def test_reimaged_cross_cell_bond_does_not_become_long_visible_diagonal():
    f=Frame(['O','H'],[[4.8,0,0],[5.2,0,0]],np.eye(3)*10,(True,True,True))
    f.bond_snapshot=frozenset({(0,1)});f.periodic_bond_snapshot=((0,1,(0,0,0)),);f.bond_added={(0,1)}
    transform_complete_frame(f,np.eye(3),np.zeros(3),nearest_origin=np.zeros(3))
    assert f.periodic_bond_snapshot==((0,1,(1,0,0)),)
    assert visible_bonds(f)==[]
    xyz,_=normalized_positions(f)
    i,j,s=periodic_bonds(f)[0]
    assert np.linalg.norm(xyz[j]+np.asarray(s)@f.cell-xyz[i])==pytest.approx(.4)


@pytest.mark.parametrize('matrix',[np.diag([1.,1.,-1.]),np.eye(3)*2,np.ones((3,3)),np.full((3,3),np.nan)])
def test_deformation_or_reflection_is_rejected_without_mutation(matrix):
    f=crystal();old=f.clone()
    with pytest.raises(ValueError):transform_complete_frame(f,matrix,np.zeros(3))
    np.testing.assert_array_equal(f.positions,old.positions);np.testing.assert_array_equal(f.cell,old.cell)


@pytest.mark.parametrize('indices',[(0,0,2),(0,1,8)])
def test_invalid_atom_axes_are_atomic_errors(indices):
    f=crystal();old=f.clone()
    with pytest.raises(ValueError):reorient_from_atoms(f,*indices)
    np.testing.assert_array_equal(f.positions,old.positions)


def test_parallel_and_periodically_coincident_axes_are_rejected():
    f=Frame(['H']*3,[[0,0,0],[1,0,0],[2,0,0]],np.eye(3)*10,(True,True,True))
    with pytest.raises(ValueError,match='parallel'):reorient_from_atoms(f,0,1,2)
    f.positions[1]=[10,0,0]
    with pytest.raises(ValueError,match='Coincident'):reorient_from_atoms(f,0,1,2)


def test_complete_grid_and_qe_force_vectors_rotate_and_scalar_energy_survives():
    f=crystal();old=f.clone();f.info['qe_forces_ev_ang']=np.array([[1.,2,3]]*4)
    volume=Volume(np.arange(27).reshape(3,3,3),[1,2,3],np.diag([.2,.3,.4]));v0=volume.origin.copy();voxel=volume.voxel_vectors.copy()
    r=np.array([[0,-1.,0],[1.,0,0],[0,0,1.]])
    transform_complete_frame(f,r,[-1,-2,-3],volume=volume)
    np.testing.assert_array_equal(volume.data,np.arange(27).reshape(3,3,3))
    np.testing.assert_allclose(volume.origin,v0@r.T+[-1,-2,-3])
    np.testing.assert_allclose(volume.voxel_vectors,voxel@r.T)
    np.testing.assert_allclose(f.info['qe_forces_ev_ang'],[[-2,1,3]]*4)
    assert rigid_equivalent(old,f) and f.energy_ev==-12


def test_rigid_equivalence_rejects_original_atoms_only_bug_and_real_geometry_edits():
    old=crystal();new=old.clone();r=np.array([[0,-1.,0],[1.,0,0],[0,0,1.]])
    new.positions=new.positions@r.T
    assert not rigid_equivalent(old,new)
    new=old.clone();transform_complete_frame(new,r,np.ones(3),nearest_origin=old.positions[0])
    assert rigid_equivalent(old,new)
    new.positions[1,0]+=.01
    assert not rigid_equivalent(old,new)


@pytest.mark.parametrize('target',['poscar-cartesian','poscar-direct'])
def test_reoriented_poscar_export_preserves_cell_atom_order_and_coordinates(tmp_path,target):
    f=crystal();reorient_from_atoms(f,0,1,2)
    path=tmp_path/'POSCAR';export_frame(f,path,target)
    restored=load_document(path).frames[0]
    assert restored.symbols==f.symbols
    np.testing.assert_allclose(restored.cell,f.cell,atol=1.e-12)
    np.testing.assert_allclose(restored.positions,f.positions,atol=1.e-12)


def test_gui_dialog_defaults_matrix_convention_apply_undo_and_project(gui,tmp_path):
    from PySide6.QtWidgets import QDialog
    from lele.reorientation_dialog import ReorientationDialog
    f=crystal();gui.attach(f);w=gui.window;gui.select([0,1,2]);old=w.frame.clone()
    dialog=ReorientationDialog(w.frame,w.selection,w);gui.addCleanup(dialog.deleteLater)
    assert (dialog.origin.value(),dialog.x_atom.value(),dialog.z_atom.value())==(1,2,3)
    assert dialog.nearest.isChecked()
    rotation,translation,center,details=dialog.plan()
    with patch.object(ReorientationDialog,'exec',return_value=QDialog.DialogCode.Accepted):w.configure_coordinate_reorientation()
    assert w.frame.info['coordinate_reorientation']['selection']==[0,1,2]
    assert w.frame.energy_ev==-12 and w.frame.info['optimization_converged']
    np.testing.assert_allclose(w.frame.cell,old.cell@rotation.T,atol=1.e-12)
    np.testing.assert_allclose(w.frame.positions[0],0,atol=1.e-12)
    assert w.atom_table.item(0,1).text()=='0.000000'
    path=tmp_path/'reoriented.lele'
    save_project(path,dict(documents=[dict(document=w.doc,options=RenderOptions(),frame_index=0)],current_document=0))
    loaded=load_project(path)['documents'][0]['document'].frames[0]
    assert loaded.info['coordinate_reorientation']==w.frame.info['coordinate_reorientation']
    np.testing.assert_array_equal(loaded.cell,w.frame.cell)
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions,old.positions);np.testing.assert_array_equal(w.frame.cell,old.cell)
    assert w.frame.bond_snapshot==old.bond_snapshot
    dialog.mode.setCurrentIndex(1);dialog.matrix.setPlainText('0 1 0; -1 0 0; 0 0 1')
    r,_,_,_=dialog.plan();np.testing.assert_array_equal(r,[[0,-1,0],[1,0,0],[0,0,1]])


def test_gui_xyz_rotates_periodic_grid_and_undo_restores_it(gui):
    f=crystal();volume=Volume(np.ones((2,2,2)),[1.,2,3],np.diag([.2,.3,.4]))
    gui.attach(f,volume=volume);w=gui.window;old=f.clone();v=volume.origin.copy();voxel=volume.voxel_vectors.copy()
    gui.select([0,1]);w.align_combo.setCurrentText('X');w.align_selected_pair()
    record=w.frame.info['coordinate_reorientation'];r=np.asarray(record['rotation']);t=np.asarray(record['translation'])
    np.testing.assert_allclose(volume.origin,v@r.T+t,atol=1.e-12)
    np.testing.assert_allclose(volume.voxel_vectors,voxel@r.T,atol=1.e-12)
    w.undo_edit();np.testing.assert_array_equal(w.frame.cell,old.cell);np.testing.assert_array_equal(volume.origin,v)


def test_actual_poscar_pair_is_a_rigid_reorientation(tmp_path):
    directory=os.environ.get('LELE_ROTATION_EXAMPLE_DIR')
    if not directory:pytest.skip('Set LELE_ROTATION_EXAMPLE_DIR to the supplied private POSCAR1/POSCAR2.')
    root=Path(directory);a=load_document(root/'POSCAR1').frames[0];b=load_document(root/'POSCAR2').frames[0]
    q=np.linalg.solve(a.cell,b.cell);origin=int(np.argmin(np.linalg.norm(b.positions,axis=1)))
    assert origin==19 and a.symbols==b.symbols and len(a.symbols)==100
    old=a.clone();transform_complete_frame(a,q.T,-a.positions[origin]@q,nearest_origin=a.positions[origin])
    np.testing.assert_allclose(a.cell,b.cell,atol=1.e-11)
    np.testing.assert_allclose(a.positions,b.positions,atol=8.e-8)
    np.testing.assert_allclose(distances(a),distances(old),atol=1.e-11)
    assert rigid_equivalent(old,a)
    path=tmp_path/'POSCAR_reoriented';export_frame(a,path,'poscar-cartesian')
    saved=load_document(path).frames[0]
    assert saved.symbols==b.symbols
    np.testing.assert_allclose(saved.cell,b.cell,atol=1.e-11)
    np.testing.assert_allclose(saved.positions,b.positions,atol=8.e-8)


def test_local_axes_match_supplied_rotation_script_without_pymatgen():
    path=os.environ.get('LELE_ROTATION_SCRIPT')
    if not path:pytest.skip('Set LELE_ROTATION_SCRIPT to the supplied v13 rotation script.')
    tree=ast.parse(Path(path).read_text());wanted={'unit_vector','strict_minimum_image_delta','axis_fractional_delta','build_rotation_from_points'}
    nodes=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]
    nodes.extend(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted)
    namespace={'np':np,'math':math};exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),namespace)
    f=crystal();fractional=f.positions@np.linalg.inv(f.cell)
    expected,q,_=namespace['build_rotation_from_points'](f.cell,*fractional[:3],'mic')
    actual,_=local_axis_rotation(f,0,1,2)
    np.testing.assert_allclose(actual,expected,atol=1.e-12)
    np.testing.assert_allclose(actual.T,q,atol=1.e-12)
