from pathlib import Path
import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy
from lele.core import Volume
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer, volume_surface_specs


def test_legacy_default_surfaces():
    opts=RenderOptions();specs=volume_surface_specs(opts)
    assert [x['value'] for x in specs]==[-.035,.035]
    assert [x['color'] for x in specs]==['#556EE6','#EC6B46']
    assert [x['opacity'] for x in specs]==[.65,.65]


def test_independent_signs_opacity_and_styles():
    opts=RenderOptions();opts.volume_iso=.3;opts.volume_independent_negative=True
    opts.volume_negative_iso=.7;opts.volume_independent_opacity=True;opts.volume_negative_opacity=.2
    opts.volume_opacity=.9;opts.volume_positive_color='#FF0000';opts.volume_negative_color='#00FF00'
    opts.volume_representation='Wireframe'
    specs=volume_surface_specs(opts)
    assert [x['value'] for x in specs]==[-.7,.3]
    assert [x['opacity'] for x in specs]==[.2,.9]
    assert all(x['style']=='Wireframe' for x in specs)


def test_multiple_levels_custom_zero_and_hidden():
    opts=RenderOptions();opts.volume_surfaces=[
        dict(value=-.5,color='#FF0000',opacity=.2,style='Wireframe'),
        dict(value=0.,color='#00FF00',opacity=.6,style='Points'),
        dict(value=.5,color='#0000FF',opacity=.9,style='Surface'),
        dict(value=.2,color='#FFFFFF',visible=False)]
    data=np.indices((5,5,5))[0].astype(float)-2
    draw=MoleculeRenderer(vtkRenderer());draw.options=opts
    draw._volume(Volume(data,[2,3,4],[[1,0,0],[.2,1,0],[.1,.3,1]]))
    assert len(draw.dynamic)==3
    for i,actor in enumerate(draw.dynamic):
        assert actor.GetProperty().GetRepresentation()==[1,0,2][i]
        assert actor.GetProperty().GetOpacity()==[.2,.6,.9][i]
        actor.GetMapper().Update()
        points=vtk_to_numpy(actor.GetMapper().GetInput().GetPoints().GetData())
        coords=(points-[2,3,4])@np.linalg.inv([[1,0,0],[.2,1,0],[.1,.3,1]])
        np.testing.assert_allclose(coords[:,0],[1.5,2,2.5][i],atol=1e-6)


@pytest.mark.parametrize('spec',[
    dict(value=float('nan')),dict(value=.2,opacity=2),dict(value=.2,color='red'),
    dict(value=.2,style='Anything')])
def test_invalid_custom_surface_rejected(spec):
    opts=RenderOptions();opts.volume_surfaces=[spec]
    with pytest.raises(ValueError):volume_surface_specs(opts)


def test_surface_shading_and_empty_range():
    draw=MoleculeRenderer(vtkRenderer());opts=draw.options
    opts.volume_smooth_normals=False;opts.volume_signs='Positive';opts.volume_iso=.4
    draw._volume(Volume(np.indices((4,4,4))[0]/3,[0,0,0],np.eye(3)))
    assert draw.dynamic[0].GetProperty().GetInterpolation()==0
    opts.volume_surfaces=[dict(value=10,color='#FFFFFF',opacity=.5)]
    previous=len(draw.dynamic);draw._volume(Volume(np.zeros((3,3,3)),[0,0,0],np.eye(3)))
    assert len(draw.dynamic)==previous


def test_actual_egl_multisurface_render():
    scene=vtkRenderer();scene.SetBackground(1,1,1)
    draw=MoleculeRenderer(scene)
    x,y,z=np.meshgrid(*[np.linspace(-2,2,29)]*3,indexing='ij')
    data=np.exp(-(x*x+y*y+z*z))*x
    volume=Volume(data,[-2,-2,-2],np.eye(3)/7)
    draw.options.volume_surfaces=[dict(value=-.15,color='#0000FF',opacity=1.,style='Surface'),
        dict(value=.15,color='#FF0000',opacity=1.,style='Surface')]
    draw._volume(volume)
    window=vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(240,180)
    window.AddRenderer(scene);scene.ResetCamera();window.Render()
    capture=vtkWindowToImageFilter();capture.SetInput(window);capture.Update()
    pixels=vtk_to_numpy(capture.GetOutput().GetPointData().GetScalars())[:,:3]
    assert np.count_nonzero((pixels[:,0]>pixels[:,2]+20)&(pixels[:,0]>pixels[:,1]+20))>100
    assert np.count_nonzero((pixels[:,2]>pixels[:,0]+20)&(pixels[:,2]>pixels[:,1]+20))>100
    window.Finalize()
