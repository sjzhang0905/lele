"""CUBE and VASP real-space scalar fields in an explicit common grid basis.

VASP stores x fastest, CUBE normally z fastest. VASP charge files store
rho*cell_volume, whereas ELFCAR and LOCPOT store their native scalar values.
No interpolation or normalization of orbital CUBE amplitudes is performed.
"""
from pathlib import Path
from math import prod
from collections import deque
import numpy as np
from .core import Document, Volume
from .output_text import check_load_cancelled, load_progress, open_output_text, LoadCancelled
from .vasp_volume_detection import is_vasp_volume, named_vasp_volume_kind

MAX_GRID_VALUES = 64_000_000
VASP_FIELD_NAMES = ('CHGCAR','CHG','ELFCAR','LOCPOT','PARCHG','AECCAR0','AECCAR1','AECCAR2')


def _kind(path):
    return named_vasp_volume_kind(path) or 'CHGCAR'


_FIELD_CHUNK_CHARS = 1024 * 1024


class _FieldStream:
    """Small pushback buffer for consecutive VASP numeric and header blocks.

    Text offsets are not byte offsets (especially for UTF-16), so no seek or
    TextIOWrapper cookies are used to undo a chunk that crossed a block end.
    """
    def __init__(self, stream):
        self.stream=stream
        self.pending=deque()

    def read(self,size):
        pieces=[];remaining=size
        while self.pending and remaining:
            text,start=self.pending[0]
            end=min(len(text),start+remaining)
            pieces.append(text[start:end]);remaining-=end-start
            if end==len(text):self.pending.popleft()
            else:self.pending[0]=(text,end)
        if remaining:pieces.append(self.stream.read(remaining))
        return ''.join(pieces)

    def unread(self,text):
        if text:self.pending.appendleft((text,0))

    def readline(self,size=-1):
        if size==0:return ''
        pieces=[];remaining=size
        while self.pending:
            text,start=self.pending[0]
            end=text.find('\n',start)+1 or len(text)
            if size>=0:end=min(end,start+remaining)
            part=text[start:end];pieces.append(part)
            if end==len(text):self.pending.popleft()
            else:self.pending[0]=(text,end)
            if size>=0:remaining-=len(part)
            if part.endswith('\n') or remaining==0:return ''.join(pieces)
        pieces.append(self.stream.readline(remaining))
        return ''.join(pieces)

    def __iter__(self):return self

    def __next__(self):
        line=self.readline()
        if not line:raise StopIteration
        return line

    def numeric_chunk(self,size):
        """Finish at a physical line, or a token in one very long line."""
        text=self.read(size)
        while text:
            end=text.rfind('\n')+1
            if not end:end=max(text.rfind(c) for c in ' \t\r\v\f')+1
            if end:
                self.unread(text[end:])
                return text[:end]
            check_load_cancelled()
            more=self.read(size)
            if not more:break
            text+=more
        return text


def _numeric_values(text):
    """Convert a chunk in C; preserve Python float's unusual spellings."""
    import warnings
    if 'D' in text or 'd' in text:text=text.replace('D','E').replace('d','e')
    with warnings.catch_warnings():
        warnings.simplefilter('error',DeprecationWarning)
        values=np.fromstring(text,sep=' ',dtype=np.float64)
    with np.errstate(over='ignore'):
        return np.asarray(values,dtype=np.float32)


def _array_tail(stream,text,remaining,label):
    """Resolve the final chunk without consuming a later field or PAW header."""
    count=0;end=0
    # This slow path touches at most one bounded chunk per field, except when
    # valid rare numeric spelling needs the Python float compatibility path.
    for line in text.split('\n'):
        count+=len(line.split());end+=len(line)
        if end<len(text):end+=1  # Include only an actual physical newline.
        if count>=remaining:break
    if count>remaining:raise ValueError(f'Too many values in {label}.')
    selected=text[:end]
    stream.unread(text[end:])
    try:
        with np.errstate(over='ignore'):
            values=np.asarray([float(x.replace('D','E').replace('d','e'))
                               for x in selected.split()],dtype=np.float32)
    except ValueError:raise ValueError(f'Invalid numeric value in {label}.') from None
    return values,selected.endswith('\n')


