"""Generate the v4.0 target sizes or measure one complete import per process.

    python tools/performance/benchmark_large_files.py make ./lele-fixtures
    python tools/performance/benchmark_large_files.py run ./lele-fixtures --case xd
    python tools/performance/benchmark_large_files.py run ./lele-fixtures --case wave --source ../v3.18

Generation uses about 6 GiB (9 GiB without hard links) in a new or empty directory. Local Linux
timings use a warm file cache. Hash checks run after taking the import RSS/time.
"""
import argparse
import gc
import hashlib
from itertools import product
import json
import os
from pathlib import Path
import shutil
import sys
from time import perf_counter

import numpy as np

FILES = {'cube400':'density400.cube','cube416':'density416.cube','out':'OUTCAR_long',
         'xd':'XDATCAR','cp':'cp2k.xyz','wave':'wave/WAVECAR','companion':'wave-outcar/WAVECAR'}
WARM = {'cube400':'artificial_signed_field.cube','cube416':'artificial_signed_field.cube',
        'out':'synthetic_vasp_v210.OUTCAR','xd':'synthetic_vasp_geometry_only_v210.XDATCAR',
        'cp':'synthetic_cp2k_v240.xyz','wave':'Si_POSCAR','companion':'Si_POSCAR'}


def make_trajectories(directory):
    cell = np.diag([20.,21.,22.])
    base = (np.indices((10,10,5)).reshape(3,-1).T+.4)/[10,10,5]
    phase = np.arange(500)*.083
    symbols = ['O']*167+['H']*333
    blocks = []
    for j in range(64):
        p = base + .0005*np.sin(phase[:,None]+j*(2*np.pi/64)+[0.,1.,2.])
        direct = ''.join(' %.9f %.9f %.9f\n'%tuple(row) for row in p)
        cartes = ''.join('%s %.9f %.9f %.9f\n'%(s,*row) for s,row in zip(symbols,p@cell))
        blocks.append((direct,cartes))
    with (directory/'XDATCAR').open('w',newline='\n') as xd, (directory/'cp2k.xyz').open('w',newline='\n') as cp:
        xd.write('AIMD synthetic\n1\n20 0 0\n0 21 0\n0 0 22\nO H\n167 333\n')
        for step in range(10000):
            direct,cartes=blocks[step%64]
            xd.write(f'Direct configuration= {step+1}\n'+direct)
            cp.write(f'500\n i = {step+1}, time = {step:.1f}, E = {-1000-step*.00002:.8f}\n'+cartes)


