#!/usr/bin/env python3
"""Reliable local Windows installer/launcher for LELE.

Uses *only* a validated 64-bit CPython 3.11/3.12. Never silently reuses an
incompatible .venv created by an older start_windows.bat script.
No third-party dependencies are required to execute this file.
"""
from __future__ import annotations

from datetime import datetime
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
WIN_PY = VENV / "Scripts" / "python.exe"
EXPECTED = {(3, 11), (3, 12)}
CHECK_CMD = (
    "import sys,struct; "
    "print(f'{sys.version_info.major}.{sys.version_info.minor}|{struct.calcsize(\"P\")*8}')"
)
IMPORT_CMD = ("import ase, numpy, scipy, PySide6, vtkmodules, matplotlib, PIL; "
              "from PIL import Image, GifImagePlugin; "
              "assert 10 <= int(PIL.__version__.split('.')[0]) < 13")
VERIFICATION_CACHE = VENV / '.lele_dependencies_verified.json'
REQUIRED_PACKAGES = ('ase', 'numpy', 'scipy', 'PySide6', 'vtkmodules', 'matplotlib', 'PIL')


def dependency_fingerprint():
    """Cheap installation identity; never imports scientific packages twice.

    Metadata from *all* installed distributions detects dependency updates as
    well as direct package updates. Top-level package files detect missing
    modules and replaced native extensions even before pip changes metadata.
    A failed launch invalidates the cache; explicit verification is always
    available through LELE_VERIFY_DEPENDENCIES=1.
    """
    site = VENV / 'Lib' / 'site-packages'
    try:
        paths = [WIN_PY, VENV / 'pyvenv.cfg', ROOT / 'requirements.txt', site]
        for package in REQUIRED_PACKAGES:
            directory = site / package
            # All supported distributions are packages, not single modules.
            if not (directory / '__init__.py').is_file():
                return None
            paths.append(directory)
            paths.extend(entry for entry in directory.iterdir()
                         if entry.name != '__pycache__')
        for directory in site.glob('*.dist-info'):
            paths.append(directory)
            for name in ('METADATA', 'RECORD', 'INSTALLER'):
                path = directory / name
                if path.exists():paths.append(path)
            record = directory / 'RECORD'
            if record.is_file():
                # A nested DLL/extension can be replaced without changing its
                # package directory's timestamp. Check every recorded native
                # runtime file, including transitive dependencies' binaries.
                with record.open(encoding='utf-8', newline='') as stream:
                    for row in csv.reader(stream):
                        if not row:continue
                        relative = Path(row[0])
                        if relative.is_absolute() or '..' in relative.parts:continue
                        name = relative.name.lower()
                        if name.endswith(('.pyd', '.dll', '.dylib')) or '.so' in name:
                            paths.append(site / relative)
        stats = []
        for path in sorted(set(paths)):
            stat = path.stat()
            stats.append((str(path), stat.st_size, stat.st_mtime_ns))
        return {
            'schema': 1,
            'requirements_sha256': hashlib.sha256((ROOT / 'requirements.txt').read_bytes()).hexdigest(),
            'check_sha256': hashlib.sha256(IMPORT_CMD.encode()).hexdigest(),
            'files': stats,
        }
    except (OSError, UnicodeError, csv.Error):
        return None


def dependencies_verified() -> bool:
    if os.environ.get('LELE_VERIFY_DEPENDENCIES') == '1':
        return False
    current = dependency_fingerprint()
    if current is None:return False
    try:
        # Round-trip the stat tuples for equality with JSON arrays.
        return json.loads(VERIFICATION_CACHE.read_text(encoding='utf-8')) == json.loads(json.dumps(current))
    except (OSError, ValueError):
        return False


def save_dependency_verification() -> None:
    current = dependency_fingerprint()
    if current is None:return
    temporary = VERIFICATION_CACHE.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(current, separators=(',', ':')), encoding='utf-8')
        temporary.replace(VERIFICATION_CACHE)
    except OSError:
        # A read-only environment still launches after normal verification.
        pass


