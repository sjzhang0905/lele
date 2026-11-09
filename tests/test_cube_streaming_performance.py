"""Chunk boundaries must not change CUBE numeric data or accept truncation."""
from io import StringIO
import numpy as np
import pytest
from lele import cube_input
from lele.cube_input import read_cube_file
from lele.output_text import LoadCancelled, output_read_session


@pytest.mark.parametrize('chunk_size', [1, 7, 31, 1024])
@pytest.mark.parametrize('separator', [' ', '\t', '\r\n', '\u2003'])
def test_block_parser_keeps_split_exponents_and_float32_rounding(monkeypatch, chunk_size, separator):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', chunk_size)
    tokens = ['1.2345678901234567', '-9.876543210D-4', '+4.21e+3', '0', '-0',
              '1.1754943508222875E-38', '1.401298464324817E-45', '3.4028234663852886E+38']
    actual = cube_input._cube_array(StringIO(separator.join(tokens)), len(tokens))
    expected = np.asarray([float(x.replace('D', 'E')) for x in tokens], dtype=np.float32)
    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))


@pytest.mark.parametrize('tail', ['1 2x', '1 2 junk', '1 2,', '1 2 3', '1 2\n3',
                                   '1 nan', '1 inf', '1 1e99', '1', ''])
def test_block_parser_rejects_corrupt_incomplete_nonfinite_and_extra_values(monkeypatch, tail):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 3)
    with pytest.raises(ValueError):
        cube_input._cube_array(StringIO(tail), 2)


def test_block_parser_bounds_reads_even_for_one_very_long_line(monkeypatch):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 97)

    class BoundedStream(StringIO):
        def read(self, size=-1):
            assert size == 97
            return super().read(size)

    np.testing.assert_array_equal(cube_input._cube_array(BoundedStream('1.25 '*10_000), 10_000), 1.25)


def test_block_parser_midfield_cancellation_and_progress(monkeypatch):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 64)
    calls = []
    progress = []

    def cancel():
        calls.append(None)
        return len(calls) >= 9

    with pytest.raises(LoadCancelled), output_read_session(
            cancelled=cancel, progress=lambda *event: progress.append(event)):
        cube_input._cube_array(StringIO('1.25 '*10_000), 10_000)
    assert progress[0] == ('CUBE scalar field', 0, 10_000)
    assert all(event[1] < 10_000 for event in progress)


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16'])
def test_multichannel_nondefault_axes_and_encoding_at_chunk_boundaries(tmp_path, monkeypatch, encoding):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 17)
    path = tmp_path/'多轨道.cube'
    values = np.arange(48, dtype=np.float32) / 7
    text = ('Orbitals\nOUTER LOOP: Z, MIDDLE LOOP: X, INNER LOOP: Y\n'
            '-1 1 2 3\n-2 .5 0 0\n-3 .1 .4 0\n-4 0 .2 .3\n'
            '8 0 1.25 2.5 3.75\n2 5\n9\n')
    text += ' '.join(f'{float(x):.17e}'.replace('e', 'D') for x in values)
    path.write_text(text, encoding=encoding)
    actual = read_cube_file(path)
    assert actual['labels'] == [5, 9]
    for i in range(2):
        expected = values[i::2].reshape(4, 2, 3).transpose(1, 2, 0)
        np.testing.assert_array_equal(actual['datas'][i], expected)
    np.testing.assert_allclose(actual['origin'], [1, 2, 3])
    np.testing.assert_allclose(actual['atoms'].positions, [[1.25, 2.5, 3.75]])


def test_block_parser_does_not_hide_error_after_exact_final_value(monkeypatch):
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 4)
    with pytest.raises(ValueError, match='Extra values'):
        cube_input._cube_array(StringIO('1 2 '+' '*50+'garbage'), 2)
