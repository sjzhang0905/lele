#!/usr/bin/env python3
"""Reproduce CP2K stdout parsing timings in separate source-tree processes.

Example:
    python tools/performance/benchmark_cp2k.py --baseline /path/to/3.5.0/LELE \
        --current /path/to/3.5.1/LELE --directory /path/to/benchmark-output

Creates a 50.75 MB synthetic stdout with 6,000 MD steps and 128 atoms per step.
Times native read_cp2k_output() plus frames(), excluding imports, input generation,
checksum validation, and GUI work. Does not clear the operating-system file cache.
Requires the same Python/dependencies as LELE. No private scientific data is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


N_STEPS = 6000
N_ATOMS = 128


def generate_stdout(path: Path) -> None:
    """Generate exactly the source used for the recorded v3.5.1 measurements."""
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write('CP2K| version string: CP2K version 2026.2\n'
                     ' GLOBAL| Run type MD\n GLOBAL| Project name benchmark\n'
                     ' - Atoms: 128\n CELL| Vector a [angstrom]: 12 0 0 |a| = 12\n'
                     ' CELL| Vector b [angstrom]: 0 12 0 |b| = 12\n'
                     ' CELL| Vector c [angstrom]: 0 0 12 |c| = 12\n'
                     ' CELL| Periodicity XYZ\n')
        for step in range(N_STEPS):
            stream.write(f' MD| Step number {step}\n'
                         ' MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM\n\n'
                         ' Atom Kind Element X Y Z Z(eff) Mass\n')
            for atom in range(N_ATOMS):
                stream.write(f' {atom+1} 1 H 1 {atom*.01:.8f} {step*.00001:.8f} '
                             f'{atom*.02:.8f} 1.0 1.0\n')
            stream.write('\n SCF WAVEFUNCTION OPTIMIZATION\n' +
                         ' 1 OT CG  0.15E+00  0.10E-04  -100.000000000  -0.10E-08\n' * 25)
            stream.write(f' SCF run converged in 25 steps\n'
                         f' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] '
                         f'{-100-step*.00001:.8f}\n')
            for label in ('Time [fs]', 'Potential energy', 'Kinetic energy',
                          'Temperature [K]', 'Conserved quantity', 'Pressure [bar]',
                          'CPU time per MD step'):
                stream.write(f' MD| {label} 10.00 20.00 30.00\n')


def peak_rss_kib():
    """Return process peak RSS when the platform exposes resource.getrusage."""
    try:
        import resource
    except ImportError:
        return None  # Standard Windows Python does not provide resource.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / 1024 if sys.platform == 'darwin' else value


def run_worker(source_root: Path, source_file: Path) -> dict:
    sys.path.insert(0, str(source_root))
    import ase
    import numpy
    from lele.cp2k_results import read_cp2k_output
    from lele.output_text import output_read_session

    start = time.perf_counter()
    with output_read_session():
        results = read_cp2k_output(source_file)
        frames = results.frames()
    elapsed = time.perf_counter() - start
    rss = peak_rss_kib()
    checksum = hashlib.sha256()
    for frame in frames:
        checksum.update(frame.positions.tobytes())
        checksum.update(frame.cell.tobytes())
        checksum.update(str((frame.symbols, frame.pbc, frame.energy_ev,
                             sorted(frame.info.items()))).encode())
    for step in results.steps:
        checksum.update(str((step.source_line, step.frame_index, step.energy_ev,
                             step.cycle, step.job_index, step.stage_index,
                             sorted(step.info.items()))).encode())
    return {'seconds': elapsed, 'rss_kib': rss, 'frames': len(frames),
            'steps': len(results.steps), 'sha256': checksum.hexdigest(),
            'numpy_version': numpy.__version__, 'ase_version': ase.__version__}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', type=Path, help='Baseline source root containing lele/')
    parser.add_argument('--current', type=Path, help='Current source root containing lele/')
    parser.add_argument('--directory', type=Path, help='Output directory for generated input and JSON')
    parser.add_argument('--repeats', type=int, default=3, help='Fresh processes per version (default: 3)')
    parser.add_argument('--worker-root', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--worker-file', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_root is not None:
        if args.worker_file is None:
            parser.error('--worker-file is required for a worker')
        print(json.dumps(run_worker(args.worker_root.resolve(), args.worker_file.resolve())))
        return 0
    if args.baseline is None or args.current is None or args.directory is None:
        parser.error('--baseline, --current and --directory are required')
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    roots = {'baseline': args.baseline.expanduser().resolve(),
             'current': args.current.expanduser().resolve()}
    for label, root in roots.items():
        if not (root / 'lele' / 'cp2k_results.py').is_file():
            parser.error(f'{label} root does not contain lele/cp2k_results.py: {root}')
    destination = args.directory.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    source_file = destination / 'long_cp2k.out'
    generate_stdout(source_file)
    runs = {}
    for label, root in roots.items():
        runs[label] = []
        for repeat in range(args.repeats):
            command = [sys.executable, str(Path(__file__).resolve()),
                       '--worker-root', str(root), '--worker-file', str(source_file)]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            sample = json.loads(completed.stdout)
            runs[label].append(sample)
            print(f'{label} {repeat+1}/{args.repeats}: {sample["seconds"]:.6f} s', flush=True)
    medians = {label: statistics.median(item['seconds'] for item in samples)
               for label, samples in runs.items()}
    hashes = {item['sha256'] for samples in runs.values() for item in samples}
    matching = len(hashes) == 1 and all(
        item['frames'] == item['steps'] == N_STEPS
        for samples in runs.values() for item in samples)
    report = {
        'benchmark': 'CP2K stdout native read_cp2k_output + frames',
        'input': {'filename': source_file.name, 'size_bytes': source_file.stat().st_size,
                  'steps': N_STEPS, 'atoms_per_step': N_ATOMS, 'synthetic': True},
        'environment': {'python': sys.version, 'platform': platform.platform(),
                        'source_roots': {label: str(root) for label, root in roots.items()}},
        'timing_scope': 'Reader and frame collection only; imports, checksum, GUI and generation excluded',
        'cache_policy': 'OS file cache not cleared; each sample uses a fresh Python process',
        'rss_note': 'Process peak RSS in KiB including imports; null where resource is unavailable',
        'repeats': args.repeats, 'runs': runs, 'median_seconds': medians,
        'speedup': medians['baseline'] / medians['current'],
        'all_results_match': matching,
    }
    output = destination / 'cp2k_results.json'
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'result_file': str(output), 'median_seconds': medians,
                      'speedup': report['speedup'], 'all_results_match': matching}, indent=2))
    return 0 if matching else 1


if __name__ == '__main__':
    raise SystemExit(main())
