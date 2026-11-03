"""Corner-axis extents, readable glyph margins, and isolated PNG overlays."""
import numpy as np
import pytest
from PIL import Image

from lele.animation_export import _OffscreenScene, GifSettings
from lele.core import Frame
from lele.png_export import PngSettings, export_png, frozen_overlays
from lele.render_options import RenderOptions
from lele.renderer import set_isometric_view


@pytest.fixture
def corner_scene(request):
    basis, font = getattr(request, 'param', ('XYZ', 15))
    scene = _OffscreenScene(GifSettings(width=480,height=320,supersample=1),
                            RenderOptions(axes_basis=basis,label_font_size=font),None,(),(480,320))
    frame=Frame(['C'],[[0,0,0]],[[5,0,0],[1,5,0],[.5,.5,6]],(True,)*3)
    image=scene.render(frame,None);image.close();set_isometric_view(scene.scene);scene.window.Render()
    try:yield scene
    finally:scene.close()


def capture(window):
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    window.Render();shot=vtkWindowToImageFilter();shot.SetInput(window)
    shot.ReadFrontBufferOff();shot.ShouldRerenderOff();shot.Update()
    width,height,_=shot.GetOutput().GetDimensions()
    return vtk_to_numpy(shot.GetOutput().GetPointData().GetScalars()).reshape(height,width,3)[::-1].copy()


def extent(rgb):
    height,width,_=rgb.shape;corner=rgb[round(height*.75):,:round(width*.24)].astype(int)
    yy,xx=np.nonzero(corner.max(2)-corner.min(2)>45)
    assert len(xx)>0
    return np.array([np.ptp(xx)+1,np.ptp(yy)+1])


@pytest.mark.parametrize('corner_scene',[('XYZ',15),('abc',15)],indirect=True)
@pytest.mark.parametrize('factor',[1,2,3,4])
@pytest.mark.parametrize('smooth',[False,True])
def test_png_preserves_corner_extent_and_original_pixels(corner_scene,factor,smooth,tmp_path):
    scene=corner_scene;before=capture(scene.window);old=extent(before)
    width,height=scene.window.GetSize();path=tmp_path/'axes.png'
    export_png(path,scene.window,PngSettings(width*factor,height*factor,2 if smooth else 1),
               mesh_items=scene.draw._keepalive)
    with Image.open(path) as image:
        assert image.size==(width*factor,height*factor)
        reduced=np.asarray(image.resize((width,height),Image.Resampling.LANCZOS))
    ratios=extent(reduced)/old
    assert np.all((ratios>=.85)&(ratios<=1.15)),(old,extent(reduced))
    np.testing.assert_array_equal(capture(scene.window),before)
    assert all(np.isfinite(label.GetAnchorDC()).all() for label in scene.draw.corner_labels)


@pytest.mark.parametrize('corner_scene',[(basis,font) for basis in ('XYZ','abc')
                                      for font in (8,15,32,72)],indirect=True)
def test_full_letter_bounds_fit_after_rotation_font_and_resize(corner_scene):
    from vtkmodules.vtkRenderingCore import vtkTextRenderer
    scene=corner_scene;camera=scene.scene.GetActiveCamera()
    for azimuth,roll,size in [(0,0,(480,320)),(35,25,(480,320)),(70,70,(640,360)),(120,160,(400,280))]:
        camera.Azimuth(azimuth);camera.Roll(roll);scene.window.SetSize(*size);scene.window.Render()
        renderer=scene.marker.GetRenderer();left,bottom,right,top=renderer.GetViewport()
        for label in scene.draw.corner_labels:
            bbox=[0,0,0,0]
            assert vtkTextRenderer.GetInstance().GetBoundingBox(label.GetTextProperty(),label.GetInput(),bbox,scene.window.GetDPI())
            x,y,_=label.GetAnchorDC()
            assert np.isfinite([x,y]).all()
            assert x+bbox[0]>=left*size[0]+1 and x+bbox[1]<=right*size[0]-1
            assert y+bbox[2]>=bottom*size[1]+1 and y+bbox[3]<=top*size[1]-1


def test_overlay_snapshot_owns_text_and_restores_on_error(corner_scene):
    scene=corner_scene;window=scene.window;renderer=scene.marker.GetRenderer()
    count=window.GetRenderers().GetNumberOfItems();viewport=renderer.GetViewport()
    original=[(label.GetInput(),label.GetTextProperty().GetFontSize()) for label in scene.draw.corner_labels]
    before=capture(window)
    with pytest.raises(RuntimeError,match='forced'):
        with frozen_overlays(window):
            assert not renderer.GetDraw() and renderer.GetRenderWindow() is window
            assert window.GetRenderers().GetNumberOfItems()==count+1
            copied=next(r for r in window.GetRenderers() if r is not renderer and r.GetLayer()>0)
            labels=[p for p in copied.GetViewProps() if p.IsA('vtkBillboardTextActor3D')]
            assert len(labels)==3 and not any(p is q for p in labels for q in scene.draw.corner_labels)
            labels[0].SetInput('changed');labels[0].GetTextProperty().SetFontSize(60)
            assert original==[(label.GetInput(),label.GetTextProperty().GetFontSize()) for label in scene.draw.corner_labels]
            raise RuntimeError('forced')
    assert renderer.GetDraw() and renderer.GetViewport()==viewport
    assert window.GetRenderers().GetNumberOfItems()==count
    np.testing.assert_array_equal(capture(window),before)
