"""Independent acceptance of the v2.12.1 fixes and v2.13.0 changes."""
import os
import re
from pathlib import Path

import numpy as np
import pytest
from ase.io.cif import parse_cif

from lele.atom_clipboard import paste_atoms
from lele.atom_indices import index_order, reorder_atoms, source_order
from lele.core import Document, Frame
from lele.formats import export_frame, load_document
from lele.selection_geometry import delete_selected_atoms
from lele.trajectory_analysis import GeometryParameter, parameter_values
from lele.vacuum import change_vacuum, slab_vacuum

HEADER = """data_delta
_cell_length_a 5
_cell_length_b 6
_cell_length_c 7
_cell_angle_alpha {alpha}
_cell_angle_beta {beta}
_cell_angle_gamma {gamma}
_space_group_IT_number 1
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
"""


def make_cif(path, rows, angles=(90,90,90)):
    path.write_text(HEADER.format(alpha=angles[0], beta=angles[1], gamma=angles[2]) + rows)
    return path


@pytest.mark.parametrize('angles',[(90,90,90),(76,88,105)])
def test_equivalent_boundary_site_in_skew_cell(tmp_path, angles):
    rows = 'Co1 Co 0 .5 .25 .6\nNi1 Ni 0 .5 .25 .4\nO1 O .4 .3 .2 1\n'
    f = load_document(make_cif(tmp_path/'face.cif',rows,angles)).frames[0]
    assert f.info['site_occupancies'] == [{'Co':.6,'Ni':.4},{'O':1.}]


def test_three_component_occupancy_survives_saved_cif(tmp_path):
    rows = ('Co1 Co .25 .5 .25 .1666667\nNi1 Ni .25 .5 .25 .1666667\n'
            'Fe1 Fe .25 .5 .25 .6666666\nO1 O .75 .5 .4 1\n')
    f=load_document(make_cif(tmp_path/'mixture.cif',rows)).frames[0]
    expected={'Co':.1666667,'Ni':.1666667,'Fe':.6666666}
    assert f.info['site_occupancies'][0]==expected
    out=tmp_path/'out.cif';export_frame(f,out,'cif')
    reread=load_document(out).frames[0]
    for s,v in expected.items():
        assert reread.info['site_occupancies'][0][s]==pytest.approx(v,abs=1e-8)


def test_append_after_a_mixed_site_preserves_raw_cif_row_order(tmp_path):
    rows='Co1 Co .1 .2 .3 .6\nNi1 Ni .1 .2 .3 .4\nO1 O .3 .4 .5 1\n'
    f=load_document(make_cif(tmp_path/'start.cif',rows)).frames[0]
    paste_atoms(f,Frame(['H'],[[0.,0.,0.]]),[2,3,3])
    path=tmp_path/'add.cif';export_frame(f,path,'cif')
    g=load_document(path).frames[0]
    assert g.symbols==['Co','O','H']  # Site order and raw atom-loop rows are distinct.
    assert next(parse_cif(str(path)))['_atom_site_type_symbol']==['Co','Ni','O','H']


POSCAR="""repeated carbon blocks
1
10 0 0
0 10 0
0 0 20
C C O
1 1 2
Selective dynamics
Cartesian
1 1 1 F F F
2 1 1 T F T
3 2 1 T T T
4 2 3 T T T
"""


@pytest.mark.parametrize('swap', [False,True])
def test_unedited_blocks_survive_swapping_two_other_atoms(tmp_path,swap):
    path=tmp_path/'POSCAR';path.write_text(POSCAR)
    f=load_document(path).frames[0]
    if swap:reorder_atoms(f,index_order(4,2,3,swap=3))
    out=tmp_path/'edited.POSCAR';export_frame(f,out,'poscar-direct')
    lines=out.read_text().splitlines()
    assert (lines[5].split(),lines[6].split()) == (['C','C','O'],['1','1','2'])


@pytest.mark.parametrize('replace_last_atom',[False,True])
def test_unchanged_h_identity_after_editing_unrelated_carbon(replace_last_atom):
    initial=Frame(['O','H','H','C'],[[0,0,0],[1,0,0],[0,2,0],[5,5,0]])
    doc=Document(Path('same.xyz'),'XYZ',[initial.clone(),initial.clone()])
    f=doc.frames[0];reorder_atoms(f,index_order(4,1,2,swap=2))
    probe=GeometryParameter('Distance',(0,1),reference_symbols=tuple(f.symbols),
                            reference_order=source_order(f))
    if replace_last_atom:
        delete_selected_atoms(f,[3]);paste_atoms(f,Frame(['C'],[[0,0,0]]),[5,5,0])
    curve=parameter_values(doc,[0,1],probe,f.symbols)
    # A monitor must never return the distance to the other H.
    assert np.all(np.isnan(curve) | np.isclose(curve,2.)),curve


def test_palette_against_original_tcl():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.renderer import MoleculeRenderer
    from lele.atom_legend import legend_samples
    path=os.environ.get('QA_SIBYL_TCL')
    if not path:pytest.skip('Set QA_SIBYL_TCL to the original Sibyl.tcl')
    source=Path(path).read_text()
    colors={int(i):tuple(map(float,(r,g,b))) for i,r,g,b in
            re.findall(r'^color change rgb (\d+) ([\d.]+) ([\d.]+) ([\d.]+)$',source,re.M)}
    pairs=re.search(r'set elem_color_list\s*\{([^}]+)\}',source).group(1).split()
    expected={s:'#'+''.join(f'{round(255*v):02X}' for v in colors[int(i)]) for s,i in zip(pairs[::2],pairs[1::2])}
    assert len(expected)==111
    draw=MoleculeRenderer(vtkRenderer());symbols=list(expected)
    f=Frame(symbols,[[n*5,0,0] for n in range(len(symbols))])
    draw.set_scene(f)
    assert {s:draw.atom_color(f,i) for i,s in enumerate(symbols)}==expected
    assert {s:draw.atom_color(f,i,for_bond=True) for i,s in enumerate(symbols)}==expected
    assert {sample['symbol']:sample['color'] for sample in legend_samples(draw)}==expected


@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian'])
def test_user_poscar_vacuum_append_and_export(tmp_path,target):
    directory=os.environ.get('LELE_ROTATION_EXAMPLE_DIR')
    if not directory:pytest.skip('Set LELE_ROTATION_EXAMPLE_DIR to the original POSCAR1 folder')
    f=load_document(Path(directory)/'POSCAR1').frames[0]
    before=f.clone()
    assert np.all(f.info['vasp_fixed_axes'],axis=1).sum()==96
    d=slab_vacuum(f);change_vacuum(f,d['gap']+5,d['axis'])
    for batch,at in [(['H','O'],[4,4,12]),(['H','Li'],[8,6,14])]:
        paste_atoms(f,Frame(batch,[[0,0,0],[.2,1.4,0]]),at)
    out=tmp_path/'export.POSCAR';export_frame(f,out,target)
    g=load_document(out).frames[0]
    assert g.symbols==before.symbols+['H','O','H','Li']
    np.testing.assert_allclose(g.positions[:100],before.positions,atol=1e-10)
    assert g.info['vasp_fixed_axes']==before.info['vasp_fixed_axes']+[[False]*3]*4
