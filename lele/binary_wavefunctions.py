"""Validated WAVECAR access.

WAVECAR bands are read lazily; PAW on-site
augmentation is not present in the reconstructed pseudo-wavefunction.
"""
from dataclasses import dataclass
from functools import lru_cache
from math import prod
from pathlib import Path
import re
import numpy as np
from .core import Document, Frame, Volume
from .calculation_results import CalculationResults, CalculationJob, Orbital, OrbitalSet
from .output_text import check_load_cancelled


KINETIC_EV_ANG2 = 3.80998211615486
UNSUPPORTED_LAYOUT = ('WAVECAR is not a verified full-complex scalar wavefunction '
                      '(Gamma-only, spinor/SOC, or incompatible cutoff convention). '
                      'Export a CUBE with a compatible VASP tool.')
GRID_LIMIT = 'WAVECAR FFT grid exceeds the display memory limit; use a smaller exported CUBE'


def _ordered_basis(cell, k, cutoff, bounds, expected):
    reciprocal = 2*np.pi*np.linalg.inv(np.asarray(cell).reshape(3,3)).T
    nx, ny, nz = (2*n+1 for n in bounds)
    vectors = np.empty((expected, 3), dtype=np.int32)
    written = 0
    # VASP advances Gx first. Positive frequencies precede negative ones on
    # each axis. A bounded block works for long thin as well as cubic cells.
    for start in range(0, nx*ny*nz, 32768):
        check_load_cancelled()
        ranks = np.arange(start, min(start+32768, nx*ny*nz), dtype=np.int64)
        candidates = np.empty((len(ranks), 3), dtype=np.int32)
        for axis, (n, extent) in enumerate(zip(bounds, (nx,ny,nz))):
            index = ranks % extent
            candidates[:,axis] = np.where(index <= n, index, index-extent)
            ranks //= extent
        kinetic = KINETIC_EV_ANG2 * np.sum(((candidates+k) @ reciprocal)**2, axis=1)
        block = candidates[kinetic < cutoff]
        end = written + len(block)
        if end > expected:
            raise ValueError(UNSUPPORTED_LAYOUT)
        vectors[written:end] = block
        written = end
    if written != expected:
        raise ValueError(UNSUPPORTED_LAYOUT)
    vectors.flags.writeable = False
    return vectors


# Only small bases enter this cache. Keys include all geometric inputs and
# the printed count, so later edits and files with different layouts revalidate.
_cached_basis = lru_cache(maxsize=8)(_ordered_basis)


