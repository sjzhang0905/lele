#!/usr/bin/env python3
"""Integration with the user's ChemStructConverter 1.1.0 structure readers.

Native readers retain calculation records and trajectories independently.
Additional ASE-supported multi-image formats use unrestricted iteration;
unsupported legacy formats may still provide only their final geometry.
"""
from __future__ import annotations

from pathlib import Path
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
MAX_FRAMES = None  # No application frame-count limit.
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
    from .site_occupancy import from_ase
    info.update(from_ase(atoms))
    from .vasp_constraints import read_fixed_axes
    flags=read_fixed_axes(atoms)
    if flags is not None:info['vasp_fixed_axes']=flags
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
    with Path(path).open('r',encoding='utf-8-sig',errors='replace') as stream:
        header=[next(stream,'') for _ in range(9)]
    if any(line.strip().lower().startswith('selective') for line in header):
        frame.info.setdefault('vasp_fixed_axes',[[False]*3 for _ in frame.symbols])
    return frame


def _cube_grid(path: Path) -> Volume:
    """Use the same normalized CUBE geometry and units as the atom reader."""
    from .cube_input import read_cube_file
    result=read_cube_file(path,max_points=MAX_VOLUME_POINTS)
    return Volume(result['data'],result['origin'],result['spacing'])


def _load_document(filename: str | Path, max_frames: int | None = MAX_FRAMES) -> Document:
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

    if kind in ('qe_in','qe_out'):
        from .qe_results import read_qe_input,read_qe_output
        results=read_qe_input(path) if kind=='qe_in' else read_qe_output(path)
        return Document(path,detection.label,results.frames(max_frames),calculation_results=results,note=results.note)
    if kind in ('qe_phonon','qe_modes'):
        from .qe_phonons import read_qe_phonons
        if kind=='qe_modes' and path.suffix.lower()=='.eig':
            raise ValueError('Open normalized QE .modes displacements; .eig mass-weighted eigenvectors are a different representation.')
        return read_qe_phonons(path,stdout=kind=='qe_phonon')

    if kind=='molden_vib':
        from .molden_vibrations import read_molden_vibrations
        frame,vibrations,results,note=read_molden_vibrations(path)
        return Document(path,detection.label,[frame.clone()],vibrations=vibrations,calculation_results=results,note=note)

    if kind in ('cp2k_in','cp2k_out','cp2k_xyz'):
        from .cp2k_results import read_cp2k_output,read_cp2k_xyz
        from .cp2k_input import read_cp2k_input
        if kind=='cp2k_in':results,frames=read_cp2k_input(path)
        else:
            results=read_cp2k_xyz(path,max_frames) if kind=='cp2k_xyz' else read_cp2k_output(path)
            frames=results.frames(max_frames)
        if max_frames is not None and len(frames)>max_frames:raise ValueError(f'Trajectory exceeds {max_frames} frames')
        return Document(path,detection.label,frames,note=results.note,calculation_results=results,
                        electronic_spectra=results.spectra,dipoles=results.dipoles)

    if kind in ('vasp_out', 'vasp_xdatcar', 'vasp_oszicar'):
        from .vasp_results import read_vasp_results, read_xdatcar, read_oszicar
        results = (read_xdatcar(path, max_frames) if kind == 'vasp_xdatcar' else
                   read_oszicar(path) if kind == 'vasp_oszicar' else read_vasp_results(path))
        frames = results.frames(max_frames)
        note = results.note
        if not frames:
            note += ' Results loaded independently; no complete, identified structure was printed in this file.'
        return Document(path, detection.label, frames, note=note,
                        calculation_results=results, vibrations=results.vibrations)

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

    if kind=='nwchem_out':
        from .nwchem_trajectory import read_nwchem_frames
        return Document(path,detection.label,read_nwchem_frames(path,max_frames))

    # CUBE readers return the atomic configuration; separately recover 3D grid.
    if path.suffix.lower() in ('.cube', '.cub'):
        atoms, detection = legacy.read_structure(path, detection)
        try:
            volume = _cube_grid(path)
        except Exception as ex:
            from .output_text import LoadCancelled
            if isinstance(ex,LoadCancelled):raise
            note = f'Atomic structure loaded; volumetric field unavailable: {ex}'
        return Document(path, detection.label, [_frame_from_ase(atoms)], volume, note)

    # Some ASE multi-image formats use a fixed explicit format identifier.
    # For all non-trajectory formats, keep the exact legacy parser behaviour.
    if kind in TRAJECTORY_KINDS:
        if kind == 'xyz':
            from .trajectory_io import read_plain_xyz, NotPlainXYZ, FrameLimitExceeded
            try:
                frames = read_plain_xyz(path, max_frames)
                if frames:
                    return Document(path, detection.label, frames)
            except FrameLimitExceeded:
                raise
            except (NotPlainXYZ, ValueError):
                pass  # Full ASE semantics for metadata, columns or unusual XYZ.
        ase_format = {
            'xyz': 'extxyz', 'vasp_out': 'vasp-out',
            'gaussian_out': 'gaussian-out', 'orca_out': 'orca-output',
            'nwchem_out': 'nwchem-out', 'qe_out': 'espresso-out',
        }.get(kind, detection.ase_format)
        opts = {'format': ase_format} if ase_format else {}
        if kind == 'qe_out':
            opts['results_required'] = False
        frames = []
        from .output_text import load_progress
        report=load_progress('ASE: reading '+detection.label)
        try:
            for atoms in iread(str(path), index=':', **opts):
                from .output_text import check_load_cancelled
                check_load_cancelled()
                if max_frames is not None and len(frames) == max_frames:
                    from .trajectory_io import FrameLimitExceeded
                    raise FrameLimitExceeded(f'Trajectory exceeds {max_frames} frames')
                frames.append(_frame_from_ase(atoms))
                report(len(frames))
        except Exception as ex:
            from .trajectory_io import FrameLimitExceeded
            from .output_text import LoadCancelled
            if isinstance(ex, (FrameLimitExceeded, LoadCancelled)):
                raise
            # If a reader provides only the final structure, preserve that
            # existing converter feature rather than rejecting the file.
            final_atoms, detection = legacy.read_structure(path, detection)
            frames = [_frame_from_ase(final_atoms)]
            note = f'Only last geometry loaded (multi-frame reader: {str(ex)[:150]})'
        if frames:
            return _with_output_vibrations(Document(path, detection.label, frames, volume, note), kind)

    if kind=='cif':
        from .cif_input import read_cif_atoms
        atoms=read_cif_atoms(path)
    else:atoms, detection = legacy.read_structure(path, detection)
    frame = _frame_from_ase(atoms)
    if kind == 'vasp_in':
        frame = _with_poscar_groups(frame, path)
    return _with_output_vibrations(Document(path, detection.label, [frame], volume,
                    'Final structure only (legacy parser).' if kind.endswith('_out') else ''), kind)


