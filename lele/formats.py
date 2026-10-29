#!/usr/bin/env python3
"""Integration with the user's ChemStructConverter 1.1.0 structure readers.

Geometry support follows the converter. Additional trajectory readers handle
ASE-supported multi-image formats and SIESTA output/ANI histories. Other legacy
parsers (e.g. CP2K output) may still return the final geometry only.
"""
from __future__ import annotations

from pathlib import Path
import itertools
import numpy as np

from .core import Document, Frame, Volume
from .poscar_labels import read_poscar_groups
from .siesta_trajectory import load_siesta_history
from . import legacy_converter as legacy

# iread(index=':') supports these formats reliably enough for a first pass.
# The original converter only reads the last configuration.
TRAJECTORY_KINDS = {
    'xyz', 'vasp_out', 'gaussian_out', 'orca_out', 'nwchem_out',
    'qe_out', 'ase_generic',
}
MAX_FRAMES = 750
MAX_VOLUME_POINTS = 2_000_000
BOHR_ANG = 0.529177210903


def _with_output_vibrations(document, kind):
    if kind == 'gaussian_out':
        from .gaussian_vibrations import read_gaussian_vibrations
        document.vibrations, note = read_gaussian_vibrations(document.path)
        document.note = ' '.join(filter(None, (document.note, note)))
    elif kind == 'orca_out':
        from .orca_results import read_orca_results
        from .orca_vibrations import read_orca_vibrations
        if document.calculation_results is None:
            document.calculation_results = read_orca_results(document.path)
        document.vibrations, note = read_orca_vibrations(document.path, document.calculation_results)
        document.note = ' '.join(filter(None, (document.note, note)))
    return document


def _frame_from_ase(atoms):
    energy = None
    # The SinglePointCalculator attached by ASE is the only supported energy
    # source here; we intentionally do not trigger a new quantum calculation.
    calc = getattr(atoms, 'calc', None)
    if calc is not None and 'energy' in getattr(calc, 'results', {}):
        try:
            energy = float(calc.results['energy'])
        except (TypeError, ValueError):
            pass
    info = {str(k): str(v)[:180] for k, v in atoms.info.items()
            if isinstance(v, (str, int, float, bool))}
    if calc is not None and 'forces' in getattr(calc, 'results', {}):
        forces=np.asarray(calc.results['forces'],float)
        if forces.size and np.isfinite(forces).all():
            info['cartesian_max_force_ev_ang']=float(np.abs(forces).max())
            info['cartesian_rms_force_ev_ang']=float(np.sqrt(np.mean(forces**2)))
    return Frame(symbols=atoms.get_chemical_symbols(),
                 positions=atoms.get_positions().copy(),
                 cell=atoms.cell.array.copy(),
                 pbc=tuple(bool(x) for x in atoms.pbc),
                 energy_ev=energy, info=info)


def _with_poscar_groups(frame: Frame, path: Path) -> Frame:
    groups = read_poscar_groups(path, frame.symbols)
    if groups is not None:
        frame.info['poscar_groups'] = groups
    return frame


def _cube_grid(path: Path) -> Volume:
    """Read grid axes from CUBE header, data via ASE; no artificial axes.

    All-negative grid counts represent Angstrom in the Gaussian CUBE convention.
    The ASE loader handles the full field data and negative atom counts.
    """
    from ase.io.cube import read_cube_data

    with path.open('r', errors='replace') as f:
        next(f); next(f)
        header = next(f).split()
        n_atoms = abs(int(header[0]))
        origin = np.asarray([float(x) for x in header[1:4]], dtype=float)
        counts = []
        steps = []
        for _ in range(3):
            fields = next(f).split()
            counts.append(int(fields[0]))
            steps.append([float(x) for x in fields[1:4]])
    if len(set(x < 0 for x in counts)) > 1:
        raise ValueError('CUBE axes mix Bohr and Angstrom conventions')
    if np.prod(np.abs(counts), dtype=np.int64) > MAX_VOLUME_POINTS:
        raise ValueError(f'CUBE grid exceeds MVP limit ({MAX_VOLUME_POINTS:,} points)')
    factor = 1.0 if counts[0] < 0 else BOHR_ANG
    data, _atoms = read_cube_data(str(path))
    if data.ndim != 3:
        raise ValueError('Multi-channel CUBE grid is not yet supported')
    return Volume(data, origin * factor, np.asarray(steps) * factor)


