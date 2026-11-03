"""Independent v2.13.1 acceptance. Run with PYTHONPATH=<LELE source>.

Scientific oracles are written in terms of invariants and source inputs rather
than implementation-specific helper output. No production source is modified.
"""
import itertools
import os
from pathlib import Path

import numpy as np
import pytest

from lele.core import Document, Frame
from lele.formats import export_frame, load_document
from lele.atom_clipboard import paste_atoms
from lele.atom_indices import reorder_atoms, source_order
from lele.selection_geometry import delete_selected_atoms
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.periodic_geometry import minimum_image
from lele.coordinate_reorientation import transform_complete_frame
from lele.trajectory_analysis import GeometryParameter

SOURCE = Path(os.environ.get('LELE_AUDIT_SOURCE', Path(__file__).resolve().parents[1]/'source/LELE'))
EXAMPLES = SOURCE/'examples'
CELL = np.array([[8.,0,0],[2.1,9,0],[-1.3,1.7,16.]])


def project_roundtrip(tmp_path, document):
    path=tmp_path/'portable.lele'
    save_project(path,dict(documents=[dict(document=document,options=RenderOptions())],current_document=0))
    return load_project(path)['documents'][0]['document']


@pytest.mark.parametrize('seed',range(8))
@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian'])
def test_poscar_combined_edits_keep_every_surviving_atom_and_constraint(tmp_path,seed,target):
    rng=np.random.default_rng(seed)
    symbols=['C','C','C','O','O','H','H','Ni']
    positions=rng.uniform(.1,.7,(8,3))@CELL
    flags=rng.choice([False,True],(8,3)).tolist()
    frame=Frame(symbols.copy(),positions.copy(),CELL.copy(),(True,)*3,
        info=dict(poscar_groups=[('C',1),('C',2),('O',2),('H',2),('Ni',1)],vasp_fixed_axes=flags))
    originals={i:(s,p.copy(),f) for i,(s,p,f) in enumerate(zip(symbols,positions,flags))}
    order=rng.permutation(8).tolist();reorder_atoms(frame,order)
    removed=sorted(rng.choice(8,3,replace=False).tolist());delete_selected_atoms(frame,removed)
    survivors=[order[i] for i in range(8) if i not in removed]
    paste_atoms(frame,Frame(['Fe','H'],[[0,0,0],[.2,.4,.7]]),[4,5,6])
    assert list(source_order(frame))[:5]==survivors
    order2=rng.permutation(7).tolist();reorder_atoms(frame,order2)
    restored=project_roundtrip(tmp_path,Document(Path('input.POSCAR'),'POSCAR',[frame])).frames[0]
    out=tmp_path/'edited.POSCAR';export_frame(restored,out,target)
    actual=load_document(out).frames[0]
    expected_symbols=[originals[i][0] for i in survivors]+['Fe','H']
    expected_pos=np.array([originals[i][1] for i in survivors]+[[4,5,6],[4.2,5.4,6.7]])
    expected_flags=[originals[i][2] for i in survivors]+[[False]*3]*2
    assert actual.symbols==[expected_symbols[i] for i in order2]
    np.testing.assert_allclose(actual.positions,expected_pos[order2],atol=2.e-12)
    assert actual.info['vasp_fixed_axes']==[expected_flags[i] for i in order2]
    np.testing.assert_allclose(actual.cell,CELL,atol=1.e-13)
    assert len(set(source_order(restored)))==7


@pytest.mark.parametrize('seed',range(6))
@pytest.mark.parametrize('pbc',[(True,True,True),(True,False,True),(False,True,False)])
def test_skew_minimum_image_matches_exhaustive_cartesian_oracle(seed,pbc):
    rng=np.random.default_rng(seed+123)
    cell=np.array([[4.,0,0],[3.7,2.2,0],[-1.4,1.5,6.]])
    frame=Frame(['H'],[[0,0,0]],cell,pbc)
    for _ in range(5):
        delta=rng.uniform(-1.5,1.5,3)@cell
        ranges=[range(-8,9) if periodic else [0] for periodic in pbc]
        translations=np.asarray(list(itertools.product(*ranges)))
        all_vectors=delta+translations@cell
        expected=np.linalg.norm(all_vectors,axis=1).min()
        vector,shift=minimum_image(delta,frame)
        assert np.linalg.norm(vector)==pytest.approx(expected,abs=2.e-12)
        np.testing.assert_allclose(vector,delta+np.asarray(shift)@cell,atol=1.e-12)
        assert all(s==0 for s,periodic in zip(shift,pbc) if not periodic)


