"""Deterministic import batches and bounded, recursive folder discovery.

Requests are inert: constructing a batch performs no filesystem access and is
safe in a native drop callback. Discovery belongs on an import worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key, lru_cache
from pathlib import Path
import os
import re
import sys


@dataclass(frozen=True)
class ImportBatch:
    paths: tuple

    def __post_init__(self):
        object.__setattr__(self, 'paths', tuple(self.paths))


@dataclass(frozen=True)
class PreparedImportBatch:
    paths: tuple[Path, ...]
    skipped: int = 0
    issues: tuple[str, ...] = ()


_DIGITS = re.compile(r'([0-9]+)')
# These names are specific structure/property formats; unlike .log/.inp they
# do not need a content detector just to enter a folder's import queue.
_DIRECT_SUFFIXES = frozenset((
    '.xyz', '.gjf', '.cif', '.fdf', '.pdb', '.pqr', '.mol', '.mol2', '.sdf',
    '.xsf', '.cube', '.cub', '.gen', '.cfg', '.gro', '.g96', '.traj', '.res',
    '.xsd', '.xtd', '.vasp', '.xv', '.ani', '.struct', '.molden', '.mld',
    '.fchk', '.fch',
))
_PROBE_SUFFIXES = frozenset((
    '.com', '.log', '.out', '.inp', '.in', '.pwi', '.pwo', '.nw', '.nwi',
    '.nwo', '.input', '.restart', '.poscar', '.modes', '.txt', '.data',
))
_VASP_NAME = re.compile(r'^(?:POSCAR|CONTCAR|OUTCAR|OSZICAR|XDATCAR|WAVECAR)(?:$|[._ ()-])', re.I)
_VASP_FIELD = re.compile(r'(?:^|[._ -])(?:CHGCAR|CHG|ELFCAR|LOCPOT|PARCHG|AECCAR[012])(?=$|[._ ()-])', re.I)


def natural_text_key(value):
    """Portable numeric-run fallback with deterministic case/zero-padding ties."""
    text = str(value)
    parts = tuple((1, int(part), len(part)) if part.isascii() and part.isdigit()
                  else (0, part.casefold()) for part in _DIGITS.split(text))
    return parts, text.casefold(), text


def natural_filename_key(path):
    path = Path(path)
    return natural_text_key(path.name), natural_text_key(str(path.parent))


@lru_cache(maxsize=1)
def _windows_logical_compare():
    """Use Explorer's filename collation on Windows when available."""
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        library = ctypes.WinDLL('shlwapi', use_last_error=True)
        compare = library.StrCmpLogicalW
        compare.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p)
        compare.restype = ctypes.c_int
        return compare
    except (OSError, AttributeError):
        return None


def sort_import_paths(paths):
    """Explorer logical name order, or portable natural order elsewhere."""
    compare = _windows_logical_compare()
    if compare is None:
        return tuple(sorted(paths, key=natural_filename_key))

    def logical(left, right):
        left, right = Path(left), Path(right)
        value = compare(left.name, right.name)
        if value:
            return -1 if value < 0 else 1
        # Explorer can equate case/padding variants. Parent path and then the
        # complete name provide a stable final order independent of drop order.
        a = (natural_text_key(str(left.parent)), natural_filename_key(left))
        b = (natural_text_key(str(right.parent)), natural_filename_key(right))
        return (a > b) - (a < b)

    return tuple(sorted(paths, key=cmp_to_key(logical)))


