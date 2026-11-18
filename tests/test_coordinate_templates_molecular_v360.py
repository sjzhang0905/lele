"""Only explicit structure records change in reusable calculation inputs."""
from pathlib import Path
import re

import numpy as np
import pytest

from lele.core import Frame
from lele.coordinate_templates_molecular import replace_molecular_coordinates, BOHR_ANG
from lele.formats import load_document


GJF = '%chk=keep.chk\r\n%mem=4GB\r\n#p B3LYP/6-31G(d) opt\r\n\r\nKeep this title\r\n\r\n0 1\r\n  O   0.0   0.0   0.0\r\n  H   0.0   0.0   1.0\r\n\r\n'
ORCA = '! PBE def2-SVP TightSCF\n%pal nprocs 4 end\n%maxcore 1000\n* xyz 0 1\n O 0 0 0 # oxygen\n H 0 0 1\n*\n'
NW = 'start keep\ncharge 0\ngeometry units angstrom noautoz\n O 0 0 0\n H 0 0 1\nend\nbasis\n * library 6-31g\nend\ntask dft energy\n'


def frame(symbols=('O', 'H'), periodic=False):
    return Frame(list(symbols), np.arange(len(symbols)*3).reshape(-1,3) / 7. + .125,
                 cell=[[6.,0,0],[1.,7.,0],[-.5,2.,8.]], pbc=(periodic,)*3)


@pytest.mark.parametrize('kind,source,suffix', [('gaussian_in',GJF,'.gjf'),('orca_in',ORCA,'.inp'),('nwchem_in',NW,'.nw')])
def test_cartesian_replacement_preserves_all_other_text_and_source_frame(tmp_path,kind,source,suffix):
    original=frame();positions=original.positions.copy();cell=original.cell.copy()
    changed=replace_molecular_coordinates(source,kind,original)
    assert changed.splitlines(keepends=True)[:source.splitlines().index(next(l for l in source.splitlines() if l.strip().startswith('O ')))] == source.splitlines(keepends=True)[:source.splitlines().index(next(l for l in source.splitlines() if l.strip().startswith('O ')))]
    assert changed.endswith(source[source.index('\n*\n'):] if kind=='orca_in' else source[source.index('\nend\n'):] if kind=='nwchem_in' else '\r\n\r\n')
    if kind=='orca_in':assert '# oxygen\n' in changed
    if kind=='gaussian_in':assert '\n' not in changed.replace('\r\n','')
    path=tmp_path/('updated'+suffix);path.write_bytes(changed.encode())
    actual=load_document(path).frames[0]
    np.testing.assert_allclose(actual.positions,positions,atol=1.e-12)
    assert actual.symbols==original.symbols and not any(actual.pbc)
    np.testing.assert_array_equal(original.positions,positions)
    np.testing.assert_array_equal(original.cell,cell)


def test_gaussian_freeze_connectivity_and_basis_remain_byte_identical(tmp_path):
    prefix='%chk=original.chk\n#p B3LYP/gen opt=modredundant geom=connectivity\n\nTitle\n\n0 1\n'
    atoms='O  -1  0.0  0.0  0.0 ! retained\nH 0 0 1\n'
    tail='\n1 2 1.0\n2\n\nB 1 2 F\n\nO H 0\n6-31G\n****\n'
    text=prefix+atoms+tail
    result=replace_molecular_coordinates(text,'gaussian_in',frame())
    assert result.startswith(prefix) and result.endswith(tail)
    assert 'O  -1  ' in result and ' ! retained\n' in result
    with pytest.raises(ValueError,match='atom-specific'):
        replace_molecular_coordinates(text,'gaussian_in',frame(('H','O')))
    f=frame();f.info['atom_order_edited']=True
    with pytest.raises(ValueError,match='atom-specific'):
        replace_molecular_coordinates(text,'gaussian_in',f)


