"""Measured corner-axis geometry after projecting every saved PNG onto the canvas."""
import json
import os
from pathlib import Path
import pytest

base=Path(os.environ.get('LELE_ACCEPT_EVIDENCE',Path(__file__).resolve().parents[1]))
scenes=json.loads((base/'axis/axis_probe.json').read_text())['scenes']
labels=json.loads((base/'labels/live_label_probe.json').read_text())

@pytest.mark.parametrize('scene', ['molecule','crystal'])
@pytest.mark.parametrize('factor', [1,2,3,4])
@pytest.mark.parametrize('smooth', [False,True])
def test_corner_axes_keep_extent(scene,factor,smooth):
    row=scenes[scene]
    old=row['live']['all']
    actual=row[f"{factor}x_{'smooth' if smooth else 'standard'}"]['all']
    # Different tessellation / resampling can change edge pixels by a few units.
    assert all(.85 <= actual[k]/old[k] <= 1.15 for k in ('height','width')), (old,actual)

@pytest.mark.parametrize('scene,letter',[('molecule','Z'),('crystal','c')])
def test_top_corner_label_not_clipped_in_live_view(scene,letter):
    row=labels[scene]['letters'][letter]
    assert row['original']['height'] >= .8*row['inset_control']['height'], row
