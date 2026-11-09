from pathlib import Path
import numpy as np
import pytest
from lele.volumetric_input import read_vasp_volume_document,read_cube_document,is_vasp_volume
from lele.cube_input import read_cube_file
from lele.output_text import output_read_session,LoadCancelled


def vasp_text(values,extra='',scale='1.0',lattice=None):
    lattice=lattice or '2 0 0\n0 3 0\n0 0 4'
    return f'water\n{scale}\n{lattice}\nO H\n1 1\nDirect\n0 0 0\n.5 .5 .5\n\n2 2 2\n'+ ' '.join(map(str,values))+'\n'+extra


@pytest.mark.parametrize('name,unit,divisor',[('CHGCAR','e/Å³',24),('CHG','e/Å³',24),('PARCHG.0001','e/Å³',24),('AECCAR2','e/Å³',24),('ELFCAR','dimensionless',1),('LOCPOT','eV',1)])
def test_vasp_grid_order_and_units(tmp_path,name,unit,divisor):
    p=tmp_path/name;p.write_text(vasp_text(np.arange(8)))
    doc=read_vasp_volume_document(p)
    assert doc.volume is not None,doc.note
    assert doc.frames[0].symbols==['O','H']
    assert doc.volume.unit==unit and doc.volume.periodic
    np.testing.assert_allclose(doc.volume.data,np.arange(8).reshape((2,2,2),order='F')/divisor)
    np.testing.assert_allclose(doc.volume.voxel_vectors,np.diag([1,1.5,2]))
    assert is_vasp_volume(p)


def test_vasp_magnetization_skips_augmentation(tmp_path):
    # Integer augmentation values that resemble a grid header must not be read
    # as dimensions. Four channels represent non-collinear magnetization.
    aug='augmentation occupancies 1 3\n2 2 2\n'
    extra=aug+''.join('2 2 2\n'+' '.join([str(i)]*8)+'\n'+aug for i in [2,3,4])
    p=tmp_path/'CHGCAR';p.write_text(vasp_text([24]*8,extra))
    doc=read_vasp_volume_document(p)
    assert len(doc.volumes)==4,doc.note
    assert doc.volumes[3].label.endswith('z')
    np.testing.assert_allclose(doc.volumes[0].data,1)
    np.testing.assert_allclose(doc.volumes[2].data,3/24)


def test_vasp_negative_volume_scale_and_skew(tmp_path):
    p=tmp_path/'CHGCAR';p.write_text(vasp_text([48]*8,scale='-48',lattice='2 0 0\n1 3 0\n0 0 4'))
    doc=read_vasp_volume_document(p)
    assert abs(np.linalg.det(doc.frames[0].cell))==pytest.approx(48)
    np.testing.assert_allclose(doc.volume.data,1)
    np.testing.assert_allclose(doc.volume.voxel_vectors,doc.frames[0].cell/2)


@pytest.mark.parametrize('tail',['2 2 2\n1 2\n','2 2 3\n','augmentation occupancies 1 4\n1 2\n','garbage\n'])
def test_vasp_incomplete_channel_rejects_all_fields_preserves_geometry(tmp_path,tail):
    p=tmp_path/'CHGCAR';p.write_text(vasp_text(range(8),tail))
    doc=read_vasp_volume_document(p)
    assert doc.volume is None and 'unavailable' in doc.note
    assert len(doc.frames[0].symbols)==2


def test_vasp_limit_and_cancellation(tmp_path):
    p=tmp_path/'CHGCAR';p.write_text(vasp_text(range(8)))
    assert read_vasp_volume_document(p,max_points=7).volume is None
    with pytest.raises(LoadCancelled),output_read_session(cancelled=lambda:True):
        read_vasp_volume_document(p)


def cube(channels=2,labels=True):
    text='Multichannel\nOUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z\n'
    text+=f'{-1 if labels else 1} 0 0 0'+('' if labels else f' {channels}')+'\n'
    text+='-2 1 0 0\n-2 0 1 0\n-2 0 0 1\n1 0 0 0 0\n'
    if labels:text+=f'{channels} '+' '.join(str(5+i) for i in range(channels))+'\n'
    text+=' '.join(str(i+100*j) for i in range(8) for j in range(channels))+'\n'
    return text


@pytest.mark.parametrize('labels',[True,False])
def test_cube_multichannel_values_not_mixed(tmp_path,labels):
    p=tmp_path/'orbitals.cube';p.write_text(cube(labels=labels))
    doc=read_cube_document(p)
    assert len(doc.volumes)==2,doc.note
    np.testing.assert_array_equal(doc.volumes[0].data,np.arange(8).reshape(2,2,2))
    np.testing.assert_array_equal(doc.volumes[1].data,(100+np.arange(8)).reshape(2,2,2))
    assert doc.volumes[0].label==('Orbital 5' if labels else 'Field 1')


def test_cube_fortran_numbers_and_configured_limit(tmp_path):
    p=tmp_path/'d.cube';p.write_text(cube(channels=1).replace(' 0 0 0\n',' 0D0 0D0 0D0\n'))
    doc=read_cube_document(p)
    assert doc.volume is not None,doc.note
    assert read_cube_document(p,max_points=7).volume is None


def test_cube_nondefault_axis_order(tmp_path):
    p=tmp_path/'order.cube';p.write_text(cube(channels=1).replace('OUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z','OUTER LOOP: Z, MIDDLE LOOP: Y, INNER LOOP: X'))
    doc=read_cube_document(p)
    np.testing.assert_array_equal(doc.volume.data,np.arange(8).reshape(2,2,2).transpose(2,1,0))
