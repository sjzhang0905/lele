from pathlib import Path
import pytest
from lele.formats import load_document
from lele.binary_wavefunctions import read_gbw

LOG=''' O   R   C   A
GEOMETRY OPTIMIZATION CYCLE 1
CARTESIAN COORDINATES (ANGSTROEM)
----------------
O 0.0 0.0 0.0
H 0.0 0.0 1.0

FINAL SINGLE POINT ENERGY -75.000000
THE OPTIMIZATION HAS CONVERGED
ORCA TERMINATED NORMALLY
'''

def test_companion_is_explicit_not_decoded(tmp_path,monkeypatch):
    monkeypatch.delenv('LELE_ORCA_2MKL',raising=False)
    monkeypatch.setattr('shutil.which',lambda _:None)
    p=tmp_path/'sample.gbw';p.write_bytes(b'opaque gbw')
    (tmp_path/'sample.log').write_text(LOG)
    doc=load_document(p)
    assert doc.path==p and doc.wavefunction is None
    assert len(doc.frames)==1 and doc.frames[0].symbols==['O','H']
    assert doc.frames[0].info['gbw_match_verified'] is False
    assert 'NOT decoded' in doc.note and 'sample.log' in doc.note
    assert 'does not verify' in doc.note
    assert p.read_bytes()==b'opaque gbw'

def test_wrong_basename_not_used(tmp_path,monkeypatch):
    monkeypatch.delenv('LELE_ORCA_2MKL',raising=False)
    monkeypatch.setattr('shutil.which',lambda _:None)
    p=tmp_path/'sample.gbw';p.write_bytes(b'opaque')
    (tmp_path/'other.log').write_text(LOG)
    with pytest.raises(ValueError,match='requires the matching'):read_gbw(p)

def test_non_orca_companion_not_used(tmp_path,monkeypatch):
    monkeypatch.delenv('LELE_ORCA_2MKL',raising=False)
    monkeypatch.setattr('shutil.which',lambda _:None)
    p=tmp_path/'sample.gbw';p.write_bytes(b'opaque')
    (tmp_path/'sample.log').write_text('not an orca output')
    with pytest.raises(ValueError):read_gbw(p)
