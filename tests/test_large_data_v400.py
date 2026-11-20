"""Large-file paths at small fixture sizes, including source/display isolation."""
from io import StringIO
import mmap
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lele.formats import load_document


def test_cube_native_and_general_readers_agree(monkeypatch):
    from lele import cube_input
    rng = np.random.default_rng(47)
    values = rng.uniform(-1, 1, 4096) * 10.**rng.integers(-18, 18, 4096)
    tokens = [f'{x:.9e}'.replace('e','D') for x in values]
    tokens += ['-0.0', '.125', '+22.', '1.000000059604644775390625', '1e-60']
    text = ' \n'.join(tokens)
    monkeypatch.setattr(cube_input, '_SCALAR_CHUNK_CHARS', 101)
    accelerated = cube_input._cube_array(StringIO(text), len(tokens))
    monkeypatch.setattr(cube_input, 'reader', lambda: None)
    expected = cube_input._cube_array(StringIO(text), len(tokens))
    assert np.array_equal(accelerated.view('u4'), expected.view('u4'))


@pytest.mark.parametrize('bad', ['1z', 'NaN', 'inf', '1.0 2.0', '3d+', '1e500'])
def test_cube_rejects_malformed_tail(bad):
    from lele.cube_input import _cube_array
    with pytest.raises(ValueError):
        _cube_array(StringIO('1.25 '+bad), 2)


def test_cube_available_budget_accounts_for_all_channels(monkeypatch, tmp_path):
    from lele import grid_memory
    from lele.volumetric_input import read_cube_document
    path=tmp_path/'two.cube'
    path.write_text('test\nfields\n1 0 0 0 2\n2 1 0 0\n2 0 1 0\n2 0 0 1\n1 0 0 0 0\n'+'0 1 '*8)
    monkeypatch.setattr(grid_memory, 'available_bytes', lambda: 16*15)
    assert not read_cube_document(path).volumes
    monkeypatch.setattr(grid_memory, 'available_bytes', lambda: 16*16)
    assert len(read_cube_document(path).volumes)==2


def test_vtk_grid_cached_levels_and_writable_scalar_views():
    from lele.surface_rendering import _prepared_grid
    from lele.core import Volume
    draw=SimpleNamespace(_scalar_grids={})
    source=np.arange(125,dtype='f4').reshape(5,5,5)
    volume=Volume(source[::2,::2,::2], [0,0,0], np.eye(3),periodic=True)
    grid, scalars, buffer, limits, levels=_prepared_grid(draw,volume)
    assert limits==(0,124)
    assert _prepared_grid(draw,volume)[0] is grid
    assert np.shares_memory(buffer, __import__('vtkmodules.util.numpy_support', fromlist=['vtk_to_numpy']).vtk_to_numpy(scalars))
    assert np.array_equal(buffer[-1,:,:],buffer[0,:,:])
    source[-1,-1,-1]=-2
    new, _, _, new_limits, _=_prepared_grid(draw,volume)
    assert new is not grid and new_limits[0]==-2


@pytest.mark.parametrize('encoding', ['utf-8','utf-16'])
def test_sparse_outcar_multirun_final_complete_and_precise_sources(tmp_path,encoding):
    from lele.vasp_results import last_outcar_frame, read_vasp_results
    first=('vasp.6.3\n TITEL = PAW H\n ions per type = 2\n IBRION = 0\n'
           ' direct lattice vectors\n 3 0 0\n 0 3 0\n 0 0 3\n'
           ' POSITION      TOTAL-FORCE\n ------\n .0 .1 .2 0 0 0\n 1 .3 .4 0 0 0\n'
           ' free energy TOTEN = -5\n energy without entropy = -4 energy(sigma->0) = -3\n')
    text=first+first.replace('1 .3 .4','2 .3 .4')+' POSITION    TOTAL-FORCE\n --\n 0 0 0 0 0 0\n'
    path=tmp_path/'OUTCAR'
    path.write_bytes(text.replace('\n','\r\n').encode(encoding))
    doc=load_document(path)
    assert len(doc.frames)==2
    assert doc.frames[-1].info['source_line']==first.count('\n')+9
    assert doc.frames[-1].energy_ev==-3
    selected=last_outcar_frame(path)
    assert np.array_equal(selected.positions, doc.frames[-1].positions)
    assert selected.info=={k:v for k,v in read_vasp_results(path).frames()[-1].info.items()}


