"""Streaming XYZ blocks shared by native long-trajectory readers."""
from itertools import islice
import numpy as np
from ase.data import atomic_numbers
from .output_text import open_output_text, check_load_cancelled, load_progress


class IncompleteXYZ(ValueError):
    pass


class NotPlainXYZ(ValueError):
    """The full ASE extended-XYZ reader is needed for this file."""


class FrameLimitExceeded(ValueError):
    """Only used for an explicitly requested programmatic limit."""


def numeric_array(rows):
    """Convert a coordinate/force block once, retaining Fortran D exponents."""
    try:
        return np.asarray(rows, dtype=float)
    except ValueError:
        return np.asarray([[x.replace('D', 'E').replace('d', 'e') for x in row]
                           for row in rows], dtype=float)


# Structured loadtxt parses normal XYZ atom rows in C without allocating a
# Python string for every coordinate. Object strings preserve the complete
# symbol token, so malformed labels cannot be truncated to valid elements.
_XYZ_DTYPE = np.dtype([('symbol', object), ('position', float, (3,))])


def coordinate_lines(stream, count):
    """Read a bounded frame in C-backed iterator batches, keeping cancellation."""
    rows = []
    for start in range(0, count, 1024):
        check_load_cancelled()
        chunk = list(islice(stream, min(1024, count-start)))
        rows.extend(chunk)
        if len(chunk) < min(1024, count-start):
            break
    return rows


def _xyz_coordinates(rows, count, source, plain):
    if len(rows) != count:
        raise IncompleteXYZ(f'Incomplete XYZ coordinates at line {source}')
    # Tiny frames are cheaper through the straightforward reader. The slow
    # path also retains precise legacy errors and Fortran-D support.
    if count >= 24:
        try:
            values = np.loadtxt(rows, dtype=_XYZ_DTYPE, comments=None, ndmin=1, encoding=None,
                                usecols=None if plain else (0, 1, 2, 3))
            symbols = values['symbol'].tolist()
            if len(values) == count and set(symbols).issubset(atomic_numbers):
                return symbols, values['position'].copy()
        except ValueError:
            pass
    symbols, coordinates = [], []
    for index, raw in enumerate(rows):
        if index % 1024 == 0:
            check_load_cancelled()
        fields = raw.split()
        if len(fields) < 4:
            raise IncompleteXYZ(f'Incomplete XYZ coordinates at line {source}')
        if plain and (len(fields) != 4 or fields[0] not in atomic_numbers):
            raise NotPlainXYZ('Extended XYZ atom fields require ASE')
        if fields[0] not in atomic_numbers:
            raise IncompleteXYZ(f'Unknown XYZ element at line {source+2+index}')
        symbols.append(fields[0])
        coordinates.append(fields[1:4])
    return symbols, numeric_array(coordinates)


def xyz_blocks(path, *, plain=False):
    """Yield complete blocks in one pass, converting coordinate arrays in C.

    Keep only one block of source text at a time. Extended-XYZ metadata and
    additional columns always go through ASE rather than being discarded.
    """
    from pathlib import Path
    size = Path(path).stat().st_size
    progress = load_progress('XYZ: reading coordinate frames', size)
    with open_output_text(path) as stream:
        line_number = 0
        while True:
            check_load_cancelled()
            raw = stream.readline()
            if not raw:
                progress(size)
                return
            line_number += 1
            if not raw.strip():
                continue
            source = line_number
            try:
                count = int(raw.strip())
            except ValueError:
                raise ValueError(f'Invalid XYZ atom count at line {source}') from None
            if count <= 0:
                raise IncompleteXYZ(f'Incomplete XYZ frame at line {source}')
            raw = stream.readline()
            if not raw:
                raise IncompleteXYZ(f'Incomplete XYZ comment at line {source+1}')
            line_number += 1
            comment = raw.rstrip('\r\n')
            if plain and '=' in comment:
                raise NotPlainXYZ('Extended XYZ metadata requires ASE')
            rows = coordinate_lines(stream, count)
            line_number += len(rows)
            symbols, positions = _xyz_coordinates(rows, count, source, plain)
            progress(min(max(0, size-1), stream.buffer.tell()))
            yield source, comment, symbols, positions


def read_plain_xyz(path, max_frames=None):
    from ase.io.extxyz import key_val_str_to_dict
    from .core import Frame
    frames = []
    for _, comment, symbols, positions in xyz_blocks(path, plain=True):
        if max_frames is not None and len(frames) >= max_frames:
            raise FrameLimitExceeded(f'Trajectory exceeds {max_frames} frames')
        info = {str(k): str(v)[:180] for k, v in key_val_str_to_dict(comment).items()
                if isinstance(v, (str, int, float, bool))}
        frames.append(Frame(symbols, positions, info=info))
    return frames