def is_folder_import_candidate(path):
    """Recognize supported names, probing ambiguous text with bounded reads.

    No actual scientific reader, whole-text read or grid allocation runs here.
    Explicitly selected files bypass this filter and keep ordinary load errors.
    """
    path = Path(path)
    suffix = path.suffix.casefold()
    name = path.name
    upper = name.upper()
    # Opening a project replaces the entire workspace, so only an explicit
    # project selection may do that during a mixed batch.
    if suffix in ('.gbw', '.lele'):
        return False
    if suffix in _DIRECT_SUFFIXES:
        return True
    if (_VASP_NAME.match(name) or _VASP_FIELD.search(name) or upper.startswith('PARCHG')
            or upper == 'VASPRUN.XML' or suffix in ('.outcar', '.oszicar', '.xdatcar')):
        return True
    if name.endswith(('.NEB.log', '.interp', '.interp.final')):
        return True
    probe = (suffix in _PROBE_SUFFIXES or re.search(r'\.restart\.bak-\d+$', name, re.I))
    # Bare files can be recognized structure/output files; do not inspect every
    # unrelated binary with an arbitrary extension in a recursively dropped tree.
    if not probe and suffix:
        return False
    from .legacy_converter import detect_format, ConversionError
    if suffix == '.com':
        # The existing single-file detector accepts .com as Gaussian by name;
        # folder discovery must not queue Windows executables or command files.
        from .legacy_converter import read_probe
        text = read_probe(path, head_bytes=32768, tail_bytes=0)
        return ('\x00' not in text and bool(re.search(r'(?m)^\s*#\S*\s+\S+', text))
                and bool(re.search(r'(?m)^\s*[+-]?\d+\s+\d+\s*$', text)))
    if suffix in ('.out', '.log', '.data', '.txt'):
        from .nmr_input import standalone_nmr_kind
        if standalone_nmr_kind(path):
            return True
    try:
        detect_format(path, check_volume=False)
    except (ConversionError, ValueError):
        return False
    return True


def prepare_import_batch(paths, *, cancelled=None, progress=None):
    """Expand folders recursively, dedupe resolved files, then sort by name.

    Directory links/junctions are not followed. Explicit directory links are
    resolved once, and visited real directories prevent overlapping traversal.
    Unreadable entries are reported without discarding other valid files.
    """
    from .output_text import LoadCancelled
    paths = paths.paths if isinstance(paths, ImportBatch) else tuple(paths)
    files = {}
    visited = set()
    checked = set()
    skipped = 0
    issues = []
    scanned = 0

    def checkpoint():
        if cancelled is not None and cancelled():
            raise LoadCancelled()

    def issue(path, exc):
        if len(issues) < 30:
            issues.append(f'{path}: {exc}')

    def add_file(path, *, explicit):
        nonlocal skipped, scanned
        checkpoint()
        scanned += 1
        if progress is not None and scanned % 128 == 1:
            progress(f'Checking files ({scanned})', scanned, 0)
        try:
            resolved = path.resolve(strict=True)
            key = os.path.normcase(str(resolved))
            if key in files or (not explicit and key in checked):
                return
            if explicit or is_folder_import_candidate(resolved):
                files[key] = resolved
            else:
                skipped += 1
            checked.add(key)
        except OSError as exc:
            issue(path, exc)

    def walk(root):
        pending = [root]
        while pending:
            checkpoint()
            directory = pending.pop()
            try:
                real = directory.resolve(strict=True)
                key = os.path.normcase(str(real))
                if key in visited:
                    continue
                visited.add(key)
                with os.scandir(real) as entries:
                    for entry in entries:
                        checkpoint()
                        path = Path(entry.path)
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                if not getattr(os.path, 'isjunction', lambda _: False)(entry.path):
                                    pending.append(path)
                            elif entry.is_file():
                                add_file(path, explicit=False)
                        except OSError as exc:
                            issue(path, exc)
            except OSError as exc:
                issue(directory, exc)

    # Root enumeration order cannot change representative paths or the final
    # import order. Resolving a directory link here still never follows children.
    for raw in sorted(paths, key=lambda p: natural_text_key(os.fspath(p))):
        checkpoint()
        path = Path(raw).expanduser()
        try:
            if path.is_dir():
                walk(path)
            elif path.is_file():
                add_file(path, explicit=True)
            else:
                issue(path, 'File or folder does not exist or is not a regular file.')
        except OSError as exc:
            issue(path, exc)
    checkpoint()
    ordered = sort_import_paths(files.values())
    if progress is not None:
        progress(f'Found {len(ordered)} supported files', scanned, scanned)
    return PreparedImportBatch(ordered, skipped, tuple(issues))
