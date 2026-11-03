"""Streaming XYZ blocks shared by native long-trajectory readers."""
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


def xyz_blocks(path, *, plain=False):
    """Yield complete blocks in one pass, converting coordinate arrays in C.

    Keep only one block of source text at a time. Extended-XYZ metadata and
    additional columns always go through ASE rather than being discarded.
    """
    from pathlib import Path
    size=Path(path).stat().st_size
    progress=load_progress('XYZ: reading coordinate frames',size)
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
            rows = []
            symbols = []
            for _ in range(count):
                if _%1024==0:check_load_cancelled()
                raw = stream.readline()
                line_number += 1
                fields = raw.split()
                if not raw or len(fields) < 4:
                    raise IncompleteXYZ(f'Incomplete XYZ coordinates at line {source}')
                if plain and (len(fields) != 4 or fields[0] not in atomic_numbers):
                    raise NotPlainXYZ('Extended XYZ atom fields require ASE')
                if fields[0] not in atomic_numbers:
                    raise IncompleteXYZ(f'Unknown XYZ element at line {line_number}')
                symbols.append(fields[0])
                rows.append(fields[1:4])
            positions = numeric_array(rows)
            progress(min(max(0,size-1),stream.buffer.tell()))
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
