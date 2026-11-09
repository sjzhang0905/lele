from pathlib import Path
import numpy as np
import pytest
from ase.units import Bohr,Hartree
from lele.core import Document,Frame,Volume
from lele.field_export import export_active_cube,cube_scalar_units
from lele.volumetric_input import read_cube_document
from lele.output_text import output_read_session,LoadCancelled


def sample(unit='dimensionless'):
    frame=Frame(['O','H'],np.array([[.2,.3,.4],[1.,2.,3.]]),np.array([[2.,0,0],[.3,3.,0],[.4,.2,4.]]),(True,False,True))
    volume=Volume(np.arange(24,dtype=np.float32).reshape(2,3,4)-4,np.array([1.,-2.,3.]),np.array([[.2,0,0],[.1,.3,0],[.05,.1,.4]]),label='test field',unit=unit,periodic=True)
    return Document(Path('test'), 'test',[frame],volume)


@pytest.mark.parametrize('unit,factor,expected',[
    ('e/Å³',Bohr**3,'e/Bohr³'),('Å⁻³ᐟ²',Bohr**1.5,'Bohr⁻³ᐟ²'),
    ('eV',1/Hartree,'Hartree'),('dimensionless',1.,'dimensionless'),
    ('Bohr⁻³ᐟ² (orbital amplitude)',1.,'Bohr⁻³ᐟ² (orbital amplitude)'),
    ('source units',1.,'source units'),
    ('Å⁻³ (unweighted pseudo state)',Bohr**3,'Bohr⁻³ (unweighted pseudo state)')])
def test_active_cube_units_and_skew_roundtrip(tmp_path,unit,factor,expected):
    doc=sample(unit);path=tmp_path/'field.cube'
    export_active_cube(path,doc,doc.frames[0])
    result=read_cube_document(path)
    assert result.volume is not None,result.note
    np.testing.assert_allclose(result.volume.data,doc.volume.data*factor,rtol=2e-7)
    np.testing.assert_allclose(result.volume.voxel_vectors,doc.volume.voxel_vectors,atol=1e-14)
    np.testing.assert_allclose(result.volume.origin,doc.volume.origin,atol=1e-14)
    np.testing.assert_allclose(result.frames[0].positions,doc.frames[0].positions,atol=1e-14)
    np.testing.assert_array_equal(result.frames[0].cell,doc.frames[0].cell)
    assert result.frames[0].pbc==doc.frames[0].pbc
    assert result.volume.unit==expected
    assert result.volume.label=='test field' and result.volume.periodic
    assert int(path.read_text().splitlines()[3].split()[0])==2


def test_only_active_dataset_and_detachment(tmp_path):
    doc=sample();other=Volume(np.ones((2,2,2)),np.zeros(3),np.eye(3),label='other',unit='dimensionless')
    doc.volumes=[doc.volume,other];doc.volume=other
    path=tmp_path/'field.cube';export_active_cube(path,doc,doc.frames[0])
    loaded=read_cube_document(path)
    assert len(loaded.volumes)==1 and loaded.volume.label=='other'
    np.testing.assert_array_equal(loaded.volume.data,other.data)
    doc.volume=None
    with pytest.raises(ValueError,match='attached'):export_active_cube(path,doc,doc.frames[0])


def test_atomic_cancel_preserves_target(tmp_path):
    doc=sample();path=tmp_path/'field.cube';path.write_text('old')
    checks=[0]
    def cancelled():
        checks[0]+=1
        return checks[0]>=3
    with pytest.raises(LoadCancelled),output_read_session(cancelled=cancelled):
        export_active_cube(path,doc,doc.frames[0])
    assert path.read_text()=='old'
    assert list(tmp_path.iterdir())==[path]


def test_reject_nonfinite_singular_and_disorder(tmp_path):
    doc=sample();path=tmp_path/'field.cube';doc.volume.data[0,0,0]=np.nan
    with pytest.raises(ValueError,match='finite'):export_active_cube(path,doc,doc.frames[0])
    doc=sample();doc.volume.voxel_vectors[1]=doc.volume.voxel_vectors[0]
    with pytest.raises(ValueError,match='independent'):export_active_cube(path,doc,doc.frames[0])
    doc=sample();doc.frames[0].info['site_occupancies']=[{'O':.5},{'H':1.}]
    with pytest.raises(ValueError,match='occupancy'):export_active_cube(path,doc,doc.frames[0])
    assert not path.exists()


def test_unknown_unit_not_claimed_atomic(tmp_path):
    factor,unit,note=cube_scalar_units('mystery')
    assert factor==1 and unit=='mystery' and 'not relabeled' in note
