"""PQR field layouts and CUBE geometry/field unit consistency."""
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from ase.units import Bohr
from lele.formats import load_document,export_frame
from lele.legacy_converter import ConversionError,read_structure,convert_one,DEFAULT_GAUSSIAN_ROUTE
from lele.cube_input import read_cube_file
from lele.output_text import LoadCancelled
from lele.project_file import save_project,load_project
from lele.render_options import RenderOptions


@pytest.mark.parametrize('separator',[' ','  ','\t'])
@pytest.mark.parametrize('record',['ATOM','HETATM'])
@pytest.mark.parametrize('chain',[False,True])
def test_pqr_fields_keep_element_and_large_coordinates(tmp_path,separator,record,chain):
    prefix=[record,'9','O','ASN']+(['B'] if chain else [])+['15']
    text=separator.join(prefix+['-1234.56789','2345.67891','-3456.78912','-0.8','1.5'])+'\n'
    source=tmp_path/'fields.pqr';source.write_text('REMARK example\n  '+text+'END\n')
    frame=load_document(source).frames[0]
    assert frame.symbols==['O']
    np.testing.assert_array_equal(frame.positions,[[-1234.56789,2345.67891,-3456.78912]])


def fixed_row(*,element=False):
    row=list(' '*80)
    for start,stop,value in [(0,6,'ATOM  '),(6,11,'    1'),(12,16,' O  '),(17,20,'ASN'),
        (21,22,'B'),(22,26,'   1'),(30,38,'-123.456'),(38,46,'-234.567'),(46,54,'-345.678'),
        (54,62,' -0.8000'),(62,69,' 1.5000')]:row[start:stop]=value
    if element:row[12:16]=' N  ';row[76:78]=' O'
    return ''.join(row).rstrip()+'\n'


@pytest.mark.parametrize('element',[False,True])
def test_fixed_column_pqr_is_one_consistent_record_even_without_coordinate_spaces(tmp_path,element):
    source=tmp_path/'fixed.pqr';source.write_text(fixed_row(element=element))
    frame=load_document(source).frames[0]
    assert frame.symbols==['O']
    np.testing.assert_array_equal(frame.positions,[[-123.456,-234.567,-345.678]])


@pytest.mark.parametrize('name,expected',[('O1','O'),('1HG1','H'),('Cl','Cl'),('Fe','Fe'),('N2','N')])
def test_pqr_atom_name_field_not_residue_or_serial_determines_element(tmp_path,name,expected):
    source=tmp_path/'names.pqr';source.write_text(f'HETATM 12345 {name} ASN 22 1 2 3 0 1.5\n')
    assert load_document(source).frames[0].symbols==[expected]


@pytest.mark.parametrize('name,residue,expected',[('CA','ASN','C'),('CD1','ILE','C'),
    ('NE2','GLN','N'),('HG1','SER','H'),('SE','MSE','Se'),('CA','CA','Ca'),
    ('FE','HEM','Fe'),('Cl','LIG','Cl')])
def test_biomolecular_atom_labels_and_ion_elements_remain_distinct(tmp_path,name,residue,expected):
    source=tmp_path/'residues.pqr';source.write_text(f'HETATM 1 {name} {residue} 1 1 2 3 0 1.5\n')
    assert load_document(source).frames[0].symbols==[expected]


@pytest.mark.parametrize('row',[
    'ATOM 2 O ASN 1 nan 2 3 0 1.5','ATOM 2 O ASN 1 1 2 3 inf 1.5',
    'ATOM 2 O ASN 1 1 2 3 0 -1.5','ATOM 2 O ASN 1 1 2 3',
    'ATOM 2 ? ASN 1 1 2 3 0 1.5'])
def test_malformed_pqr_record_does_not_silently_drop_an_atom(tmp_path,row):
    source=tmp_path/'bad.pqr';source.write_text('ATOM 1 O ASN 1 1 2 3 0 1.5\n'+row+'\n')
    with pytest.raises(ConversionError,match='line 2'):load_document(source)