def test_gaussian_freeze_comment_and_bohr_coordinates_read_back(tmp_path):
    source='#p hf/sto-3g Units=(Rad,AU)\n\nTitle\n\n0 1\nO -1 0.0 0.0 0.0 ! keep\nH 0 0.0 0.0 1.0\n\n'
    f=frame();result=replace_molecular_coordinates(source,'gaussian_in',f)
    path=tmp_path/'frozen.gjf';path.write_text(result)
    actual=load_document(path).frames[0]
    np.testing.assert_allclose(actual.positions,f.positions,atol=1.e-8)
    assert actual.info['fixed_axes']==[[True]*3,[False]*3]
    assert ' ! keep\n' in result


@pytest.mark.parametrize('kind,source',[('gaussian_in',GJF),('orca_in',ORCA.replace(' # oxygen','')),('nwchem_in',NW)])
def test_plain_templates_allow_atom_count_and_element_order_change(kind,source):
    f=frame(('C','H','N'))
    changed=replace_molecular_coordinates(source,kind,f)
    assert re.search(r'(?m)^\s*C\s',changed) and re.search(r'(?m)^\s*N\s',changed)
    assert not re.search(r'(?m)^\s*O\s',changed)
    assert len(re.findall(r'(?m)^\s*(?:C|H|N)\s+[-+\d.]',changed))==3


@pytest.mark.parametrize('units',['AU','(Rad,AU)'])
def test_gaussian_bohr_input_keeps_unit_keyword(units):
    text=GJF.replace(' opt',' Units='+units)
    f=frame()
    result=replace_molecular_coordinates(text,'gaussian_in',f)
    assert 'Units='+units in result
    oxygen=next(line for line in result.splitlines() if line.strip().startswith('O '))
    np.testing.assert_allclose(np.array(oxygen.split()[1:],float)*BOHR_ANG,f.positions[0],atol=1.e-12)


@pytest.mark.parametrize('periodic',[False,True])
def test_gaussian_existing_tv_template_updates_cell_or_supplies_30_angstrom(periodic,tmp_path):
    text=GJF[:-2]+'Tv 5 0 0\r\nTv 0 5 0\r\nTv 0 0 5\r\n\r\n'
    f=frame(periodic=periodic)
    result=replace_molecular_coordinates(text,'gaussian_in',f)
    path=tmp_path/'periodic.gjf';path.write_bytes(result.encode())
    actual=load_document(path).frames[0]
    np.testing.assert_allclose(actual.positions,f.positions)
    np.testing.assert_allclose(actual.cell,f.cell if periodic else np.eye(3)*30.)
    assert all(actual.pbc)


@pytest.mark.parametrize('kind,text',[('gaussian_in',GJF),('orca_in',ORCA),('nwchem_in',NW)])
def test_periodic_frame_to_molecular_template_has_no_cell(kind,text,tmp_path):
    result=replace_molecular_coordinates(text,kind,frame(periodic=True))
    assert not re.search(r'(?im)^\s*(?:Tv|system|cell)\b',result)


@pytest.mark.parametrize('mode',['simple','coords_units','coords_geometry'])
def test_orca_bohr_roundtrip_for_both_inline_forms(tmp_path,mode):
    if mode=='simple':text=ORCA.replace('! PBE','! Bohrs PBE')
    elif mode=='coords_units':text='%coords\n Units Bohrs\nend\n'+ORCA
    else:text='! PBE def2-SVP\n%coords\n CTyp xyz\n Charge 0\n Mult 1\n Units Bohrs\n coords\n O 0 0 0 # keep\n H 0 0 1\n end\nend\n'
    f=frame();result=replace_molecular_coordinates(text,'orca_in',f)
    path=tmp_path/'orca.inp';path.write_text(result)
    actual=load_document(path).frames[0]
    np.testing.assert_allclose(actual.positions,f.positions,atol=1.e-12)
    assert actual.info['converter_charge']=='0' and actual.info['converter_mult']=='1'
    if mode=='coords_geometry':assert ' CTyp xyz\n Charge 0\n Mult 1\n Units Bohrs\n coords\n' in result


def test_orca_constraint_block_preserved_and_reordering_rejected():
    source=ORCA+'%geom\n Constraints\n { C 0 C }\n end\nend\n'
    result=replace_molecular_coordinates(source,'orca_in',frame())
    assert result.endswith(source[source.index('%geom'):])
    with pytest.raises(ValueError,match='atom-specific'):
        replace_molecular_coordinates(source,'orca_in',frame(('H','O')))


