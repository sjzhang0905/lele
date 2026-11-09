"""Validated WAVECAR access and official ORCA GBW conversion.

No GBW binary layout is guessed. WAVECAR bands are read lazily; PAW on-site
augmentation is not present in the reconstructed pseudo-wavefunction.
"""
from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import time
import numpy as np
from .core import Document, Frame, Volume
from .calculation_results import CalculationResults, CalculationJob, Orbital, OrbitalSet
from .output_text import check_load_cancelled


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

    def reciprocal_vectors(self, spin=0, kpoint=0, max_points=16_000_000):
        """Enumerate the full-complex scalar G basis in VASP record order."""
        if not (0 <= spin < self.spins and 0 <= kpoint < self.nkpoints):
            raise IndexError('WAVECAR spin or k-point index out of range')
        k = self.kpoints[spin,kpoint]
        constant = 3.80998211615486  # eV Angstrom²
        bounds = np.ceil(np.linalg.norm(self.cell,axis=1) * np.sqrt(self.encut_ev/constant)/(2*np.pi) + np.abs(k)).astype(int) + 1
        if int(np.prod(2*bounds+1, dtype=object)) > max_points:
            raise ValueError('WAVECAR FFT grid exceeds the display memory limit; use a smaller exported CUBE')
        axes = [np.r_[np.arange(n+1),np.arange(-n,0)] for n in bounds]
        reciprocal = 2*np.pi*np.linalg.inv(self.cell).T
        vectors=[]
        for gz in axes[2]:
            check_load_cancelled()
            for gy in axes[1]:
                gs = np.column_stack((axes[0],np.full(len(axes[0]),gy),np.full(len(axes[0]),gz)))
                kinetic=constant*np.sum(((gs+k)@reciprocal)**2,axis=1)
                vectors.extend(gs[kinetic < self.encut_ev].tolist())
        vectors=np.asarray(vectors,dtype=int).reshape(-1,3)
        if len(vectors) != int(self.ncoeff[spin,kpoint]):
            raise ValueError('WAVECAR is not a verified full-complex scalar wavefunction (Gamma-only, spinor/SOC, or incompatible cutoff convention). Export a CUBE with a compatible VASP tool.')
        return vectors, bounds

    def validate_reconstruction(self):
        try:
            for spin in range(self.spins):
                for kpoint in range(self.nkpoints):
                    self.reciprocal_vectors(spin,kpoint)
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
        vectors,bounds = self.reciprocal_vectors(spin,kpoint,max_points)
        shape=4*bounds+1
        if int(np.prod(shape, dtype=object)) > max_points:
            raise ValueError('WAVECAR FFT grid exceeds the display memory limit; use a smaller exported CUBE')
        reciprocal_grid=np.zeros(tuple(shape),dtype=complex)
        reciprocal_grid[tuple((vectors % shape).T)] = coefficients
        check_load_cancelled()
        wave=np.fft.ifftn(reciprocal_grid)*np.prod(shape)/np.sqrt(abs(np.linalg.det(self.cell)))
        k=self.kpoints[spin,kpoint]
        if kind in ('real','imag'):
            for axis in range(3):
                view=[1,1,1];view[axis]=shape[axis]
                wave *= np.exp(2j*np.pi*k[axis]*np.arange(shape[axis])/shape[axis]).reshape(view)
            values=wave.real if kind=='real' else wave.imag
        elif kind=='density':values=np.abs(wave)**2
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
                frames=[Frame(atoms.get_chemical_symbols(),atoms.positions,atoms.cell.array,(True,True,True))]
                note+=f' Display geometry from adjacent {name}; lattice matches, atomic correspondence is not encoded in WAVECAR.'
                break
            except (OSError,ValueError,IndexError):continue
    if not frames:
        candidates=[]
        for companion in sorted(Path(path).parent.iterdir()):
            if not companion.is_file() or not re.match(r'^OUTCAR(?:$|[._ (])',companion.name,re.I):continue
            try:
                from .vasp_results import read_vasp_results
                records=read_vasp_results(companion).frames()
                if records and np.allclose(records[-1].cell,wave.cell,atol=1.e-5,rtol=1.e-6):
                    candidates.append((companion,records[-1]))
            except (OSError,ValueError,IndexError):continue
        if len(candidates)==1:
            companion,frame=candidates[0];frames=[frame.clone()]
            note+=f' Display geometry from adjacent {companion.name} (last complete frame); lattice matches, but this does not establish an exact calculation match.'
        elif len(candidates)>1:
            note+=' Multiple matching OUTCAR companions found; geometry was not selected automatically.'
    note+=' '+wave.reconstruction_reason
    doc=Document(Path(path),'VASP WAVECAR',frames,note=note,calculation_results=results)
    doc.source_preview=note+'\n\nBinary WAVECAR content is not displayed as text.'
    doc.wavecar=wave
    return doc