@pytest.mark.parametrize('encoding',['utf-8-sig','utf-16'])
def test_pqr_text_encoding_and_unicode_paths(tmp_path,encoding):
    source=tmp_path/'氧原子.pqr';source.write_text('ATOM 1 O ASN 1 1 2 3 0 1.5\n',encoding=encoding)
    assert load_document(source).frames[0].symbols==['O']


def cube_text(*,angstrom=True,labels=False,skew=False,nvalues=1,field=True,shape=(2,3,4)):
    shape=np.array(shape);steps=np.array([[.5,0,0],[.1 if skew else 0,.4,0],[0,.2 if skew else 0,.3]])
    text='Synthetic field\nOUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z\n'
    text+=f'{-2 if labels else 2} 1 -2 3 {nvalues}\n'
    for count,vector in zip(shape,steps):text+=' '.join(map(str,[int(-count if angstrom else count),*vector]))+'\n'
    text+='8 0 1.25 -1.75 3.25\n1 0 1.75 -1.75 3.25\n'
    if labels:text+='1 5\n'
    values=np.linspace(-2,3,int(np.prod(shape)))
    if field:text+=' '.join(map(str,values))+'\n'
    return text,shape,steps,values


@pytest.mark.parametrize('angstrom',[False,True])
@pytest.mark.parametrize('labels',[False,True])
@pytest.mark.parametrize('skew',[False,True])
def test_cube_geometry_origin_steps_cell_and_signed_field_use_same_units(tmp_path,angstrom,labels,skew):
    text,shape,steps,values=cube_text(angstrom=angstrom,labels=labels,skew=skew)
    source=tmp_path/'grid.cub';source.write_text(text);before=source.read_bytes()
    document=load_document(source);frame=document.frames[0];volume=document.volume
    factor=1. if angstrom else Bohr
    assert frame.symbols==['O','H'] and volume is not None,document.note
    np.testing.assert_allclose(frame.positions,np.array([[1.25,-1.75,3.25],[1.75,-1.75,3.25]])*factor,atol=1.e-14)
    np.testing.assert_allclose(frame.cell,shape[:,None]*steps*factor,atol=1.e-14)
    np.testing.assert_allclose(volume.origin,np.array([1,-2,3])*factor,atol=1.e-14)
    np.testing.assert_allclose(volume.voxel_vectors,steps*factor,atol=1.e-14)
    np.testing.assert_array_equal(volume.data,values.astype(np.float32).reshape(tuple(shape)))
    assert source.read_bytes()==before
    # Legacy conversion and native display must see the same atom geometry.
    atoms,_=read_structure(source)
    np.testing.assert_array_equal(atoms.positions,frame.positions)


@pytest.mark.parametrize('mutation',['mixed_sign','zero_count','nonfinite','missing_atom','missing_labels'])
def test_cube_invalid_header_is_rejected_explicitly(tmp_path,mutation):
    text,_,_,_=cube_text(labels=mutation=='missing_labels')
    if mutation=='mixed_sign':text=text.replace('-3 0.0','3 0.0',1)
    if mutation=='zero_count':text=text.replace('-2 0.5','0 0.5',1)
    if mutation=='nonfinite':text=text.replace('1 -2 3 1','nan -2 3 1',1)
    if mutation=='missing_atom':text='\n'.join(text.splitlines()[:7])+'\n'
    if mutation=='missing_labels':text='\n'.join(text.splitlines()[:8])+'\n'
    source=tmp_path/'bad.cube';source.write_text(text)
    with pytest.raises((ValueError,ConversionError)):load_document(source)


@pytest.mark.parametrize('problem',['incomplete','nonfinite','multiple_fields','point_limit'])
def test_unavailable_cube_field_retains_valid_geometry_with_a_note(tmp_path,problem):
    text,_,_,_=cube_text(nvalues=2 if problem=='multiple_fields' else 1)
    if problem=='incomplete':text='\n'.join(text.splitlines()[:8])+ '\n0 1\n'
    if problem=='nonfinite':text=text.rsplit('\n',2)[0]+'\n'+' '.join(['nan']*24)+'\n'
    source=tmp_path/'geometry.cube';source.write_text(text)
    with patch('lele.formats.MAX_VOLUME_POINTS',10 if problem=='point_limit' else 2_000_000):
        document=load_document(source)
    assert document.frames[0].symbols==['O','H'] and document.volume is None
    assert 'volumetric field unavailable' in document.note
    np.testing.assert_allclose(document.frames[0].positions[0],[1.25,-1.75,3.25],atol=1.e-14)