@pytest.mark.parametrize('fmt', ['xdatcar','cp2k'])
def test_private_mapped_frames_are_editable_and_self_contained(tmp_path,monkeypatch,fmt):
    from lele import trajectory_storage
    from lele.project_file import save_project,load_project
    from test_projects_v230 import state_for
    monkeypatch.setattr(trajectory_storage,'MIN_SOURCE_BYTES',0)
    if fmt=='xdatcar':
        p=tmp_path/'XDATCAR'
        p.write_text('test\n1\n2 0 0\n0 3 0\n0 0 4\nH O\n1 1\n'
                     +'Direct configuration= 1\n0 0 0\n.1 .2 .3\nCartesian configuration= 2\n1 1 1\n.4 .5 .6\n')
    else:
        p=tmp_path/'pos-1.xyz'
        p.write_text('2\n i = 1, time = 0, E = -1\nH 0 0 0\nO .1 .2 .3\n'
                     '2\n i = 2, time = 1, E = -2\nH 1 1 1\nO .4 .5 .6\n')
    d=load_document(p)
    source=d.calculation_results.steps[0].geometry
    edit=d.frames[0]
    assert isinstance(source.positions.base,mmap.mmap)
    assert isinstance(edit.positions.base,mmap.mmap)
    assert edit.positions.base is not source.positions.base
    p.unlink()
    edit.positions[:,0]+=7
    source.positions[1,1]=42
    assert source.positions[0,0]==0 and edit.positions[1,1]!=42 and d.frames[1].positions[0,0]==1
    assert np.array_equal(d.calculation_results.frames()[0].positions,source.positions)
    project=tmp_path/'edited.lele'
    save_project(project,state_for(d))
    recovered=load_project(project)['documents'][0]['document']
    assert np.array_equal(recovered.frames[0].positions,edit.positions)
    assert np.array_equal(recovered.calculation_results.steps[0].geometry.positions,source.positions)


def test_native_xyz_repeated_and_changed_species(monkeypatch,tmp_path):
    from lele.trajectory_io import xyz_blocks
    from lele import _cube_native
    path=tmp_path/'t.xyz'
    sets=[['Mo','H','He']*15,['Mo','H','He']*15,['Na','Ne','N']*15]
    with path.open('w') as stream:
        for i,labels in enumerate(sets):
            stream.write(f'{len(labels)}\n frame {i}\n')
            for j,sym in enumerate(labels):
                stream.write(f'{sym} {i+1} {j}.065432100D-2 -0.1234567890\n')
    native=list(xyz_blocks(path))
    monkeypatch.setattr(_cube_native,'_coordinate_reader',lambda:None)
    generic=list(xyz_blocks(path))
    for a,b,labels in zip(native,generic,sets):
        assert a[2]==b[2]==labels and np.array_equal(a[3].view('u8'),b[3].view('u8'))
    native[0][2][0]='Fe'
    assert native[1][2][0]=='Mo'


def test_wavecar_order_matches_scalar_reference_and_cache_is_private():
    from lele.binary_wavefunctions import Wavecar, KINETIC_EV_ANG2
    cell=np.array([[8.,0,0],[1.2,7.,0],[-1.1,.7,6.]])
    k=np.array([.19,-.27,.13])
    cutoff=83.
    b=np.ceil(np.linalg.norm(cell,axis=1)*np.sqrt(cutoff/KINETIC_EV_ANG2)/(2*np.pi)+np.abs(k)).astype(int)+1
    ax=[[*range(n+1),*range(-n,0)] for n in b]
    recip=2*np.pi*np.linalg.inv(cell).T
    reference=[(x,y,z) for z in ax[2] for y in ax[1] for x in ax[0]
               if KINETIC_EV_ANG2*np.sum(((np.array([x,y,z])+k)@recip)**2)<cutoff]
    w=Wavecar(Path('WAVECAR'),0,2,45200,'<',1,1,cutoff,cell,None,
              np.tile(k,(2,1,1)),np.full((2,1),len(reference)),np.zeros((2,1,1)),np.zeros((2,1,1)))
    assert w.validate_reconstruction()
    vec,bounds=w.reciprocal_vectors()
    assert np.array_equal(vec,reference) and np.array_equal(bounds,b)
    vec[:]=99
    assert np.array_equal(w.reciprocal_vectors(1,0)[0],reference)
    w.ncoeff[1,0]+=1
    assert not w.validate_reconstruction()


def test_large_trajectory_coordinate_scroll_and_atom_panel(gui,tmp_path):
    from lele.core import Document,Frame
    from PySide6.QtWidgets import QApplication
    n=150
    frames=[Frame(['H']*n,np.column_stack((np.arange(n)+i,np.zeros(n),np.zeros(n))))
            for i in range(64)]
    w=gui.window
    w._attach_loaded_document(Document(tmp_path/'t.xyz','XYZ',frames))
    w.tabs.setCurrentWidget(w.atom_table)
    w.change_frame(61)
    assert w.atom_table.rowCount()==n
    w.atom_table.scrollToBottom()
    QApplication.processEvents()
    assert w.atom_table.item(n-1,1).text()==f'{n-1+61:.6f}'
    w.sidebar_tabs.setCurrentWidget(w.atom_panel)
    assert w.atom_panel._frame is w.frame
    w.change_frame(4)
    assert w.atom_panel._frame is frames[4]
    assert f'{n-1+4:.8f}' in w.atom_panel._items[n-1].toolTip(0)


