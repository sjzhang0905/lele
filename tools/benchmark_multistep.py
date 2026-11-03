#!/usr/bin/env python3
"""Reproducible complete imports of synthetic multi-step outputs.

Run --generate once, then the same inputs with --source /path/to/old/LELE.
Digests cover complete documents except the new convergence annotation and QE
source-line/job annotations (additive metadata, not changed numeric values).
"""
import argparse,gc,json,statistics,sys,time
from pathlib import Path
from dataclasses import is_dataclass
import numpy as np
from benchmark_orca_loading import document_digest


def records(kind,count):
    if kind=='cp2k':
        yield 'CP2K| version string: CP2K version 2026.2\nGLOBAL| Run type GEO_OPT\n - Atoms: 2\n'
        for i in range(count):
            yield (f'OPTIMIZATION STEP: {i+1}\n MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM\n\n Atom Kind Element X Y Z\n'
                f' 1 1 O 8 0 0 0\n 2 2 H 1 0 0 {1+i*.00001:.8f}\n\n'
                'State Excitation Transition dipole (a.u.) Oscillator\nTDDFPT| 1 2.0 0.1 0.2 0.3 0.05\n'
                f'ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-10-i*.0001:.8f}\n')
    elif kind=='xtb':
        yield ' * xtb version 6.7.0\n'
        for i in range(count):
            yield (f' ... CYCLE {i+1} ...\n * total energy : {-10-i*.0001:.8f} Eh\n'
                ' # Occupation Energy/Eh Energy/eV\n 1 2.0 -0.5 -13.6057\n 2 0.0 0.1 2.7211\n'
                ' HL-Gap 0.6 Eh 16.3268 eV\n')
    elif kind=='qe':
        yield ('Program PWSCF v.7.5 starts\n celldm(1)= 10.00000\n number of atoms/cell = 2\n number of atomic types = 1\n'
            ' crystal axes: (cart. coord. in units of alat)\n a(1) = ( 1.0 0.0 0.0 )\n a(2) = ( 0.0 1.0 0.0 )\n a(3) = ( 0.0 0.0 1.0 )\n'
            ' positions (alat units)\n 1 H tau( 1) = ( 0.0 0.0 0.0 )\n 2 H tau( 2) = ( 0.0 0.0 0.2 )\n')
        for i in range(count):
            if i:yield f'ATOMIC_POSITIONS (angstrom)\nH 0 0 0\nH 0 0 {1+i*.00001:.8f}\n'
            yield f'!    total energy = {-2-i*.001:.9f} Ry\n'
    elif kind=='vasp':
        yield ('vasp.6.3.0\n POTCAR: PAW_PBE H 08Apr2002\n ions per type = 2\n NIONS = 2\n IBRION = 2\n'
            ' direct lattice vectors reciprocal lattice vectors\n 8 0 0 0 0 0\n 0 8 0 0 0 0\n 0 0 8 0 0 0\n')
        for i in range(count):
            yield (f' POSITION TOTAL-FORCE\n ------------------\n 0 0 0 .01 0 0\n 0 0 {1+i*.00001:.8f} -.01 0 0\n ------------------\n'
                f' FREE ENERGIE OF THE ION-ELECTRON SYSTEM\n energy without entropy = -10 energy(sigma->0) = {-10-i*.0001:.8f}\n')
    elif kind=='siesta':
        yield 'siesta: SIESTA\n Species number: 1 Atomic number: 1 Label: H\n'
        for i in range(count):
            yield (f'outcoor: Atomic coordinates (Ang)\n 0 0 0 1 H\n 0 0 {1+i*.00001:.8f} 1 H\n\n'
                f'siesta: Etot = {-10-i*.0001:.8f}\n')
    elif kind=='gaussian':
        yield 'Entering Gaussian System\n #p hf/sto-3g opt\n\n Charge = 0 Multiplicity = 1\n'
        for i in range(count):
            yield (' Standard orientation:\n ---------------------------------------------------------------------\n'
                ' Center Atomic Atomic Coordinates (Angstroms)\n Number Number Type X Y Z\n ---------------------------------------------------------------------\n'
                f' 1 1 0 0 0 0\n 2 1 0 0 0 {1+i*.00001:.8f}\n ---------------------------------------------------------------------\n'
                f' SCF Done: E(RHF) = {-2-i*.0001:.8f} A.U. after 8 cycles\n'
                ' Dipole moment (field-independent basis, Debye):\n X= 0.0 Y= 0.0 Z= 0.1 Tot= 0.1\n')
    elif kind in ('nwchem','nwchem_continuation'):
        yield ' Northwest Computational Chemistry Package\n'
        for i in range(count):
            yield f'                                 NWChem DFT Module\n Total DFT energy = {-10-i*.0001:.8f}\n'
            if kind=='nwchem' or i in (0,count-1):
                yield (' DFT ENERGY GRADIENTS\n\n atom coordinates gradient\n x y z x y z\n'
                    f' 1 H 0 0 0 0 0 .001\n 2 H 0 0 {1+i*.00001:.8f} 0 0 -.001\n\n')
    elif kind in ('xyz','xdatcar'):
        if kind=='xdatcar':yield 'H\n1.0\n8 0 0\n0 8 0\n0 0 8\nH\n2\n'
        for i in range(count):
            yield (f'2\nstep {i+1}\nH 0 0 0\nH 0 0 {1+i*.00001:.8f}\n' if kind=='xyz' else
                   f'Direct configuration= {i+1}\n0 0 0\n0 0 {0.1+i*.000001:.8f}\n')


