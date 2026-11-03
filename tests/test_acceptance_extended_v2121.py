"""Regression boundaries for the independent v2.12.0 acceptance findings."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import os
import numpy as np
import pytest
from ase.io import read

from lele.atom_indices import atom_mapping, index_order, reorder_atoms, source_order
from lele.appearance_workflow import apply_appearance, restore_appearance
from lele.core import Document, Frame
from lele.formats import export_frame, load_document
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.site_occupancy import composition
from lele.trajectory_analysis import DisplayAlignment, GeometryParameter, parameter_values
from lele.vacuum import change_vacuum, slab_vacuum
from lele.vasp_constraints import read_fixed_axes
from test_acceptance_v2121 import CIF, POSCAR, slab, trajectory
from test_periodic_fragment_ui_v171 import gui


def roundtrip_project(tmp_path, frame, **entry_values):
    doc=Document(Path('source'), 'test', [frame]) if isinstance(frame,Frame) else frame
    path=tmp_path/'session.lele'
    state=dict(documents=[dict(document=doc, options=RenderOptions(), frame_index=0, **entry_values)], current_document=0)
    save_project(path,state)
    return load_project(path)['documents'][0]


@pytest.mark.parametrize('kind', ['boundary','inversion','special_position'])
def test_equivalent_cif_components_survive_export_and_redundant_representatives(tmp_path,kind):
    head=CIF.split('Co1 Co')[0]
    if kind=='boundary':
        rows='Co1 Co 0 .5 .25 .6\nCo2 Co 1 .5 .25 .6\nNi1 Ni -1 .5 .25 .4\n';count=1
    else:
        head=head.replace("'P 1'","'P -1'").replace("'x,y,z'","'x,y,z'\n'-x,-y,-z'")
        if kind=='inversion':
            rows='Co1 Co .2 .5 .25 .6\nCo2 Co .8 .5 .75 .6\nNi1 Ni .8 .5 .75 .4\n';count=2
        else:
            rows='Co1 Co 0 .5 0 .6\nNi1 Ni 1 -.5 0 .4\n';count=1
    source=tmp_path/'equivalent.cif';source.write_text(head+rows)
    f=load_document(source).frames[0]
    assert len(f.symbols)==count
    assert f.info['site_occupancies']==[{'Co':.6,'Ni':.4}]*count
    out=tmp_path/'output.cif';export_frame(f,out,'cif');g=load_document(out).frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']
    assert composition(g)==composition(f)
    np.testing.assert_allclose(g.positions,f.positions,atol=1.e-10)


def test_conflicting_equivalent_occupancies_report_an_error(tmp_path):
    p=tmp_path/'conflict.cif'
    p.write_text(CIF.split('Co1 Co')[0]+'Co1 Co 0 .5 .25 .6\nCo2 Co 1 .5 .25 .7\n')
    with pytest.raises(ValueError,match='Conflicting occupancies'):load_document(p)


@pytest.mark.parametrize('occupancy',[False,True])
def test_unnamed_explicit_identity_import_with_and_without_occupancy(tmp_path,occupancy):
    text=CIF.replace("_space_group_name_H-M_alt 'P 1'\n",'')
    if not occupancy:
        text=text.split('Co1 Co')[0].replace('_atom_site_occupancy\n','')+'O1 O .2 .3 .4\nH1 H .3 .4 .5\n'
    p=tmp_path/'chemcraft.cif';p.write_text(text)
    f=load_document(p).frames[0]
    assert len(f.symbols)==2
    assert composition(f)==('Co0.5Fe0.15Ni0.3O' if occupancy else 'H1O1')


def test_nonidentity_operations_are_not_guessed_to_be_p1(tmp_path):
    p=tmp_path/'unknown_group.cif'
    p.write_text(CIF.replace("_space_group_name_H-M_alt 'P 1'\n",'').replace("'x,y,z'","'x,y,z'\n'-x,-y,-z'"))
    with pytest.raises(ValueError,match='nonidentity'):load_document(p)


@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian'])
@pytest.mark.parametrize('operation',['unchanged','vacuum','reindex'])
def test_selective_axis_flags_positions_and_atom_order_roundtrip(tmp_path,target,operation):
    p=tmp_path/'POSCAR';p.write_text(POSCAR);f=load_document(p).frames[0]
    expected=np.array([[True]*3,[False,True,False],[False]*3])
    np.testing.assert_array_equal(f.info['vasp_fixed_axes'],expected)
    if operation=='vacuum':change_vacuum(f,1,2)
    if operation=='reindex':
        order=index_order(3,0,2);reorder_atoms(f,order);expected=expected[order]
    out=tmp_path/'edited.POSCAR';export_frame(f,out,target)
    a=read(out,format='vasp');g=load_document(out).frames[0]
    assert g.symbols==f.symbols
    np.testing.assert_array_equal(read_fixed_axes(a),expected)
    np.testing.assert_array_equal(g.info['vasp_fixed_axes'],expected)
    np.testing.assert_allclose(g.positions,f.positions,atol=1.e-12)
    np.testing.assert_allclose(g.cell,f.cell,atol=1.e-12)


def test_explicit_all_free_selective_header_and_repeated_species_blocks(tmp_path):
    p=tmp_path/'POSCAR'
    p.write_text(POSCAR.replace('Ni O C\n','Ni O Ni\n').replace('F F F','T T T').replace('T F T','T T T'))
    f=load_document(p).frames[0]
    assert f.info['vasp_fixed_axes']==[[False]*3]*3
    out=tmp_path/'all_free.POSCAR';export_frame(f,out,'poscar-direct')
    text=out.read_text().splitlines()
    assert text[5].split()==['Ni','O','Ni'] and text[7]=='Selective dynamics'
    g=load_document(out).frames[0]
    assert g.info['vasp_fixed_axes']==f.info['vasp_fixed_axes']


def test_fixed_flags_follow_project_deletion_and_supercell(tmp_path):
    from lele.selection_geometry import delete_selected_atoms
    from lele.supercell import make_supercell
    p=tmp_path/'POSCAR';p.write_text(POSCAR);f=load_document(p).frames[0]
    reorder_atoms(f,[2,0,1])
    f=roundtrip_project(tmp_path,f)['document'].frames[0]
    assert f.info['vasp_fixed_axes']==[[False]*3,[True]*3,[False,True,False]]
    delete_selected_atoms(f,[0]);flags=f.info['vasp_fixed_axes']
    f=make_supercell(f,(2,1,1))
    out=tmp_path/'expanded.POSCAR';export_frame(f,out,'poscar-cartesian')
    assert read_fixed_axes(read(out,format='vasp'))==flags*2


@pytest.mark.parametrize('reference_index',[0,1])
def test_monitor_snapshot_tracks_identity_after_more_reindexing_and_project_reload(tmp_path,reference_index):
    doc=trajectory();reference=doc.frames[reference_index]
    atoms=(0,1) if reference_index==0 else (0,2)
    p=GeometryParameter('Distance',atoms,reference_order=source_order(reference),reference_symbols=tuple(reference.symbols))
    for frame,order in zip(doc.frames,([2,1,0],[1,0,2])):reorder_atoms(frame,order)
    state=roundtrip_project(tmp_path,doc,geometry_parameters=[p])
    restored=state['document'];saved=state['geometry_parameters'][0]
    np.testing.assert_allclose(parameter_values(restored,[1,0],saved,()),[2,2])


@pytest.mark.parametrize('invalid',[[0,0,2],[0,1,9],[0,1],[[0],1,2]])
def test_ambiguous_identity_mapping_does_not_color_or_measure_another_atom(invalid):
    doc=trajectory();doc.frames[1].info['atom_source_order']=invalid
    p=GeometryParameter('Distance',(0,1))
    assert atom_mapping(doc.frames[0],doc.frames[1]) is None
    assert np.isnan(parameter_values(doc,[0,1],p,doc.frames[0].symbols)[1])
    w=SimpleNamespace(doc=doc,frame=doc.frames[0],current_doc=0,frame_index=0,_vibration_references={},undo_stack=[],selection=[1],_active_vibration=None)
    apply_appearance(w,[1],{'color':'#123456'})
    assert doc.frames[0].atom_appearance[1].color=='#123456' and doc.frames[1].atom_appearance=={}


def test_appearance_reset_and_undo_use_each_target_mapping():
    doc=trajectory();w=SimpleNamespace(doc=doc,documents=[doc],frame=doc.frames[0],current_doc=0,frame_index=0,_vibration_references={},undo_stack=[],selection=[1],_active_vibration=None)
    apply_appearance(w,[1],{'color':'#123456'})
    apply_appearance(w,[1],{},reset=True)
    assert not any(f.atom_appearance for f in doc.frames)
    restore_appearance(w,0,w.undo_stack[-1][-1])
    assert doc.frames[0].atom_appearance[1].color==doc.frames[1].atom_appearance[2].color=='#123456'
    restore_appearance(w,0,w.undo_stack[0][-1])
    assert not any(f.atom_appearance for f in doc.frames)


def test_rigid_alignment_and_dipole_fit_follow_reindexed_atoms():
    from lele.gaussian_properties import vector_for_geometry
    original=Frame(['C','H','H','O'],[[0,0,0],[1,0,0],[0,2,0],[0,0,3]])
    edited=original.clone();rotation=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    edited.positions=edited.positions@rotation+[3,4,5];reorder_atoms(edited,[2,3,0,1])
    display,_,_=DisplayAlignment(original,(0,1,2,3)).apply(edited)
    np.testing.assert_allclose(display.positions[list(atom_mapping(original,edited))],original.positions,atol=1.e-12)
    np.testing.assert_allclose(vector_for_geometry(original,[1,2,3],edited),np.array([1,2,3])@rotation,atol=1.e-12)


def test_polyhedron_trajectory_follows_reindexed_center():
    from lele.polyhedron_analysis import polyhedron_series
    f=Frame(['Ti','O','Ti','O'],[[0,0,0],[1,0,0],[10,0,0],[12,0,0]])
    g=f.clone();reorder_atoms(g,[2,1,0,3])
    doc=Document(Path('polyhedron.xyz'),'XYZ',[f,g])
    options=RenderOptions(polyhedra_centers='Ti',polyhedra_ligands='O',polyhedra_search='Distance range',polyhedra_max_distance=3)
    rows=polyhedron_series(doc,options,0,reference=f)
    assert [r['status'] for r in rows]==['OK','OK']
    np.testing.assert_allclose([r['mean_length_A'] for r in rows],[1,1])
    assert [r['center'] for r in rows]==[0,2]


@pytest.mark.parametrize('legacy',[False,True])
def test_small_gap_surfaces_persist_in_projects_translation_rotation_and_reindex(tmp_path,legacy):
    f=slab();change_vacuum(f,1,2)
    if legacy:f.info['vacuum_adjustment'].pop('slab_surface_offsets')
    f=roundtrip_project(tmp_path,f)['document'].frames[0]
    assert slab_vacuum(f)['gap']==1
    f.positions+=[0,0,33];reorder_atoms(f,[2,0,1])
    if not legacy:
        rotation=np.array([[0,-1,0],[0,0,1],[1,0,0]])
        f.positions=f.positions@rotation;f.cell=f.cell@rotation
    for gap in (.5,0.,16.,1.):
        old=f.positions.copy();change_vacuum(f,gap)
        data=slab_vacuum(f)
        assert data['axis']==2 and data['gap']==pytest.approx(gap) and data['thickness']==4 and not data['split']
        np.testing.assert_array_equal(f.positions,old)


def test_small_gap_cache_is_invalidated_by_changes_in_surface_geometry():
    f=slab();change_vacuum(f,1,2);f.positions[1,2]+=.3
    assert slab_vacuum(f,2).get('surface_source')!='confirmed'


def test_confirming_rounded_displayed_vacuum_is_a_complete_gui_noop(gui):
    from PySide6.QtWidgets import QDialog
    from lele.structure_edit_dialogs import VacuumDialog
    f=slab();f.cell[2,2]+=0.123456789
    gui.attach(f);w=gui.window;original=w.frame
    original_positions=f.positions.copy();original_cell=f.cell.copy();original_info=dict(f.info)
    observed=[]
    def accept(dialog):
        observed.append((dialog.gap.value(),dialog.requested_gap()))
        return QDialog.DialogCode.Accepted
    with patch.object(VacuumDialog,'exec',accept):w.configure_vacuum()
    assert observed[0][0]!=observed[0][1]
    assert w.frame is original and not w.undo_stack and not w.doc.modified
    assert w.frame.info==original_info and w.frame.energy_ev==-12.34
    np.testing.assert_array_equal(w.frame.positions,original_positions)
    np.testing.assert_array_equal(w.frame.cell,original_cell)


def test_footer_aligns_from_real_layout_events_without_manual_sync(gui):
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    gui.attach(slab());w=gui.window;w.show()
    for width in (1100,1400,1600,1100):
        w.resize(width,850);QTest.qWait(120)
        assert abs(w.summary_label.mapToGlobal(QPoint()).x()-w.tabs.mapToGlobal(QPoint()).x())<=1
    # A longer selection measurement changes the same footer layout.
    gui.select([0,1]);QTest.qWait(120)
    assert abs(w.summary_label.mapToGlobal(QPoint()).x()-w.tabs.mapToGlobal(QPoint()).x())<=1


def test_gui_monitor_created_after_current_frame_reindex_keeps_identity(gui,tmp_path):
    from lele.geometry_curve_dialog import GeometryCurveDialog
    doc=trajectory();w=gui.window;w.documents=[doc];w.current_doc=0;w.change_frame(0);gui.select([0,1])
    dialog=GeometryCurveDialog(doc,w);gui.addCleanup(dialog.close)
    np.testing.assert_allclose(dialog.values[0],[2,2])
    w.apply_atom_index(1,2,swap=2);dialog.redraw()
    np.testing.assert_allclose(dialog.values[0],[2,2])
    state=roundtrip_project(tmp_path,doc,geometry_parameters=dialog.parameters)
    p=state['geometry_parameters'][0]
    np.testing.assert_allclose(parameter_values(state['document'],[0,1],p,()),[2,2])


def test_supplied_chemcraft_cif_without_spacegroup_metadata():
    path=os.environ.get('LELE_CHEMCRAFT_CIF_EXAMPLE')
    if not path:pytest.skip('Set LELE_CHEMCRAFT_CIF_EXAMPLE to the private 22.cif; it is not redistributed.')
    f=load_document(path).frames[0]
    assert len(f.symbols)==434 and composition(f)=='C4H6F4Mn140O280'


@pytest.mark.parametrize('operation',['unchanged','vacuum','reindex'])
def test_supplied_poscar1_preserves_all_selective_flags_and_rows(tmp_path,operation):
    directory=os.environ.get('LELE_ROTATION_EXAMPLE_DIR')
    if not directory:pytest.skip('Set LELE_ROTATION_EXAMPLE_DIR to the private POSCAR1/POSCAR2 directory.')
    source=Path(directory)/'POSCAR1';f=load_document(source).frames[0];flags=np.array(read_fixed_axes(read(source,format='vasp')))
    assert len(f.symbols)==100 and flags.all(axis=1).sum()==96
    if operation=='vacuum':
        d=slab_vacuum(f);change_vacuum(f,d['gap']+5,d['axis'])
    if operation=='reindex':
        order=index_order(len(f.symbols),0,99,swap=99);reorder_atoms(f,order);flags=flags[order]
    out=tmp_path/'edited.POSCAR';export_frame(f,out,'poscar-direct');g=load_document(out).frames[0]
    assert g.symbols==f.symbols
    np.testing.assert_array_equal(g.info['vasp_fixed_axes'],flags)
    np.testing.assert_allclose(g.positions,f.positions,atol=1.e-12)
