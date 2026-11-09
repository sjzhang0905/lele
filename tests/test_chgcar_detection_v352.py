"""Content-based VASP volume routing, independent of source filename."""
from io import StringIO
from unittest.mock import patch

import numpy as np
import pytest

from lele.formats import load_document
from lele.legacy_converter import detect_format, read_structure
from lele.output_text import output_read_session, LoadCancelled
from lele.vasp_volume_detection import (
    has_vasp_volume_data, is_vasp_volume, named_vasp_volume_kind,
)
from test_volumetric_readers_v320 import vasp_text,cube


@pytest.mark.parametrize('name',[
    'CHGCAR(1)', 'CHGCAR (copy)', 'CHGCAR-final', 'density.CHGCAR',
    'density.dat', 'density.txt', 'density.vasp', 'density.xyz',
    'density.cube', 'density.out', 'density', '电荷密度（重命名）',
])
def test_renamed_charge_grid_keeps_geometry_values_and_kind(tmp_path,name):
    path=tmp_path/name
    path.write_text(vasp_text(range(8)))
    assert detect_format(path).kind == 'vasp_volume'
    assert is_vasp_volume(path)
    doc=load_document(path)
    assert doc.volume is not None,doc.note
    assert doc.volume.data.shape == (2,2,2)
    np.testing.assert_array_equal(doc.volume.data,
        np.arange(8,dtype=np.float32).reshape((2,2,2),order='F')/24)
    assert doc.frames[0].symbols == ['O','H']
    assert doc.frames[0].info['source_kind'] == 'vasp_volume'
    assert doc.volume.unit == 'e/Å³'
    assert ('interpreted as CHGCAR' in doc.note) == (named_vasp_volume_kind(path) is None)


@pytest.mark.parametrize('name,unit,divisor',[
    ('LOCPOT(1)','eV',1), ('prefix.LOCPOT','eV',1),
    ('ELFCAR - copy','dimensionless',1), ('field.ELFCAR(2)','dimensionless',1),
    ('AECCAR2 (1)','e/Å³',24), ('PARCHG.0001','e/Å³',24),
])
def test_named_copied_grids_keep_native_units(tmp_path,name,unit,divisor):
    path=tmp_path/name;path.write_text(vasp_text([24]*8))
    doc=load_document(path)
    assert doc.volume is not None,doc.note
    assert doc.volume.unit==unit
    np.testing.assert_array_equal(doc.volume.data,24/divisor)


@pytest.mark.parametrize('name',['CHGCAR.cube','LOCPOT.cube','ELFCAR.cub','CHGCAR(1).cube'])
def test_converted_actual_cube_keeps_cube_parser_despite_vasp_name(tmp_path,name):
    path=tmp_path/name;path.write_text(cube(channels=1))
    assert not is_vasp_volume(path)
    doc=load_document(path)
    assert doc.format_name=='Gaussian CUBE'
    assert doc.volume is not None,doc.note
    np.testing.assert_array_equal(doc.volume.data,np.arange(8).reshape(2,2,2))


@pytest.mark.parametrize('encoding',['utf-8-sig','utf-16','utf-16-le','utf-16-be'])
@pytest.mark.parametrize('mode',['Direct','Cartesian','Selective dynamics\nDirect'])
def test_content_probe_retains_text_encodings_and_coordinate_modes(tmp_path,encoding,mode):
    path=tmp_path/'renamed.data'
    text=vasp_text(range(8)).replace('Direct',mode)
    if mode.startswith('Selective'):
        text=text.replace('0 0 0\n.5 .5 .5','0 0 0 T F T\n.5 .5 .5 T T T')
    path.write_bytes(text.encode(encoding))
    assert has_vasp_volume_data(path)
    assert load_document(path).volume is not None


@pytest.mark.parametrize('tail',[
    '', '\n', '\n0.1 0.2 0.3\n0.4 0.5 0.6\n',
    '\nCartesian\n0.1 0.2 0.3\n0.4 0.5 0.6\n',
    '\n2 2 2\n0.4 0.5 0.6\n',
    '\nLattice velocities and vectors\n1\n0 0 0\n0 0 0\n0 0 0\n',
])
def test_plain_poscar_and_velocities_are_not_volumes(tmp_path,tail):
    header=vasp_text(range(8)).split('\n\n2 2 2')[0]+'\n'
    path=tmp_path/'structure.vasp';path.write_text(header+tail)
    assert not has_vasp_volume_data(path)
    assert detect_format(path).kind=='vasp_in'


def test_converter_reads_only_volume_geometry_not_grid_as_velocities(tmp_path):
    path=tmp_path/'renamed.data';path.write_text(vasp_text(range(8)))
    atoms,detection=read_structure(path)
    assert detection.kind=='vasp_volume'
    assert atoms.get_chemical_symbols()==['O','H']
    np.testing.assert_array_equal(atoms.positions,[[0,0,0],[1,1.5,2]])


@pytest.mark.parametrize('name',['POSCAR','CONTCAR','velocity.POSCAR','renamed.data'])
@pytest.mark.parametrize('first_velocity',['2 2 3','10 10 10'])
@pytest.mark.parametrize('tail',['','\nPREDICTOR-CORRECTOR\n1 2 3\n'])
def test_complete_integer_velocity_triplets_are_not_invented_charge(tmp_path,name,first_velocity,tail):
    text=('H\n1\n3 0 0\n0 3 0\n0 0 3\nH\n5\nDirect\n'+
          '0 0 0\n'*5+'\n'+first_velocity+'\n'+'0.1 0.2 0.3\n'*4+tail)
    path=tmp_path/name;path.write_text(text)
    assert not has_vasp_volume_data(path)
    doc=load_document(path)
    assert doc.volume is None
    assert len(doc.frames[0].symbols)==5
    # A known CHGCAR name resolves the otherwise indistinguishable small grid.
    if first_velocity=='2 2 3' and not tail:
        known=tmp_path/'CHGCAR';known.write_text(text)
        assert load_document(known).volume is not None


def test_augmentation_resolves_ambiguous_small_grid(tmp_path):
    text=('H\n1\n3 0 0\n0 3 0\n0 0 3\nH\n5\nDirect\n'+
          '0 0 0\n'*5+'\n2 2 3\n'+'0.1 0.2 0.3\n'*4+
          'augmentation occupancies 1 3\n1 2 3\n')
    path=tmp_path/'density.data';path.write_text(text)
    assert has_vasp_volume_data(path)
    assert load_document(path).volume is not None


def test_large_grid_probe_never_reads_scalar_tail_or_ase_registry(tmp_path):
    text=vasp_text(range(8)).replace('\n2 2 2\n','\n200 200 200\n')
    header_bytes=len(text)
    class ProbeStream(StringIO):
        def readline(self,size=-1):
            assert size>0
            assert self.tell()<header_bytes
            return super().readline(size)
    with patch('lele.vasp_volume_detection.open_output_text',return_value=ProbeStream(text+'extra\n'*10000)):
        assert has_vasp_volume_data(tmp_path/'unused')


def test_probe_cancel_propagates_and_grid_load_only_probes_once(tmp_path):
    path=tmp_path/'renamed.data';path.write_text(vasp_text(range(8)))
    with pytest.raises(LoadCancelled),output_read_session(cancelled=lambda:True):
        has_vasp_volume_data(path)

    from lele import vasp_volume_detection as detection
    with patch.object(detection,'has_vasp_volume_data',wraps=detection.has_vasp_volume_data) as probe:
        doc=load_document(path)
    assert doc.volume is not None
    assert probe.call_count==1
