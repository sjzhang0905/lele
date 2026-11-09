"""Optional producer-file QA; no user data or pymatgen runtime dependency.

Set LELE_REAL_WAVECAR to a standard scalar WAVECAR; optional
LELE_REAL_OUTCAR compares printed bands and occupations for ISPIN=1.
"""
import os
from pathlib import Path
import numpy as np
import pytest


def test_real_wavecar_independent_direct_sum():
    path=os.environ.get('LELE_REAL_WAVECAR')
    if not path or not Path(path).is_file():pytest.skip('No external standard WAVECAR fixture supplied')
    outputs=pytest.importorskip('pymatgen.io.vasp.outputs')
    from lele.binary_wavefunctions import inspect_wavecar
    reference=outputs.Wavecar(path,vasp_type='std')
    wave=inspect_wavecar(path)
    np.testing.assert_allclose(wave.cell,reference.a,atol=1e-12)
    np.testing.assert_allclose(wave.kpoints[0],reference.kpoints,atol=1e-12)
    assert wave.spins==1, 'This reference fixture test expects ISPIN=1 standard scalar storage'
    np.testing.assert_array_equal(wave.energies[0],np.asarray(reference.band_energy)[:,:,0])
    for k in range(wave.nkpoints):
        for band in sorted(set([0,wave.nbands//2-1,wave.nbands//2,wave.nbands-1])):
            coefficients=wave.coefficients(0,k,band)
            np.testing.assert_array_equal(coefficients,reference.coeffs[k][band])
            real=wave.volume(0,k,band,'real');imag=wave.volume(0,k,band,'imag')
            density=wave.volume(0,k,band,'density')
            rng=np.random.default_rng(734+k*wave.nbands+band)
            indices=np.column_stack([rng.integers(0,n,size=32) for n in real.data.shape])
            values=[];expected=[]
            for index in indices:
                position=index@real.voxel_vectors
                phase=(reference.Gpoints[k]+reference.kpoints[k])@reference.b@position
                expected.append(np.sum(reference.coeffs[k][band].astype(complex)*np.exp(1j*phase))/np.sqrt(reference.vol))
                values.append(real.data[tuple(index)]+1j*imag.data[tuple(index)])
            np.testing.assert_allclose(values,expected,atol=2e-7,rtol=2e-6)
            # A PAW pseudo-wavefunction is not generally norm-one in real space.
            integral=float(density.data.mean(dtype=np.float64)*abs(np.linalg.det(wave.cell)))
            np.testing.assert_allclose(integral,np.vdot(coefficients.astype(complex),coefficients).real,rtol=2e-6,atol=1e-7)
    out=os.environ.get('LELE_REAL_OUTCAR')
    if out and Path(out).is_file():
        lines=Path(out).read_text().splitlines()
        rows=np.array([[[float(x) for x in line.split()] for line in lines[i+1:i+1+wave.nbands]] for i,line in enumerate(lines) if 'band No.' in line])
        if rows.shape[0]==wave.nkpoints:
            np.testing.assert_allclose(rows[:,:,1],wave.energies[0],atol=5.1e-5,rtol=0)
            np.testing.assert_allclose(rows[:,:,2],2*wave.occupations[0],atol=5.1e-6,rtol=0)
