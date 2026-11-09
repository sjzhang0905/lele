"""Scientific invariants across fast C-level long-trajectory parsing paths."""
import numpy as np
import pytest
from lele.trajectory_io import xyz_blocks, IncompleteXYZ, NotPlainXYZ
from lele.vasp_results import read_xdatcar, read_vasp_results
from lele.output_text import output_read_session, LoadCancelled


def write(tmp_path, name, text, encoding='utf-8'):
    path = tmp_path / name
    path.write_text(text, encoding=encoding)
    return path


def xyz_rows(count=32, exponent='e'):
    return ''.join(f'{"O" if i%3==0 else "H"} {i}{exponent}-2 2.0 3.0\n' for i in range(count))


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-16', 'utf-16-le'])
@pytest.mark.parametrize('exponent', ['e', 'D'])
def test_xyz_bulk_exact_coordinates_comments_lines_and_encoding(tmp_path, encoding, exponent):
    path = write(tmp_path, 'frames.xyz', '\n32\nfirst\n'+xyz_rows(exponent=exponent)+
                 '32\nsecond\n'+xyz_rows(exponent=exponent), encoding)
    frames = list(xyz_blocks(path, plain=True))
    assert [frame[0] for frame in frames] == [2, 36]
    assert [frame[1] for frame in frames] == ['first', 'second']
    assert frames[0][2] == ['O' if i%3==0 else 'H' for i in range(32)]
    np.testing.assert_allclose(frames[0][3][:, 0], np.arange(32)/100, rtol=0, atol=0)
    assert frames[0][3].flags.c_contiguous


def test_xyz_extra_columns_require_full_extended_reader(tmp_path):
    rows = xyz_rows().replace('2.0 3.0', '2.0 3.0 5')
    path = write(tmp_path, 'frames.xyz', '32\ncomment\n'+rows)
    with pytest.raises(NotPlainXYZ):list(xyz_blocks(path, plain=True))
    assert len(list(xyz_blocks(path))[0][2]) == 32


@pytest.mark.parametrize('replacement', ['H123x 0 0 0', '', 'H 0 0'])
def test_xyz_invalid_rows_are_not_silently_skipped_or_labels_truncated(tmp_path, replacement):
    rows = xyz_rows().splitlines()
    rows[15] = replacement
    path = write(tmp_path, 'frames.xyz', '32\ncomment\n'+'\n'.join(rows)+'\n')
    with pytest.raises(IncompleteXYZ):list(xyz_blocks(path))


def test_cancellation_during_one_large_coordinate_block(tmp_path):
    path = write(tmp_path, 'frames.xyz', '5000\ncomment\n'+xyz_rows(5000))
    calls = [0]
    def cancelled():
        calls[0] += 1
        return calls[0] >= 4
    with output_read_session(cancelled=cancelled), pytest.raises(LoadCancelled):
        list(xyz_blocks(path))
    assert calls[0] == 4


def xdat_header(scale='1', cell='2 0 0\n0 3 0\n0 0 4'):
    return f'O H\n{scale}\n{cell}\nO H\n16 16\n'


@pytest.mark.parametrize('exponent', ['e', 'D'])
def test_xdat_bulk_keeps_repeated_headers_and_cartesian_scale(tmp_path, exponent):
    rows = ''.join(f'{i}{exponent}-2 0.2 0.3\n' for i in range(32))
    text = xdat_header()+'Direct configuration= 7\n'+rows
    text += xdat_header(scale='2')+'Cartesian configuration= 11\n'+rows
    path = write(tmp_path, 'XDATCAR', text, 'utf-16')
    result = read_xdatcar(path)
    frames = result.frames()
    assert [step.cycle for step in result.steps] == [7, 11]
    np.testing.assert_allclose(frames[0].positions[:, 0], np.arange(32)/50)
    np.testing.assert_allclose(frames[0].positions[0], [0, 0.6, 1.2])
    np.testing.assert_allclose(frames[1].positions[0], [0, 0.4, 0.6])
    np.testing.assert_array_equal(frames[1].cell, np.diag([4, 6, 8]))
    assert all(frame.energy_ev is None for frame in frames)
    frames[0].positions[0, 0] = 99
    frames[0].symbols[0] = 'C'
    assert result.steps[0].geometry.positions[0, 0] == 0
    assert result.steps[0].geometry.symbols[0] == 'O'


@pytest.mark.parametrize('badrow', ['0 0', '0 0 0 0', '', '0 nan 0', '0 0 text'])
def test_xdat_bad_table_preserves_only_complete_previous_frames(tmp_path, badrow):
    rows = ['0.1 0.2 0.3']*32
    text = xdat_header()+'Direct configuration= 1\n'+'\n'.join(rows)+'\n'
    rows[15] = badrow
    text += 'Direct configuration= 2\n'+'\n'.join(rows)+'\n'
    result = read_xdatcar(write(tmp_path, 'XDATCAR', text))
    assert len(result.steps) == 1
    assert 'Incomplete XDATCAR configuration' in result.note


def test_outcar_case_whitespace_and_scf_ionic_energy_separation(tmp_path):
    text = '''vasp.6.4.0
 TITEL = PAW_PBE H 01Jan2000
 ions per type = 1
 IBRION = 0
 NELECT = 1
 DIRECT LATTICE VECTORS
 2 0 0
 0 3 0
 0 0 4
 Iteration 1( 1)
 free energy TOTEN = -88
 energy without entropy = -89 energy(sigma->0) = -90
 FREE ENERGIE OF THE ION-ELECTRON SYSTEM
 PoSiTiOn\tToTaL-FoRcE
 --------------------------
 0.1 0.2 0.3 0 0 0
 FREE ENERGY TOTEN = -1
 ENERGY WITHOUT ENTROPY = -2 ENERGY(SIGMA -> 0) = -3
 General timing and accounting
'''
    result = read_vasp_results(write(tmp_path, 'OUTCAR', text))
    assert len(result.steps) == 1
    assert result.steps[0].energy_ev == -3
    assert result.steps[0].info['vasp_free_energy_ev'] == -1
    assert result.steps[0].geometry.pbc == (True, True, True)
