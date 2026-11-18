"""Read-only NEB paths assembled from final, printed VASP output frames.

An image is a complete output document, not an ionic iteration within a file.
No energy convention is inferred or mixed. Atom identities follow the source
atom sequence; images must have the same sequence and fixed periodic cell.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from .core import Frame
from .output_text import check_load_cancelled, load_progress


ENERGIES = {
    'E0': ('vasp_energy_sigma0_ev', 'E0 (σ→0)'),
    'TOTEN': ('vasp_free_energy_ev', 'Free energy TOTEN'),
}


@dataclass(frozen=True)
class VaspNebPath:
    frames: tuple
    sources: tuple
    frame_indices: tuple
    energies: np.ndarray
    relative_energies: np.ndarray
    distances: np.ndarray
    positions: np.ndarray
    energy_label: str
    energy_kind: str

    @property
    def forward_barrier(self):
        """Highest sampled image minus the first image, in eV."""
        return float(self.energies.max() - self.energies[0])

    @property
    def reverse_barrier(self):
        """Highest sampled image minus the last image, in eV."""
        return float(self.energies.max() - self.energies[-1])


def is_vasp_output(document):
    if not getattr(document, 'frames', None):
        return False
    results = getattr(document, 'calculation_results', None)
    # XDATCAR and scalar grids have structures but are not energy-bearing
    # output images. A result-only OSZICAR likewise cannot supply a geometry.
    kind = str(document.frames[-1].info.get('source_kind', ''))
    if kind:
        return kind == 'vasp_out'
    return getattr(results, 'program', '') == 'VASP'


def natural_path_key(document_or_path):
    value = str(getattr(document_or_path, 'path', document_or_path)).replace('\\', '/').casefold()
    return tuple((1, int(part)) if part.isdigit() else (0, part)
                 for part in re.split(r'(\d+)', value))


def _geometry_matches_source(document, frame, index):
    """Prevent retained raw metadata from reviving an edited geometry's energy."""
    results = getattr(document, 'calculation_results', None)
    if getattr(results, 'program', '') != 'VASP':
        return None
    source_line = frame.info.get('source_line')
    candidates = [s for s in getattr(results, 'steps', ())
                  if getattr(s, 'geometry', None) is not None
                  and (getattr(s, 'frame_index', None) == index
                       or (source_line is not None and getattr(s, 'source_line', None) == source_line))]
    if not candidates:
        return None
    for step in candidates:
        original = step.geometry
        if (original.symbols == frame.symbols and tuple(original.pbc) == tuple(frame.pbc)
                and np.allclose(original.cell, frame.cell, atol=2.e-5, rtol=0)
                and np.allclose(original.positions, frame.positions, atol=2.e-5, rtol=0)):
            return True
    return False