def _load_document(filename: str | Path, max_frames: int = MAX_FRAMES) -> Document:
    from ase.io import iread

    path = Path(filename).expanduser().resolve()
    if path.name.endswith('.finalensemble.xyz'):
        from .orca_goat import read_goat_ensembles
        ensembles=read_goat_ensembles(path)
        frames=[]
        for ei,e in enumerate(ensembles):
            for c in e.conformers:
                if c.reference is not None:
                    c.reference.info.update(goat_ensemble=ei,goat_conformer=c.number,series_key=f'goat:{ei}',series_label=f'GOAT ensemble {ei+1}')
                    frames.append(c.reference)
        if not frames:raise ValueError('No complete conformer coordinates in ensemble XYZ')
        return Document(path,'ORCA GOAT ensemble',frames)
    if path.name.endswith(('.NEB.log','.interp','.interp.final','_MEP_trj.xyz','_MEP_ALL_trj.xyz')):
        from .orca_neb import companion_prefix,read_xyz_records
        prefix=companion_prefix(path,[])
        xyz=Path(str(prefix)+'_MEP_trj.xyz')
        if not xyz.exists():xyz=Path(str(prefix)+'_MEP_ALL_trj.xyz')
        records=read_xyz_records(xyz) if xyz.exists() else []
        if not records:raise ValueError('Open the main NEB output, or place the MEP XYZ beside this NEB results file.')
        if path.name.endswith('_MEP_ALL_trj.xyz') and not Path(str(prefix)+'.NEB.log').exists() and not Path(str(prefix)+'.interp').exists() and not Path(str(prefix)+'_MEP_trj.xyz').exists():
            return Document(path,'XYZ NEB records (image count unavailable)',records,note='Place the main output/NEB.log beside this file to identify images and iterations.')
        return Document(path,'ORCA NEB results',[records[0]])
    detection = legacy.detect_format(path)
    kind = detection.kind
    note = ''
    volume = None

    if kind in ('xtb_out','xtb_trj'):
        from .xtb_results import read_xtb_results
        results=read_xtb_results(path,trajectory=kind=='xtb_trj')
        frames=results.frames(max_frames)
        note=results.note
        if not frames:
            note+=' Results loaded independently; no coordinate records were printed in this file.'
        return Document(path,detection.label,frames,note=note,calculation_results=results)

    if kind in ('gaussian_out','orca_out'):
        from .calculation_results import read_calculation_results
        results=read_calculation_results(path,kind)
        frames=results.frames(max_frames)
        if not frames and kind=='orca_out':
            from .orca_goat import read_goat_ensembles
            ensembles=read_goat_ensembles(path)
            for ei,e in enumerate(ensembles):
                for c in e.conformers:
                    if c.reference is not None:
                        c.reference.info.update(goat_ensemble=ei,goat_conformer=c.number,series_key=f'goat:{ei}',series_label=f'GOAT ensemble {ei+1}')
                        frames=[c.reference];break
                if frames:break
            if ensembles and not frames:
                frames=[Frame([],np.empty((0,3)),info={'missing_geometry':True})]
                note='Analysis-only ensemble: no printed or companion geometry was found.'
        if frames and not results.periodic_geometry_seen:
            return _with_output_vibrations(Document(path,detection.label,frames,note=note,
                calculation_results=results),kind)

    if kind == 'siesta_out':
        frames, note = load_siesta_history(path, max_frames)
        if frames:
            return Document(path, detection.label, frames, None, note)
        # Retain the converter fallback when the output has no printed steps.

    if path.suffix.lower() == '.ani':
        frames, note = load_siesta_history(path, max_frames)
        if frames:
            return Document(path, 'SIESTA ANI trajectory', frames, None, note)

    # CUBE readers return the atomic configuration; separately recover 3D grid.
    if path.suffix.lower() in ('.cube', '.cub'):
        atoms, detection = legacy.read_structure(path, detection)
        try:
            volume = _cube_grid(path)
        except Exception as ex:
            note = f'Atomic structure loaded; volumetric field unavailable: {ex}'
        return Document(path, detection.label, [_frame_from_ase(atoms)], volume, note)

    # Some ASE multi-image formats use a fixed explicit format identifier.
    # For all non-trajectory formats, keep the exact legacy parser behaviour.
    if kind in TRAJECTORY_KINDS:
        ase_format = {
            'xyz': 'extxyz', 'vasp_out': 'vasp-out',
            'gaussian_out': 'gaussian-out', 'orca_out': 'orca-output',
            'nwchem_out': 'nwchem-out', 'qe_out': 'espresso-out',
        }.get(kind, detection.ase_format)
        opts = {'format': ase_format} if ase_format else {}
        if kind == 'qe_out':
            opts['results_required'] = False
        frames = []
        try:
            for atoms in itertools.islice(iread(str(path), index=':', **opts), max_frames + 1):
                if len(frames) == max_frames:
                    raise ValueError(f'Trajectory exceeds {max_frames} frames; use frame chunks in a future version')
                frames.append(_frame_from_ase(atoms))
        except Exception as ex:
            # If a reader provides only the final structure, preserve that
            # existing converter feature rather than rejecting the file.
            final_atoms, detection = legacy.read_structure(path, detection)
            frames = [_frame_from_ase(final_atoms)]
            note = f'Only last geometry loaded (multi-frame reader: {str(ex)[:150]})'
        if frames:
            return _with_output_vibrations(Document(path, detection.label, frames, volume, note), kind)

    atoms, detection = legacy.read_structure(path, detection)
    frame = _frame_from_ase(atoms)
    if kind == 'vasp_in':
        frame = _with_poscar_groups(frame, path)
    return _with_output_vibrations(Document(path, detection.label, [frame], volume,
                    'Final structure only (legacy parser).' if kind.endswith('_out') else ''), kind)


