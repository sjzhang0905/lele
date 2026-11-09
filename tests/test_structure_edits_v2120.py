"""Occupancy probabilities, real atom indices, fixed-coordinate vacuum and UI."""
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from lele.core import Frame,Document,freeze_bonds
from lele.atom_appearance import AtomAppearance
from lele.formats import load_document,export_frame
from lele.site_occupancy import site_species,composition,is_disordered
from lele.chemical_analysis import electron_parity
from lele.atom_indices import index_order,reorder_atoms
from lele.vacuum import slab_vacuum,change_vacuum
from lele.boundary import boundary_view
from lele.supercell import make_supercell
from lele.selection_geometry import delete_selected_atoms
from lele.atom_clipboard import copy_atoms,read_atoms,paste_atoms
from lele.project_file import save_project,load_project
from lele.render_options import RenderOptions
from test_periodic_fragment_ui_v171 import gui

CIF='''data_partial
_cell_length_a 5
_cell_length_b 6
_cell_length_c 8
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 110
_space_group_name_H-M_alt 'P 1'
_space_group_IT_number 1
loop_
_space_group_symop_operation_xyz
'x,y,z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Fe1 Fe .1 .2 .3 .6
Ni1 Ni .1 .2 .3 .4
O1 O .5 .6 .7 .5
'''


def partial(tmp_path):
    p=tmp_path/'partial.cif';p.write_text(CIF);return load_document(p).frames[0]


def slab():
    return Frame(['Co','Se','S'],[[1.,1,3],[2,2,5],[3,1,7]],np.diag([5.,6,20]),(True,)*3,-10.,{'optimization_converged':True})


def test_cif_mixed_and_vacant_sites_are_not_integerized(tmp_path):
    f=partial(tmp_path)
    assert len(f.symbols)==2 and site_species(f,0)=={'Fe':.6,'Ni':.4} and site_species(f,1)=={'O':.5}
    assert is_disordered(f) and composition(f)=='Fe0.6Ni0.4O0.5'
    assert electron_parity(f).startswith('Unknown')
    np.testing.assert_allclose(f.positions,np.array([[.1,.2,.3],[.5,.6,.7]])@f.cell)
    p=tmp_path/'out.cif';export_frame(f,p,'cif');g=load_document(p).frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']
    np.testing.assert_allclose(g.cell@ g.cell.T,f.cell@f.cell.T,atol=1.e-11)


def test_cif_symmetry_expanded_sites_keep_their_occupancies(tmp_path):
    text=CIF.replace("'P 1'","'P -1'").replace('_space_group_IT_number 1','_space_group_IT_number 2').replace("'x,y,z'","'x,y,z'\n'-x,-y,-z'")
    p=tmp_path/'symmetric.cif';p.write_text(text);f=load_document(p).frames[0]
    assert len(f.symbols)==4
    assert f.info['site_occupancies']==[{'Fe':.6,'Ni':.4}]*2+[{'O':.5}]*2


@pytest.mark.parametrize('target',['xyz','poscar-direct','poscar-cartesian','gjf'])
def test_nonoccupancy_formats_do_not_silently_export_a_fully_occupied_model(tmp_path,target):
    with pytest.raises(ValueError,match='Fractional'):export_frame(partial(tmp_path),tmp_path/'bad',target)
    assert not (tmp_path/'bad').exists()


def test_occupancy_survives_boundary_supercell_delete_clipboard_and_projects(tmp_path):
    f=partial(tmp_path)
    b=boundary_view(f,((0,2),(0,1),(0,1))).frame
    assert b.info['site_occupancies']==f.info['site_occupancies']*2
    s=make_supercell(f,(2,1,1));assert s.info['site_occupancies']==f.info['site_occupancies']*2
    delete_selected_atoms(s,[1]);assert s.info['site_occupancies']==[{'Fe':.6,'Ni':.4}]*2+[{'O':.5}]
    text,data=copy_atoms(f,[1]);fragment=read_atoms(text,data);assert fragment.info['site_occupancies']==[{'O':.5}]
    paste_atoms(f,fragment,[10,10,10]);assert f.info['site_occupancies'][-1]=={'O':.5}
    path=tmp_path/'partial.lele'
    doc=Document(tmp_path/'p.cif','CIF',[f]);save_project(path,dict(documents=[dict(document=doc,options=RenderOptions(),frame_index=0)],current_document=0))
    g=load_project(path)['documents'][0]['document'].frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']


