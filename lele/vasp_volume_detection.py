"""Recognize VASP scalar grids independently of an arbitrary file basename.

Only the POSCAR header, atom table and a small scalar sample are inspected.
No ASE format registry, whole-output text copy or volumetric allocation is
needed for detection. Grid type/units cannot be inferred from numeric values;
the caller retains explicit CHGCAR/LOCPOT/ELFCAR naming when it is available.
"""
from math import isfinite, prod
from pathlib import Path
import re

from .output_text import check_load_cancelled, open_output_text

VASP_FIELD_NAMES = ('CHGCAR','CHG','ELFCAR','LOCPOT','PARCHG','AECCAR0','AECCAR1','AECCAR2')
_NAMED_FIELD = re.compile(
    r'(?:^|[._ -])(' + '|'.join(VASP_FIELD_NAMES) + r')(?=$|[._ ()-])', re.I)
_INTEGER = re.compile(r'\+?\d+\Z')
_MAX_LINE = 65536


def named_vasp_volume_kind(path):
    """Retain field units for canonical, copied and prefixed filenames."""
    match = _NAMED_FIELD.search(Path(path).name)
    return match[1].upper() if match else None


def _numbers(fields):
    try:
        values = [float(value.replace('D','E').replace('d','e')) for value in fields]
    except ValueError:
        return None
    return values if all(isfinite(value) for value in values) else None


def has_vasp_volume_data(path):
    """Probe a complete POSCAR geometry followed by a volumetric grid.

    Small grids are sampled to their exact row boundary, preventing ordinary
    POSCAR velocity rows from being mistaken for a grid header. A tail that
    can be exactly one velocity triplet per atom remains a structure unless
    augmentation/a further matching grid resolves the ambiguity. Ordinary
    five-/ten-column fields need only their first scalar row; triplet tails
    inspect at most one additional atom table to exclude velocities. The
    reader checks all scalar data and further channels during the actual load.
    """
    def line(stream):
        raw = stream.readline(_MAX_LINE)
        if not raw or (len(raw) == _MAX_LINE and not raw.endswith('\n')):
            raise ValueError('Missing or excessive header line')
        return raw

    def next_content(stream):
        for _ in range(64):
            raw = line(stream)
            if raw.strip():
                return raw.split()
        raise ValueError('No nearby content')

    def velocity_tail(stream,count):
        """The putative grid header may actually be atom 1's velocity."""
        position=stream.tell()
        try:
            for index in range(count-1):
                if index % 512 == 0:
                    check_load_cancelled()
                try:
                    row=next_content(stream)
                except ValueError:
                    return False  # Not enough triplets for all atom velocities.
                if len(row)!=3 or _numbers(row) is None:
                    return False
            try:
                following=next_content(stream)
            except ValueError:
                return True
            # A normal POSCAR can append predictor-corrector data after its
            # velocities. A further scalar grid/augmentation header instead
            # proves the volumetric interpretation and is checked by the reader.
            return following[0].lower().startswith('predictor')
        finally:
            stream.seek(position)

    try:
        with open_output_text(path) as stream:
            check_load_cancelled()
            line(stream)  # Free-form title; a blank title is valid.
            scale = _numbers(line(stream).split())
            if scale is None or len(scale) not in (1,3) or any(value == 0 for value in scale):
                return False
            if len(scale) == 3 and any(value < 0 for value in scale):
                return False
            for _ in range(3):
                row = line(stream).split()
                if len(row) < 3 or _numbers(row[:3]) is None:
                    return False
            row = line(stream).split()
            if not row:
                return False
            if not all(_INTEGER.fullmatch(value) for value in row):
                # VASP 5 element labels precede the counts. VASP 4 starts
                # directly with counts, with species recovered by the reader.
                row = line(stream).split()
            if not row or not all(_INTEGER.fullmatch(value) for value in row):
                return False
            count = sum(map(int,row))
            if count < 1:
                return False
            mode = line(stream).strip().lower()
            if mode.startswith('s'):
                mode = line(stream).strip().lower()
            if not mode or mode[0] not in 'dck' or 'configuration' in mode:
                return False
            for index in range(count):
                if index % 512 == 0:
                    check_load_cancelled()
                row = line(stream).split()
                if len(row) < 3 or _numbers(row[:3]) is None:
                    return False
            shape = next_content(stream)
            if len(shape) != 3 or not all(_INTEGER.fullmatch(value) for value in shape):
                return False
            shape = tuple(map(int,shape))
            if min(shape) < 1:
                return False
            # Only triplet-form scalar rows reach an O(natoms) look-ahead.
            # Ordinary five-/ten-column CHGCAR rows stop after one short row.
            if velocity_tail(stream,count):
                return False
            expected = prod(shape)
            if expected <= 64:
                seen = 0
                while seen < expected:
                    row = next_content(stream)
                    if _numbers(row) is None:
                        return False
                    seen += len(row)
                return seen == expected
            # A long physical data row should not turn this cheap probe into
            # a whole-line allocation. Numeric tokens can cross the boundary.
            for _ in range(64):
                sample = stream.readline(4096)
                if not sample:
                    return False
                if not sample.strip():
                    continue
                if len(sample) == 4096 and not sample.endswith('\n'):
                    sample = sample.rsplit(None,1)[0] if any(c.isspace() for c in sample) else ''
                row = sample.split()
                return bool(row) and _numbers(row[:16]) is not None
            return False
    except (OSError,ValueError,OverflowError):
        return False


def is_vasp_volume(path):
    # CHGCAR.cube / LOCPOT.cube commonly denote an actual format conversion.
    # Check their contents before honoring the VASP name, while a CHGCAR merely
    # renamed to *.cube must still bypass the CUBE parser.
    if Path(path).suffix.lower() in ('.cube','.cub'):
        return has_vasp_volume_data(path)
    return named_vasp_volume_kind(path) is not None or has_vasp_volume_data(path)