@dataclass
class Wavecar:
    path: Path
    record_length: int
    spins: int
    tag: int
    endian: str
    nkpoints: int
    nbands: int
    encut_ev: float
    cell: np.ndarray
    fermi_ev: float | None
    kpoints: np.ndarray
    ncoeff: np.ndarray
    energies: np.ndarray
    occupations: np.ndarray
    reconstruction_supported: bool = False
    reconstruction_reason: str = "Layout has not been validated for reconstruction."

    def coefficients(self, spin=0, kpoint=0, band=0):
        """Return one raw coefficient record; all indices are zero based."""
        if not (0 <= spin < self.spins and 0 <= kpoint < self.nkpoints and 0 <= band < self.nbands):
            raise IndexError('WAVECAR spin, k-point or band index out of range')
        record = 2 + (spin * self.nkpoints + kpoint) * (self.nbands + 1) + band + 1
        dtype = np.dtype(self.endian + ('c8' if self.tag == 45200 else 'c16'))
        if not self.path.is_file():
            raise ValueError('The original WAVECAR is unavailable. Reopen the original WAVECAR to access coefficients; saved projects retain metadata but do not embed the binary source.')
        with self.path.open('rb') as stream:
            stream.seek(record * self.record_length)
            data = np.fromfile(stream, dtype=dtype, count=int(self.ncoeff[spin,kpoint]))
        if len(data) != self.ncoeff[spin,kpoint] or not np.isfinite(data).all():
            raise ValueError('Truncated or non-finite WAVECAR coefficient record')
        return data

    def _basis(self, spin, kpoint, max_points):
        if not (0 <= spin < self.spins and 0 <= kpoint < self.nkpoints):
            raise IndexError('WAVECAR spin or k-point index out of range')
        k = self.kpoints[spin,kpoint]
        radii = np.ceil(np.linalg.norm(self.cell,axis=1) *
                        np.sqrt(self.encut_ev/KINETIC_EV_ANG2)/(2*np.pi) + np.abs(k)) + 1
        if not np.isfinite(radii).all() or np.any(2*radii+1 > max_points):
            raise ValueError(GRID_LIMIT)
        bounds = radii.astype(np.int64)
        counts = tuple(int(x) for x in bounds)
        size = prod(2*x+1 for x in counts)
        if size > max_points:
            raise ValueError(GRID_LIMIT)
        expected = int(self.ncoeff[spin,kpoint])
        if not 0 < expected <= size:
            raise ValueError(UNSUPPORTED_LAYOUT)
        compute = _cached_basis if expected*12 <= 2*1024*1024 else _ordered_basis
        vectors = compute(tuple(self.cell.flat), tuple(k), self.encut_ev, counts, expected)
        return vectors, bounds

    def reciprocal_vectors(self, spin=0, kpoint=0, max_points=16_000_000):
        """Return independently writable G vectors in VASP coefficient order."""
        vectors, bounds = self._basis(spin, kpoint, max_points)
        return vectors.astype(int, copy=True), bounds

    def validate_reconstruction(self):
        try:
            verified = set()
            for spin in range(self.spins):
                for kpoint in range(self.nkpoints):
                    check_load_cancelled()
                    key = (tuple(self.kpoints[spin,kpoint]), int(self.ncoeff[spin,kpoint]))
                    if key not in verified:
                        self._basis(spin, kpoint, 16_000_000)
                        verified.add(key)
        except ValueError as exc:
            self.reconstruction_supported=False
            self.reconstruction_reason=str(exc)
        else:
            self.reconstruction_supported=True
            self.reconstruction_reason='Full-complex scalar plane-wave layout validated. PAW augmentation is not included.'
        return self.reconstruction_supported

    def volume(self, spin=0, kpoint=0, band=0, kind='density', max_points=16_000_000):
        """Reconstruct a single pseudo Bloch state, never a total charge density.

        No occupation/k-point weighting or artificial coefficient normalization
        is applied. Real/imaginary components depend on the stored global phase.
        A doubled Fourier grid also resolves the |psi|² bandwidth.
        """
        coefficients = self.coefficients(spin,kpoint,band)
        vectors,bounds = self._basis(spin,kpoint,max_points)
        shape=4*bounds+1
        if int(np.prod(shape, dtype=object)) > max_points:
            raise ValueError(GRID_LIMIT)
        reciprocal_grid=np.zeros(tuple(shape),dtype=complex)
        reciprocal_grid[tuple((vectors % shape).T)] = coefficients
        check_load_cancelled()
        wave=np.fft.ifftn(reciprocal_grid)
        del reciprocal_grid
        wave *= np.prod(shape)
        wave /= np.sqrt(abs(np.linalg.det(self.cell)))
        k=self.kpoints[spin,kpoint]
        if kind in ('real','imag'):
            for axis in range(3):
                view=[1,1,1];view[axis]=shape[axis]
                wave *= np.exp(2j*np.pi*k[axis]*np.arange(shape[axis])/shape[axis]).reshape(view)
            values=wave.real if kind=='real' else wave.imag
        elif kind=='density':
            values=np.abs(wave)
            np.square(values, out=values)
        else:raise ValueError('Wavefunction field must be density, real, or imag')
        check_load_cancelled()
        label=f'WAVECAR spin {spin+1}, k {kpoint+1}, band {band+1}: '+({'density':'|psi|² (single pseudo state)','real':'Re psi (stored phase)','imag':'Im psi (stored phase)'}[kind])
        return Volume(values,np.zeros(3),self.cell/shape[:,None],label=label,
                      unit='Å⁻³ (unweighted pseudo state)' if kind=='density' else 'Å⁻³ᐟ²',
                      periodic=bool(kind=='density' or np.allclose(k,np.round(k),atol=1e-12)))


def _integer(value, label, low=1, high=1_000_000_000):
    if not np.isfinite(value) or value != int(value) or not low <= int(value) <= high:
        raise ValueError('Invalid WAVECAR '+label)
    return int(value)


