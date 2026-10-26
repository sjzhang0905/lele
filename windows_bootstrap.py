#!/usr/bin/env python3
"""Reliable local Windows installer/launcher for LELE v0.9.1.

Uses *only* a validated 64-bit CPython 3.11/3.12. Never silently reuses an
incompatible .venv created by an older start_windows.bat script.
No third-party dependencies are required to execute this file.
"""
from __future__ import annotations

from datetime import datetime
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
IMPORT_CMD = "import ase, numpy, scipy, PySide6, vtkmodules, matplotlib"


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

    r = subprocess.run(
        [str(WIN_PY), "-c", IMPORT_CMD], cwd=ROOT,
        check=False, capture_output=True, text=True,
    )
    if r.returncode != 0:
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

    print("[3/3] Starting LELE...", flush=True)
    return run([WIN_PY, "-m", "lele", *sys.argv[1:]])


if __name__ == "__main__":
    raise SystemExit(main())
