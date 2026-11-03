#!/usr/bin/env python3
"""Complete ORCA parses and full-Document digests; synthetic inputs, no frame sampling.

python tools/benchmark_orca_loading.py --data /tmp/orca-bench --generate \
    --output /tmp/orca-current.json
Run the same script with --source /path/to/LELE-2.5.0 for a baseline.
"""
import argparse
from dataclasses import is_dataclass
import gc
import hashlib
import json
from pathlib import Path
import statistics
import struct
import sys
import time
import numpy as np


def document_digest(value):
    """Include every dataclass field, array, source link and optional result."""
    h=hashlib.sha256()
    def visit(v):
        if isinstance(v,np.ndarray):
            h.update(b'array');h.update(str(v.shape).encode());h.update(v.dtype.str.encode());h.update(v.tobytes())
        elif isinstance(v,np.generic):visit(v.item())
        elif v is None:h.update(b'none')
        elif isinstance(v,bool):h.update(b'true' if v else b'false')
        elif isinstance(v,int):h.update(b'int'+str(v).encode()+b';')
        elif isinstance(v,float):h.update(b'float'+struct.pack('d',v))
        elif isinstance(v,complex):h.update(b'complex');visit(v.real);visit(v.imag)
        elif isinstance(v,str):h.update(b'str'+str(len(v.encode())).encode()+b':'+v.encode())
        elif isinstance(v,Path):visit(str(v))
        elif isinstance(v,dict):
            h.update(b'dict')
            for key in sorted(v,key=repr):visit(key);visit(v[key])
        elif isinstance(v,(tuple,list,set,frozenset)):
            h.update(type(v).__name__.encode()+b'[')
            for item in sorted(v,key=repr) if isinstance(v,(set,frozenset)) else v:visit(item)
            h.update(b']')
        elif is_dataclass(v):h.update(type(v).__name__.encode());visit(vars(v))
        else:raise TypeError(type(v))
    visit(value);return h.hexdigest()


def generate(directory,counts):
    directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for count in counts:
        path=directory/f'orca_{count}.out';paths.append(path)
        with path.open('w') as stream:
            stream.write('O   R   C   A\n ! PBE def2-SVP Opt\n * xyz 0 1\n')
            for step in range(count):
                stream.write(f'GEOMETRY OPTIMIZATION CYCLE {step+1}\nCARTESIAN COORDINATES (ANGSTROEM)\n----------------\n')
                for atom in range(16):stream.write(f'C {atom*.3:.6f} 0.0 {step*.0001:.6f}\n')
                stream.write('\n'+' 1 DIIS 0.000001 -0.001 -10.00001\n'*30)
                stream.write(f'FINAL SINGLE POINT ENERGY {-100-step*.000001:.8f}\nTotal Dipole Moment : 0.1000 0.2000 0.3000\n')
            stream.write('THE OPTIMIZATION HAS CONVERGED\nORCA TERMINATED NORMALLY\n')
    return paths


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--generate',action='store_true')
    parser.add_argument('--counts',type=int,nargs='+',default=[1500,6000,12000])
    parser.add_argument('--repeat',type=int,default=3)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.repeat<1 or any(n<1 for n in args.counts):parser.error('Counts and repeats must be positive')
    paths=generate(args.data,args.counts) if args.generate else [args.data/f'orca_{n}.out' for n in args.counts]
    sys.path.insert(0,str(args.source.resolve()))
    from lele.formats import load_document
    from lele import __version__
    from lele import orca_results,orca_properties,orca_vibrations  # warm parser imports
    report={'version':__version__,'python':sys.version.split()[0],'synthetic':True,
            'repeat':args.repeat,'timing':'warm imports, entire parse; digest excluded; seconds','cases':{}}
    for path in paths:
        times=[];digests=[]
        for _ in range(args.repeat):
            gc.collect();start=time.perf_counter();doc=load_document(path)
            times.append(time.perf_counter()-start);digests.append(document_digest(doc))
            frames=len(doc.frames);steps=len(doc.calculation_results.steps);dipoles=len(doc.dipoles);del doc
        assert len(set(digests))==1
        row=dict(bytes=path.stat().st_size,frames=frames,steps=steps,dipoles=dipoles,
                 seconds=times,median_seconds=statistics.median(times),complete_document_sha256=digests[0])
        report['cases'][path.name]=row;print(path.name,row,flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
