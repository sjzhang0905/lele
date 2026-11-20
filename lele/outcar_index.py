"""Sparse OUTCAR record index. Numeric tables stay on disk until requested."""
from bisect import bisect_left, bisect_right
from contextlib import contextmanager
from itertools import islice
from pathlib import Path
import re
import tempfile

from .output_text import check_load_cancelled, load_progress, open_output_text, output_encoding

_MARKER = re.compile(rb'Iteration\s+\d+\(|free energie of the ion-electron system|direct lattice vectors|position of ions in cartesian coordinates|^\s*POSITION\s+TOTAL-FORCE|^\s*free\s+energy\s+TOTEN|energy\s+without\s+entropy|energy\s*\(sigma\s*->\s*0\)|reached required accuracy|General timing and accounting|Eigenvectors and eigenvalues of the dynamical matrix|Eigenvectors after division by SQRT\(mass\)|cm-1|CSA tensor|IF\s+SPAN', re.I)
_TAG = re.compile(rb'ions per type|^\s*(?:TITEL|POTCAR|VRHFIN|POMASS)\b|\b(?:NIONS|IBRION|ISIF|ENCUT|EDIFFG?|ISPIN|NELECT)\s*=')
# All structural and metadata markers contain a letter other than a decimal exponent.
_WORD = re.compile(rb'[A-CF-Za-cf-z]')
_VERSION = re.compile(rb'^\s*vasp\.\d', re.I)
_BARE_CR = re.compile(rb'\r(?!\n|$)')


class _NeedsNewlines(Exception):
    pass


class Run:
    def __init__(self, stream, start):
        self.stream = stream
        self.start = start
        self.length = 0
        self.numbers = []
        self.records = {}
        self.metadata = []
        self.nmr = []

    def __len__(self):
        return self.length

    def next_event(self, line):
        i = bisect_left(self.numbers, line)
        return self.numbers[i] if i < len(self.numbers) else self.length

    def seek_line(self, line):
        anchor = self.numbers[bisect_right(self.numbers, line)-1]
        self.stream.seek(self.records[anchor][0])
        for _ in range(line-anchor):
            self.stream.readline()

    def __getitem__(self, line):
        if line in self.records:
            return self.records[line][1]
        self.seek_line(line)
        return self.stream.readline().decode('utf-8', errors='replace').rstrip('\r\n')

    def rows(self, start, columns, count=None):
        import numpy as np
        from .vasp_results import _rows
        self.seek_line(start)
        raw = []
        numeric_start = 0
        while start + len(raw) < self.length:
            row = self.stream.readline()
            if row.strip() and row.strip().strip(b'-'):
                if count is not None:
                    raw.append(row)
                    remaining = min(count - 1, self.length - start - len(raw))
                    while remaining > 0:
                        check_load_cancelled()
                        chunk = list(islice(self.stream, min(remaining, 1024)))
                        if not chunk:
                            break
                        raw.extend(chunk)
                        remaining -= len(chunk)
                else:
                    while row.strip() and row.lstrip()[:1] in b'+-.0123456789':
                        raw.append(row)
                        if start+len(raw) >= self.length:
                            break
                        if len(raw) % 1024 == 0:
                            check_load_cancelled()
                        row = self.stream.readline()
                break
            raw.append(row)
            numeric_start += 1
            if numeric_start % 1024 == 0:
                check_load_cancelled()
        if len(raw) > numeric_start:
            try:
                values = np.loadtxt(raw[numeric_start:], comments=None, ndmin=2)
                if values.shape[0] == len(raw)-numeric_start and values.shape[1] >= columns and np.isfinite(values).all():
                    return values[:, :columns], start + len(raw)
            except (ValueError, TypeError):
                pass
        rows, consumed = _rows([r.decode('utf-8', errors='replace') for r in raw], 0, columns, count)
        return rows, start + consumed


def _index(stream, size):
    runs = [Run(stream, 0)]
    version_seen = False
    offset = 0
    count = 0
    report = load_progress('VASP: indexing OUTCAR records', size)
    while block := stream.read(1024*1024):
        if b'\r' in block and _BARE_CR.search(block):
            raise _NeedsNewlines()
        if not block.endswith(b'\n'):
            tail = stream.readline()
            if _BARE_CR.search(block[-1:]+tail):
                raise _NeedsNewlines()
            block += tail
        cursor = 0
        while match := _WORD.search(block, cursor):
            begin = block.rfind(b'\n', cursor, match.start())+1
            begin = max(begin, cursor)
            end = block.find(b'\n', match.end())
            end = len(block) if end < 0 else end+1
            count += block.count(b'\n', cursor, begin)
            raw = block[begin:end]
            line = count
            count += 1
            cursor = end
            if line == 0:
                raw = raw.removeprefix(b'\xef\xbb\xbf')
            if _VERSION.match(raw):
                if version_seen:
                    runs[-1].length = line-runs[-1].start
                    runs.append(Run(stream, line))
                version_seen = True
            run = runs[-1]
            if (b'=' in raw or b':' in raw) and _TAG.search(raw):
                run.metadata.append(raw.decode('utf-8', errors='replace').rstrip('\r\n'))
            if _MARKER.search(raw):
                local = line-run.start
                run.numbers.append(local)
                decoded = raw.decode('utf-8', errors='replace').rstrip('\r\n')
                run.records[local] = (offset+begin, decoded)
                if 'CSA tensor' in decoded or re.search(r'IF\s+SPAN', decoded, re.I):
                    run.nmr.append(local)
        count += block.count(b'\n', cursor)
        if cursor < len(block) and not block.endswith(b'\n'):
            count += 1
        offset += len(block)
        check_load_cancelled()
        report(offset)
    runs[-1].length = count-runs[-1].start
    report(size)
    return runs


@contextmanager
def indexed_outcar(path):
    path = Path(path)
    with path.open('rb') as raw:
        sample = raw.read(65536)
        raw.seek(0)
        if not output_encoding(sample).startswith('utf-16') and not _BARE_CR.search(sample):
            try:
                runs = _index(raw, path.stat().st_size)
            except _NeedsNewlines:
                pass
            else:
                yield runs
                return
        # Normalize redirected and mixed-newline output without a decoded
        # whole-file copy. Offsets in the index refer to this temporary stream.
        with tempfile.TemporaryFile() as temp, open_output_text(path) as text:
            for chunk in iter(lambda: text.read(1024*1024), ''):
                check_load_cancelled()
                temp.write(chunk.encode('utf-8'))
            size = temp.tell()
            temp.seek(0)
            yield _index(temp, size)
