#!/usr/bin/env python3
"""Compare welcome painting and the first real file in fresh Python processes.

Uses a Qt shell and real standalone VTK/EGL canvas on Linux. This is NOT an OS reboot
or filesystem-cache-cleared benchmark. Samples alternate baseline and current,
using the same interpreter and dependencies. Startup background work must reach
Ready before opening the first and second equal-sized files.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys

METRICS = ('imports_s', 'constructed_s', 'first_paint_s', 'welcome_paint_s',
           'ready_s', 'first_file_s', 'second_file_s', 'ready_plus_first_file_s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--scenarios', nargs='+', choices=('xyz', 'poscar', 'orca', 'pdb'),
                        default=['xyz', 'poscar', 'orca', 'pdb'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    roots = {'baseline': args.baseline.resolve(), 'current': args.current.resolve()}
    for root in roots.values():
        if not (root / 'lele' / 'app.py').is_file():
            parser.error(f'Not a LELE source root: {root}')
    probe = Path(__file__).with_name('_first_structure_probe.py')
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       VTK_DEFAULT_OPENGL_WINDOW='vtkEGLRenderWindow',
                       LIBGL_ALWAYS_SOFTWARE='1')
    records = {scenario: {'baseline': [], 'current': []} for scenario in args.scenarios}
    for scenario in args.scenarios:
        for repeat in range(args.repeats):
            for label, root in roots.items():
                process = subprocess.run([sys.executable, str(probe), scenario], cwd=root,
                                         env=environment, capture_output=True, text=True, timeout=40)
                if process.returncode:
                    raise RuntimeError(f'{label}/{scenario} failed:\n{process.stdout}\n{process.stderr}')
                row = json.loads(process.stdout.strip().splitlines()[-1])
                records[scenario][label].append(row)
                print(f'{scenario} {repeat + 1}/{args.repeats} {label}: '
                      f'welcome {row["welcome_paint_s"]:.3f}s; ready {row["ready_s"]:.3f}s; '
                      f'first {row["first_file_s"]:.3f}s; second {row["second_file_s"]:.3f}s', flush=True)
    medians = {scenario: {label: {metric: statistics.median(row[metric] for row in rows)
                                 for metric in METRICS}
                         for label, rows in versions.items()}
               for scenario, versions in records.items()}
    result = {'platform': platform.platform(), 'python': platform.python_version(),
              'conditions': 'Fresh process per sample; Qt offscreen shell and real standalone VTK/EGL canvas; '
                            'excludes Windows native QVTK embedding and bootstrap; '
                            'OS filesystem cache not cleared; not a reboot benchmark.',
              'source_roots': {key: str(root) for key, root in roots.items()},
              'repeats': args.repeats, 'medians': medians, 'runs': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(medians, indent=2))


if __name__ == '__main__':
    main()
