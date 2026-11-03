"""Shared CUBE geometry/grid input with consistent Bohr/Angstrom handling.

Normalize only the small header and atom table before delegating field order,
orbital labels and CASTEP duplicate-plane handling to ASE. The source is never
rewritten and its scalar field values are not rescaled.
"""
from io import StringIO
from math import prod
import numpy as np
from ase.io.cube import read_cube
from ase.units import Bohr
from .output_text import check_load_cancelled, open_output_text


class _HeaderStream:
    def __init__(self, header, stream):
        self.header=StringIO(''.join(header));self.stream=stream

    def readline(self):
        check_load_cancelled()
        return self.header.readline() or self.stream.readline()

    def read(self):
        check_load_cancelled()
        return self.header.read()+self.stream.read()


def _header(stream):
    def line():
        text=stream.readline()
        if not text:raise ValueError('Incomplete CUBE header or atom table.')
        return text

    header=[line(),line()];origin=line().split()
    if len(origin) not in (4,5):raise ValueError('Invalid CUBE atom count/origin.')
    natoms=int(origin[0]);nvalues=int(origin[4]) if len(origin)==5 else 1
    if nvalues<1:raise ValueError('CUBE value count must be positive.')
    grid=[line().split() for _ in range(3)]
    if any(len(row)!=4 for row in grid):raise ValueError('Invalid CUBE grid vector.')
    counts=[int(row[0]) for row in grid]
    if any(n==0 for n in counts):raise ValueError('CUBE grid counts must be nonzero.')
    if len({n<0 for n in counts})!=1:
        raise ValueError('CUBE axes mix Bohr and Angstrom conventions.')
    lengths=np.asarray([[float(x) for x in origin[1:4]],
                        *[[float(x) for x in row[1:]] for row in grid]])
    if not np.isfinite(lengths).all():raise ValueError('Non-finite CUBE origin/grid vector.')
    angstrom=counts[0]<0
    # ASE always interprets lengths as Bohr and expects positive dimensions.
    if angstrom:lengths=lengths/Bohr
    header.append(' '.join([str(natoms),*(format(v,'.17g') for v in lengths[0]),*origin[4:]])+'\n')
    for n,vector in zip(counts,lengths[1:]):
        header.append(' '.join([str(abs(n)),*(format(v,'.17g') for v in vector)])+'\n')
    for _ in range(abs(natoms)):
        check_load_cancelled();row=line().split()
        if len(row)!=5:raise ValueError('Invalid CUBE atom row.')
        int(row[0]);coordinates=np.asarray([float(x) for x in row[2:]])
        if not np.isfinite(coordinates).all():raise ValueError('Non-finite CUBE atom position.')
        if angstrom:coordinates=coordinates/Bohr
        header.append(' '.join([*row[:2],*(format(v,'.17g') for v in coordinates)])+'\n')
    labels=[]
    if natoms<0:
        row=line().split()
        if not row:raise ValueError('Missing CUBE orbital labels.')
        nlabels=int(row[0]);labels=row[1:];header.append(' '.join(row)+'\n')
        if nlabels<1:raise ValueError('Invalid CUBE orbital label count.')
        while len(labels)<nlabels:
            row=line().split()
            if not row:raise ValueError('Incomplete CUBE orbital labels.')
            labels.extend(row);header.append(' '.join(row)+'\n')
        if len(labels)!=nlabels:raise ValueError('CUBE orbital label count does not match its values.')
        for value in labels:int(value)
    return header,tuple(abs(n) for n in counts),nvalues,len(labels)


def read_cube_file(path,*,read_data=True,max_points=2_000_000):
    """Return ASE's atoms and optional grid, all geometric lengths in Angstrom.

    Negative atom counts describe orbital labels independently of grid-count
    signs. Multi-channel fields remain unavailable rather than choosing one
    channel silently; their geometry can still be read.
    """
    with open_output_text(path) as stream:
        header,shape,nvalues,nlabels=_header(stream)
        if read_data:
            if prod(shape)>max_points:
                raise ValueError(f'CUBE grid exceeds MVP limit ({max_points:,} points).')
            if nvalues!=1 or nlabels>1:
                raise ValueError('Multi-channel CUBE grid is not yet supported.')
        result=read_cube(_HeaderStream(header,stream),read_data=read_data)
    check_load_cancelled()
    if read_data:
        if not np.isfinite(result['data']).all():raise ValueError('Non-finite CUBE scalar field.')
        if len(result.get('datas',()))!=1:raise ValueError('Multi-channel CUBE grid is not yet supported.')
    return result
