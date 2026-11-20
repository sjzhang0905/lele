"""Optional C ABI accelerator for CUBE values and trajectory coordinates."""
import ctypes
from functools import lru_cache
from pathlib import Path
import platform
import sys

_POWERS = (ctypes.c_double * 23)(*(10 ** i for i in range(23)))


@lru_cache(maxsize=1)
def _library():
    names = {'win32': 'cube_win_x64.dll', 'linux': 'cube_linux_x64.so'}
    if sys.platform not in names or platform.machine().lower() not in ('amd64', 'x86_64'):
        return None
    try:
        return ctypes.CDLL(str(Path(__file__).with_name('native') / names[sys.platform]))
    except OSError:
        return None


@lru_cache(maxsize=1)
def reader():
    try:
        parse = _library().lele_cube_numbers
        parse.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p,
                          ctypes.c_int, ctypes.POINTER(ctypes.c_double)]
        parse.restype = ctypes.c_int
    except (OSError, AttributeError):
        return None
    return parse


def write_chunk(parse, text, output, offset):
    if len(text) > 2**31-1 or not text.isascii():
        return -1
    raw = text.encode('ascii')
    # A chunk cannot contain more scalar values than there are characters.
    return parse(raw, len(raw), output.ctypes.data + offset * output.itemsize,
                 min(len(raw), output.size - offset), _POWERS)


@lru_cache(maxsize=1)
def _coordinate_reader():
    try:
        parse = _library().lele_coordinate_rows
        parse.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                          ctypes.c_void_p, ctypes.POINTER(ctypes.c_double)]
        parse.restype = ctypes.c_int
        return parse
    except AttributeError:
        return None


def coordinate_array(rows, *, labeled=False):
    """Return float64 coordinates and optional two-byte species codes."""
    parse = _coordinate_reader()
    if parse is None:
        return None
    import numpy as np
    text = ''.join(rows)
    if len(text) > 2**31-1 or not text.isascii():
        return None
    data = np.empty((len(rows), 3), dtype=np.float64)
    symbols = np.empty(len(rows), dtype=np.uint16) if labeled else None
    if parse(text.encode('ascii'), len(text), data.ctypes.data, len(rows),
             symbols.ctypes.data if labeled else None, _POWERS):
        return data, symbols
    return None