from test_periodic_fragment_ui_v171 import gui


def test_complex_bloch_state_matches_direct_sum(tmp_path):
    from lele.binary_wavefunctions import Wavecar,KINETIC_EV_ANG2
    cell=np.diag([5.,5.5,6.])
    k=np.array([.18,-.25,.03])
    en=30.
    bound=np.ceil(np.linalg.norm(cell,axis=1)*np.sqrt(en/KINETIC_EV_ANG2)/(2*np.pi)+np.abs(k)).astype(int)+1
    axes=[[*range(n+1),*range(-n,0)] for n in bound]
    recip=2*np.pi*np.linalg.inv(cell).T
    gs=np.array([(x,y,z) for z in axes[2] for y in axes[1] for x in axes[0]
                 if KINETIC_EV_ANG2*np.sum(((np.array([x,y,z])+k)@recip)**2)<en])
    rng=np.random.default_rng(12)
    coeff=(rng.normal(size=len(gs))+1j*rng.normal(size=len(gs))).astype('<c8')
    recl=coeff.nbytes
    path=tmp_path/'WAVECAR'
    with path.open('wb') as stream:
        stream.seek(3*recl)
        stream.write(coeff.tobytes())
    w=Wavecar(path,recl,1,45200,'<',1,1,en,cell,None,k.reshape(1,1,3),
              np.array([[len(gs)]]),np.zeros((1,1,1)),np.zeros((1,1,1)))
    shape=4*bound+1
    pts=np.array([[0,0,0],[1,3,2],shape//2,shape-1])
    phase=2j*np.pi*((pts/shape)@(gs+k).T)
    expected=np.exp(phase)@coeff/np.sqrt(np.linalg.det(cell))
    for kind,truth in [('real',expected.real),('imag',expected.imag),('density',np.abs(expected)**2)]:
        volume=w.volume(kind=kind)
        assert np.allclose(volume.data[tuple(pts.T)],truth,rtol=1e-6,atol=1e-7)


def test_partial_temp_write_recovers_previous_coordinates(tmp_path):
    from lele.trajectory_storage import CoordinateStore
    from lele.core import Frame
    with (tmp_path/'coords').open('w+b',buffering=0) as stream:
        class ShortWrite:
            def __getattr__(self,name):
                return getattr(stream,name)
            def write(self,value):
                return stream.write(value if not stream.tell() else value[:1])
        store=CoordinateStore(ShortWrite())
        arrays=[np.arange(12).reshape(4,3).astype(float)+i for i in range(3)]
        frames=[Frame(['H']*4,x.copy()) for x in arrays]
        for frame in frames:
            store.append(frame)
        store.finish()
        assert all(np.array_equal(frame.positions,array) for frame,array in zip(frames,arrays))


@pytest.mark.parametrize('periodic',[False,True])
def test_trilinear_skew_grid_seams_and_roundoff(periodic):
    from itertools import product
    from lele.core import Volume
    from lele.field_mapping import sample_field
    rng=np.random.default_rng(331)
    a=rng.normal(size=(6,7,8)).astype('f4')
    basis=np.array([[.7,0,0],[.13,.8,0],[.1,-.22,.77]])
    origin=np.array([-.1,.2,.9])
    shape=np.array(a.shape)
    xyz=np.vstack((rng.uniform(-3,10,(210,3)), [0.,0.,0.],shape-1,[-1.e-7,1,1],shape))
    result=sample_field(Volume(a,origin,basis,periodic=periodic),origin+xyz@basis,chunk_size=31)
    expected=[]
    for point in xyz:
        if not periodic and (np.any(point < -2e-5) or np.any(point > shape-1+2e-5)):
            expected.append(np.nan)
            continue
        point=point%shape if periodic else np.clip(point,0,shape-1)
        lo=np.floor(point).astype(int)
        frac=point-lo
        value=0.
        for bits in product((0,1),repeat=3):
            idx=lo+bits
            idx=idx%shape if periodic else np.minimum(idx,shape-1)
            value+=float(a[tuple(idx)])*np.prod(np.where(bits,frac,1-frac))
        expected.append(value)
    np.testing.assert_allclose(result,expected,atol=1e-12,rtol=1e-12)