@pytest.mark.parametrize('source',[
    ORCA.replace('* xyz 0 1','* xyz 0 1 # structure').replace('\n*\n','\n* # end\n'),
    '! PBE\n%coords # settings\n Units Bohrs # units\n Charge 0\n Mult 1\n coords # atom records\n O 0 0 0\n H 0 0 1\n end # atoms end\nend # all end\n',
])
def test_orca_comments_on_delimiters_do_not_consume_coordinates(tmp_path,source):
    result=replace_molecular_coordinates(source,'orca_in',frame())
    path=tmp_path/'comments.inp';path.write_text(result)
    actual=load_document(path).frames[0]
    np.testing.assert_allclose(actual.positions,frame().positions,atol=1.e-12)


@pytest.mark.parametrize('unit,factor',[('au',1/1.8897265),('nm',10),('pm',.01),('angstrom',1)])
def test_nwchem_units_preserve_geometry_directive(unit,factor):
    source=NW.replace('units angstrom','units '+unit)
    f=frame();result=replace_molecular_coordinates(source,'nwchem_in',f)
    assert 'geometry units '+unit+' noautoz\n' in result
    oxygen=next(line for line in result.splitlines() if line.strip().startswith('O '))
    np.testing.assert_allclose(np.array(oxygen.split()[1:],float)*factor,f.positions[0],atol=1.e-12)


def test_nwchem_custom_tag_velocity_mass_parameters_stay_on_original_identity():
    source=NW.replace('O 0 0 0','O1 0 0 0 0.1 0.2 0.3 mass 18')
    result=replace_molecular_coordinates(source,'nwchem_in',frame())
    assert ' 0.1 0.2 0.3 mass 18\n' in result and '\n O1 ' in result
    with pytest.raises(ValueError,match='atom-specific'):
        replace_molecular_coordinates(source,'nwchem_in',frame(('H','O')))


@pytest.mark.parametrize('directive',['set geometry:actlist 1','set nwpw:shake_constraint 1 2'])
def test_nwchem_indexed_set_directives_block_same_element_reorder(directive):
    source=NW.replace(' O 0 0 0',' H 0 0 0')+directive+'\n'
    f=frame(('H','H'));f.info['atom_order_edited']=True
    with pytest.raises(ValueError,match='atom-specific'):
        replace_molecular_coordinates(source,'nwchem_in',f)


@pytest.mark.parametrize('kind,source',[
    ('gaussian_in',GJF+'--Link1--\n'+GJF),
    ('gaussian_in',GJF.replace('O   0.0   0.0   0.0','O')),
    ('gaussian_in',GJF.replace(' opt',' ONIOM(HF:UFF)')),
    ('gaussian_in',GJF.replace(' opt',' opt=QST2')),
    ('gaussian_in',GJF.replace(' opt',' geom=allcheck')),
    ('orca_in','! PBE\n* xyzfile 0 1 external.xyz\n'),
    ('orca_in',ORCA+'$new_job\n'+ORCA),
    ('orca_in',ORCA.replace('* xyz','* int')),
    ('orca_in',ORCA.replace('O 0 0 0','O(1) 0 0 0')),
    ('nwchem_in',NW+NW),
    ('nwchem_in',NW.replace(' O 0 0 0',' system crystal\n  lat_a 5\n end\n O 0 0 0')),
    ('nwchem_in',NW.replace(' O 0 0 0',' load coords.xyz')),
    ('nwchem_in',NW.replace(' O 0 0 0',' symmetry c2v\n O 0 0 0')),
])
def test_ambiguous_templates_fail_with_actionable_sample_request(kind,source):
    with pytest.raises(ValueError,match='sample'):
        replace_molecular_coordinates(source,kind,frame())


def test_disorder_is_not_silently_projected_to_one_element():
    f=frame();f.info['site_occupancies']=[{'O':.5,'N':.5},{'H':1.}]
    with pytest.raises(ValueError,match='occupancies'):
        replace_molecular_coordinates(GJF,'gaussian_in',f)
