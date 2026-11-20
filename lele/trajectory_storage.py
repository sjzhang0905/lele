"""Compact float64 coordinate snapshots for large, editable trajectories."""
from contextlib import contextmanager
from copy import copy
import mmap
from pathlib import Path
import tempfile

import numpy as np

from .output_text import check_load_cancelled

# Small files are faster in memory. Each large input is decoded and validated
# once, even if it contains changing cells, atom counts or coordinate modes.
MIN_SOURCE_BYTES = 8 * 1024 * 1024


class CoordinateStore:
    def __init__(self, stream):
        self.stream = stream
        self.records = []
        self.offsets = {}
        self.edited = None

    def append(self, frame):
        if self.stream is None:
            return
        offset = self.stream.tell()
        array = np.ascontiguousarray(frame.positions, dtype=np.float64)
        try:
            if self.stream.write(memoryview(array).cast('B')) != array.nbytes:
                raise OSError('Incomplete temporary trajectory write')
        except OSError:
            # Keep already accepted frames when the temporary directory fills.
            self.restore()
            return
        self.records.append((frame, offset, array.shape))
        frame.positions = None  # Unpublished until finish(), including on cancellation.

    def restore(self):
        for frame, offset, shape in self.records:
            check_load_cancelled()
            self.stream.seek(offset)
            count = shape[0] * shape[1]
            data = np.fromfile(self.stream, dtype=np.float64, count=count)
            if data.size != count:
                raise OSError('Unable to recover the temporary trajectory coordinates')
            frame.positions = data.reshape(shape)
        self.records.clear()
        self.stream = None

    def finish(self, editable=True):
        if not self.records:
            return
        try:
            self.stream.flush()
            source = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_COPY)
            if editable:
                self.edited = mmap.mmap(self.stream.fileno(), 0, access=mmap.ACCESS_COPY)
        except (OSError, MemoryError, OverflowError):
            self.restore()
            return
        for i, (frame, offset, shape) in enumerate(self.records):
            if i % 512 == 0:
                check_load_cancelled()
            frame.positions = np.ndarray(shape, dtype=np.float64, buffer=source, offset=offset)
            if editable:
                self.offsets[id(frame)] = offset
        self.records.clear()

    def editable_frame(self, frame):
        offset = self.offsets.get(id(frame))
        if offset is None:
            return frame.clone()
        # Two independent private mappings share the clean file pages. Direct
        # NumPy writes on either side (including slices) cannot alter the other.
        # These fresh input frames already passed Frame's full validation.
        twin = copy(frame)
        for name, value in vars(frame).items():
            if name != 'positions' and isinstance(value, (dict, list, set, np.ndarray)):
                setattr(twin, name, value.copy())
        twin.positions = np.ndarray(frame.positions.shape, dtype=np.float64,
                                    buffer=self.edited, offset=offset)
        return twin


@contextmanager
def trajectory_store(path):
    stream = None
    if Path(path).stat().st_size >= MIN_SOURCE_BYTES:
        try:
            stream = tempfile.TemporaryFile(buffering=0)
        except OSError:
            pass
    try:
        yield CoordinateStore(stream)
    finally:
        if stream is not None:
            stream.close()
