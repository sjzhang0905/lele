"""Original independent v3.3.0 acceptance cases, retained as regression tests.

Set LELE_REVIEW_SOURCE to an unpacked LELE source directory. All nine cases must now pass.
Qt uses the package's headless canvas adapter; scientific/VTK objects and
LELEWindow callbacks are real. This is not a Windows desktop test.
"""
import os, sys
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(os.environ.get('LELE_REVIEW_SOURCE',Path(__file__).resolve().parents[1])).resolve()
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_periodic_fragment_ui_v171 import gui
from lele.core import Document,Frame,Volume
from lele.formats import load_document

MOLDEN='''[Molden Format]
[Atoms] Angs
H 1 1 0 0 0
[GTO]
1 0
s 1 1.0
0.2 1.0
[MO]
Sym= A1
Ene= -0.2
Spin= Alpha
Occup= 1.0
1 1.0
'''

def write_fchk(path):
    lines=['Independent H atom','SP UHF custom']
    scalar={'Number of atoms':1,'Number of basis functions':1,'Number of alpha electrons':1,'Number of beta electrons':0}
    for key,value in scalar.items():lines.append(f'{key:<43} I {value}')
    arrays={'Atomic numbers':('I',[1]),'Current cartesian coordinates':('R',[0,0,0]),
        'Shell types':('I',[0]),'Number of primitives per shell':('I',[1]),'Shell to atom map':('I',[1]),
        'Primitive exponents':('R',[.2]),'Contraction coefficients':('R',[1.]),
        'Alpha Orbital Energies':('R',[-.2]),'Alpha MO coefficients':('R',[1.])}
    for key,(kind,values) in arrays.items():
        lines.extend([f'{key:<43} {kind} N= {len(values)}',' '.join(map(str,values))])
    path.write_text('\n'.join(lines)+'\n');return path

@pytest.mark.parametrize('extension',['fchk','molden'])
def test_A1_parsed_orbital_file_must_attach_to_main_window(gui,tmp_path,extension):
    path=tmp_path/('H.'+extension)
    if extension=='fchk':write_fchk(path)
    else:path.write_text(MOLDEN)
    doc=load_document(path)
    assert doc.wavefunction.can_evaluate
    assert doc.frames[0].info['stage_index']==0
    # Expected: ordinary user open finishes without IndexError.
    gui.window._attach_loaded_document(doc)
    assert gui.window.mo_generate.isEnabled()

def field_points(draw):
    from vtkmodules.util.numpy_support import vtk_to_numpy
    points=[]
    for actor in draw.dynamic:
        if not hasattr(actor,'GetMapper'):continue
        mapper=actor.GetMapper()
        if mapper is None or not hasattr(mapper,'GetInput'):continue
        mapper.Update();data=mapper.GetInput()
        if data and data.GetPointData().GetScalars() and data.GetPointData().GetScalars().GetName()=='volume_field':
            points.append(vtk_to_numpy(data.GetPoints().GetData()))
    return np.concatenate(points)

def test_A2_first_generated_orbital_must_be_within_camera_clipping(gui,tmp_path):
    path=tmp_path/'H.molden';path.write_text(MOLDEN);parsed=load_document(path)
    # Isolate camera behavior from A1's unrelated missing-stage metadata.
    doc=Document(path,'Analytic S orbital',[Frame(['H'],[[0.,0.,0.]])],wavefunction=parsed.wavefunction)
    w=gui.window;w._attach_loaded_document(doc)
    w.render_options.axes_position='Off';w.refresh_scene(reset_camera=True)
    w._generate_orbital_grid()
    camera=w.scene.GetActiveCamera();near,far=camera.GetClippingRange()
    points=field_points(w.renderer)
    depth=(points-np.asarray(camera.GetPosition()))@np.asarray(camera.GetDirectionOfProjection())
    assert depth.min()>=near and depth.max()<=far, (
        f'New orbital depth [{depth.min():.6g}, {depth.max():.6g}] is clipped by [{near:.6g}, {far:.6g}]')

@pytest.mark.parametrize('bounds,expected_x',[
    (((0,2),(0,1),(0,1)),(.25,1.75)),
    (((1,2),(0,1),(0,1)),(1.25,1.75))])
def test_A3_periodic_surface_must_follow_boundary(gui,bounds,expected_x):
    n=20;data=np.broadcast_to(np.cos(2*np.pi*np.arange(n)[:,None,None]/n),(n,n,n)).copy()
    vol=Volume(data,[0,0,0],np.eye(3)/n,'Periodic analytic field','dimensionless',True)
    frame=Frame(['H'],[[.5,.5,.5]],np.eye(3),(True,)*3)
    gui.attach(frame,volume=vol);w=gui.window
    w.render_options.volume_surfaces=[dict(value=0.,color='#ff0000',opacity=1.,style='Surface',visible=True)]
    w._apply_boundary(True,bounds)
    points=field_points(w.renderer)
    np.testing.assert_allclose([points[:,0].min(),points[:,0].max()],expected_x,atol=1e-6)

@pytest.mark.parametrize('axis',[0,1,2])
def test_control_skew_slice_matches_independent_cartesian_linear_field(axis):
    from lele.field_slice import grid_plane_slice
    shape=(5,6,7);origin=np.array([.3,-1.,.7]);basis=np.array([[.4,.1,0],[-.1,.5,.1],[.2,-.1,.6]])
    xyz=np.moveaxis(np.indices(shape),0,-1)@basis+origin
    gradient=np.array([2.1,-.7,.8]);values=xyz@gradient+.31
    section=grid_plane_slice(Volume(values,origin,basis),axis,.371)
    np.testing.assert_allclose(section.values,section.xyz@gradient+.31,atol=8e-7,rtol=2e-7)

def test_control_export_density_matches_ase(tmp_path):
    from ase.io.cube import read_cube
    from ase.units import Bohr
    from lele.field_export import export_active_cube
    basis=np.array([[.2,.1,0],[0,.3,.1],[.1,0,.4]])
    vol=Volume(np.arange(60).reshape(3,4,5)/10,[.1,.2,.3],basis,'Test density','e/Å³',True)
    frame=Frame(['H'],[[.2,.3,.4]],basis*np.array([3,4,5])[:,None],(True,)*3)
    doc=Document(tmp_path/'CHGCAR','VASP CHGCAR',[frame],vol)
    path=tmp_path/'field.cube';export_active_cube(path,doc,frame)
    with path.open() as stream:actual=read_cube(stream)
    np.testing.assert_allclose(actual['data'],vol.data*Bohr**3,rtol=2e-7,atol=1e-9)
    np.testing.assert_allclose(actual['origin'],vol.origin,atol=1e-12)
    np.testing.assert_allclose(actual['spacing'],basis,atol=1e-12)
    np.testing.assert_allclose(actual['atoms'].positions,frame.positions,atol=1e-12)
