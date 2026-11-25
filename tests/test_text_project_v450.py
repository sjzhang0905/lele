import json
from pathlib import Path
from zipfile import is_zipfile

import numpy as np
import pytest

from lele.output_text import LoadCancelled, output_read_session
from lele.project_file import load_project, save_project


# Written by the unmodified v4.4.0 release, including its original NPY arrays.
LEGACY = Path(__file__).parent / 'fixtures' / 'project_v440.lele'


def test_old_project_becomes_editable_utf8_json(tmp_path):
    assert is_zipfile(LEGACY)
    state = load_project(LEGACY)
    doc = state['documents'][0]['document']
    assert state['result_sequence'][0] is doc
    assert doc.frames[0].info['description'] == '原始晶胞'
    path = save_project(tmp_path/'晶胞.lele', state)
    text = path.read_text(encoding='utf-8')
    assert '原始晶胞' in text and '[1.25, -2.5, 3.0]' in text
    records = json.loads(text)
    positions = next(i for i, node in enumerate(records) if node.get('name') == 'positions')
    records[positions+1]['values'][0][0] = -4.125
    # A text editor can change layout, line endings or add a UTF-8 signature.
    path.write_bytes(('\ufeff' + json.dumps(records, ensure_ascii=False, indent=4).replace('\n','\r\n')).encode())
    reopened = load_project(path)
    new = reopened['documents'][0]['document']
    np.testing.assert_array_equal(new.frames[0].positions, [[-4.125,-2.5,3],[.5,.75,1]])
    np.testing.assert_array_equal(new.volume.data, np.arange(24).reshape(2,3,4))
    assert reopened['result_sequence'][0] is new


def test_array_types_shared_references_and_large_blocks(tmp_path):
    state = load_project(LEGACY)
    rng = np.random.default_rng(404)
    grid = rng.normal(size=(33,31,19)).T
    complex_values = np.array([complex(3, np.nan), complex(-0., np.inf), 1e-100-2.33j], dtype='>c16')
    arrays = dict(grid=grid, same=grid, amplitudes=complex_values, pressure=np.array(1.25),
                  counts=np.array([0,2**64-1],dtype='>u8'), empty=np.empty((2,0,3)),
                  mask=np.array([True,False]), labels=np.array(['晶胞','α'],dtype='U4'),
                  floats=np.array([-np.inf, np.nan, -0., 1e-30],dtype='>f4'),
                  bytes=np.array([b'\x00a', b'\xff'],dtype='S2'),
                  time=np.array(['2026-11-25','NaT'],dtype='datetime64[D]'),
                  records=np.array([(3,.25)], dtype=[(('Index','number'),'<i2'),('value','>f8')]))
    state['scientific_arrays'] = arrays
    path = save_project(tmp_path/'arrays.lele', state)
    restored = load_project(path)['scientific_arrays']
    for key, value in arrays.items():
        assert restored[key].dtype == value.dtype and restored[key].shape == value.shape
        np.testing.assert_array_equal(restored[key], value)
    assert restored['grid'] is restored['same'] and np.signbit(restored['floats'][2])
    assert not np.isnan(restored['amplitudes'][0].real)
    # Standard JSON readers can also consume the whole file on a single line.
    records = json.loads(path.read_text(encoding='utf-8'))
    path.write_text(json.dumps(records, separators=(',', ':')), encoding='utf-8')
    np.testing.assert_array_equal(load_project(path)['scientific_arrays']['grid'], grid)


def test_float32_grid_uses_short_roundtripping_decimals(tmp_path):
    state = load_project(LEGACY)
    rng = np.random.default_rng(9)
    grid = rng.integers(0, 2**32, 100000, dtype=np.uint32).view(np.float32)
    grid = grid[np.isfinite(grid)]
    grid[:3] = [.1, .2, -.3]
    state['grid'] = grid
    path = save_project(tmp_path/'float_grid.lele', state)
    assert '[0.1, 0.2, -0.3,' in path.read_text(encoding='utf-8')
    np.testing.assert_array_equal(load_project(path)['grid'].view(np.uint32), grid.view(np.uint32))


@pytest.mark.parametrize('damage',['truncated_array','overrun','invalid_type','tail','schema'])
def test_damaged_text_project_rejected(tmp_path, damage):
    path = save_project(tmp_path/'project.lele', load_project(LEGACY))
    records = json.loads(path.read_text(encoding='utf-8'))
    pos = next(i for i, node in enumerate(records) if node.get('name') == 'positions')
    if damage == 'truncated_array':
        records[pos+1]['values'].pop()
    elif damage == 'overrun':
        records[pos+1]['values'][0].append(0)
    elif damage == 'invalid_type':
        records[pos]['dtype'] = '|O'
    elif damage == 'schema':
        records[0]['schema'] += 1
    text = json.dumps(records)
    path.write_text(text[:-1] if damage == 'tail' else text, encoding='utf-8')
    with pytest.raises(ValueError):
        load_project(path)


def test_cancel_during_array_write_preserves_previous_file(tmp_path):
    state = load_project(LEGACY)
    path = save_project(tmp_path/'project.lele', state)
    before = path.read_bytes()
    state['large_grid'] = np.zeros(70_000)
    cancel = []
    def progress(label, value, total):
        if label == 'Project: writing large_grid':
            cancel.append(True)
    with output_read_session(cancelled=lambda:bool(cancel), progress=progress), pytest.raises(LoadCancelled):
        save_project(path, state)
    assert path.read_bytes() == before and list(tmp_path.iterdir()) == [path]