def inspect_wavecar(path):
    path=Path(path);size=path.stat().st_size
    if size < 24:raise ValueError('WAVECAR header is truncated')
    with path.open('rb') as stream:
        raw=stream.read(24); endian=None
        for candidate in ('<','>'):
            header=np.frombuffer(raw,dtype=candidate+'f8')
            if header[2] in (45200,45210,53300,53310) and header[1] in (1,2):
                endian=candidate;break
        if endian is None:raise ValueError('Unrecognized WAVECAR header or byte order')
        recl=_integer(header[0],'record length',96,size)
        spins=int(header[1]);tag=int(header[2])
        if tag not in (45200,45210):raise ValueError('WAVECAR compressed format is unsupported; use standard VASP WAVECAR or exported CUBE')
        stream.seek(recl);second=np.fromfile(stream,dtype=endian+'f8',count=min(13,recl//8))
        if len(second)<12 or not np.isfinite(second).all():raise ValueError('Invalid WAVECAR second header')
        nk=_integer(second[0],'k-point count');nb=_integer(second[1],'band count')
        if (4+3*nb)*8>recl:raise ValueError('WAVECAR band header exceeds record length')
        if (2+spins*nk*(nb+1))*recl>size:raise ValueError('WAVECAR is truncated or has incompatible record layout')
        encut=float(second[2]);cell=second[3:12].reshape(3,3)
        if encut<=0 or abs(np.linalg.det(cell))<1.e-10:raise ValueError('Invalid WAVECAR cutoff or lattice')
        kpoints=np.empty((spins,nk,3));counts=np.empty((spins,nk),dtype=int)
        energies=np.empty((spins,nk,nb));occupations=np.empty_like(energies)
        for spin in range(spins):
            for ik in range(nk):
                check_load_cancelled()
                stream.seek((2+(spin*nk+ik)*(nb+1))*recl)
                values=np.fromfile(stream,dtype=endian+'f8',count=4+3*nb)
                if len(values)!=4+3*nb or not np.isfinite(values).all():raise ValueError('Invalid WAVECAR band header')
                counts[spin,ik]=_integer(values[0],'coefficient count')
                if counts[spin,ik]*(8 if tag==45200 else 16)>recl:raise ValueError('WAVECAR coefficients exceed record length')
                kpoints[spin,ik]=values[1:4];bands=values[4:].reshape(nb,3)
                energies[spin,ik]=bands[:,0];occupations[spin,ik]=bands[:,2]
        return Wavecar(path,recl,spins,tag,endian,nk,nb,encut,cell,float(second[12]) if len(second)>12 else None,kpoints,counts,energies,occupations)


def read_wavecar(path):
    wave=inspect_wavecar(path)
    wave.validate_reconstruction()
    results=CalculationResults('VASP')
    results.jobs=[CalculationJob(0,0,method='WAVECAR',termination='Wavefunction file; convergence not recorded')]
    for ik in range(wave.nkpoints):
        snapshot=OrbitalSet(ik,0,numbering=f'Raw WAVECAR occupation weights (not spin-degeneracy-scaled OUTCAR occupations); 1-based VASP bands; k-point {ik+1}: '+', '.join(f'{v:.8g}' for v in wave.kpoints[0,ik]))
        for spin in range(wave.spins):
            name=f'Spin {spin+1}' if wave.spins>1 else 'Bands'
            snapshot.channels[name]=[Orbital(i+1,float(occ),float(energy)) for i,(energy,occ) in enumerate(zip(wave.energies[spin,ik],wave.occupations[spin,ik]))]
        results.orbitals.append(snapshot)
    note=(f'WAVECAR: {wave.nkpoints} k-points, {wave.nbands} bands, {wave.spins} spin channel(s); ENCUT {wave.encut_ev:g} eV. '
          'Atomic positions and species are not stored in WAVECAR. Energies and raw occupation weights are read directly; raw weights are not spin-degeneracy-scaled OUTCAR occupations. Geometry is not invented. '
          'Saved projects retain metadata; lazy coefficients still require the original WAVECAR at its original path. '
          'Pseudo-wavefunction reconstruction excludes PAW augmentation. Gamma-only and spinor/SOC reconstruction are not supported.')
    frames=[]
    for name in ('CONTCAR','POSCAR'):
        companion=Path(path).parent/name
        if companion.is_file():
            try:
                from ase.io import read
                atoms=read(companion,format='vasp')
                if not np.allclose(atoms.cell.array,wave.cell,atol=1.e-5,rtol=1.e-6):continue
                from .formats import _frame_from_ase, _with_poscar_groups
                frames=[_with_poscar_groups(_frame_from_ase(atoms), companion)]
                note+=f' Display geometry from adjacent {name}; lattice matches, atomic correspondence is not encoded in WAVECAR.'
                break
            except (OSError,ValueError,IndexError):continue
    if not frames:
        candidates=[]
        for companion in sorted(Path(path).parent.iterdir()):
            if not companion.is_file() or not re.match(r'^OUTCAR(?:$|[._ (])',companion.name,re.I):continue
            try:
                from .vasp_results import last_outcar_frame
                frame=last_outcar_frame(companion)
                if frame is not None and np.allclose(frame.cell,wave.cell,atol=1.e-5,rtol=1.e-6):
                    candidates.append((companion,frame))
            except (OSError,ValueError,IndexError):continue
        if len(candidates)==1:
            companion,frame=candidates[0];frames=[frame.clone()]
            note+=f' Display geometry from adjacent {companion.name} (last complete frame); lattice matches, but this does not establish an exact calculation match.'
        elif len(candidates)>1:
            note+=' Multiple matching OUTCAR companions found; geometry was not selected automatically.'
    note+=' '+wave.reconstruction_reason
    doc=Document(Path(path),'VASP WAVECAR',frames,note=note,calculation_results=results)
    doc.wavecar=wave
    return doc