def forget_dependency_verification() -> None:
    try:VERIFICATION_CACHE.unlink(missing_ok=True)
    except OSError:pass


def describe_python(executable: Path | str) -> tuple[int, int, int] | None:
    """Read interpreter version/bitness without executing any package code."""
    try:
        r = subprocess.run(
            [str(executable), "-c", CHECK_CMD], capture_output=True,
            text=True, timeout=15, check=False,
        )
        if r.returncode:
            return None
        version, width = r.stdout.strip().split("|")
        major, minor = (int(x) for x in version.split("."))
        return major, minor, int(width)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def acceptable(info: tuple[int, int, int] | None) -> bool:
    return info is not None and info[:2] in EXPECTED and info[2] == 64


def run(args: list[str]) -> int:
    print("+", " ".join(str(x) for x in args), flush=True)
    return subprocess.call([str(x) for x in args], cwd=ROOT)


def backup_old_venv() -> None:
    target = ROOT / (".venv_incompatible_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    suffix = 1
    while target.exists():
        target = ROOT / (target.name + f"_{suffix}")
        suffix += 1
    VENV.rename(target)
    print(f"[INFO] Backed up old environment as: {target.name}", flush=True)
    print("[INFO] This is a virtual environment backup; it can be removed later.", flush=True)


def main() -> int:
    base = (sys.version_info.major, sys.version_info.minor, struct.calcsize("P") * 8)
    print(f"[INFO] Selected Python: {sys.version.split()[0]}, {base[2]}-bit", flush=True)
    if not acceptable(base):
        print("[ERROR] This release needs 64-bit Python 3.11 or 3.12.", flush=True)
        return 2

    if VENV.exists() and describe_python(WIN_PY) != base:
        print("[INFO] Existing .venv is missing, broken or uses a different Python.", flush=True)
        try:
            backup_old_venv()
        except OSError as ex:
            print(f"[ERROR] Cannot back up .venv: {ex}", flush=True)
            print("Close applications using the old environment and retry.", flush=True)
            return 3

    if not WIN_PY.exists():
        print("[1/3] Creating isolated environment...", flush=True)
        if run([sys.executable, "-m", "venv", str(VENV)]) != 0:
            return 4

    verified_cache = dependencies_verified()
    r = None if verified_cache else subprocess.run(
        [str(WIN_PY), "-c", IMPORT_CMD], cwd=ROOT,
        check=False, capture_output=True, text=True,
    )
    if r is not None and r.returncode != 0:
        print("[2/3] Installing Python dependencies...", flush=True)
        if run([WIN_PY, "-m", "pip", "install", "--upgrade", "pip"]) != 0:
            print("[ERROR] pip update failed. Check network and package index.", flush=True)
            return 5
        if run([WIN_PY, "-m", "pip", "install", "-r", "requirements.txt"]) != 0:
            print("\n[ERROR] Dependency installation failed.", flush=True)
            print("- Check that the interpreter shown above is 64-bit Python 3.12/3.11.", flush=True)
            print("- A private package mirror may not contain VTK wheels.", flush=True)
            print("- Run diagnose_windows.bat to inspect Python and pip settings.", flush=True)
            print("- If your package index lacks VTK, try official PyPI:", flush=True)
            print(r'  .venv\Scripts\python.exe -m pip install --only-binary=:all: --index-url https://pypi.org/simple "vtk>=9.3,<10"', flush=True)
            return 6
        verified = subprocess.run(
            [str(WIN_PY), "-c", IMPORT_CMD], cwd=ROOT,
            check=False, capture_output=True, text=True,
        )
        if verified.returncode != 0:
            print("[ERROR] A required module still fails to import after installation.", flush=True)
            print(verified.stderr, flush=True)
            return 7

    if not verified_cache:
        save_dependency_verification()

    print("[3/3] Starting LELE...", flush=True)
    result = run([WIN_PY, "-m", "lele", *sys.argv[1:]])
    if result:
        forget_dependency_verification()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