def convert_gbw_to_molden(path, destination, executable=None, timeout=120):
    """Run the installed official converter on a disposable copy, without shell.

    LELE_ORCA_2MKL can name an absolute official executable; otherwise PATH is
    used. Source and neighboring files are never overwritten by the converter.
    """
    executable=executable or os.environ.get('LELE_ORCA_2MKL') or shutil.which('orca_2mkl') or shutil.which('orca_2mkl.exe')
    if not executable:
        raise ValueError('ORCA GBW requires the matching ORCA orca_2mkl utility. Put it on PATH or set LELE_ORCA_2MKL to its full path, or run: orca_2mkl basename -molden and open basename.molden.input.')
    executable=str(Path(executable).expanduser().resolve())
    if not Path(executable).is_file():raise ValueError('Configured orca_2mkl executable does not exist')
    destination=Path(destination)
    with tempfile.TemporaryDirectory(prefix='lele-gbw-') as directory:
        local=Path(directory)/'wavefunction.gbw';shutil.copyfile(path,local)
        with tempfile.TemporaryFile(mode='w+b') as log:
            process=subprocess.Popen([executable,'wavefunction','-molden'],cwd=directory,stdout=log,stderr=subprocess.STDOUT,shell=False)
            start=time.monotonic()
            try:
                while process.poll() is None:
                    check_load_cancelled()
                    if time.monotonic()-start>timeout:raise ValueError('ORCA GBW conversion timed out')
                    time.sleep(.05)
            except BaseException:
                process.kill();process.wait();raise
            output=Path(directory)/'wavefunction.molden.input'
            if process.returncode or not output.is_file():
                log.seek(0);detail=log.read(4096).decode('utf-8',errors='replace')
                raise ValueError('ORCA GBW conversion failed; use the ORCA version that created the GBW. '+detail)
            check_load_cancelled();shutil.copyfile(output,destination)
    return destination


def read_gbw(path):
    from .formats import load_document
    path = Path(path)
    converter = (os.environ.get('LELE_ORCA_2MKL') or shutil.which('orca_2mkl')
                 or shutil.which('orca_2mkl.exe'))
    if not converter:
        # A GBW is not self-describing across ORCA releases. A neighboring log
        # is useful, but is not evidence that its wavefunction matches the GBW.
        for suffix in ('.log', '.out'):
            companion = path.with_suffix(suffix)
            if not companion.is_file():
                continue
            from .legacy_converter import detect_format, ConversionError
            try:
                kind = detect_format(companion).kind
            except ConversionError:
                continue
            if kind != 'orca_out':
                continue
            document = load_document(companion)
            document.path = path
            document.format_name = 'ORCA GBW companion output (GBW not decoded)'
            document.wavefunction = None
            for frame in document.frames:
                frame.info['companion_output_path'] = str(companion)
                frame.info['gbw_match_verified'] = False
            document.note = (
                f'The GBW was NOT decoded. Displayed geometry, energies and other results '
                f'come only from the same-basename companion {companion.name}; this does '
                f'not verify that the output and GBW describe the same calculation. '
                f'GBW orbital coefficients and surfaces are unavailable. Install the '
                f'orca_2mkl utility from the ORCA release that created this GBW, put it on '
                f'PATH or set LELE_ORCA_2MKL to its full path, then reopen the GBW. '
                f'Alternatively run: orca_2mkl "{path.stem}" -molden and open '
                f'"{path.stem}.molden.input". ' + document.note)
            return document
    with tempfile.TemporaryDirectory(prefix='lele-molden-') as directory:
        converted=convert_gbw_to_molden(path,Path(directory)/'wavefunction.molden.input')
        document=load_document(converted)
        document.path=Path(path);document.format_name='ORCA GBW via orca_2mkl'
        document.note=('GBW converted using the installed official ORCA orca_2mkl utility. '+document.note)
        return document