def load_document(filename: str | Path, max_frames: int = MAX_FRAMES) -> Document:
    document = _load_document(filename, max_frames)
    try:kind = legacy.detect_format(document.path).kind
    except Exception:kind = 'siesta_out' if document.path.suffix.lower()=='.ani' else document.format_name
    if document.format_name.startswith('ORCA'):kind='orca_out'
    for frame in document.frames:
        frame.info['source_kind'] = kind
        frame.info['source_format'] = document.format_name
        if frame.energy_ev is not None and not np.isfinite(frame.energy_ev):frame.energy_ev = None
    if kind == 'gaussian_out':
        from .gaussian_properties import read_gaussian_properties
        document.dipoles, document.electronic_spectra = read_gaussian_properties(document.path)
    for analysis in document.vibrations:
        analysis.reference.info['source_kind']=kind
    if document.calculation_results is None:
        from .calculation_results import read_calculation_results
        document.calculation_results=read_calculation_results(document.path,kind)
    if kind == 'orca_out':
        from .gaussian_properties import read_orca_properties
        document.dipoles,document.electronic_spectra=read_orca_properties(document.path,document.calculation_results)
        from .orca_neb import attach_neb
        from .orca_goat import attach_goat
        from .orca_soc import read_soc
        if document.format_name=='ORCA NEB results':document.frames.clear()
        attach_neb(document)
        attach_goat(document)
        document.soc_results=read_soc(document.path)
        for frame in document.frames:
            frame.info.setdefault('source_kind',kind)
            frame.info.setdefault('source_format',document.format_name)
    return document


def export_frame(frame: Frame, filename: str | Path, target: str, box_size: float = 30.0):
    """Write a structure in one of the original converter's 5 output modes."""
    from ase import Atoms

    if target not in legacy.TARGETS.values():
        raise ValueError(f'Unsupported export target: {target}')
    atoms = Atoms(symbols=frame.symbols, positions=frame.positions.copy(),
                  cell=frame.cell.copy(), pbc=frame.pbc)
    for k in ('converter_charge', 'converter_mult'):
        if k in frame.info:
            try:
                atoms.info[k] = int(frame.info[k])
            except (ValueError, TypeError):
                pass
    prepared, notices = legacy.prepare_for_target(atoms, target, float(box_size))
    legacy.write_target(Path(filename), prepared, target,
                        Path(filename).stem, legacy.DEFAULT_GAUSSIAN_ROUTE)
    return notices
