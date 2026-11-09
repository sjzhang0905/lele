"""Streaming CUBE fields, orbital channels, and consistent geometric units.

Header geometry is normalized to Bohr, then returned in Angstrom. Scalar
values retain source units; skew grids and CASTEP duplicate planes are kept
consistent with their atom geometry.
"""
from math import prod
import numpy as np
from ase.units import Bohr
from .output_text import check_load_cancelled, load_progress, open_output_text


_SCALAR_CHUNK_CHARS = 1024 * 1024


def _cube_array(stream, count):
    """Parse the scalar tail in bounded chunks, including files with long lines.

    NumPy converts whole blocks in C instead of allocating a Python float and
    a tiny array for every row. A trailing partial token is carried to the next
    block, so neither exponents nor interleaved orbital channels are split.
    Geometry and all field values keep the same precision as the old reader.
    """
    import warnings
    data = np.empty(count, dtype=np.float32)
    offset = 0
    carry = ''
    report = load_progress('CUBE scalar field', count)
    while True:
        check_load_cancelled()
        chunk = stream.read(_SCALAR_CHUNK_CHARS)
        text = carry + chunk
        if chunk:
            # Find the last complete token without splitting the whole block
            # into Python strings. CUBE numeric data normally uses ASCII space.
            end = max(text.rfind(c) for c in ' \t\r\n\v\f') + 1
            if not end:
                carry = text
                continue
            carry = text[end:]
            text = text[:end]
        else:
            carry = ''
        if text.strip():
            if offset == count:
                raise ValueError('Extra values after CUBE scalar field.')
            if 'D' in text or 'd' in text:
                text = text.replace('D', 'E').replace('d', 'e')
            try:
                # NumPy 1.x warns on an unmatched suffix; NumPy 2.x raises.
                # Both must reject corrupt input rather than accept its prefix.
                with warnings.catch_warnings():
                    warnings.simplefilter('error', DeprecationWarning)
                    values = np.fromstring(text, sep=' ', dtype=np.float32)
            except (ValueError, DeprecationWarning):
                # Retain Python float's support for unusual but valid numeric
                # spelling/Unicode whitespace on this rare compatibility path.
                try:
                    values = np.asarray([float(x) for x in text.split()], dtype=np.float32)
                except ValueError:
                    raise ValueError('Invalid numeric value in CUBE scalar field.') from None
            if len(values) > count - offset:
                raise ValueError('Too many values in CUBE scalar field.')
            if not np.isfinite(values).all():
                raise ValueError('Non-finite value in CUBE scalar field.')
            data[offset:offset + len(values)] = values
            offset += len(values)
            report(offset)
        if not chunk:
            break
    if offset != count:
        raise ValueError(f'Incomplete CUBE scalar field: expected {count} values, found {offset}.')
    check_load_cancelled()
    return data


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
    lengths=np.asarray([[float(x.replace('D','E').replace('d','e')) for x in origin[1:4]],
                        *[[float(x.replace('D','E').replace('d','e')) for x in row[1:]] for row in grid]])
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
        int(row[0]);coordinates=np.asarray([float(x.replace('D','E').replace('d','e')) for x in row[2:]])
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


def read_cube_file(path,*,read_data=True,max_points=64_000_000):
    """Return atoms and scalar channels with geometric lengths in Angstrom.

    Field channels are interleaved per voxel in CUBE. Orbital labels on a
    negative-atom-count header are retained; no scalar-value rescaling occurs.
    """
    from ase import Atoms
    import re
    with open_output_text(path) as stream:
        header,shape,nvalues,nlabels=_header(stream)
        origin_row=header[2].split();natoms=abs(int(origin_row[0]))
        origin=np.asarray(origin_row[1:4],float)*Bohr
        spacing=np.asarray([row.split()[1:4] for row in header[3:6]],float)*Bohr
        rows=[row.split() for row in header[6:6+natoms]]
        numbers=[int(row[0]) for row in rows]
        if any(n<0 or n>118 for n in numbers):raise ValueError('Invalid CUBE atomic number.')
        positions=np.asarray([row[2:5] for row in rows],float).reshape((-1,3))*Bohr
        castep='castep2cube' in header[1].lower()
        cell=(np.asarray(shape)-(1 if castep else 0))[:,None]*spacing
        atoms=Atoms(numbers=numbers,positions=positions,cell=cell,pbc=True)
        labels=[]
        if nlabels:
            tokens=' '.join(header[6+natoms:]).split();labels=[int(x) for x in tokens[1:]]
        result={'atoms':atoms,'origin':origin,'spacing':spacing,'labels':labels}
        if header[0].startswith('LELE_CUBE ') and len(header[0]) < 16384:
            import json
            try:
                metadata=json.loads(header[0][10:])
                if not isinstance(metadata,dict):raise ValueError()
                if not all(isinstance(metadata.get(k,''),str) for k in ('label','unit')):raise ValueError()
                if type(metadata.get('periodic',False)) is not bool:raise ValueError()
                saved_cell=np.asarray(metadata['cell'],float)
                saved_pbc=metadata['atom_pbc']
                if saved_cell.shape!=(3,3) or not np.isfinite(saved_cell).all():raise ValueError()
                if len(saved_pbc)!=3 or any(type(x) is not bool for x in saved_pbc):raise ValueError()
                atoms.set_cell(saved_cell);atoms.set_pbc(saved_pbc)
                result['metadata']=metadata
            except (ValueError,KeyError,TypeError):pass
        if not read_data:return result
        channels=nlabels or nvalues
        if nlabels and nvalues not in (1,nlabels):raise ValueError('Conflicting CUBE orbital/value counts.')
        total=prod(shape)*channels
        if max_points is not None and total>max_points:
            raise ValueError(f'CUBE grid exceeds configured limit ({max_points:,} scalar values).')
        values=_cube_array(stream,total)
        axes=re.findall(r'(?:OUTER|MIDDLE|INNER) LOOP:\s*([XYZ])',header[1].upper())
        order=['XYZ'.index(a) for a in axes] if len(axes)==3 else [0,1,2]
        if sorted(order)!=[0,1,2]:raise ValueError('Invalid CUBE loop-axis order.')
        datas=[]
        for channel in range(channels):
            check_load_cancelled()
            data=values[channel::channels].reshape(tuple(shape[a] for a in order))
            data=data.transpose(np.argsort(order))
            if castep:data=data[:-1,:-1,:-1]
            datas.append(data)
        result.update(data=datas[0],datas=datas)
        return result