def test_reindex_moves_all_atom_properties_and_preserves_physical_paths(tmp_path):
    f=partial(tmp_path);f.energy_ev=-3;f.atom_appearance={0:AtomAppearance(color='#123456')}
    f.bond_added={(0,1)};f.bond_snapshot=frozenset({(0,1)});f.periodic_bond_snapshot=((0,1,(1,0,0)),)
    f.hbond_added={(0,1):(1,0,0)};f.info['qe_forces_ev_ang']=np.array([[1,2,3],[4,5,6]])
    old=f.clone();mapping=reorder_atoms(f,index_order(2,0,1,swap=1))
    assert mapping=={1:0,0:1} and f.symbols==old.symbols[::-1] and f.energy_ev==-3
    np.testing.assert_array_equal(f.positions,old.positions[::-1]);np.testing.assert_array_equal(f.cell,old.cell)
    assert f.atom_appearance[1].color=='#123456' and f.info['site_occupancies']==old.info['site_occupancies'][::-1]
    assert f.periodic_bond_snapshot==((0,1,(-1,0,0)),) and f.hbond_added=={(0,1):(-1,0,0)}
    np.testing.assert_array_equal(f.info['qe_forces_ev_ang'],old.info['qe_forces_ev_ang'][::-1])


def test_move_index_shifts_intermediate_indices_and_export_preserves_order(tmp_path):
    f=slab();old=f.clone();mapping=reorder_atoms(f,index_order(3,0,2))
    assert f.symbols==['Se','S','Co'] and mapping[0]==2
    np.testing.assert_array_equal(f.positions,old.positions[[1,2,0]])
    p=tmp_path/'POSCAR';export_frame(f,p,'poscar-cartesian');g=load_document(p).frames[0]
    assert g.symbols==f.symbols;np.testing.assert_allclose(g.positions,f.positions,atol=1.e-12)


@pytest.mark.parametrize('order',[[0,0,2],[1,0],[0,1,4]])
def test_invalid_reindex_is_not_a_partial_mutation(order):
    f=slab();old=f.clone()
    with pytest.raises(ValueError):reorder_atoms(f,order)
    np.testing.assert_array_equal(f.positions,old.positions);assert f.symbols==old.symbols


@pytest.mark.parametrize('gap',[4.,12.,30.])
def test_vacuum_changes_only_cell_normal_and_keeps_every_cartesian_coordinate(gap):
    f=slab();old=f.clone();data=slab_vacuum(f)
    assert data['axis']==2 and data['gap']==16 and data['thickness']==4 and not data['split']
    change_vacuum(f,gap)
    np.testing.assert_array_equal(f.positions,old.positions);np.testing.assert_array_equal(f.cell[:2],old.cell[:2])
    np.testing.assert_allclose(f.cell[2],[0,0,4+gap]);assert f.pbc==old.pbc and f.symbols==old.symbols
    assert f.energy_ev is None and not f.info.get('optimization_converged')


def test_skew_and_rotated_slab_use_true_surface_normal():
    f=slab();f.cell=np.array([[5.,0,0],[1,6,0],[2,3,25]])
    r=np.array([[0.,0,1],[1.,0,0],[0,1.,0]])
    f.cell=f.cell@r;f.positions=f.positions@r;old=f.clone()
    d=slab_vacuum(f);assert d['axis']==2 and d['gap']==21
    change_vacuum(f,10.)
    np.testing.assert_array_equal(f.positions,old.positions)
    np.testing.assert_allclose(f.cell[2],[2,3,14]@r)
    np.testing.assert_allclose(f.cell[:2],old.cell[:2])


def test_wrapped_slab_is_detected_without_secretly_moving_atoms():
    f=slab();f.positions[:,2]=[19,0,1];old=f.clone();d=slab_vacuum(f,2)
    assert d['gap']==18 and d['split']
    with pytest.raises(ValueError,match='crosses'):change_vacuum(f,8.,2)
    np.testing.assert_array_equal(f.positions,old.positions);np.testing.assert_array_equal(f.cell,old.cell)


@pytest.mark.parametrize('gap',[-1,float('nan'),float('inf')])
def test_invalid_vacuum_cannot_modify_cell(gap):
    f=slab();old=f.cell.copy()
    with pytest.raises(ValueError):change_vacuum(f,gap)
    np.testing.assert_array_equal(f.cell,old)


