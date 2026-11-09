#!/usr/bin/env python3
"""Compare fresh-process Qt startup for two LELE source directories.

The supplied v3.5.1 measurements used Linux, Qt's offscreen plugin, the actual
VTK canvas and a warm OS filesystem cache. This measures imports, window
construction, first welcome paint and empty-canvas backend readiness, not the
Windows bootstrap script or a first structure's OpenGL rendering. Each sample
is a new process using this script's Python interpreter and installed packages.
Baseline/current samples alternate; no filesystem cache is forcibly cleared.

Example:
    python tools/performance/benchmark_startup.py --baseline ../LELE_v3.5.0 \
        --current . --repeats 7 --output startup_results.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys


METRICS = ('imports_s', 'constructed_s', 'first_paint_s', 'ready_s')


def source_root(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not (path / 'lele' / 'app.py').is_file():
        raise argparse.ArgumentTypeError(f'Not a LELE source directory: {path}')
    return path


def positive_integer(value: str) -> int:
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('repeats must be at least 1')
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', required=True, type=source_root,
                        help='Unmodified baseline source directory containing lele/app.py')
    parser.add_argument('--current', required=True, type=source_root,
                        help='Optimized source directory containing lele/app.py')
    parser.add_argument('--repeats', type=positive_integer, default=7,
                        help='Fresh-process samples per version (default: 7)')
    parser.add_argument('--output', required=True, type=Path,
                        help='Destination JSON containing every run and medians')
    args = parser.parse_args(argv)
    helper = Path(__file__).with_name('_startup_probe.py')
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       VTK_DEFAULT_OPENGL_WINDOW='vtkEGLRenderWindow')
    runs = {'baseline': [], 'current': []}
    try:
        for _ in range(args.repeats):
            for label, root in (('baseline', args.baseline), ('current', args.current)):
                process = subprocess.run([sys.executable, str(helper)], cwd=root,
                                         env=environment, text=True, capture_output=True,
                                         timeout=30, check=False)
                if process.returncode:
                    raise RuntimeError(f'{label} startup failed ({process.returncode}):\n'
                                       + process.stdout + process.stderr)
                record = json.loads(process.stdout.splitlines()[-1])
                if not all(key in record for key in METRICS):
                    raise RuntimeError(f'{label} returned incomplete startup measurements: {record}')
                runs[label].append(record)
    except (OSError, ValueError, IndexError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        return 1
    medians = {label: {key: statistics.median(row[key] for row in records)
                       for key in METRICS} for label, records in runs.items()}
    report = {
        'platform': f'{platform.system()}, Qt offscreen, actual VTK canvas, '
                    f'Python {platform.python_version()}; fresh process, filesystem cache not cleared',
        'scope': 'Imports, first welcome paint and empty-canvas backend readiness; '
                 'excludes Windows bootstrap and first-structure GPU rendering',
        'repeats': args.repeats,
        'medians': medians,
        'runs': runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(medians, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
