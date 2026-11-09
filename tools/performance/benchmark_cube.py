#!/usr/bin/env python3
"""Compare CUBE parsing with two LELE source trees in fresh subprocesses.

Example:
    python tools/performance/benchmark_cube.py --baseline ../LELE-v3.5.0 \
        --current . --directory ../cube-benchmark --repeats 3

The two generated inputs occupy about 191 MiB. Existing inputs are reused.
Package imports and a small warm-up read are outside the timed parse; disk
caches are not flushed. Peak RSS includes imports and warm-up, but excludes
the subsequent output-hash buffer. Results are local performance measurements,
not promises for every computer, source file, or rendering operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


def generate(path, size, line_values):
    total = size ** 3
    header = (
        'Performance fixture\nOUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z\n'
        f'1 0 0 0\n{size} 0.1 0 0\n{size} 0 0.1 0\n{size} 0 0 0.1\n8 0 0 0 0\n'
    )
    tokens = ['-1.2345678E-03', ' 2.7182818E-04', '-9.8765432E-05',
              ' 3.1415927E-02', ' 1.2345678E-06', '-6.0221408E-01']
    unit = ' '.join(tokens) + ('\n' if line_values else ' ')
    with path.open('w', encoding='utf-8', newline='\n') as stream:
        stream.write(header)
        repeats, remainder = divmod(total, 6)
        block = unit * 8192
        while repeats >= 8192:
            stream.write(block)
            repeats -= 8192
        stream.write(unit * repeats)
        if remainder:
            stream.write(' '.join(tokens[:remainder]))
        stream.write('\n')


def peak_rss_mib():
    """Standard-library peak resident memory on Linux/macOS/Windows."""
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in (
                    'PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage',
                    'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                    'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                          ctypes.byref(counters), counters.cb):
            return None
        return counters.PeakWorkingSetSize / 1024 ** 2
    try:
        import resource
    except ImportError:
        return None
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss / (1024 ** 2 if sys.platform == 'darwin' else 1024)


def one(source_root, path):
    from lele.cube_input import read_cube_file
    from lele.volumetric_input import read_cube_document

    # Resolve the warm-up input against the selected tree, never the launcher.
    read_cube_document(source_root / 'examples' / 'artificial_signed_field.cube')
    begin = time.perf_counter()
    result = read_cube_file(path)
    elapsed = time.perf_counter() - begin
    data = result['data']
    rss = peak_rss_mib()
    print(json.dumps(dict(seconds=elapsed, peak_rss_mib=rss,
                          shape=list(data.shape), dtype=str(data.dtype),
                          sha256=hashlib.sha256(data.tobytes()).hexdigest(),
                          file_mib=path.stat().st_size / 1024 ** 2)))


def summarize(results):
    summary = {}
    for fixture in sorted({row['fixture'] for row in results}):
        item = {}
        for version in ('baseline', 'current'):
            rows = [row for row in results
                    if row['fixture'] == fixture and row['version'] == version]
            rss = [row['peak_rss_mib'] for row in rows if row['peak_rss_mib'] is not None]
            item[version] = dict(
                median_seconds=statistics.median(row['seconds'] for row in rows),
                median_peak_rss_mib=statistics.median(rss) if rss else None)
        item['speedup'] = item['baseline']['median_seconds'] / item['current']['median_seconds']
        item['hashes_equal'] = len({row['sha256'] for row in results
                                   if row['fixture'] == fixture}) == 1
        summary[fixture] = item
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline', type=Path, help='Baseline source root containing lele/')
    parser.add_argument('--current', type=Path, help='Current source root containing lele/')
    parser.add_argument('--directory', type=Path, help='Directory for generated inputs and JSON results')
    parser.add_argument('--repeats', type=int, default=3, help='Fresh-process runs per tree/input (default: 3)')
    parser.add_argument('--one', nargs=2, metavar=('SOURCE_ROOT', 'INPUT'), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.one:
        one(Path(args.one[0]).resolve(), Path(args.one[1]).resolve())
        return 0
    if args.baseline is None or args.current is None or args.directory is None:
        parser.error('--baseline, --current and --directory are required')
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    sources = [('baseline', args.baseline.resolve()), ('current', args.current.resolve())]
    for _, source in sources:
        if not (source / 'lele' / 'cube_input.py').is_file():
            parser.error(f'Not a LELE source root: {source}')
        if not (source / 'examples' / 'artificial_signed_field.cube').is_file():
            parser.error(f'Missing warm-up example in {source}')
    directory = args.directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = [(directory / 'cube_224.cube', 224, 6),
                (directory / 'cube_128_single_line.cube', 128, 0)]
    for path, size, line_values in fixtures:
        if not path.exists():
            generate(path, size, line_values)
    results = []
    script = Path(__file__).resolve()
    for path, _, _ in fixtures:
        for version, source in sources:
            for repeat in range(args.repeats):
                environment = dict(os.environ, PYTHONPATH=str(source))
                completed = subprocess.run(
                    [sys.executable, str(script), '--one', str(source), str(path)],
                    env=environment, cwd=directory, capture_output=True, text=True,
                    check=True)
                record = dict(version=version, fixture=path.name, repeat=repeat,
                              **json.loads(completed.stdout))
                results.append(record)
                print(json.dumps(record), flush=True)
                (directory / 'cube_results.json').write_text(
                    json.dumps(results, indent=2) + '\n', encoding='utf-8')
    summary = summarize(results)
    (directory / 'cube_summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return 0 if all(item['hashes_equal'] for item in summary.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
