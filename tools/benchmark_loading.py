#!/usr/bin/env python3
"""Reproducible parser benchmarks; never drop frames to improve timings.

Example: python tools/benchmark_loading.py --generate /tmp/lele-bench \
    --repeat 3 --output /tmp/loading.json
Use --source /path/to/older/LELE --legacy-limit 20000 to compare 2.4.0.
"""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time


def generate(directory):
    directory.mkdir(parents=True,exist_ok=True)
    xyz=''.join(f'C {i%8*.7:.6f} {i//8%8*.7:.6f} {i//64*.7:.6f}\n' for i in range(128))
    paths=[directory/name for name in ('long_cp2k.xyz','long_plain.xyz','XDATCAR_long','long_noisy_cp2k.out','long_staged.out')]
    with paths[0].open('w') as stream:
        for i in range(10000):stream.write(f'128\n i = {i}, time = {i*.5:.3f}, E = {-100+i*.000001:.12f}\n'+xyz)
    with paths[1].open('w') as stream:
        for i in range(10000):stream.write('128\nframe '+str(i)+'\n'+xyz)
    with paths[2].open('w') as stream:
        stream.write('C\n1\n8 0 0\n0 8 0\n0 0 8\nC\n128\n')
        rows=''.join(f'{i%8*.1:.6f} {i//8%8*.1:.6f} {i//64*.1:.6f}\n' for i in range(128))
        for i in range(10000):stream.write(f'Direct configuration= {i+1}\n'+rows)
    with paths[3].open('w') as stream:
        stream.write('CP2K| version string: CP2K 2026.2\nGLOBAL| Run type GEO_OPT\n')
        noise='  42 OT DIIS 0.15E+00 0.2 1.1E-06 -697.0000000000 -1.0E-06\n'*300
        for i in range(4000):stream.write(noise+f'ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-10-i*.001:.8f}\n')
    with paths[4].open('w') as stream:
        for job in range(2):
            stream.write(' CP2K| version string: CP2K version 2026.2\n GLOBAL| Run type GEO_OPT\n')
            for i in range(2000):
                stream.write(f' OPTIMIZATION STEP: {i}\n MODULE QUICKSTEP: ATOMIC COORDINATES IN angstrom\n\n Atom Kind Element Z X Y Z\n')
                for j in range(16):stream.write(f' {j+1} 1 C 6 {j*.7:.6f} 0.0 {i*.00001:.8f}\n')
                stream.write(f'\n ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-100+i*.000001:.12f}\n')
    return paths


def science_digest(doc):
    """Coordinates, cells, symbols, energies and record links, outside timing."""
    h=hashlib.sha256()
    for frame in doc.frames:
        h.update('\0'.join(frame.symbols).encode())
        h.update(frame.positions.tobytes());h.update(frame.cell.tobytes())
        h.update(bytes(bool(value) for value in frame.pbc))
        h.update(repr(frame.energy_ev).encode())
    results=doc.calculation_results
    if results is not None:
        for step in results.steps:
            h.update(repr((step.energy_ev,step.frame_index,step.source_line,step.cycle,step.stage_index)).encode())
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--generate',type=Path)
    parser.add_argument('--file',type=Path,action='append',default=[])
    parser.add_argument('--repeat',type=int,default=3)
    parser.add_argument('--legacy-limit',type=int)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.repeat<1:parser.error('--repeat must be positive')
    paths=args.file or (generate(args.generate) if args.generate else [])
    if not paths:parser.error('Supply --file or --generate')
    sys.path.insert(0,str(args.source.resolve()))
    from lele import __version__
    from lele.formats import load_document
    from lele import cp2k_results,vasp_results  # warm native parser imports
    import ase.io.extxyz  # warm full XYZ fallback dependencies
    report={'version':__version__,'python':sys.version.split()[0],
            'repeat':args.repeat,'timing':'warm imports; complete parse, no GUI; wall seconds',
            'explicit_legacy_api_limit':args.legacy_limit,'cases':{}}
    for path in paths:
        times=[];digests=[];count=records=0
        for sample in range(args.repeat):
            gc.collect();start=time.perf_counter()
            doc=load_document(path,**({'max_frames':args.legacy_limit} if args.legacy_limit is not None else {}))
            times.append(time.perf_counter()-start)
            count=len(doc.frames);records=len(doc.calculation_results.steps) if doc.calculation_results else 0
            digests.append(science_digest(doc));del doc
        assert len(set(digests))==1
        row={'source_bytes':path.stat().st_size,'frames':count,'records':records,
             'seconds':times,'median_seconds':statistics.median(times),'science_sha256':digests[0]}
        report['cases'][path.name]=row
        print(path.name,json.dumps(row),flush=True)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