def build_neb_path(documents, energy='E0'):
    """Snapshot the supplied order, using each document's last ionic geometry.

    Distances accumulate the Cartesian 3N displacement norm (Å), with each
    atom's adjacent displacement reduced to its minimum periodic image. This
    assumes neighboring NEB images move each atom by the shortest image and
    cannot recover an intentionally longer jump from endpoint coordinates.
    """
    from copy import deepcopy
    if energy not in ENERGIES:
        raise ValueError('Choose E0 or TOTEN; energy conventions cannot be mixed.')
    documents = tuple(documents)
    if len(documents) < 2:
        raise ValueError('Select at least two VASP output files, including the path endpoints.')
    if len({id(d) for d in documents}) != len(documents):
        raise ValueError('Each loaded output file can occur only once in a NEB path.')
    key, label = ENERGIES[energy]
    frames, sources, values, frame_indices = [], [], [], []
    report = load_progress('Preparing VASP NEB images', len(documents))
    for image, document in enumerate(documents):
        check_load_cancelled();report(image)
        source = str(document.path)
        prefix = f'Image {image} ({Path(source).name})'
        if not is_vasp_output(document):
            raise ValueError(prefix + ': select a VASP output with atomic coordinates.')
        frame = document.frames[-1]
        if not frame.symbols:
            raise ValueError(prefix + ': the final frame has no atoms.')
        value = frame.info.get(key)
        if value is None or not np.isfinite(value):
            raise ValueError(prefix + f': the final geometry has no printed {label}. All images must use the same energy convention.')
        source_match = _geometry_matches_source(document, frame, len(document.frames) - 1)
        if source_match is False:
            raise ValueError(prefix + ': its final geometry has been edited. Reload the original output before building a NEB path.')
        # Saving/deleting a named fragment changes document metadata, not its
        # physical geometry. Permit it when the retained output record proves
        # the geometry is unchanged; reject an unprovable modified snapshot.
        if source_match is None and getattr(document, 'modified', False):
            raise ValueError(prefix + ': this modified output has no unchanged source geometry to verify. Reload the original output.')
        # E0 cleared by an edit stays invalid even if its printed metadata is
        # still present. With TOTEN-only outputs, an absent E0 is legitimate.
        stale_e0 = 'vasp_energy_sigma0_ev' in frame.info and frame.energy_ev is None
        if stale_e0:
            raise ValueError(prefix + ': the final-frame energy was invalidated by editing. Reload the original output.')
        if frames:
            first = frames[0]
            if first.symbols != frame.symbols:
                raise ValueError(prefix + ': atom count, elements or atom order differs from the first image.')
            if tuple(first.pbc) != tuple(frame.pbc):
                raise ValueError(prefix + ': periodic boundary conditions differ from the first image.')
            if not np.allclose(first.cell, frame.cell, atol=2.e-5, rtol=0):
                raise ValueError(prefix + ': cell vectors differ. This viewer requires a fixed-cell NEB path.')
        if not np.isfinite(frame.positions).all() or not np.isfinite(frame.cell).all():
            raise ValueError(prefix + ': non-finite coordinates or cell vectors.')
        if any(frame.pbc) and abs(np.linalg.det(frame.cell)) < 1.e-9:
            raise ValueError(prefix + ': the periodic cell is singular.')
        frames.append(deepcopy(frame));sources.append(source)
        values.append(float(value));frame_indices.append(len(document.frames) - 1)
    raw = np.asarray([frame.positions for frame in frames])
    positions = raw.copy()
    distances = np.zeros(len(frames), dtype=float)
    for image in range(1, len(frames)):
        check_load_cancelled()
        delta = raw[image] - raw[image-1]
        if any(frames[0].pbc):
            from ase.geometry import find_mic
            # Full VASP cells use vectorized MIC, which also handles reduced
            # and non-reduced skew cells (fractional rounding does not).
            if all(frames[0].pbc):
                delta, _ = find_mic(delta, frames[0].cell, pbc=frames[0].pbc)
            else:
                from .periodic_geometry import minimum_image
                delta = np.asarray([minimum_image(d, frames[0])[0] for d in delta])
        positions[image] = positions[image-1] + delta
        distances[image] = distances[image-1] + np.linalg.norm(delta)
    energies = np.asarray(values, dtype=float)
    relative = energies - energies[0]
    for array in (energies, relative, distances, positions):
        array.setflags(write=False)
    report(len(documents))
    return VaspNebPath(tuple(frames), tuple(sources), tuple(frame_indices), energies,
                       relative, distances, positions, label, energy)


def parse_atom_indices(text, natoms, *, base=1):
    """Parse explicit-base atoms/ranges, preserving order and removing duplicates."""
    if base not in (0, 1):
        raise ValueError("Atom numbering base must be 0 or 1.")
    text = str(text).strip().replace('，', ',').replace('；', ';')
    if not text:
        raise ValueError('Enter migrating atom numbers, such as 1, 2, 5-8.')
    text = re.sub(r'\s*-\s*', '-', text)
    indices = []
    for token in re.split(r'[,;\s]+', text):
        if not token:
            continue
        match = re.fullmatch(r'(\d+)(?:-(\d+))?', token)
        if match is None:
            raise ValueError('Use atom numbers and ascending ranges, such as 1, 2, 5-8.')
        first = int(match[1]);last = int(match[2] or first)
        if not base <= first <= last < natoms + base:
            raise ValueError(f'Atom numbers must be between {base} and {natoms + base - 1}; ranges must ascend.')
        indices.extend(range(first - base, last - base + 1))
    if not indices:
        raise ValueError('Select at least one migrating atom.')
    return tuple(dict.fromkeys(indices))