def make_wave(directory):
    wave=directory/'wave'
    wave.mkdir()
    cell=np.eye(3)*16.
    kpoints=list(product((-.25,.25),repeat=3))
    q=np.arange(-30,31)
    grid=np.stack(np.meshgrid(q,q,q,indexing='ij'),axis=-1).reshape(-1,3)
    reciprocal=2*np.pi*np.linalg.inv(cell).T
    counts=[int(np.sum(3.80998211615486*np.square((grid+k)@reciprocal).sum(axis=1)<400.)) for k in kpoints]
    recl=((8*max(counts)+255)//256)*256
    bands=round((3*2**30/recl-2)/(len(kpoints)*2)-1)
    def header(stream,values):
        raw=np.asarray(values,dtype='<f8').tobytes()
        stream.write(raw)
        stream.write(bytes(recl-len(raw)))
    with (wave/'WAVECAR').open('wb') as stream:
        header(stream,[recl,2,45200])
        header(stream,[8,bands,400.,*cell.ravel(),.12])
        states=np.zeros((bands,3))
        states[:,0]=np.arange(bands)*.02-6
        states[:bands//2,2]=1.
        for spin in range(2):
            for i,k in enumerate(kpoints):
                header(stream,[counts[i],*k,*states.ravel()])
                coeff=np.zeros(recl//8,dtype='<c8')
                prior=0
                for band in range(bands):
                    coeff[prior]=0
                    prior=(band*127+i*73+spin)%counts[i]
                    coeff[prior]=1j
                    stream.write(memoryview(coeff))
    (wave/'POSCAR').write_text('synthetic\n1\n16 0 0\n0 16 0\n0 0 16\nO\n1\nDirect\n0 0 0\n')
    other=directory/'wave-outcar'
    other.mkdir()
    try:
        os.link(wave/'WAVECAR',other/'WAVECAR')
    except OSError:
        shutil.copyfile(wave/'WAVECAR',other/'WAVECAR')
    with (directory/'OUTCAR_long').open('rb') as src,(other/'OUTCAR').open('wb') as out:
        for line in src:
            out.write(line)
            if b'direct lattice vectors' in line:
                for prefix in (b'10.0',b'11.0',b'12.0'):
                    out.write(next(src).replace(prefix,b'16.0',1))
                break
        shutil.copyfileobj(src,out,2**20)


def generate(directory):
    from benchmark_cube import generate as make_cube
    from benchmark_trajectory import generate_inputs
    directory.mkdir(parents=True,exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError('Generate the benchmark in a new or empty directory.')
    generate_inputs(directory,500,0,5678)
    make_trajectories(directory)
    make_cube(directory/'density400.cube',400,True)
    make_cube(directory/'density416.cube',416,True)
    make_wave(directory)


def rss_mib():
    try:
        import resource
        value=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value/(2**20 if sys.platform=='darwin' else 1024)
    except ImportError:
        return None


def measure(directory,case,root):
    sys.path.insert(0,str(root.resolve()))
    from lele import __version__
    from lele.formats import load_document
    path=directory/FILES[case]
    warm=load_document(root/'examples'/WARM[case])
    del warm
    gc.collect()
    started=perf_counter()
    doc=load_document(path)
    result=dict(version=__version__,case=case,bytes=path.stat().st_size,
                seconds=perf_counter()-started,peak_MiB=rss_mib(),frames=len(doc.frames))
    if case.startswith('cube'):
        result['shape']=None if doc.volume is None else list(doc.volume.data.shape)
        assert result['shape'] == [int(case[4:])]*3 or (case=='cube416' and __version__=='3.18.0')
        if doc.volume is not None:
            result['field_sha256']=hashlib.sha256(doc.volume.data.ravel(order='C').view('u1')).hexdigest()
            pattern=np.array([-1.2345678e-3,2.7182818e-4,-9.8765432e-5,
                              3.1415927e-2,1.2345678e-6,-6.0221408e-1],dtype='f4')
            block=np.tile(pattern,32768)
            repeats,tail=divmod(doc.volume.data.size,len(block))
            reference=hashlib.sha256()
            for _ in range(repeats):
                reference.update(block.view('u1'))
            reference.update(block[:tail].view('u1'))
            assert result['field_sha256']==reference.hexdigest()
    elif case in ('xd','cp','out'):
        assert len(doc.frames)==(5678 if case=='out' else 10000)
        assert len(doc.frames[0].symbols)==500
        digest=hashlib.sha256()
        for step in doc.calculation_results.steps:
            frame=doc.frames[step.frame_index]
            assert np.array_equal(frame.positions,step.geometry.positions)
            digest.update(frame.positions.tobytes())
            digest.update(frame.cell.tobytes())
            digest.update(json.dumps([frame.symbols,frame.pbc,frame.info,step.source_line,
                                      step.cycle,step.energy_ev,step.info,step.convergence],
                                     sort_keys=True,default=lambda v:v.item()).encode())
        result['all_frames_sha256']=digest.hexdigest()
    else:
        w=doc.wavecar
        assert len(doc.frames)==1 and w.reconstruction_supported
        if case=='companion':
            assert 'adjacent OUTCAR' in doc.note and len(doc.frames[0].symbols)==500
        started=perf_counter()
        volume=w.volume(1,w.nkpoints-1,w.nbands-1)
        result['density_seconds']=perf_counter()-started
        result['density_peak_MiB']=rss_mib()
        assert np.allclose(volume.data,1./np.linalg.det(w.cell),atol=1e-9)
        result['density_sha256']=hashlib.sha256(volume.data.tobytes()).hexdigest()
        digest=hashlib.sha256()
        for spin in range(w.spins):
            for kpoint in range(w.nkpoints):
                vectors,_=w.reciprocal_vectors(spin,kpoint)
                digest.update(vectors.astype('<i4').tobytes())
        result['ordered_G_sha256']=digest.hexdigest()
    print(json.dumps(result))


def visual_measure(directory, case, root):
    sys.path.insert(0,str(root.resolve()))
    from lele import __version__
    if case == 'mesh':
        from vtkmodules.util.numpy_support import vtk_to_numpy
        from vtkmodules.vtkRenderingCore import vtkRenderer
        from lele.core import Frame,Volume
        from lele.renderer import MoleculeRenderer
        n=400
        grid=np.empty((n,n,n),dtype='f4')
        axis=np.linspace(-1,1,n,dtype='f4')
        yz=axis[:,None]**2+axis[None,:]**2
        for i,x in enumerate(axis):
            np.exp(-6*(x*x+yz),out=grid[i])
        frame=Frame(['O'],[[0.,0.,0.]])
        field=Volume(grid,[-1]*3,np.eye(3)*2/(n-1))
        scene=MoleculeRenderer(vtkRenderer())
        scene.options.volume_signs='Positive'
        scene.options.volume_iso=.2
        times=[]
        for _ in range(2):
            started=perf_counter()
            scene.set_scene(frame,field)
            times.append(perf_counter()-started)
            assert len(scene.field_actors)==1
            poly=scene.field_actors[0].GetMapper().GetInput()
            digest=hashlib.sha256(vtk_to_numpy(poly.GetPoints().GetData()).tobytes()).hexdigest()
        print(json.dumps(dict(v=__version__,case=case,times=times,peak=rss_mib(),
                              triangles=poly.GetNumberOfCells(),points=digest)))
    else:
        # The GUI test fixture runs normal frame-change handlers with the final
        # window paint disabled. This measures CPU work per step, not display FPS.
        sys.path.insert(1,str(root.resolve()/'tests'))
        from test_selection_ui_v090 import SelectionWorkflowTests
        from lele.formats import load_document
        SelectionWorkflowTests.setUpClass()
        suite=SelectionWorkflowTests('test_invert_complements_selection_and_updates_coordinate_table')
        suite.setUp()
        try:
            window=suite.window
            doc=load_document(directory/'XDATCAR')
            started=perf_counter()
            window._attach_loaded_document(doc)
            attach=perf_counter()-started
            times=[]
            for index in range(10,16):
                started=perf_counter()
                window.change_frame(index)
                times.append(perf_counter()-started)
                assert window.frame_index==index and window.atom_table.rowCount()==500
                SelectionWorkflowTests.app.processEvents()
            print(json.dumps(dict(v=__version__,case=case,attach=attach,frame_times=times)))
        finally:
            suite.doCleanups()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['make','run'])
    parser.add_argument('directory',type=Path)
    parser.add_argument('--case',choices=(*FILES,'mesh','gui'),default='cube400')
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
    args=parser.parse_args()
    if args.action=='make':
        generate(args.directory)
    elif args.case in ('mesh','gui'):
        visual_measure(args.directory,args.case,args.source)
    else:
        measure(args.directory,args.case,args.source)
