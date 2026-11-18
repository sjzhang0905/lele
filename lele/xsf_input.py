"""Read XSF geometry and endpoint-inclusive, real-space 3D scalar grids."""
from math import prod
from pathlib import Path
import re

import numpy as np
from ase.io.xsf import iread_xsf

from .core import Document, Volume
from .output_text import check_load_cancelled, open_output_text
from .volumetric_input import MAX_GRID_VALUES, _FieldStream, _array

_DIMENSIONS = ('ATOMS', 'POLYMER', 'SLAB', 'CRYSTAL')
_GRID = re.compile(r'(?:BEGIN_)?DATAGRID_?3D(?:[_\s]+(.*))?$', re.I)
_BLOCK = re.compile(r'BEGIN_BLOCK_DATAGRID_?3D$', re.I)
_END_GRID = re.compile(r'END_DATAGRID_?3D$', re.I)
_END_BLOCK = re.compile(r'END_BLOCK_DATAGRID_?3D$', re.I)


def _content(stream):
    for line in stream:
        check_load_cancelled()
        line = line.partition('#')[0].strip()
        if line:
            yield line


def _geometry_lines(stream):
    """Normalize the old dimension record for ASE without copying a scalar grid."""
    dimension = None
    for line in _content(stream):
        keyword = line.split()[0].upper()
        if 'DATAGRID' in keyword or 'BANDGRID' in keyword:
            stream.unread(line + '\n')
            return
        if keyword == 'DIM-GROUP':
            tokens = line.split()[1:] or next(_content(stream), '').split()
            if len(tokens) != 2 or tokens[0] not in ('0', '1', '2', '3'):
                raise ValueError('Invalid XSF DIM-GROUP record.')
            int(tokens[1])  # The group does not change the supplied Cartesian positions.
            declared = _DIMENSIONS[int(tokens[0])]
            if dimension and declared != dimension:
                raise ValueError('Conflicting XSF dimension records.')
            if dimension is None and declared != 'ATOMS':
                yield declared
            dimension = declared
        elif keyword in _DIMENSIONS:
            if dimension is not None and keyword != dimension:
                raise ValueError('Conflicting XSF dimension records.')
            if keyword == 'ATOMS' or dimension is None:
                yield line.upper()
            dimension = keyword
        elif keyword in ('ANIMSTEPS', 'PRIMVEC', 'CONVVEC', 'PRIMCOORD'):
            yield line.upper()
        else:
            yield line


def _images(stream):
    try:
        yield from iread_xsf(_geometry_lines(stream))
    except (AssertionError, IndexError, KeyError, RuntimeError) as exc:
        raise ValueError(f'Incomplete or invalid XSF geometry: {exc}') from exc


def read_xsf_atoms(path):
    """Final ASE configuration for the standalone structure converter."""
    with open_output_text(path) as source:
        atoms = None
        for atoms in _images(_FieldStream(source)):
            pass
    if atoms is None:
        raise ValueError('No structure in XSF file.')
    return atoms


def _vector(lines):
    values = [float(x.replace('D', 'E').replace('d', 'e'))
              for x in next(lines, '').split()]
    if len(values) != 3 or not np.isfinite(values).all():
        raise ValueError('Expected a finite three-component XSF grid vector.')
    return values


def _field(stream, lines, label, frame, remaining):
    shape = tuple(int(x) for x in next(lines, '').split())
    if len(shape) != 3 or min(shape) < 2:
        raise ValueError(f'{label} needs at least two grid points on each of three axes.')
    count = prod(shape)
    if remaining is not None and count > remaining:
        raise ValueError('XSF grids exceed the configured scalar-value memory limit.')
    origin = _vector(lines)
    spans = np.array([_vector(lines) for _ in range(3)])
    basis = spans / (np.asarray(shape)[:, None] - 1)
    if abs(np.linalg.det(basis)) < 1e-15:
        raise ValueError(f'{label} has dependent grid vectors.')
    data = _array(stream, count, f'XSF grid {label}').reshape(shape, order='F')
    if not _END_GRID.fullmatch(next(lines, '')):
        raise ValueError(f'Missing END_DATAGRID_3D or extra values in {label}.')

    # VTK/LELE periodically wrap *unique* samples. Only remove an end plane
    # when every value is a duplicate and the box is a whole primitive cell.
    periodic = (all(frame.pbc) and min(shape) > 2
                and np.allclose(spans, frame.cell, atol=2e-5, rtol=1e-6)
                and all(np.array_equal(np.take(data, 0, axis=i),
                                       np.take(data, -1, axis=i)) for i in range(3)))
    if periodic:
        data = data[:-1, :-1, :-1].copy(order='F')
    provenance = {'source_format': 'XSF'}
    if not periodic:
        provenance['grid_extent'] = 'first_to_last_sample'
    return Volume(data, origin, basis, label, 'source units', periodic, provenance=provenance), count


def read_xsf_document(path, *, max_points=MAX_GRID_VALUES, max_frames=None):
    from .formats import _frame_from_ase
    path = Path(path)
    with open_output_text(path) as source:
        stream = _FieldStream(source)
        frames = []
        for atoms in _images(stream):
            check_load_cancelled()
            if max_frames is not None and len(frames) >= max_frames:
                raise ValueError(f'Trajectory exceeds {max_frames} frames')
            frames.append(_frame_from_ase(atoms))
        if not frames:
            raise ValueError('No structure in XSF file.')
        fields = []
        used_labels = set()
        block = None
        remaining = max_points
        lines = _content(stream)
        try:
            for line in lines:
                if _BLOCK.fullmatch(line):
                    if block is not None:
                        raise ValueError('Missing END_BLOCK_DATAGRID_3D.')
                    block = next(lines, '')
                    if not block:
                        raise ValueError('Missing XSF grid block identifier.')
                elif _END_BLOCK.fullmatch(line):
                    block = None
                else:
                    match = _GRID.fullmatch(line)
                    if match:
                        name = match[1] or block or f'Field {len(fields)+1}'
                        label = name
                        suffix = 1
                        while label in used_labels:
                            suffix += 1
                            label = f'{name} ({suffix})'
                        used_labels.add(label)
                        field, count = _field(stream, lines, label, frames[0], remaining)
                        fields.append(field)
                        if remaining is not None:
                            remaining -= count
            if block is not None:
                raise ValueError('Missing END_BLOCK_DATAGRID_3D.')
        except (ValueError, MemoryError, OverflowError) as exc:
            return Document(path, 'XCrySDen XSF', frames,
                            note=f'Atomic structure loaded; volumetric field unavailable: {exc}')
    return Document(path, 'XCrySDen XSF', frames, fields[0] if fields else None, volumes=fields)
