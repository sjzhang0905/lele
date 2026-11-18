"""World-space text follows the camera, edits independently, and survives .lele."""
from copy import deepcopy
from pathlib import Path
import numpy as np
import pytest
from lele.annotations import TextAnnotation, AnnotationRenderer, transform_annotation
from lele.core import Document, Frame
from lele.fragment import rotation_about_axis


def test_annotation_transform_rotates_about_anchor_without_touching_position():
    text = TextAnnotation('Cu–O', [1., 2., 3.])
    transform_annotation(text, translation=[2., -1., 4.])
    transform_annotation(text, rotation=rotation_about_axis([0, 0, 1], 90))
    np.testing.assert_allclose(text.position, [3, 1, 7])
    np.testing.assert_allclose(np.array(text.rotation) @ [1, 0, 0], [0, 1, 0], atol=1e-15)
    text.__post_init__()


@pytest.mark.parametrize('values', [dict(text=' '),dict(text='ok',position=[0,0,float('nan')]),
    dict(text='ok',rotation=np.diag([1,1,-1])),dict(text='ok',height=0),dict(text='ok',color='bad')])
def test_annotation_rejects_invalid_geometry_and_content(values):
    with pytest.raises(ValueError):TextAnnotation(**values)


def test_annotation_actors_are_world_space_pickable_and_transform_live():
    from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
    scene = vtkRenderer();window = vtkRenderWindow();window.SetSize(600,400);window.AddRenderer(scene)
    camera=scene.GetActiveCamera();camera.SetPosition(0,0,10);camera.SetFocalPoint(0,0,0)
    camera.SetViewUp(0,1,0);camera.ParallelProjectionOn();camera.SetParallelScale(2);camera.SetClippingRange(.1,100)
    text = TextAnnotation('Structure A',height=.5)
    manager=AnnotationRenderer(scene);manager.set_annotations([text],0)
    assert len(manager.actors)==1 and manager.outline is not None
    center=manager.corners(0).mean(axis=0)
    scene.SetWorldPoint(*center,1);scene.WorldToDisplay();x,y,_=scene.GetDisplayPoint()
    assert manager.pick(x,y)==0
    assert manager.pick(-500,-500) is None
    old=manager.corners(0).copy()
    transform_annotation(text,translation=[1,2,0]);manager.update_transform(0)
    np.testing.assert_allclose(manager.corners(0),old+[1,2,0])
    actor=manager.actors[0]
    # A camera move does not billboard or otherwise mutate annotation geometry.
    camera.Azimuth(45)
    np.testing.assert_allclose([actor.GetUserMatrix().GetElement(i,3) for i in range(3)],[1,2,0])
    manager.clear();assert scene.GetViewProps().GetNumberOfItems()==0
    window.Finalize()


def test_annotation_project_roundtrip(tmp_path):
    from lele.project_file import save_project,load_project
    from lele.render_options import RenderOptions
    frame=Frame(['C'],[[0,0,0]])
    doc=Document(Path('example.xyz'),'XYZ',[frame],annotations=[TextAnnotation('Bridge\nsite',[1,2,3],height=.8,color='#123456')])
    state={'documents':[{'document':doc,'options':RenderOptions(),'frame_index':0}], 'current_document':0}
    path=tmp_path/'text.lele';save_project(path,state)
    restored=load_project(path)['documents'][0]['document']
    assert restored.annotations==doc.annotations
    restored.annotations[0].position[0]=9
    assert doc.annotations[0].position[0]==1
