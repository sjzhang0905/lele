"""Apply a frame to an existing calculation input without rewriting settings.

The format-specific editors replace source text spans, never ASE-serialize a
calculation input. Preparation is read-only and validates the complete result
before an atomic save can replace the selected file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import difflib
import os
import stat
import tempfile

import numpy as np


SUPPORTED_INPUT_KINDS = frozenset({
    'gaussian_in', 'orca_in', 'nwchem_in', 'cp2k_in', 'qe_in', 'siesta_in', 'vasp_in',
})
_LABELS = {
    'gaussian_in': 'Gaussian', 'orca_in': 'ORCA', 'nwchem_in': 'NWChem',
    'cp2k_in': 'CP2K', 'qe_in': 'Quantum ESPRESSO', 'siesta_in': 'SIESTA',
    'vasp_in': 'VASP POSCAR / CONTCAR',
}


@dataclass(frozen=True)
class CoordinateUpdatePlan:
    path: Path
    kind: str
    original_bytes: bytes = field(repr=False)
    new_bytes: bytes = field(repr=False)
    summary: str
    preview_text: str
    validated_document: object = field(repr=False, compare=False)

    @property
    def changed(self):
        return self.original_bytes != self.new_bytes


def supported_input_kind(path):
    """Return a supported calculation-input kind; outputs/fields are excluded."""
    from .legacy_converter import detect_format, ConversionError
    try:
        kind = detect_format(Path(path)).kind
    except (OSError, ValueError, ConversionError):
        return None
    return kind if kind in SUPPORTED_INPUT_KINDS else None


def _decode(raw):
    for marker, encoding in ((b'\xef\xbb\xbf', 'utf-8'),
                             (b'\xff\xfe', 'utf-16-le'), (b'\xfe\xff', 'utf-16-be')):
        if raw.startswith(marker):
            return raw[len(marker):].decode(encoding), encoding, marker
    try:
        return raw.decode('utf-8'), 'utf-8', b''
    except UnicodeDecodeError:
        # Atom/keyword syntax is ASCII. Latin-1 preserves every original byte
        # of legacy-encoded comments; do not replace undecodable characters.
        return raw.decode('latin-1'), 'latin-1', b''


def _validated_document(text, path, frame):
    from .formats import load_document
    with tempfile.TemporaryDirectory(prefix='lele-coordinate-check-') as directory:
        temporary = Path(directory) / path.name
        # Validation uses normalized encoding only in the disposable copy;
        # the eventual save retains the selected file's original encoding.
        temporary.write_bytes(text.encode('utf-8'))
        document = load_document(temporary)
    if len(document.frames) != 1:
        raise ValueError('Coordinate replacement must produce exactly one input structure; provide this input as a sample.')
    restored = document.frames[0]
    if restored.symbols != frame.symbols or restored.positions.shape != frame.positions.shape:
        raise ValueError('The updated input did not retain the requested atom order and elements; no file was changed.')
    if not np.allclose(restored.positions, frame.positions, rtol=1.e-10, atol=2.e-8):
        raise ValueError('The updated input did not reproduce the requested Cartesian coordinates; no file was changed.')
    if any(restored.pbc):
        expected_cell = frame.cell if any(frame.pbc) else np.eye(3) * 30.
        if not np.allclose(restored.cell, expected_cell, rtol=1.e-10, atol=2.e-8):
            raise ValueError('The updated periodic input did not reproduce the requested cell; no file was changed.')
    document.path = path
    document.modified = False
    return document


def prepare_coordinate_update(path, frame):
    """Create a validated, read-only replacement plan for a local input."""
    from .site_occupancy import is_disordered
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError('The selected input file is no longer available.')
    if frame is None or not frame.symbols:
        raise ValueError('Open a structure with atoms before applying coordinates.')
    if is_disordered(frame):
        raise ValueError('Calculation inputs cannot preserve mixed or partial occupancies. Export an explicitly resolved structure first.')
    if any(frame.pbc) and abs(float(np.linalg.det(frame.cell))) <= 1.e-9:
        raise ValueError('The current periodic structure has no valid cell.')
    kind = supported_input_kind(path)
    if kind is None:
        raise ValueError('The file to update must be a Gaussian, ORCA, NWChem, CP2K, QE, SIESTA or VASP POSCAR/CONTCAR input.')
    original = path.read_bytes()
    text, encoding, bom = _decode(original)
    notes = []
    if kind in ('gaussian_in', 'orca_in', 'nwchem_in'):
        from .coordinate_templates_molecular import replace_molecular_coordinates
        updated = replace_molecular_coordinates(text, kind, frame)
    elif kind in ('cp2k_in', 'qe_in', 'siesta_in'):
        from .coordinate_templates_periodic import replace_periodic_coordinates
        updated = replace_periodic_coordinates(text, kind, frame)
    else:
        from .coordinate_templates_poscar import replace_poscar_coordinates
        updated = replace_poscar_coordinates(text, frame, path=path, notes=notes)
    new_bytes = bom + updated.encode(encoding)
    document = _validated_document(updated, path, frame)
    # Fail preparation if a separate editor changed the file while parsing.
    if path.read_bytes() != original:
        raise ValueError('The input file changed during preparation. Select it again to refresh the preview.')
    periodic = any(document.frames[0].pbc)
    if periodic:
        description = 'current cell' if any(frame.pbc) else '30 × 30 × 30 Å cell'
    else:
        description = 'isolated coordinates'
    summary = f'{_LABELS[kind]} · {len(frame.symbols)} atoms · {description}'
    if kind == 'vasp_in':
        old_header, new_header = text.splitlines(), updated.splitlines()
        if new_header[7].lstrip().lower().startswith('s'):
            notes.insert(0, 'Selective dynamics follows target row order. Extra rows get T T T and surplus trailing rows are removed.')
        if old_header[5].split() != new_header[5].split():
            notes.append(f'Check the POTCAR sequence for these species blocks: {new_header[5].strip()}')
        if notes:
            summary += '\n' + '\n'.join(notes)
    changes = difflib.unified_diff(text.splitlines(keepends=True), updated.splitlines(keepends=True),
                                   fromfile=path.name, tofile=path.name + ' (updated)', n=3)
    preview = ''.join(changes)
    if len(preview) > 500_000:
        preview = preview[:500_000] + '\n… Preview truncated; the complete validated input will be saved.\n'
    return CoordinateUpdatePlan(path, kind, original, new_bytes, summary, preview, document)


def _backup_original(path, original):
    number = 0
    while True:
        suffix = '.lele.bak' + (f'.{number}' if number else '')
        candidate = path.with_name(path.name + suffix)
        try:
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(candidate, stat.S_IMODE(path.stat().st_mode))
            return candidate
        except FileExistsError:
            number += 1


def save_coordinate_update(plan, destination=None, *, backup=True):
    """Atomically save a prepared input; refuse stale or unexpected overwrite.

    A destination other than the prepared target must be a new path. The GUI
    normally uses the default target and keeps its previous bytes in a unique
    ``.lele.bak`` file. Temporary validation never writes the target.
    """
    if not isinstance(plan, CoordinateUpdatePlan):
        raise TypeError('Expected a prepared coordinate update.')
    destination = plan.path if destination is None else Path(destination).expanduser().resolve()
    overwrite = destination == plan.path
    if overwrite:
        if not destination.is_file() or destination.read_bytes() != plan.original_bytes:
            raise ValueError('The input file has changed since the preview. Reopen Apply new coordinates before saving.')
        if not plan.changed:
            return destination
        mode = stat.S_IMODE(destination.stat().st_mode)
    else:
        if destination.exists():
            raise FileExistsError('The alternate destination already exists; select a new filename.')
        mode = 0o600
    fd, filename = tempfile.mkstemp(prefix='.' + destination.name + '.', suffix='.tmp', dir=destination.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(plan.new_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if overwrite:
            if destination.read_bytes() != plan.original_bytes:
                raise ValueError('The input file changed before saving. No replacement was made.')
            if backup:
                _backup_original(destination, plan.original_bytes)
            if destination.read_bytes() != plan.original_bytes:
                raise ValueError('The input file changed before saving. No replacement was made.')
            os.replace(temporary, destination)
        else:
            # Hard-link an already written temp file using exclusive creation;
            # unlike replace this cannot clobber a concurrently created path.
            os.link(temporary, destination)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)
    return destination