def test_selected_outline_is_a_dashed_camera_facing_ring_and_keeps_original_colors():
    from vtkmodules.vtkRenderingCore import vtkRenderer,vtkFollower
    from lele.renderer import MoleculeRenderer
    draw=MoleculeRenderer(vtkRenderer());f=slab();draw.selected=[0];color=draw.atom_color(f,0);draw.set_scene(f)
    actor,=draw.atom_highlights
    assert isinstance(actor,vtkFollower) and not actor.GetPickable() and actor.GetProperty().GetLineWidth()>=3
    mesh=actor.GetMapper().GetInput();assert mesh.GetNumberOfPolys()==0 and mesh.GetNumberOfLines()==32
    assert draw.atom_color(f,0)==color
    assert all(abs(mesh.GetPoint(i)[2])<1.e-12 for i in range(mesh.GetNumberOfPoints()))


def test_partial_renderer_uses_fractional_sectors_and_legend_contains_minor_species(tmp_path):
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from vtkmodules.vtkFiltersSources import vtkSphereSource
    from lele.renderer import MoleculeRenderer
    from lele.atom_legend import legend_samples
    f=partial(tmp_path);draw=MoleculeRenderer(vtkRenderer());draw.set_scene(f)
    sectors=[item[0] for item in draw._keepalive if isinstance(item,tuple) and len(item)==2 and isinstance(item[0],vtkSphereSource)]
    fractions=sorted(round((s.GetEndTheta()-s.GetStartTheta())/360,8) for s in sectors)
    assert fractions==[.4,.5,.5,.6]
    assert [x['symbol'] for x in legend_samples(draw)]==['Fe','Ni','O']


def test_gui_right_click_set_index_swap_and_undo(gui):
    from PySide6.QtWidgets import QDialog
    from lele.structure_edit_dialogs import AtomIndexDialog
    f=slab();gui.attach(f);w=gui.window;old=w.frame.clone();gui.select([0])
    w.vtk.resize(600,400);w.vtk.GetRenderWindow().SetSize(600,400)
    def set_index(dialog):dialog.index.setValue(3);return QDialog.DialogCode.Accepted
    with patch.object(w.renderer,'pick_index',return_value=0),patch.object(AtomIndexDialog,'exec',set_index):w._atom_context_from_canvas(50,50)
    assert w.frame.symbols==['Se','S','Co'] and w.selection==[2] and w.frame.energy_ev==-10
    w.undo_edit();assert w.frame.symbols==old.symbols
    gui.select([0,1])
    def swap(dialog):dialog.operation='swap';return QDialog.DialogCode.Accepted
    with patch.object(w.renderer,'pick_index',return_value=0),patch.object(AtomIndexDialog,'exec',swap):w._atom_context_from_canvas(50,50)
    assert w.frame.symbols==['Se','Co','S']
    w.undo_edit();np.testing.assert_array_equal(w.frame.positions,old.positions)
    with patch.object(w.renderer,'pick_index',return_value=None):w._atom_context_from_canvas(50,50)
    assert w.selection==[]


def test_gui_vacuum_preserves_coordinates_and_undo_restores_cell_and_energy(gui):
    from PySide6.QtWidgets import QDialog
    from lele.structure_edit_dialogs import VacuumDialog
    gui.attach(slab());w=gui.window;old=w.frame.clone()
    def accept(dialog):dialog.gap.setValue(8);return QDialog.DialogCode.Accepted
    with patch.object(VacuumDialog,'exec',accept):w.configure_vacuum()
    np.testing.assert_array_equal(w.frame.positions,old.positions);assert w.frame.cell[2,2]==12
    assert w.frame.energy_ev is None and 'Vacuum' in w.statusBar().currentMessage()
    w.undo_edit();np.testing.assert_array_equal(w.frame.cell,old.cell);assert w.frame.energy_ev==-10


def test_gui_fractional_composition_and_footer_left_edge_tracks_coordinate_tabs(gui,tmp_path):
    from PySide6.QtCore import QPoint
    gui.attach(partial(tmp_path));w=gui.window
    assert 'Fe0.6Ni0.4O0.5' in w.summary_label.text() and 'electrons unknown' in w.summary_label.text()
    for width in (1280,1600,1100):
        w.resize(width,850);w.show()
        for _ in range(3):gui.app.processEvents();w._align_summary_footer()
        left=w.lower_splitter.mapToGlobal(QPoint(0,0)).x();actual=w.summary_label.mapToGlobal(QPoint(0,0)).x()
        assert abs(left-actual)<=1