def _finish_numeric_line(stream,label):
    # The required count may end inside an unusually long physical line.
    # Any extra value on that same line is malformed, not another grid header.
    while True:
        check_load_cancelled()
        tail=stream.readline(_FIELD_CHUNK_CHARS)
        if tail.strip():raise ValueError(f'Too many values in {label}.')
        if not tail or tail.endswith('\n'):return


def _array(stream,count,label):
    """Read a field in bounded NumPy blocks, leaving later headers unread."""
    data=np.empty(count,dtype=np.float32);offset=0
    report=load_progress(label,count)
    while offset<count:
        # PAW blocks can contain only a few numbers. Reading and splitting a
        # full MiB again for each atom would turn thousands of small blocks
        # into gigabytes of redundant work. The deque also keeps unread tails
        # by offsets instead of copying them on every short header read.
        budget=min(_FIELD_CHUNK_CHARS,max(256,(count-offset)*24))
        check_load_cancelled();text=stream.numeric_chunk(budget)
        if not text:raise ValueError(f'Incomplete {label}: expected {count} values, found {offset}.')
        if not text.strip():continue
        line_end=text.endswith('\n')
        try:values=_numeric_values(text)
        except (ValueError,DeprecationWarning):
            values,line_end=_array_tail(stream,text,count-offset,label)
        else:
            if len(values)>count-offset:
                values,line_end=_array_tail(stream,text,count-offset,label)
        if not np.isfinite(values).all():raise ValueError(f'Non-finite value in {label}.')
        data[offset:offset+len(values)]=values;offset+=len(values);report(offset)
        if offset==count and not line_end:_finish_numeric_line(stream,label)
    return data


def _next_grid(stream,expected=None):
    """Skip PAW one-centre augmentation blocks before looking for next grid."""
    for line in stream:
        check_load_cancelled();row=line.split()
        if not row:continue
        if row[0].lower()=='augmentation':
            try:count=int(row[-1])
            except (ValueError,IndexError):raise ValueError('Invalid VASP augmentation header.') from None
            if count<0:raise ValueError('Invalid VASP augmentation length.')
            _array(stream,count,'VASP augmentation occupancies')
            continue
        try:shape=tuple(int(x) for x in row)
        except ValueError:
            raise ValueError('Unexpected text between VASP volumetric blocks.') from None
        if len(shape)!=3 or any(n<1 for n in shape):
            raise ValueError('Expected three positive VASP grid dimensions.')
        if expected is not None and shape!=expected:
            raise ValueError('VASP field channels use inconsistent grid dimensions.')
        return shape
    return None


def _volume(data,origin,basis,label,unit,periodic=False):
    volume=Volume(data,origin,basis)
    volume.label=label;volume.unit=unit;volume.periodic=periodic
    return volume


def _vasp_labels(kind,n):
    if kind=='ELFCAR':
        if n==2:return ['ELF (spin up)','ELF (spin down)']
        return ['Electron localization function']+[f'ELF channel {i+1}' for i in range(1,n)]
    if kind=='LOCPOT':
        if n==2:return ['Local potential (spin up)','Local potential (spin down)']
        if n==4:return ['Scalar local potential','Magnetic potential x','Magnetic potential y','Magnetic potential z']
        return ['Local potential']+[f'Potential channel {i+1}' for i in range(1,n)]
    first={'AECCAR0':'Core charge density','AECCAR1':'Atomic valence charge density',
           'AECCAR2':'Self-consistent valence charge density','PARCHG':'Partial charge density'}.get(kind,'Total charge density')
    if n==2:return [first,'Magnetization density (up − down)']
    if n==4:return [first,'Magnetization density x','Magnetization density y','Magnetization density z']
    return [first]+[f'Charge channel {i+1}' for i in range(1,n)]


