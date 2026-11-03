"""Validate final scientific records in complete, unsampled long imports."""
from pathlib import Path
import os
import numpy as np
import pytest
from ase.units import Hartree, Bohr, create_units
from lele.formats import load_document

DATA=Path(os.environ.get('LELE_AUDIT_BENCH_DATA',Path(__file__).resolve().parents[1]/'benchmark_data'))
QE_RY=create_units('2006')['Ry']  # QE / ASE espresso convention; general ASE units differ.


@pytest.mark.parametrize('count',[1200,4800])
@pytest.mark.parametrize('kind',['cp2k','xtb','qe','vasp','siesta','gaussian','xyz','xdatcar','nwchem','nwchem_continuation'])
def test_long_import_has_every_frame_or_energy_and_the_literal_final_record(count,kind):
    suffix={'qe':'pwo','xyz':'xyz','xdatcar':'xdatcar','nwchem':'nwo','nwchem_continuation':'nwo'}.get(kind,'out')
    document=load_document(DATA/f'{kind}_{count}.{suffix}')
    expected_frames=0 if kind=='xtb' else 2 if kind=='nwchem_continuation' else count
    assert len(document.frames)==expected_frames
    results=document.calculation_results
    if kind in ('cp2k','xtb','qe','vasp','gaussian','xdatcar'):assert len(results.steps)==count
    energy={
        'cp2k':(-10-(count-1)*.0001)*Hartree,'xtb':(-10-(count-1)*.0001)*Hartree,
        'vasp':-10-(count-1)*.0001,'siesta':-10-(count-1)*.0001,
        'qe':(-2-(count-1)*.001)*QE_RY,'gaussian':(-2-(count-1)*.0001)*Hartree,
        'nwchem':(-10-(count-1)*.0001)*Hartree,
        'nwchem_continuation':(-10-(count-1)*.0001)*Hartree}
    if kind in energy:
        actual=results.steps[-1].energy_ev if kind=='xtb' else document.frames[-1].energy_ev
        assert actual==pytest.approx(energy[kind],abs=1.e-8)
    if kind=='qe':
        assert document.frames[-1].info['qe_total_energy_ry']==pytest.approx(-2-(count-1)*.001,abs=1.e-14)
    if document.frames:
        expected_z=8*(.1+(count-1)*.000001) if kind=='xdatcar' else (1+(count-1)*.00001)*(Bohr if kind.startswith('nwchem') else 1.)
        assert document.frames[-1].positions[-1,2]==pytest.approx(expected_z,abs=1.e-10)


@pytest.mark.parametrize('count',[1500,6000])
def test_large_orca_retains_final_geometry_energy_and_every_dipole(count):
    document=load_document(DATA/f'orca_{count}.out')
    assert len(document.frames)==len(document.calculation_results.steps)==len(document.dipoles)==count
    assert document.frames[-1].positions[-1,2]==pytest.approx((count-1)*.0001,abs=1.e-10)
    assert document.frames[-1].energy_ev==pytest.approx((-100-(count-1)*.000001)*Hartree,abs=1.e-8)
    np.testing.assert_allclose(document.frames[-1].positions[:,0],np.arange(16)*.3,atol=1.e-10)
    assert document.frames[-1].info['optimization_converged']