def suggested_atom_indices(path):
    """The single atom with the largest summed adjacent path displacement."""
    movement = np.linalg.norm(np.diff(path.positions, axis=0), axis=2).sum(axis=0)
    return (int(np.argmax(movement)),)


def caterpillar_frame(path, indices, reference=0, *, bond_cutoff=1.):
    """Reference substrate once, plus each chosen atom at every path image.

    Moving-atom copies have no bonds. Only bonds internal to the unchanged
    reference substrate survive, preventing bonds between different images.
    The output is a display composite, not a physical calculation structure.
    Disable Boundary replication when displaying this frame.
    """
    from copy import deepcopy
    from .core import freeze_bonds
    from .site_occupancy import subset_info
    if not isinstance(reference, (int, np.integer)) or not 0 <= reference < len(path.frames):
        raise ValueError('Reference image is outside the NEB path.')
    indices = tuple(dict.fromkeys(indices))
    natoms = len(path.frames[0].symbols)
    if not indices or any(not isinstance(i, (int, np.integer)) or not 0 <= i < natoms for i in indices):
        raise ValueError('Choose valid migrating atom indices.')
    selected = set(indices)
    keep = [i for i in range(natoms) if i not in selected]
    source = deepcopy(path.frames[reference]);freeze_bonds(source, bond_cutoff)
    source_indices = keep + list(indices) * len(path.frames)
    shift = source.positions - path.positions[reference]
    track_positions = (path.positions[:, indices, :] + shift[list(indices)][None, :, :]).reshape(-1, 3)
    positions = np.concatenate((source.positions[keep], track_positions))
    mapping = {old: new for new, old in enumerate(keep)}
    bonds = frozenset((mapping[i], mapping[j]) for i, j in source.bond_snapshot
                      if i in mapping and j in mapping and (i, j) not in source.bond_removed)
    periodic = tuple((mapping[i], mapping[j], shift) for i, j, shift in (source.periodic_bond_snapshot or ())
                     if i in mapping and j in mapping and (i, j) not in source.bond_removed)
    records = [{'index': len(keep) + image * len(indices) + n,
                'source_atom': int(atom), 'image': image}
               for image in range(len(path.frames)) for n, atom in enumerate(indices)]
    # Keep only per-site physical display metadata; copied energies, input
    # provenance, fragments and constraints do not describe this composite.
    info = subset_info({key: source.info[key] for key in ('site_occupancies', 'cif_row_order')
                        if key in source.info}, source_indices)
    info.update(source_kind='neb_caterpillar_display', neb_caterpillar_atoms=records,
                neb_reference_image=int(reference), neb_source_indices=list(map(int, source_indices)),
                neb_path_sources=list(path.sources), neb_display_only=True)
    styles = {new: source.atom_appearance[old] for new, old in enumerate(source_indices)
              if old in source.atom_appearance}
    return Frame([source.symbols[i] for i in source_indices], positions, source.cell.copy(),
                 tuple(source.pbc), info=info, bond_snapshot=bonds,
                 periodic_bond_snapshot=periodic, atom_appearance=styles)


def export_path_csv(path, filename):
    """Atomically export the exact sampled energies and their source provenance."""
    import csv
    import os
    import tempfile
    destination = Path(filename);temporary = None
    try:
        report = load_progress('Exporting VASP NEB path', len(path.frames))
        with tempfile.NamedTemporaryFile(mode='w', newline='', encoding='utf-8-sig',
                                         dir=destination.parent, prefix='.'+destination.name+'.',
                                         suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name);writer = csv.writer(stream)
            writer.writerow(['image', 'path_distance_A', 'energy_eV', 'relative_energy_eV',
                             'energy_convention', 'source', 'source_frame_1based', 'source_line'])
            for i, frame in enumerate(path.frames):
                check_load_cancelled();report(i)
                writer.writerow([i, float(path.distances[i]), float(path.energies[i]),
                                 float(path.relative_energies[i]), path.energy_label, path.sources[i],
                                 path.frame_indices[i] + 1, frame.info.get('source_line', '')])
            stream.flush();os.fsync(stream.fileno())
        check_load_cancelled();os.replace(temporary, destination);temporary = None
    finally:
        if temporary is not None:
            try:temporary.unlink()
            except FileNotFoundError:pass
