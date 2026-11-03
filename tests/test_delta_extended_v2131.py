"""Boundary, persistence and identity checks beyond the five independent cases."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from ase.io.cif import parse_cif

from lele.atom_clipboard import copy_atoms,read_atoms,paste_atoms
from lele.atom_indices import index_order,reorder_atoms,source_order
from lele.appearance_workflow import apply_appearance
from lele.core import Document,Frame
from lele.formats import export_frame,load_document
from lele.project_file import load_project,save_project
from lele.render_options import RenderOptions
from lele.selection_geometry import delete_selected_atoms
from lele.site_occupancy import site_species
from lele.supercell import make_supercell
from lele.trajectory_analysis import GeometryParameter,DisplayAlignment,parameter_values
from test_delta_acceptance_v2131 import make_cif,POSCAR
from test_periodic_fragment_ui_v171 import gui


MIXED='Co1 Co .1 .2 .3 .6\nNi1 Ni .1 .2 .3 .4\nO1 O .3 .4 .5 1\n'


def project(tmp_path,document,parameters=()):
    if isinstance(document,Frame):document=Document(Path('test'),'test',[document])
    path=tmp_path/'session.lele'
    save_project(path,dict(documents=[dict(document=document,options=RenderOptions(),geometry_parameters=list(parameters))],current_document=0))
    return load_project(path)['documents'][0]


def raw_symbols(path):return next(parse_cif(str(path)))['_atom_site_type_symbol']


@pytest.mark.parametrize('axis',[0,1,2])
@pytest.mark.parametrize('translation',[0,1])
def test_all_skew_cell_faces_and_periodic_aliases_roundtrip(tmp_path,axis,translation):
    p=[.2,.3,.4];p[axis]=0;q=p.copy();q[axis]=translation
    rows='Co1 Co '+' '.join(map(str,p))+' .6\nNi1 Ni '+' '.join(map(str,q))+' .4\n'
    f=load_document(make_cif(tmp_path/'face.cif',rows,(76,88,105))).frames[0]
    assert f.info['site_occupancies']==[{'Co':.6,'Ni':.4}]
    out=tmp_path/'out.cif';export_frame(f,out,'cif');g=load_document(out).frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']
    np.testing.assert_allclose(g.cell@g.cell.T,f.cell@f.cell.T,atol=1.e-12)


@pytest.mark.parametrize('weights',[(.1666667,.1666667,.6666666),(1/3,1/3,1/3),(.111111111111111,.2,.3)])
def test_occupancy_values_survive_repeated_exports_without_rounding_or_normalization(tmp_path,weights):
    rows=''.join(f'{s}1 {s} .2 .3 .4 {v!r}\n' for s,v in zip(('Co','Ni','Fe'),weights))
    f=load_document(make_cif(tmp_path/'probability.cif',rows)).frames[0]
    for count in range(3):
        out=tmp_path/f'round{count}.cif';export_frame(f,out,'cif')
        parsed=next(parse_cif(str(out)))
        assert parsed['_atom_site_occupancy']==list(weights)
        f=load_document(out).frames[0]
        assert f.info['site_occupancies']==[dict(zip(('Co','Ni','Fe'),weights))]


def test_overoccupied_input_is_still_rejected(tmp_path):
    rows='Co1 Co .1 .2 .3 .6\nNi1 Ni .1 .2 .3 .4001\n'
    with pytest.raises(ValueError,match='total occupancy'):load_document(make_cif(tmp_path/'invalid.cif',rows))


@pytest.mark.parametrize('interleaved',[False,True])
def test_source_component_order_and_multiple_additions_persist_in_projects(tmp_path,interleaved):
    rows=MIXED.splitlines()
    if interleaved:rows=[rows[0],rows[2],rows[1]]
    f=load_document(make_cif(tmp_path/'raw.cif','\n'.join(rows)+'\n')).frames[0]
    original=['Co','O','Ni'] if interleaved else ['Co','Ni','O']
    for s in ('H','C'):paste_atoms(f,Frame([s],[[0,0,0]]),[3+len(f.symbols),2,3])
    f=project(tmp_path,f)['document'].frames[0]
    out=tmp_path/'ordered.cif';export_frame(f,out,'cif')
    assert raw_symbols(out)==original+['H','C']
    g=load_document(out).frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']


@pytest.mark.parametrize('operation',['delete','reindex','clipboard','supercell','boundary'])
def test_component_metadata_follows_structural_edits_without_dropping_minor_species(tmp_path,operation):
    f=load_document(make_cif(tmp_path/'base.cif',MIXED)).frames[0]
    expected=['Co','Ni','O']
    if operation=='delete':delete_selected_atoms(f,[1]);expected=['Co','Ni']
    if operation=='reindex':reorder_atoms(f,[1,0]);expected=['O','Co','Ni']
    if operation=='clipboard':
        text,data=copy_atoms(f,[1,0]);fragment=read_atoms(text,data)
        f=Frame([],[],np.eye(3)*20,(True,)*3);paste_atoms(f,fragment,[5,5,5]);expected=['O','Co','Ni']
    if operation=='supercell':f=make_supercell(f,(2,1,1),wrap=False);expected*=2
    if operation=='boundary':
        from lele.boundary import boundary_view
        f=boundary_view(f,((0,2),(0,1),(0,1))).frame;expected*=2
    out=tmp_path/'edited.cif';export_frame(f,out,'cif')
    assert raw_symbols(out)==expected
    g=load_document(out).frames[0]
    assert sorted(tuple(sorted(site_species(g,i).items())) for i in range(len(g.symbols)))==sorted(tuple(sorted(site_species(f,i).items())) for i in range(len(f.symbols)))


def identity_document():
    f=Frame(['O','H','H','C'],[[0,0,0],[1,0,0],[0,2,0],[5,5,0]],np.eye(3)*20,(True,)*3)
    doc=Document(Path('same.xyz'),'XYZ',[f.clone(),f.clone()])
    reorder_atoms(doc.frames[0],[0,2,1,3])
    return doc


def probe(frame,atoms=(0,1)):
    return GeometryParameter('Distance',atoms,reference_order=source_order(frame),reference_symbols=tuple(frame.symbols))


@pytest.mark.parametrize('operation',['delete_c','replace_c','append_c'])
def test_old_and_new_oh_monitors_keep_two_angstrom_values_and_color_identity(tmp_path,operation):
    doc=identity_document();f=doc.frames[0];old=probe(f)
    if operation!='append_c':delete_selected_atoms(f,[3])
    if operation!='delete_c':paste_atoms(f,Frame(['C'],[[0,0,0]]),[5,5,0])
    new=probe(f)
    entry=project(tmp_path,doc,[old,new]);doc=entry['document'];f=doc.frames[0]
    for p in entry['geometry_parameters']:np.testing.assert_allclose(parameter_values(doc,[0,1],p,()),[2,2])
    w=SimpleNamespace(doc=doc,frame=f,current_doc=0,frame_index=0,_vibration_references={},undo_stack=[],selection=[1],_active_vibration=None)
    apply_appearance(w,[1],{'color':'#123456'})
    assert f.atom_appearance[1].color==doc.frames[1].atom_appearance[2].color=='#123456'
    assert 1 not in doc.frames[1].atom_appearance


def test_replacement_is_a_new_identity_even_at_the_same_element_and_position():
    doc=identity_document();f=doc.frames[0];old=probe(f,(0,3))
    original=source_order(f)[3];seen={original}
    for _ in range(4):
        delete_selected_atoms(f,[3]);paste_atoms(f,Frame(['C'],[[0,0,0]]),[5,5,0])
        identity=source_order(f)[3];assert identity not in seen;seen.add(identity)
        values=parameter_values(doc,[0,1],old,())
        assert np.isnan(values[0]) and values[1]==pytest.approx(np.sqrt(50))
        values=parameter_values(doc,[0,1],probe(f,(0,3)),())
        assert values[0]==pytest.approx(np.sqrt(50)) and np.isnan(values[1])


def test_reindexed_supercell_keeps_base_identities_without_aliasing_the_replicas():
    doc=identity_document();f=doc.frames[0];p=probe(f)
    expanded=make_supercell(f,(2,1,1),wrap=False)
    assert source_order(expanded)[:4]==source_order(f)
    assert len(set(source_order(expanded)))==8
    doc.frames[0]=expanded
    np.testing.assert_allclose(parameter_values(doc,[0,1],p,()),[2,2])


def test_alignment_uses_surviving_high_index_scaffold_after_low_index_deletion():
    reference=Frame(['C','H','O','N'],[[9,9,9],[0,0,0],[1,0,0],[0,2,0]])
    f=reference.clone();delete_selected_atoms(f,[0]);f.positions+=[4,5,6]
    displayed,_,_=DisplayAlignment(reference,(1,2,3)).apply(f)
    np.testing.assert_allclose(displayed.positions,reference.positions[1:],atol=1.e-12)


@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian'])
@pytest.mark.parametrize('operation',['swap_o','swap_c','split_and_restore'])
def test_duplicate_block_boundaries_and_axis_flags_survive_reordering_and_projects(tmp_path,target,operation):
    source=tmp_path/'POSCAR';source.write_text(POSCAR);f=load_document(source).frames[0]
    if operation=='swap_o':reorder_atoms(f,[0,1,3,2])
    if operation=='swap_c':reorder_atoms(f,[1,0,2,3])
    if operation=='split_and_restore':reorder_atoms(f,[0,2,1,3]);reorder_atoms(f,[0,2,1,3])
    f=project(tmp_path,f)['document'].frames[0]
    out=tmp_path/'edited.POSCAR';export_frame(f,out,target);lines=out.read_text().splitlines()
    assert lines[5].split()==['C','C','O'] and lines[6].split()==['1','1','2']
    g=load_document(out).frames[0]
    assert g.info['vasp_fixed_axes']==f.info['vasp_fixed_axes']
    np.testing.assert_allclose(g.positions,f.positions,atol=1.e-12)


def test_pasted_and_replicated_poscar_blocks_remain_distinct(tmp_path):
    source=tmp_path/'POSCAR';source.write_text(POSCAR);f=load_document(source).frames[0]
    paste_atoms(f,Frame(['O'],[[0,0,0]]),[5,5,5]);reorder_atoms(f,[0,1,3,2,4])
    assert f.info['poscar_groups']==[('C',1),('C',1),('O',2),('O',1)]
    f=make_supercell(f,(2,1,1),wrap=False);reorder_atoms(f,list(range(10)))
    out=tmp_path/'supercell.POSCAR';export_frame(f,out,'poscar-cartesian')
    assert load_document(out).frames[0].info['poscar_groups']==[('C',1),('C',1),('O',2),('O',1)]*2


def test_live_monitors_survive_unrelated_deletion_paste_and_undo(gui):
    from lele.geometry_curve_dialog import GeometryCurveDialog
    doc=identity_document();w=gui.window;w.documents=[doc];w.current_doc=0;w.change_frame(0)
    gui.select([0,1]);dialog=GeometryCurveDialog(doc,w);gui.addCleanup(dialog.close)
    np.testing.assert_allclose(dialog.values[0],[2,2])
    delete_selected_atoms(w.frame,[3]);w._refresh_after_geometry_edit();gui.select([0,1]);dialog.add_selection()
    for values in dialog.values:np.testing.assert_allclose(values,[2,2])
    w._pending_paste=Frame(['C'],[[0,0,0]])
    w.vtk.GetRenderWindow().SetSize(600,400)
    assert w._paste_at_click(w.vtk.width()/2,w.vtk.height()/2)
    dialog.redraw()
    for values in dialog.values:np.testing.assert_allclose(values,[2,2])
    w.undo_edit();dialog.redraw()
    for values in dialog.values:np.testing.assert_allclose(values,[2,2])
