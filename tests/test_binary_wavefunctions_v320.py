import numpy as np
import pytest
from lele.binary_wavefunctions import inspect_wavecar, read_wavecar, convert_gbw_to_molden


def write_wavecar(path, endian='<', tag=45200, spins=1, coeff_count=1):
    recl=256;nk=2;nb=2
    data=bytearray((2+spins*nk*(nb+1))*recl)
    def put(record, values, dtype='f8'):
        raw=np.asarray(values,dtype=endian+dtype).tobytes()
        data[record*recl:record*recl+len(raw)]=raw
    put(0,[recl,spins,tag]);put(1,[nk,nb,1,*np.eye(3).ravel(),.5])
    for spin in range(spins):
        for ik in range(nk):
            rec=2+(spin*nk+ik)*(nb+1)
            put(rec,[coeff_count,0,0,0,-1-spin,0,1,2+ik,0,0])
            for band in range(nb):put(rec+1+band,[1+0j]*coeff_count,'c8' if tag==45200 else 'c16')
    path.write_bytes(data);return path

@pytest.mark.parametrize('endian',['<','>'])
@pytest.mark.parametrize('tag',[45200,45210])
def test_headers_coefficients_and_density(tmp_path,endian,tag):
    w=inspect_wavecar(write_wavecar(tmp_path/'WAVECAR',endian,tag,spins=2))
    assert w.spins==2 and w.nkpoints==2 and w.nbands==2
    assert w.energies[1,1,0]==-2 and w.occupations[0,0,1]==0
    assert np.allclose(w.coefficients(1,1,1),[1])
    assert np.allclose(w.volume().data,1)
    assert np.allclose(w.volume(kind='imag').data,0)
    d=read_wavecar(w.path)
    assert d.frames==[] and len(d.calculation_results.orbitals)==2
    assert d.calculation_results.orbitals[1].channels['Spin 2'][0].energy_ev==-2

def test_validation(tmp_path):
    p=write_wavecar(tmp_path/'WAVECAR');p.write_bytes(p.read_bytes()[:-1])
    with pytest.raises(ValueError,match='truncated'):inspect_wavecar(p)
    p.write_bytes(b'nonsense')
    with pytest.raises(ValueError):inspect_wavecar(p)
    w=inspect_wavecar(write_wavecar(p,coeff_count=2))
    with pytest.raises(ValueError,match='not a verified'):w.volume()
    with pytest.raises(IndexError):w.coefficients(band=2)
    with pytest.raises(ValueError,match='memory'):w.volume(max_points=1)

def test_companion(tmp_path):
    p=write_wavecar(tmp_path/'WAVECAR')
    pos=tmp_path/'POSCAR';pos.write_text('H\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n')
    assert read_wavecar(p).frames[0].symbols==['H']
    pos.write_text(pos.read_text().replace('1 0 0','2 0 0'))
    assert read_wavecar(p).frames==[]

def test_no_converter(tmp_path,monkeypatch):
    monkeypatch.delenv('LELE_ORCA_2MKL',raising=False);monkeypatch.setattr('shutil.which',lambda _:None)
    with pytest.raises(ValueError,match='requires the matching'):convert_gbw_to_molden(tmp_path/'x.gbw',tmp_path/'x.molden')

def test_converter_isolation(tmp_path):
    p=tmp_path/'a name.gbw';p.write_bytes(b'input');exe=tmp_path/'fake_converter'
    exe.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nimport sys\nassert sys.argv[1:]==["wavefunction", "-molden"]\nPath("wavefunction.gbw").write_bytes(b"changed")\nPath("wavefunction.molden.input").write_text("[Molden Format]\\n")\n');exe.chmod(0o755)
    target=tmp_path/'out';convert_gbw_to_molden(p,target,executable=exe)
    assert p.read_bytes()==b'input' and target.read_text()=='[Molden Format]\n'
    exe.write_text('#!/usr/bin/env python3\nraise SystemExit(1)\n')
    with pytest.raises(ValueError,match='conversion failed'):convert_gbw_to_molden(p,target,executable=exe)
    exe.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(5)\n')
    with pytest.raises(ValueError,match='timed out'):convert_gbw_to_molden(p,target,executable=exe,timeout=.05)

from test_periodic_fragment_ui_v171 import gui

def test_results_only_wavecar_gui(gui,tmp_path):
    document=read_wavecar(write_wavecar(tmp_path/'WAVECAR'))
    w=gui.window
    w._attach_loaded_document(document)
    assert w.frame is None
    assert w.canvas_stack.currentWidget() is w.results_only_page
    assert w.results_orbital_button.isEnabled()
    w.results_orbital_button.click()
    dialog=w._analysis_windows[-1]
    assert dialog.table.rowCount()==2
    dialog.close()

def test_missing_lazy_source_actionable(tmp_path):
    p=write_wavecar(tmp_path/'WAVECAR');w=inspect_wavecar(p);p.unlink()
    with pytest.raises(ValueError,match='original WAVECAR is unavailable'):w.coefficients()

def test_reconstruction_gate_metadata_and_periodicity(tmp_path):
    w=inspect_wavecar(write_wavecar(tmp_path/'WAVECAR'))
    assert w.validate_reconstruction()
    for kind in ('density','real','imag'):
        v=w.volume(kind=kind)
        assert v.periodic and 'WAVECAR' in v.label and v.unit
    w.kpoints[0,0]=[.01,0,0]
    assert w.volume(kind='density').periodic
    assert not w.volume(kind='real').periodic
    assert not w.volume(kind='imag').periodic
    w.ncoeff[0,0]=2
    assert not w.validate_reconstruction()
    assert 'not a verified' in w.reconstruction_reason

def test_outcar_companion_is_unambiguous_and_labeled(tmp_path,monkeypatch):
    from lele.core import Frame
    from types import SimpleNamespace
    p=write_wavecar(tmp_path/'WAVECAR')
    frame=Frame(['H'],np.zeros((1,3)),np.eye(3),(True,True,True))
    monkeypatch.setattr('lele.vasp_results.read_vasp_results',lambda path:SimpleNamespace(frames=lambda:[frame]))
    (tmp_path/'OUTCAR(1)').write_text('test')
    doc=read_wavecar(p)
    assert len(doc.frames)==1 and 'OUTCAR(1)' in doc.note
    assert 'does not establish an exact calculation match' in doc.note
    assert 'raw occupation' in doc.note
    (tmp_path/'OUTCAR(2)').write_text('test')
    doc=read_wavecar(p)
    assert not doc.frames and 'Multiple matching OUTCAR' in doc.note