def test_cube_multiline_orbital_labels_and_missing_labels_terminate(tmp_path):
    text,_,_,_=cube_text(labels=True)
    text=text.replace('1 5\n','2 5\n6\n')
    source=tmp_path/'orbitals.cube';source.write_text(text)
    result=read_cube_file(source,read_data=False)
    assert result['atoms'].get_chemical_symbols()==['O','H']
    assert load_document(source).volume is None


def test_cube_castep_duplicate_boundary_planes_follow_ase(tmp_path):
    text,shape,steps,values=cube_text(shape=(3,4,5))
    source=tmp_path/'castep.cube';source.write_text(text.replace('Synthetic field\nOUTER','Synthetic field\ncastep2cube OUTER').replace('castep2cube OUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z','castep2cube'))
    document=load_document(source)
    assert document.volume.data.shape==(2,3,4)
    np.testing.assert_allclose(document.frames[0].cell,(shape-1)[:,None]*steps,atol=1.e-14)
    np.testing.assert_array_equal(document.volume.data,values.astype(np.float32).reshape(tuple(shape))[:-1,:-1,:-1])


@pytest.mark.parametrize('kind',['pqr','cube'])
@pytest.mark.parametrize('target',['xyz','gjf','cif','poscar-direct','poscar-cartesian'])
def test_repaired_inputs_have_correct_elements_in_both_export_paths(tmp_path,kind,target):
    source=tmp_path/('input.'+kind)
    text=cube_text()[0] if kind=='cube' else 'HETATM 1 O ASN 1 1 2 3 0 1.5\n'
    source.write_text(text);frame=load_document(source).frames[0]
    assert frame.symbols==(['O','H'] if kind=='cube' else ['O'])
    path=tmp_path/('export.'+{'xyz':'xyz','gjf':'gjf','cif':'cif'}.get(target,'POSCAR'))
    export_frame(frame,path,target)
    assert load_document(path).frames[0].symbols==frame.symbols
    directory=tmp_path/'legacy';directory.mkdir()
    converted,_,_=convert_one(source,target,directory,30.,DEFAULT_GAUSSIAN_ROUTE)
    assert load_document(converted).frames[0].symbols==frame.symbols


@pytest.mark.parametrize('kind',['pqr','cube'])
def test_repaired_document_and_grid_survive_project_without_source(tmp_path,kind):
    source=tmp_path/('input.'+kind)
    source.write_text(cube_text()[0] if kind=='cube' else 'ATOM 1 O ASN 1 1 2 3 0 1.5\n')
    document=load_document(source);path=tmp_path/'project.lele'
    save_project(path,dict(documents=[dict(document=document,options=RenderOptions())],current_document=0));source.unlink()
    restored=load_project(path)['documents'][0]['document']
    assert restored.frames[0].symbols==document.frames[0].symbols
    np.testing.assert_array_equal(restored.frames[0].positions,document.frames[0].positions)
    if kind=='cube':np.testing.assert_array_equal(restored.volume.data,document.volume.data)


@pytest.mark.parametrize('kind',['pqr','cube'])
def test_cancelled_import_does_not_return_a_partial_document(tmp_path,kind):
    source=tmp_path/('input.'+kind)
    source.write_text(cube_text()[0] if kind=='cube' else 'ATOM 1 O ASN 1 1 2 3 0 1.5\n')
    with pytest.raises(LoadCancelled):load_document(source,cancelled=lambda:True)


@pytest.mark.parametrize('kind',['pqr','cube'])
def test_mid_import_cancellation_is_not_converted_into_a_reader_error(tmp_path,kind):
    source=tmp_path/('input.'+kind)
    source.write_text(cube_text()[0] if kind=='cube' else 'ATOM 1 O ASN 1 1 2 3 0 1.5\n'*20)
    calls=[]
    def cancel():
        calls.append(1);return len(calls)>=8
    with pytest.raises(LoadCancelled):load_document(source,cancelled=cancel)
