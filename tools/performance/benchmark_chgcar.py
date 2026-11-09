#!/usr/bin/env python3
"""Compare complete CHGCAR imports against an earlier LELE source tree.

Example:
  python benchmark_chgcar.py --baseline /path/to/old/LELE \
      --current /path/to/new/LELE --directory ./chgcar_benchmark \
      --input /path/to/CHGCAR --repeats 3

The optional input is copied to a canonical CHGCAR name so both versions use
the charge-density reader. The output directory also receives a generated
119 MB two-channel CHGCAR with PAW augmentation, and chgcar_benchmark.json.
Every timed load uses a fresh subprocess, with dependencies warmed by a tiny
CHGCAR import. The complete load_document call is timed, including format
detection and document construction, excluding imports and GUI rendering.
Files use the operating system cache; this is not a cold-disk benchmark.
No private input file is included in the release package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time


HEADER='benchmark\n1\n10 0 0\n0 11 0\n0 0 12\nH\n1\nDirect\n0 0 0\n\n'


def generate_two_channels(path):
    """Reproduce the release's 144³ × 2-channel fixture byte for byte."""
    n=144
    tokens=[' 0.123456789123E+03','-0.234567891234E+02',
            ' 0.345678912345E-03','-0.456789123456E-04',' 0.567891234567E-05']
    row=' '.join(tokens)+'\n'
    repeat,remainder=divmod(n**3,5)
    with path.open('w',encoding='utf-8',newline='\n') as stream:
        stream.write(HEADER)
        for _ in range(2):
            stream.write(f'{n} {n} {n}\n')
            times=repeat
            block=row*8192
            while times>=8192:
                stream.write(block)
                times-=8192
            stream.write(row*times)
            if remainder:stream.write(' '.join(tokens[:remainder])+'\n')
            stream.write('augmentation occupancies 1 10\n2 2 2 3 4\n5 6 7 8 9\n')


def peak_rss_mib():
    try:
        import resource
    except ImportError:
        return None  # The standard resource module is unavailable on Windows.
    value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value/(1024*1024 if sys.platform=='darwin' else 1024)


def worker(root,path,warm):
    sys.path.insert(0,root)
    from lele.formats import load_document
    load_document(warm)
    started=time.perf_counter()
    doc=load_document(path)
    seconds=time.perf_counter()-started
    if not doc.volumes:raise ValueError(doc.note)
    digest=hashlib.sha256()
    for frame in doc.frames:
        digest.update(frame.positions.tobytes())
        digest.update(frame.cell.tobytes())
        digest.update(str((frame.symbols,frame.pbc)).encode())
    for volume in doc.volumes:
        digest.update(volume.data.tobytes())
        digest.update(volume.origin.tobytes())
        digest.update(volume.voxel_vectors.tobytes())
        digest.update(str((volume.label,volume.unit,volume.periodic)).encode())
    import numpy
    import ase
    print(json.dumps({
        'seconds':seconds,'peak_rss_mib':peak_rss_mib(),
        'sha256':digest.hexdigest(),'bytes':Path(path).stat().st_size,
        'shapes':[list(volume.data.shape) for volume in doc.volumes],
        'dtypes':[str(volume.data.dtype) for volume in doc.volumes],
        'atoms':len(doc.frames[0].symbols),'numpy':numpy.__version__,
        'ase':ase.__version__,
    }))


def main():
    parser=argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--baseline',type=Path,required=True,
                        help='Baseline source root containing lele/')
    parser.add_argument('--current',type=Path,required=True,
                        help='Current source root containing lele/')
    parser.add_argument('--directory',type=Path,required=True,
                        help='Writable benchmark inputs/results directory')
    parser.add_argument('--input',type=Path,
                        help='Optional real CHGCAR charge-density file')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if args.repeats<1:parser.error('--repeats must be positive')
    roots={name:getattr(args,name).resolve() for name in ('baseline','current')}
    for name,root in roots.items():
        if not (root/'lele/formats.py').is_file():
            parser.error(f'{name} must contain lele/formats.py')
    if args.input is not None and not args.input.is_file():
        parser.error('--input must name an existing CHGCAR file')
    directory=args.directory.resolve()
    directory.mkdir(parents=True,exist_ok=True)
    warm=directory/'CHGCAR_warm'
    synthetic=directory/'CHGCAR_two_channels'
    if args.input is not None and args.input.resolve() in (warm,synthetic):
        parser.error('--input must not be one of the generated fixture paths; '
                     'choose a separate --directory')
    warm.write_text(HEADER+'2 2 2\n1 2 3 4 5 6 7 8\n',encoding='utf-8')
    inputs=[]
    if args.input is not None:
        sample=directory/'CHGCAR_input'
        if args.input.resolve()!=sample:shutil.copyfile(args.input,sample)
        inputs.append(sample)
    generate_two_channels(synthetic)
    inputs.append(synthetic)
    environment={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
    records=[]
    for path in inputs:
        for repeat in range(args.repeats):
            order=['baseline','current'] if repeat%2==0 else ['current','baseline']
            for name in order:
                process=subprocess.run([
                    sys.executable,str(Path(__file__).resolve()),'--_worker',
                    str(roots[name]),str(path),str(warm),
                ],text=True,capture_output=True,check=True,env=environment)
                result={'case':path.name,'version':name,'repeat':repeat,
                        **json.loads(process.stdout)}
                records.append(result)
                print(json.dumps(result),flush=True)
    summary={}
    for path in inputs:
        entries=[record for record in records if record['case']==path.name]
        case={}
        for name in roots:
            group=[record for record in entries if record['version']==name]
            rss=[record['peak_rss_mib'] for record in group
                 if record['peak_rss_mib'] is not None]
            case[name]={
                'seconds':statistics.median(record['seconds'] for record in group),
                'peak_rss_mib':statistics.median(rss) if rss else None,
            }
        case['equal']=len({record['sha256'] for record in entries})==1
        case['speedup']=case['baseline']['seconds']/case['current']['seconds']
        summary[path.name]=case
    payload={
        'python':sys.version,'platform':platform.platform(),
        'repeats':args.repeats,
        'measurement':'Fresh subprocess; warmed complete load_document; includes '
            'format detection and document construction; excludes package import '
            'and GUI rendering; warm operating-system file cache.',
        'rss_note':'Process peak RSS, not incremental parser memory; null where '
            'the standard resource module is unavailable.',
        'summary':summary,'runs':records,
    }
    target=directory/'chgcar_benchmark.json'
    target.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
    print(f'Results: {target}')
    if not all(case['equal'] for case in summary.values()):
        raise SystemExit('ERROR: field/geometry/metadata digests differ')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--_worker':worker(*sys.argv[2:])
    else:main()