@pytest.mark.parametrize('seed',range(6))
def test_rigid_reorientation_preserves_all_geometry_parameters_and_image_bonds(seed):
    rng=np.random.default_rng(seed+918)
    positions=rng.normal(size=(7,3))*2+5
    frame=Frame(['C']*7,positions,CELL.copy(),(True,)*3,
        periodic_bond_snapshot=((0,1,(1,-1,0)),(2,3,(0,0,1))))
    q,_=np.linalg.qr(rng.normal(size=(3,3)))
    if np.linalg.det(q)<0:q[:,0]*=-1
    parameters=[GeometryParameter('Distance',(0,1)),GeometryParameter('Angle',(0,1,2)),
        GeometryParameter('Dihedral',(0,1,2,3)),GeometryParameter('Plane angle',(0,1,2),(3,4,5)),
        GeometryParameter('Vector angle',(0,1),(3,4)),GeometryParameter('Point–plane distance',(6,),(0,1,2)),
        GeometryParameter('Point–line distance',(6,),(0,1)),GeometryParameter('Vector–plane angle',(0,1),(3,4,5))]
    before=[p.value(frame) for p in parameters]
    old_edges=[frame.positions[j]+np.asarray(s)@frame.cell-frame.positions[i] for i,j,s in frame.periodic_bond_snapshot]
    transform_complete_frame(frame,q,[10,-20,7])
    np.testing.assert_allclose([p.value(frame) for p in parameters],before,atol=1.e-10)
    for (i,j,s),old in zip(frame.periodic_bond_snapshot,old_edges):
        np.testing.assert_allclose(frame.positions[j]+np.asarray(s)@frame.cell-frame.positions[i],old@q.T,atol=1.e-12)


@pytest.mark.parametrize('name',[
    'water.xyz','water.gjf','water_trajectory.xyz','Si_POSCAR','boundary_demo.POSCAR',
    'periodic_water_boundary.POSCAR','selection_plane_demo.POSCAR','SrTiO3_polyhedra.POSCAR',
    'artificial_signed_field.cube','synthetic_opt_freq.log','synthetic_properties.log',
    'synthetic_orca_full_v190.out','synthetic_orca_analysis_v180.out','synthetic_neb_v1100.out',
    'synthetic_goat_v1100.out','synthetic_soc_v1100.out','synthetic_hessian_v1100.out',
    'synthetic_xtb_v1110.out','synthetic_gxtb_v1110.out','synthetic_xtb_energy_only_v1111.out',
    'synthetic_cp2k_v240.inp','synthetic_cp2k_v240.out','synthetic_cp2k_v240.xyz',
    'synthetic_vasp_v210.OUTCAR','synthetic_vasp_v210.OSZICAR',
    'synthetic_vasp_geometry_only_v210.XDATCAR','siesta_relax_demo.out','siesta_relax_demo.ANI'])
def test_independent_multiformat_import_project_reload_and_structure_exports(tmp_path,name):
    document=load_document(EXAMPLES/name)
    # A portable project must remain usable with every original input absent.
    document.path=tmp_path/'unavailable-original-input'/name
    assert not document.path.exists()
    for frame in document.frames:
        frame.positions=frame.positions.copy()
    restored=project_roundtrip(tmp_path,document)
    assert len(restored.frames)==len(document.frames)
    assert len(restored.vibrations)==len(document.vibrations)
    assert len(restored.dipoles)==len(document.dipoles)
    assert len(restored.electronic_spectra)==len(document.electronic_spectra)
    assert restored.calculation_results.program==document.calculation_results.program
    for old,new in zip(document.frames,restored.frames):
        assert new.symbols==old.symbols
        np.testing.assert_array_equal(new.positions,old.positions)
        np.testing.assert_array_equal(new.cell,old.cell)
        assert new.pbc==old.pbc
        assert new.energy_ev==old.energy_ev
    if restored.frames and restored.frames[0].symbols:
        frame=restored.frames[0];out=tmp_path/'copy.xyz';export_frame(frame,out,'xyz')
        actual=load_document(out).frames[0]
        assert actual.symbols==frame.symbols
        np.testing.assert_allclose(actual.positions,frame.positions,atol=5.e-9)
    if document.volume is not None:
        np.testing.assert_array_equal(restored.volume.data,document.volume.data)
        np.testing.assert_array_equal(restored.volume.voxel_vectors,document.volume.voxel_vectors)


CUBE='Synthetic field\nUnit test\n1 1 2 3\n{n} .5 0 0\n{n} 0 .5 0\n{n} 0 0 .5\n8 0 1.25 2.25 3.25\n0 1 2 3 4 5 6 7\n'


@pytest.mark.parametrize('n',[2,-2])
def test_cube_both_declared_unit_branches_load_complete_aligned_geometry_and_grid(tmp_path,n):
    # formats._cube_grid explicitly defines n<0 as Angstrom and n>0 as Bohr.
    from lele.formats import BOHR_ANG
    path=tmp_path/'unit.cube';path.write_text(CUBE.format(n=n))
    document=load_document(path);factor=BOHR_ANG if n>0 else 1.
    assert document.volume is not None,document.note
    np.testing.assert_allclose(document.frames[0].positions,[[1.25*factor,2.25*factor,3.25*factor]],atol=1.e-9)
    np.testing.assert_allclose(document.volume.origin,np.array([1,2,3])*factor,atol=1.e-9)
    np.testing.assert_allclose(document.volume.voxel_vectors,np.eye(3)*.5*factor,atol=1.e-9)
    assert document.volume.data.shape==(2,2,2)
