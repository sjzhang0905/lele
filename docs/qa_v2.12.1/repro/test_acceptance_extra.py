"""Independent LELE v2.12.0 acceptance cases. Run with the source root on PYTHONPATH."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from ase.io import read
from lele.core import Frame, Document
from lele.formats import load_document, export_frame
from lele.vacuum import change_vacuum, slab_vacuum
from lele.atom_indices import reorder_atoms, index_order
from lele.trajectory_analysis import GeometryParameter, parameter_values
from lele.appearance_workflow import apply_appearance
from lele.site_occupancy import composition, is_disordered


def trajectory():
    original = Frame(['O','H','H'], [[0,0,0],[1,0,0],[0,2,0]])
    doc = Document(Path('two.xyz'), 'XYZ', [original.clone(), original.clone()])
    reorder_atoms(doc.frames[0], index_order(3, 1, 2, swap=2))
    return doc


def slab():
    return Frame(['Ni','O','C'], [[1,1,3],[2,2,5],[3,1,7]],
                 np.diag([5.,6.,20.]), (True,)*3, -12.34,
                 {'optimization_converged': True})


def test_reindexed_atom_keeps_trajectory_monitor_identity():
    doc = trajectory()
    # Row #2 in the edited reference is now H at (0,2,0); both frames are identical.
    p = GeometryParameter('Distance', (0,1))
    distances = parameter_values(doc, (0,1), p, doc.frames[0].symbols)
    np.testing.assert_allclose(distances, [2,2])


def test_reindexed_atom_keeps_document_wide_color_identity():
    doc = trajectory()
    w = SimpleNamespace(doc=doc, frame=doc.frames[0], current_doc=0, frame_index=0,
                        _vibration_references={}, undo_stack=[], selection=[1], _active_vibration=None)
    apply_appearance(w,[1],{'color':'#123456'})
    actual = [dict((i+1, s.color) for i,s in f.atom_appearance.items()) for f in doc.frames]
    assert actual == [{2:'#123456'},{3:'#123456'}]


def test_small_vacuum_can_be_read_back_and_reset():
    f = slab()
    old = f.clone()
    change_vacuum(f,1,2)
    np.testing.assert_array_equal(f.positions,old.positions)
    assert f.cell[2,2] == 5.
    view = slab_vacuum(f,2)
    assert (view['gap'], view['thickness'], view['split']) == (1.,4.,False)
    change_vacuum(f,16,2)
    np.testing.assert_array_equal(f.cell,old.cell)


def test_confirming_current_vacuum_preserves_results():
    f=slab()
    old=f.clone()
    change_vacuum(f,slab_vacuum(f,2)['gap'],2)
    np.testing.assert_array_equal(f.cell,old.cell)
    assert (f.energy_ev, f.info.get('optimization_converged')) == (-12.34,True)


POSCAR = """slab with fixed bottom atoms
1.0
5 0 0
0 6 0
0 0 20
Ni O C
1 1 1
Selective dynamics
Cartesian
1 1 3 F F F
2 2 5 T F T
3 1 7 T T T
"""


def write_poscar(tmp_path):
    p = tmp_path/'POSCAR'
    p.write_text(POSCAR)
    assert len(read(p,format='vasp').constraints) == 2
    return p


@pytest.mark.parametrize('operation', ['vacuum','reindex'])
def test_poscar_constraints_survive_edit_and_export(tmp_path,operation):
    f=load_document(write_poscar(tmp_path)).frames[0]
    if operation=='vacuum':
        change_vacuum(f,12,2)
    else:
        reorder_atoms(f,index_order(3,0,2))
    p=tmp_path/'results.POSCAR'
    export_frame(f,p,'poscar-cartesian')
    g=read(p,format='vasp')
    assert len(g.constraints) == 2, p.read_text()


def test_poscar_vacuum_roundtrip_preserves_atom_order(tmp_path):
    f = load_document(write_poscar(tmp_path)).frames[0]
    change_vacuum(f,12,2)
    p = tmp_path/'results.POSCAR'
    export_frame(f,p,'poscar-cartesian')
    g=load_document(p).frames[0]
    assert g.symbols==f.symbols
    np.testing.assert_array_equal(g.positions,f.positions)


def test_ordinary_vacuum_roundtrip(tmp_path):
    f=slab(); old=f.clone()
    change_vacuum(f,10.,2)
    assert slab_vacuum(f,2)['gap']==10
    cell=old.cell.copy();cell[2,2]=14.
    np.testing.assert_array_equal(f.positions,old.positions)
    np.testing.assert_array_equal(cell,f.cell)
    assert f.energy_ev is None


CIF = """data_qa
_cell_length_a 8
_cell_length_b 8
_cell_length_c 20
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
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
Co1 Co .25 .5 .25 .50
Ni1 Ni .25 .5 .25 .30
Fe1 Fe .25 .5 .25 .15
O1 O .75 .5 .40 1
"""


def test_three_component_site_with_vacancy_and_full_site(tmp_path):
    p=tmp_path/'mixture.cif';p.write_text(CIF)
    f=load_document(p).frames[0]; assert len(f.symbols)==2 and is_disordered(f)
    assert composition(f)=='Co0.5Fe0.15Ni0.3O'
    assert f.info['site_occupancies']==[{'Co':.5,'Ni':.3,'Fe':.15},{'O':1.}]
    out=tmp_path/'out.cif';export_frame(f,out,'cif')
    g=load_document(out).frames[0]
    assert g.info['site_occupancies']==f.info['site_occupancies']


@pytest.mark.parametrize('equivalence', ['periodic', 'inversion'])
def test_mixed_site_retains_species_under_equivalent_coordinates(tmp_path,equivalence):
    head=CIF.split('Co1 Co')[0]
    if equivalence=='periodic':
        # The two coordinates represent the same P1 site on the cell face.
        rows='Co1 Co 0 .5 .25 .6\nNi1 Ni 1 .5 .25 .4\n'
        count=1
    else:
        head=head.replace("'P 1'","'P -1'").replace("'x,y,z'", "'x,y,z'\n'-x,-y,-z'")
        rows='Co1 Co .2 .5 .25 .6\nNi1 Ni .8 .5 .75 .4\n'
        count=2
    p=tmp_path/'equivalent.cif';p.write_text(head+rows+'O1 O .75 .5 .4 1\n')
    f=load_document(p).frames[0]
    assert f.info['site_occupancies'][:count]==[{'Co':.6,'Ni':.4}]*count


def test_explicit_identity_operation_without_spacegroup_name(tmp_path):
    p=tmp_path/'symop_only.cif';p.write_text(CIF.replace("_space_group_name_H-M_alt 'P 1'\n",''))
    f=load_document(p).frames[0]
    assert composition(f)=='Co0.5Fe0.15Ni0.3O'
