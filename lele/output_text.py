"""Decode printed output, including Windows PowerShell UTF-16 redirection."""
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar


_load_cache = ContextVar('lele_output_load_cache', default=None)
_cancelled = ContextVar('lele_output_cancelled', default=None)
_progress = ContextVar('lele_output_progress', default=None)


def load_progress(label,total=0):
    """Return a cheap, throttled stage counter; no GUI dependency in readers."""
    callback=_progress.get()
    if callback is None:
        return (lambda value:check_load_cancelled()) if _cancelled.get() is not None else (lambda value:None)
    from time import monotonic
    last=[-1,monotonic()]
    callback(label,0,total)
    def update(value):
        check_load_cancelled()
        if value==last[0]:return
        step=min(512,max(1,total//100)) if total else 512
        if value!=total and value-last[0]<step:return
        now=monotonic()
        if value!=total and now-last[1]<.05:return
        last[:]=[value,now];callback(label,value,total)
    return update


class LoadCancelled(Exception):
    """A user cancelled a background import; no partial document is attached."""


def check_load_cancelled():
    callback = _cancelled.get()
    if callback is not None and callback():
        raise LoadCancelled()


def scan_lines(lines,label):
    """One linear pass with throttled counters and cooperative cancellation."""
    report=load_progress(label,len(lines))
    for i,line in enumerate(lines):
        if i%512==0:report(i);check_load_cancelled()
        yield i,line
    report(len(lines))


def progress_items(items,label,total=None):
    """Count iterable data rows without materializing a second copy."""
    total=(len(items) if hasattr(items,'__len__') else 0) if total is None else total
    report=load_progress(label,total);count=0
    for count,item in enumerate(items,1):
        if count%128==1:report(count-1);check_load_cancelled()
        yield item
    report(total or count)


@contextmanager
def output_read_session(cancelled=None,progress=None):
    """Share decoded lines during one load; never retain source text globally.

    Context-local storage keeps simultaneous background loads independent and
    a subsequent reopen always reads the current file, even at the same path.
    """
    existing = _load_cache.get()
    token = _load_cache.set({}) if existing is None else None
    cancel_token = _cancelled.set(cancelled) if cancelled is not None else None
    progress_token = _progress.set(progress) if progress is not None else None
    try:
        check_load_cancelled()
        yield
    finally:
        if progress_token is not None:
            _progress.reset(progress_token)
        if cancel_token is not None:
            _cancelled.reset(cancel_token)
        if token is not None:
            _load_cache.reset(token)


def open_output_text(path):
    """Open a decoded text stream without a whole-file bytes/text copy."""
    path = Path(path)
    with path.open('rb') as probe:
        encoding = output_encoding(probe.read(4096))
    # utf-16 consumes the BOM itself; BOM-less redirection uses the probed order.
    if encoding.startswith('utf-16'):
        with path.open('rb') as probe:
            if probe.read(2) in (b'\xff\xfe', b'\xfe\xff'):
                encoding = 'utf-16'
    return path.open('r', encoding=encoding, errors='replace')


def output_encoding(data):
    if data.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    if data.startswith(b'\xfe\xff'):
        return 'utf-16-be'
    sample = data[:4096]
    if sample.count(b'\0') > len(sample) // 5:
        return 'utf-16-le' if sample[1::2].count(0) >= sample[::2].count(0) else 'utf-16-be'
    return 'utf-8-sig'


def decode_output(data):
    return data.decode(output_encoding(data), errors='replace').lstrip('\ufeff')


def read_output_lines(path):
    path = Path(path)
    cache = _load_cache.get()
    key = path.resolve()
    if cache is not None and key in cache:
        return cache[key]
    size=path.stat().st_size
    progress=load_progress('Reading '+path.name,size)
    with open_output_text(path) as stream:
        lines = []
        for i,line in enumerate(stream):
            if i % 4096 == 0:
                check_load_cancelled()
                progress(stream.buffer.tell())
            lines.append(line.rstrip('\r\n'))
    if cache is not None:
        cache[key] = lines
    progress(size)
    return lines