def load_document(filename: str | Path, max_frames: int | None = MAX_FRAMES, *, cancelled=None, progress=None) -> Document:
    from .output_text import output_read_session, check_load_cancelled
    with output_read_session(cancelled,progress):
        document = _load_complete_document(filename, max_frames)
        check_load_cancelled()
        return document


def _load_complete_document(filename, max_frames):
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
    from .vasp_constraints import attach_fixed_axes
    if target in ('poscar-direct','poscar-cartesian'):attach_fixed_axes(atoms,frame.info)
    from .site_occupancy import is_disordered
    if is_disordered(frame) and target!='cif':
        raise ValueError('Fractional site occupancies require CIF export. Construct an explicit ordered structure before exporting a calculation input.')
    if 'site_occupancies' in frame.info:
        atoms.info['occupancy']={str(i):dict(s) for i,s in enumerate(frame.info['site_occupancies'])}
        atoms.set_array('spacegroup_kinds',np.arange(len(atoms),dtype=int))
    for k in ('converter_charge', 'converter_mult'):
        if k in frame.info:
            try:
                atoms.info[k] = int(frame.info[k])
            except (ValueError, TypeError):
                pass
    prepared, notices = legacy.prepare_for_target(atoms, target, float(box_size))
    if target in ('poscar-direct','poscar-cartesian'):
        from ase.io import write
        write(str(filename),prepared,format='vasp',direct=target=='poscar-direct',sort=False,vasp5=True,
              symbol_count=frame.info.get('poscar_groups'))
    elif target=='cif':
        from .cif_output import write_frame_cif
        write_frame_cif(frame,prepared,filename)
    else:
        legacy.write_target(Path(filename), prepared, target,
                            Path(filename).stem, legacy.DEFAULT_GAUSSIAN_ROUTE)
    return notices
