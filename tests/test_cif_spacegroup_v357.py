"""CIF screw-axis spellings retain the explicitly supplied crystal model."""
from collections import Counter
from pathlib import Path
import os

import numpy as np
import pytest
from ase.io.cif import parse_cif
from ase.spacegroup.spacegroup import SpacegroupNotFoundError, parse_sitesym

from lele.cif_input import normalize_hm_symbol, read_cif_atoms, unit_fractions
from lele.formats import load_document


CIF = '''data_alias
_cell_length_a 8
_cell_length_b 7
_cell_length_c 6
_cell_angle_alpha 90
_cell_angle_beta 105
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P2(1)/c'
loop_
_symmetry_equiv_pos_as_xyz
'x,y,z'
'-x,y+1/2,-z+1/2'
'-x,-y,-z'
'x,-y-1/2,z-1/2'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
C1 C .137 .213 .359 .4
N1 N .137 .213 .359 .6
O1 O 0 0 0 1
H1 H .271 .367 .419 1
'''


@pytest.mark.parametrize('alias,canonical',[
    ('P2(1)/c','P21/c'),('P 2_1/c','P 21/c'),
    ('P2(1)2(1)2(1)','P212121'),('P2_12_12_1','P212121'),
    ('P 3(1) 2 1','P 31 2 1'),('P 3_2 1 2','P 32 1 2'),
    ('P4(1)','P41'),('P4_2/n','P42/n'),('P4(3)','P43'),
    ('P 6(3)/m','P 63/m'),('P6_5','P65'),
])
def test_normalize_only_screw_axis_notation(alias,canonical):
    assert normalize_hm_symbol(alias)==canonical


@pytest.mark.parametrize('symbol',['P2(2)/c','P3_3','P4(4)','P6_6','P 2(1)/nonsense','P 21/c'])
def test_invalid_axes_and_other_text_are_not_reinterpreted(symbol):
    expected='P 21/nonsense' if symbol=='P 2(1)/nonsense' else symbol
    assert normalize_hm_symbol(symbol)==expected


@pytest.mark.parametrize('tag',['_symmetry_space_group_name_H-M','_space_group_name_H-M_alt'])
@pytest.mark.parametrize('symbol',['P2(1)/c','P 2_1/c','P 21/c'])
def test_alias_has_identical_sites_cell_and_occupancies(tmp_path,tag,symbol):
    canonical=tmp_path/'canonical.cif';canonical.write_text(CIF.replace('P2(1)/c','P 21/c'))
    source=tmp_path/'alias.cif'
    text=CIF.replace('_symmetry_space_group_name_H-M',tag).replace('P2(1)/c',symbol)
    source.write_text(text)
    a=load_document(source).frames[0];b=load_document(canonical).frames[0]
    assert len(a.symbols)==10 and a.symbols==b.symbols
    np.testing.assert_allclose(a.positions,b.positions,atol=1.e-12)
    np.testing.assert_array_equal(a.cell,b.cell)
    assert a.info['site_occupancies']==b.info['site_occupancies']
    assert a.info['site_occupancies'][:4]==[{'C':.4,'N':.6}]*4
    assert source.read_text()==text
    atoms=read_cif_atoms(source)
    operations=list(parse_cif(str(source)))[0]._get_sitesym()
    rotations,translations=parse_sitesym(operations)
    np.testing.assert_array_equal(atoms.info['spacegroup'].rotations,rotations)
    np.testing.assert_array_equal(atoms.info['spacegroup'].translations,translations)


def test_valid_alias_without_explicit_operations_uses_same_database_group(tmp_path):
    section=CIF[CIF.index('loop_'):CIF.index('loop_\n_atom_site_label')]
    source=tmp_path/'no_operations.cif';source.write_text(CIF.replace(section,''))
    atoms=read_cif_atoms(source)
    assert atoms.info['spacegroup'].no==14
    assert len(atoms)==10


@pytest.mark.parametrize('symbol',['P2(9)/c','P 2(1)/nonsense','unrecognized'])
def test_unknown_group_does_not_fall_back_to_p1(tmp_path,symbol):
    source=tmp_path/'bad.cif';source.write_text(CIF.replace('P2(1)/c',symbol))
    with pytest.raises(SpacegroupNotFoundError):read_cif_atoms(source)


def test_supplied_dpa_cif_matches_explicit_operations(tmp_path):
    name=os.environ.get('LELE_DPA_CIF_EXAMPLE')
    if not name:pytest.skip('Set LELE_DPA_CIF_EXAMPLE to the supplied private DPA CIF.')
    source=Path(name);original=source.read_bytes()
    frame=load_document(source).frames[0]
    assert len(frame.symbols)==88 and Counter(frame.symbols)=={'C':52,'H':36}
    assert frame.pbc==(True,True,True)
    canonical=tmp_path/'canonical.cif'
    canonical.write_text(source.read_text().replace('P2(1)/c',"'P 21/c'"))
    expected=load_document(canonical).frames[0]
    np.testing.assert_array_equal(frame.cell,expected.cell)
    np.testing.assert_allclose(frame.positions,expected.positions,atol=1.e-12)
    assert frame.symbols==expected.symbols
    block=list(parse_cif(str(source)))[0]
    raw=block.get_unsymmetrized_structure()
    rotations,translations=parse_sitesym(block._get_sitesym())
    generated=[]
    for point in raw.get_scaled_positions(wrap=False):
        orbit=unit_fractions(np.einsum('nij,j->ni',rotations,point)+translations)
        generated.extend(orbit)
    # This sample's 22 asymmetric atoms each occupy general positions.
    actual=unit_fractions(frame.positions@np.linalg.inv(frame.cell))
    expected=np.asarray(generated)
    delta=actual[:,None,:]-expected[None,:,:]
    delta-=np.rint(delta)
    assert np.all(np.min(np.max(np.abs(delta),axis=2),axis=1)<1.e-10)
    assert source.read_bytes()==original
