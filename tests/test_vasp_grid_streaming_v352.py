"""Bounded numeric chunks preserve VASP field and augmentation boundaries."""
from io import StringIO
import numpy as np
import pytest

import lele.volumetric_input as reader
from lele.output_text import output_read_session, LoadCancelled


HEADER='sample\n1\n2 0 0\n0 3 0\n0 0 4\nH\n1\nDirect\n0 0 0\n\n'


@pytest.mark.parametrize('chunk', [7, 31, 1024*1024])
@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-be'])
def test_channels_augmentation_fortran_and_decoding(tmp_path, monkeypatch, chunk, encoding):
    monkeypatch.setattr(reader,'_FIELD_CHUNK_CHARS',chunk)
    values=[str((i-20)/17).replace('e','D') for i in range(240)]
    values[1]='1.23456789123D-4'
    grid='2 2 60\n'+'\n'.join(' '.join(values[i:i+5]) for i in range(0,240,5))+'\n'
    augment='augmentation occupancies 1 3\n2 2 60\n'
    path=tmp_path/'CHGCAR'
    path.write_bytes((HEADER+grid+augment+grid+augment).encode(encoding))
    result=reader.read_vasp_volume_document(path)
    assert len(result.volumes)==2,result.note
    expected=np.asarray([float(x.replace('D','E')) for x in values],dtype=np.float32)
    expected=(expected/abs(float(np.linalg.det(result.frames[0].cell)))).reshape((2,2,60),order='F')
    for volume in result.volumes:np.testing.assert_array_equal(volume.data,expected)
    assert result.volumes[1].label=='Magnetization density (up − down)'


@pytest.mark.parametrize('chunk', [3, 11, 1024*1024])
@pytest.mark.parametrize('separator', [' ', '\t', '\u2003'])
def test_long_line_tail_keeps_following_headers(monkeypatch, chunk, separator):
    monkeypatch.setattr(reader,'_FIELD_CHUNK_CHARS',chunk)
    values=[f'{i/100:.12e}' for i in range(300)]
    stream=reader._FieldStream(StringIO(separator.join(values)+' \n2 2 2\n9 8 7 6 5 4 3 2\nEND\n'))
    actual=reader._array(stream,300,'field')
    np.testing.assert_array_equal(actual,np.asarray([float(v) for v in values],dtype=np.float32))
    assert reader._next_grid(stream)==(2,2,2)
    np.testing.assert_array_equal(reader._array(stream,8,'field'),[9,8,7,6,5,4,3,2])
    assert stream.readline()=='END\n'


@pytest.mark.parametrize('bad', ['0 1 2 3 4 5 6 7 8\n',
    '0 1 2 3 4 5 6 7\v8\n', '0 1 2 3 4 5 6 7\u00858\n',
    '0 1 2 3 4 5 6 7 garbage\n', '0 1 2 3 4 5 6 7.0garbage\n',
    '0 1 2 3 4 5 6 nan\n', '0 1 2 3 4 5 6 1e500\n',
    '0 1 2 3 4 5 6 1e40\n', '0 1 2 3\n'])
@pytest.mark.parametrize('chunk', [7, 1024*1024])
def test_invalid_tail_preserves_geometry_without_partial_field(tmp_path,monkeypatch,bad,chunk):
    monkeypatch.setattr(reader,'_FIELD_CHUNK_CHARS',chunk)
    path=tmp_path/'CHGCAR';path.write_text(HEADER+'2 2 2\n'+bad)
    doc=reader.read_vasp_volume_document(path)
    assert doc.volume is None and not doc.volumes and len(doc.frames)==1
    assert 'unavailable' in doc.note


def test_one_long_line_cancel_is_checked_per_chunk(monkeypatch):
    monkeypatch.setattr(reader,'_FIELD_CHUNK_CHARS',1024)
    calls=0
    def cancelled():
        nonlocal calls
        calls+=1
        return calls>=7
    stream=reader._FieldStream(StringIO('1.23456789 '*10000+'\n'))
    with pytest.raises(LoadCancelled),output_read_session(cancelled=cancelled):
        reader._array(stream,10000,'field')
    assert calls==7


def test_python_numeric_compatibility_and_no_final_newline(monkeypatch):
    monkeypatch.setattr(reader,'_FIELD_CHUNK_CHARS',11)
    stream=reader._FieldStream(StringIO('1_000.0 2D-3 3d+1 4 5 6 7 8'))
    np.testing.assert_array_equal(reader._array(stream,8,'field'),
                                 np.asarray([1000,.002,30,4,5,6,7,8],np.float32))


def test_empty_augmentation_and_following_field(tmp_path):
    path=tmp_path/'CHGCAR'
    path.write_text(HEADER+'2 2 2\n1 2 3 4 5 6 7 8\naugmentation occupancies 1 0\n'
                    '2 2 2\n1 2 3 4 5 6 7 8\n')
    assert len(reader.read_vasp_volume_document(path).volumes)==2


def test_many_small_augmentation_blocks_have_bounded_numeric_work(monkeypatch):
    # Small PAW records must not repeatedly reparse a MiB of later records.
    # Count parser input bytes instead of using a machine-dependent time limit.
    text=('augmentation occupancies 1 10\n1 2 3 4 5 6 7 8 9 10\n'*2000)+'2 2 2\n'
    converted=0
    original=reader._numeric_values
    def measured(chunk):
        nonlocal converted
        converted+=len(chunk)
        return original(chunk)
    monkeypatch.setattr(reader,'_numeric_values',measured)
    stream=reader._FieldStream(StringIO(text))
    assert reader._next_grid(stream)==(2,2,2)
    assert converted<12*len(text)