def digest(doc):
    seen=set()
    def strip(value):
        if id(value) in seen:return
        seen.add(id(value))
        if type(value).__name__=='Frame':
            value.info.pop('optimization_converged',None)
            if value.info.get('source_kind')=='qe_out':
                value.info.pop('source_line',None);value.info.pop('calculation_index',None)
        if is_dataclass(value):
            for v in vars(value).values():strip(v)
        elif isinstance(value,dict):
            for v in value.values():strip(v)
        elif isinstance(value,(list,tuple)):
            for v in value:strip(v)
    strip(doc);return document_digest(doc)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument('--data',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--counts',type=int,nargs='+',default=[1000,4000]);ap.add_argument('--repeat',type=int,default=2)
    ap.add_argument('--kinds',nargs='+',default=['cp2k','xtb','qe','vasp','siesta','gaussian','xyz','xdatcar','nwchem','nwchem_continuation'])
    ap.add_argument('--generate',action='store_true');args=ap.parse_args()
    sys.path.insert(0,str(args.source.resolve()))
    from lele.formats import load_document
    from lele import __version__
    from lele import cp2k_results,vasp_results,xtb_results,gaussian_properties
    args.data.mkdir(parents=True,exist_ok=True)
    report={'version':__version__,'synthetic':True,'repeat':args.repeat,'cases':{}}
    for kind in args.kinds:
        for count in args.counts:
            path=args.data/f'{kind}_{count}.{dict(qe="pwo",xyz="xyz",xdatcar="xdatcar",nwchem="nwo",nwchem_continuation="nwo").get(kind,"out")}'
            if args.generate:
                with path.open('w') as f:f.writelines(records(kind,count))
            durations=[];digests=[]
            for _ in range(args.repeat):
                gc.collect();start=time.perf_counter();doc=load_document(path);durations.append(time.perf_counter()-start)
                digests.append(digest(doc));frames=len(doc.frames);steps=len(doc.calculation_results.steps)
            assert len(set(digests))==1
            row=dict(bytes=path.stat().st_size,frames=frames,steps=steps,seconds=durations,
                median_seconds=statistics.median(durations),document_digest=digests[0])
            report['cases'][path.name]=row;print(path.name,frames,round(row['median_seconds'],4),flush=True)
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
