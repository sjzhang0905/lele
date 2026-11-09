#!/usr/bin/env python3
"""Compare complete trajectory loading, preserving coordinates and metadata.

Example:
  python benchmark_trajectory.py --baseline /path/to/3.5.0 \
      --current /path/to/new --directory ./trajectory_benchmark --repeats 3

The directory receives reproducible synthetic inputs and benchmark_results.json.
Each measured load uses a fresh subprocess. Scientific imports are timed
separately and warmed before parsing; further lazy imports remain inside the
complete load timing (including ASE's plain-XYZ comment parser when needed).
These are local, warm filesystem-cache benchmarks, not first-ever disk reads or
GUI startup measurements. No downsampling or frame limits are used.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time


def generate_inputs(directory: Path, atoms: int, frames: int, outcar_frames: int):
    xyz = ''.join(f'{"O" if i%3==0 else "H"} {i*.001:.9f} {i*.002:.9f} {i*.003:.9f}\n'
                  for i in range(atoms))
    coordinates = ''.join(f'  {i*.001:.9f}  {i*.002:.9f}  {i*.003:.9f}\n'
                          for i in range(atoms))
    oxygen = (atoms+2)//3
    hydrogen = atoms-oxygen
    xdat_header = (f'test\n1\n10 0 0\n0 11 0\n0 0 12\nO H\n'
                   f'{oxygen} {hydrogen}\n')
    cases = [
        ('plain.xyz', '', 'frame {i}\n', xyz),
        ('cp2k.xyz', '', ' i = {i}, time = {i}, E = -1.5000\n', xyz),
        ('XDATCAR', xdat_header, 'Direct configuration= {i}\n', coordinates),
    ]
    inputs = []
    for name, prefix, comment, block in cases:
        path = directory/name
        with path.open('w', encoding='utf-8', newline='\n') as stream:
            stream.write(prefix)
            for i in range(frames):
                stream.write(('' if name == 'XDATCAR' else f'{atoms}\n')+
                             comment.format(i=i)+block)
        inputs.append(path)
    path = directory/'OUTCAR_long'
    header = (f'vasp.6.4.0\n POTCAR: PAW_PBE O 08Apr2002\n'
              f' POTCAR: PAW_PBE H 08Apr2002\n ions per type = {oxygen} {hydrogen}\n'
              f' NIONS = {atoms}\n IBRION = 0\n NELECT = {oxygen*6+hydrogen}.000\n'
              ' POMASS = 16.0 1.0\n direct lattice vectors reciprocal lattice vectors\n'
              ' 10.0 0.0 0.0 0 0 0\n 0.0 11.0 0.0 0 0 0\n 0.0 0.0 12.0 0 0 0\n')
    diagnostics = (
        '----------------------------------------- Iteration 1( 1) ---------------------------------------\n'
        '    POTLOK:  cpu time    0.0043: real time    0.0043\n'
        '    SETDIJ:  cpu time    0.0020: real time    0.0020\n'
        '    EDDIAG:  cpu time    0.0211: real time    0.0211\n'
        'DAV:   1    -0.100000000000E+03   -0.10000E-02   -0.14100E-03  1200   0.403E-02\n'
        ' Free energy of the ion-electron system (eV)\n'
        ' free energy TOTEN = -99 eV\n'
        ' energy without entropy = -98 energy(sigma->0) = -97\n'+
        ''.join(f' {j+1:6d} {j*.0008:14.9f} {j*.0033:14.9f} {j*.0444:14.9f}\n'
                for j in range(250)))
    force_table = (' POSITION TOTAL-FORCE (eV/Angst)\n ------------------\n'+
                   ''.join(f' {j*.001:.9f} {j*.002:.9f} {j*.003:.9f} .1 .2 .3\n'
                           for j in range(atoms))+' ------------------\n')
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(header)
        for i in range(outcar_frames):
            value = -100-i*.001
            stream.write(diagnostics+force_table+
                         f' FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n'
                         f' free energy TOTEN = {value:.6f} eV\n'
                         f' energy without entropy = {value:.6f} energy(sigma->0) = {value:.6f}\n')
        stream.write(' General timing and accounting\n')
    return inputs+[path]


def _json_default(value):
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if hasattr(value, 'item'):
        return value.item()
    return list(value)


def worker(root: str, filename: str):
    sys.path.insert(0, root)
    started = time.perf_counter()
    from lele.formats import load_document
    modules = ['lele.vasp_results', 'lele.cp2k_results', 'lele.trajectory_io']
    for module in modules:
        importlib.import_module(module)
    import_seconds = time.perf_counter()-started
    path = Path(filename)
    started = time.perf_counter()
    document = load_document(path)
    seconds = time.perf_counter()-started
    digest = hashlib.sha256()
    def add(value):
        digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 default=_json_default).encode())
        digest.update(b'\0')
    for frame in document.frames:
        add([frame.symbols, frame.pbc, frame.energy_ev, frame.info])
        digest.update(frame.positions.astype('<f8').tobytes())
        digest.update(frame.cell.astype('<f8').tobytes())
    result = document.calculation_results
    if result:
        for step in result.steps:
            add({key: getattr(step, key, None) for key in
                 ('job_index', 'source_line', 'stage_index', 'cycle', 'energy_ev',
                  'converged', 'convergence', 'info', 'frame_index')})
        for job in result.jobs:
            add(job.__dict__)
        for stage in result.stages:
            add(stage.__dict__)
    add(document.note)
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_rss_mib = rss/(1024*1024 if sys.platform == 'darwin' else 1024)
    except ImportError:
        peak_rss_mib = None  # resource is unavailable on Windows
    import numpy
    import ase
    print(json.dumps(dict(input=path.name, bytes=path.stat().st_size,
        import_seconds=import_seconds, load_seconds=seconds,
        total_seconds=import_seconds+seconds, peak_rss_mib=peak_rss_mib,
        frames=len(document.frames), sha256=digest.hexdigest(),
        numpy=numpy.__version__, ase=ase.__version__, warmed_imports=modules)))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', type=Path, required=True, help='Baseline source root containing lele/')
    parser.add_argument('--current', type=Path, required=True, help='Current source root containing lele/')
    parser.add_argument('--directory', type=Path, required=True, help='Synthetic inputs and JSON result directory')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--atoms', type=int, default=128)
    parser.add_argument('--frames', type=int, default=10000)
    parser.add_argument('--outcar-frames', type=int, default=3000)
    args = parser.parse_args()
    if min(args.repeats, args.atoms, args.frames, args.outcar_frames) < 1:
        parser.error('repeats, atoms and frame counts must be positive')
    roots = {'baseline': args.baseline.resolve(), 'current': args.current.resolve()}
    for label, root in roots.items():
        if not (root/'lele'/'formats.py').is_file():
            parser.error(f'{label} must be a source root containing lele/formats.py')
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    inputs = generate_inputs(directory, args.atoms, args.frames, args.outcar_frames)
    environment = {**os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
    observations = []
    for path in inputs:
        for repeat in range(args.repeats):
            order = ['baseline', 'current'] if repeat%2 == 0 else ['current', 'baseline']
            for label in order:
                output = subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
                    '--_worker', str(roots[label]), str(path)], env=environment, text=True)
                sample = json.loads(output)
                sample.update(version=label, repeat=repeat+1)
                observations.append(sample)
                print(json.dumps(sample), flush=True)
    comparisons = []
    for path in inputs:
        samples = [sample for sample in observations if sample['input'] == path.name]
        by_version = {label: [sample for sample in samples if sample['version'] == label]
                      for label in roots}
        medians = {label: statistics.median(sample['load_seconds'] for sample in items)
                   for label, items in by_version.items()}
        same = len({sample['sha256'] for sample in samples}) == 1
        comparison = dict(input=path.name, bytes=path.stat().st_size,
            frames=samples[0]['frames'], median_load_seconds=medians,
            speedup=medians['baseline']/medians['current'], output_identical=same)
        for metric in ('import_seconds', 'total_seconds', 'peak_rss_mib'):
            comparison['median_'+metric] = {
                label: statistics.median(values) if values else None
                for label, items in by_version.items()
                if (values := [sample[metric] for sample in items if sample[metric] is not None])
            }
        comparisons.append(comparison)
    report = dict(python=sys.version, platform=platform.platform(),
        parameters=dict(atoms=args.atoms, frames=args.frames, outcar_frames=args.outcar_frames,
                        repeats=args.repeats),
        description='Synthetic trajectories; serial fresh processes; initial scientific imports timed separately; deferred imports included in complete load timing; warm filesystem cache; no GUI rendering.',
        comparisons=comparisons, observations=observations)
    result_path = directory/'benchmark_results.json'
    result_path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(dict(result=str(result_path), comparisons=comparisons)), flush=True)
    if not all(item['output_identical'] for item in comparisons):
        raise SystemExit('ERROR: baseline and current outputs differ')


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--_worker':
        worker(sys.argv[2], sys.argv[3])
    else:
        main()