def read_vasp_volume_document(path,*,max_points=MAX_GRID_VALUES):
    """Read all complete scalar channels, excluding PAW augmentation values.

    A malformed/truncated field retains geometry but never presents a partial
    channel as complete. The note explains why fields were unavailable.
    """
    from ase.io.vasp import read_vasp_configuration
    from .formats import _frame_from_ase
    path=Path(path);kind=_kind(path)
    with open_output_text(path) as stream:
        atoms=read_vasp_configuration(stream)
        frame=_frame_from_ase(atoms)
        stream=_FieldStream(stream)
        grids=[]
        try:
            shape=_next_grid(stream)
            if shape is None:raise ValueError('No volumetric grid follows the VASP geometry.')
            if min(shape)<2:raise ValueError('Visualization requires at least two points per grid axis.')
            size=prod(shape);cell_volume=abs(float(np.linalg.det(frame.cell)))
            if cell_volume<1.e-12:raise ValueError('VASP cell volume is zero.')
            while shape is not None:
                if max_points is not None and size*(len(grids)+1)>max_points:
                    raise ValueError(f'VASP fields exceed configured limit ({max_points:,} scalar values).')
                data=_array(stream,size,f'VASP field {len(grids)+1}').reshape(shape,order='F')
                if kind not in ('ELFCAR','LOCPOT'):
                    with np.errstate(over='ignore'):data=data/cell_volume
                    if not np.isfinite(data).all():raise ValueError('Charge density exceeds representable numeric range.')
                grids.append(data)
                shape=_next_grid(stream,shape)
        except LoadCancelled:raise
        except (ValueError,MemoryError,OverflowError) as exc:
            return Document(path,'VASP '+kind,[frame],note=f'Atomic structure loaded; volumetric field unavailable: {exc}')
    labels=_vasp_labels(kind,len(grids));unit='dimensionless' if kind=='ELFCAR' else 'eV' if kind=='LOCPOT' else 'e/Å³'
    fields=[_volume(g,np.zeros(3),frame.cell/np.asarray(g.shape)[:,None],label,unit,True)
            for g,label in zip(grids,labels)]
    note=('VASP charge values divided by cell volume; PAW augmentation occupancies excluded from the regular grid.'
          if kind not in ('ELFCAR','LOCPOT') else 'Native scalar values retained without charge-density normalization.')
    doc=Document(path,'VASP '+kind,[frame],fields[0],note);doc.volumes=fields
    return doc


def read_cube_document(path,*,max_points=MAX_GRID_VALUES):
    from .cube_input import read_cube_file
    from .formats import _frame_from_ase
    path=Path(path)
    geometry=read_cube_file(path,read_data=False)
    frame=_frame_from_ase(geometry['atoms'])
    try:result=read_cube_file(path,max_points=max_points)
    except LoadCancelled:raise
    except (ValueError,MemoryError,OverflowError) as exc:
        return Document(path,'Gaussian CUBE',[frame],note=f'Atomic structure loaded; volumetric field unavailable: {exc}')
    labels=result.get('labels',[])
    fields=[_volume(data,result['origin'],result['spacing'],
                    f'Orbital {labels[i]}' if i<len(labels) else ('Scalar field' if len(result['datas'])==1 else f'Field {i+1}'),
                    'source units') for i,data in enumerate(result['datas'])]
    metadata=result.get('metadata',{})
    if len(fields)==1 and metadata:
        fields[0].label=metadata.get('label') or fields[0].label
        fields[0].unit=metadata.get('unit') or fields[0].unit
        fields[0].periodic=metadata.get('periodic',False)
    doc=Document(path,'Gaussian CUBE',[frame],fields[0],
                 'CUBE scalar values retain source units; geometry is in Å.');doc.volumes=fields
    return doc
