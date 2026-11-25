"""UTF-8 JSON project records. Array blocks keep large fields streamable."""
import json
import math
from json.decoder import WHITESPACE

import numpy as np

from .output_text import check_load_cancelled, load_progress, progress_items


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _float_values(values):
    if values.dtype.itemsize > 8:
        return [str(value) for value in values]
    if values.dtype.itemsize < 8:
        # NumPy prints the shortest decimal that round-trips to the source
        # precision. Keep those digits as JSON numbers for grids and orbitals.
        values = values.astype(str).astype(np.float64)
    if np.isfinite(values).all():
        return values.tolist()
    return [number if math.isfinite(number) else str(number) for number in values.tolist()]


def _encode_values(block):
    kind = block.dtype.kind
    if kind in 'Ubiu':
        return block.tolist()
    if kind == 'f':
        return _float_values(block)
    if kind == 'c':
        return list(zip(_float_values(block.real), _float_values(block.imag)))
    # Uncommon byte/record/time dtypes retain their exact binary representation.
    width = block.dtype.itemsize
    data = block.tobytes()
    return [data[i*width:(i+1)*width].hex() for i in range(block.size)]


def write_project_text(stream, header, nodes, arrays):
    stream.write('[\n  ' + _json(header))
    for index, node in progress_items(enumerate(nodes), 'Project: writing project data', total=len(nodes)):
        record = {'id': index, **node}
        if index not in arrays:
            if node['kind'] == 'object':
                attrs = record.pop('attributes')
                entries = [_json(key) + ': ' + _json(value) for key, value in attrs.items()]
                stream.write(',\n  ' + _json(record)[:-1] + ', "attributes": {\n    '
                             + ',\n    '.join(entries) + '\n  }}')
            else:
                stream.write(',\n  ' + _json(record))
            continue
        array = arrays[index]
        record.update(dtype=np.lib.format.dtype_to_descr(array.dtype), shape=array.shape)
        stream.write(',\n  ' + _json(record))
        # Coordinates and unit cells keep one atom or vector per printed row.
        width = array.shape[-1] if array.ndim >= 2 and 1 <= array.shape[-1] <= 12 else 12
        step = 64 * width
        progress = load_progress('Project: writing ' + node.get('name', 'array'), array.size) if array.size >= 65536 else None
        for start in range(0, array.size, step):
            check_load_cancelled()
            values = _encode_values(array.flat[start:start+step])
            rows = [_json(values[pos:pos+width]) for pos in range(0, len(values), width)]
            stream.write(',\n    {"values": [\n      ' + ',\n      '.join(rows) + '\n    ]}')
            if progress is not None:
                progress(min(start + step, array.size))
    stream.write('\n]\n')


def _records(stream):
    """Read a standard JSON array incrementally, including after reformatting."""
    decoder = json.JSONDecoder()
    buffer, pos = '', 0

    def peek():
        nonlocal buffer, pos
        while True:
            pos = WHITESPACE.match(buffer, pos).end()
            if pos < len(buffer):
                return buffer[pos]
            buffer, pos = stream.read(65536), 0
            if not buffer:
                return ''

    if peek() != '[':
        raise ValueError('Expected a JSON array of LELE project records.')
    pos += 1
    while True:
        if peek() != '{':
            raise ValueError('Expected a LELE project record.')
        while True:
            try:
                record, pos = decoder.raw_decode(buffer, pos)
                break
            except json.JSONDecodeError:
                buffer = buffer[pos:]
                pos = 0
                more = stream.read(max(65536, len(buffer)))
                if not more:
                    raise
                buffer += more
        yield record
        delimiter = peek()
        pos += 1
        if delimiter == ']':
            if peek():
                raise ValueError('Unexpected data after the project.')
            return
        if delimiter != ',':
            raise ValueError('Expected a comma or the end of the project.')


def _fill_values(target, rows):
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise ValueError('Expected rows of project array values.')
    values = [value for row in rows for value in row]
    if not 0 < len(values) <= target.size:
        raise ValueError('Incorrect number of project array values.')
    part = target[:len(values)]
    if part.dtype.kind == 'c':
        pairs = np.asarray(values, dtype=part.real.dtype)
        if pairs.shape != (len(values), 2):
            raise ValueError('Expected real and imaginary components.')
        part.real, part.imag = pairs[:, 0], pairs[:, 1]
    elif part.dtype.kind in 'Ubiuf':
        part[:] = values
    else:
        raw = [bytes.fromhex(value) for value in values]
        if any(len(item) != part.dtype.itemsize for item in raw):
            raise ValueError('Incorrect project array item width.')
        if part.dtype.itemsize:
            part.view(np.uint8)[:] = np.frombuffer(b''.join(raw), dtype=np.uint8)
    return len(values)


def _field_descriptor(descriptor):
    """Restore (title, name) tuples in named or nested NumPy record fields."""
    if not isinstance(descriptor, list):
        return descriptor
    fields = []
    for name, subtype, *shape in descriptor:
        if isinstance(name, list):
            name = tuple(name)
        fields.append((name, _field_descriptor(subtype), *shape))
    return fields


def read_project_text(stream, file_size, expected_format, schema):
    records = _records(stream)
    header = next(records)
    if header.get('format') != expected_format or header.get('schema') != schema:
        raise ValueError('Unsupported LELE project format/version.')
    nodes, arrays = [], {}
    target, offset = None, 0
    progress = None
    for record in records:
        check_load_cancelled()
        if 'values' in record:
            if target is None:
                raise ValueError('Project array values without an array.')
            offset += _fill_values(target[offset:], record['values'])
            if progress is not None:
                progress(offset)
            continue
        if target is not None and offset != target.size:
            raise ValueError('Incomplete project array.')
        index = len(nodes)
        if record.get('id') != index or 'kind' not in record:
            raise ValueError('Invalid project node identifier.')
        nodes.append(record)
        target, offset, progress = None, 0, None
        if record['kind'] == 'array':
            dtype = np.lib.format.descr_to_dtype(_field_descriptor(record['dtype']))
            shape = record['shape']
            if dtype.hasobject or not isinstance(shape, list) or any(type(n) is not int or n < 0 for n in shape):
                raise ValueError('Invalid project array dtype or shape.')
            if math.prod(shape) > file_size:
                raise ValueError('Project array shape exceeds the available data.')
            array = np.empty(tuple(shape), dtype=dtype)
            arrays[index] = array
            target = array.reshape(-1)
            if target.size >= 65536:
                progress = load_progress('Project: reading ' + record.get('name', 'array'), target.size)
    if target is not None and offset != target.size:
        raise ValueError('Incomplete project array.')
    return header['root'], nodes, arrays
