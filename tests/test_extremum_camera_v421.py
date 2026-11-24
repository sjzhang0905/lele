"""The anchor is in world space and the numeric glyphs are in the camera plane."""
from copy import deepcopy

import numpy as np
import pytest
import vtkmodules.vtkRenderingOpenGL2  # Register the render-window implementation for isolated tests.
from PIL import Image, ImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkCamera, vtkRenderer, vtkRenderWindow

from lele.annotations import AnnotationRenderer, EspExtremum, TextAnnotation
from lele.png_export import PngSettings, export_png
from test_periodic_fragment_ui_v171 import gui


def display_points(scene, points):
    projected = []
    for point in points:
        scene.SetWorldPoint(*point, 1.)
        scene.WorldToDisplay()
        projected.append(scene.GetDisplayPoint())
    return np.array(projected)


@pytest.mark.parametrize('parallel', [False, True])
def test_projected_anchor_upright_glyphs_outline_pick_and_camera_replacement(parallel):
    scene = vtkRenderer()
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(400,300)
    window.AddRenderer(scene)
    manager = AnnotationRenderer(scene)
    # 4.2.0 projects contain an orientation in addition to the original-file coordinates.
    rot = np.array([[0.,1,0],[-1,0,0],[0,0,1]])
    shift = np.array([.1,-.4,.2])
    value = EspExtremum('', [.9,.2,.1], rot.tolist(), height=.29, point=[.5,.1,.1], value=-18.69)
    caption = TextAnnotation('Caption', [-1,.8,0], rot.tolist(), height=.2)
    snapshot = deepcopy([value,caption])
    previous = None
    try:
        manager.set_annotations([value,caption], selected=0, extremum_transform=(rot,shift))
        mapper = manager.markers.GetMapper()
        np.testing.assert_allclose(vtk_to_numpy(mapper.GetInput().GetPoints().GetData()), [value.point @ rot + shift])
        mapper.GetInputConnection(1, 0).GetProducer().Update()
        assert mapper.GetSource(0).GetBounds()[5] == pytest.approx(.08, abs=1e-6)
        np.testing.assert_allclose(manager.markers.GetProperty().GetDiffuseColor(), np.array([212,175,55])/255)
        assert manager.markers.GetProperty().GetSpecular() > .1
        caption_initial = manager.corners(1).copy()
        for azimuth, elevation, roll in [(0,0,0),(89,15,70),(140,-35,157)]:
            camera = vtkCamera()
            camera.SetPosition(0,0,8)
            camera.SetFocalPoint(0,0,0)
            camera.SetViewUp(0,1,0)
            camera.SetParallelProjection(parallel)
            camera.SetParallelScale(2.2)
            camera.Azimuth(azimuth)
            camera.Elevation(elevation)
            camera.Roll(roll)
            camera.SetClippingRange(.1,100.)
            scene.SetActiveCamera(camera)
            window.Render()
            corners = manager.corners(0)
            screen = display_points(scene, corners)
            right, up = screen[1]-screen[0], screen[3]-screen[0]
            assert right[0] > 10 and up[1] > 5
            assert right[1] == pytest.approx(0., abs=1e-7)
            assert up[0] == pytest.approx(0., abs=1e-7)
            center = screen.mean(axis=0)
            assert manager.pick(*center[:2]) == 0
            if previous is not None:
                assert np.linalg.norm(center[:2]-previous[:2]) > 12
            previous = center
            anchor = value.position @ rot + shift
            np.testing.assert_allclose([manager.actors[0].GetMatrix().GetElement(i,3) for i in range(3)],anchor)
            outline = vtk_to_numpy(manager.outline.GetMapper().GetInput().GetPoints().GetData())
            np.testing.assert_allclose(outline, corners, atol=1e-6)
            np.testing.assert_array_equal(manager.corners(1), caption_initial)
        assert [value,caption] == snapshot
        manager.set_annotations([caption])
        assert manager._camera_observer is None
    finally:
        manager.clear()
        window.Finalize()


def test_tiled_png_keeps_same_readable_glyph_shape_after_roll(tmp_path):
    scene = vtkRenderer()
    scene.SetBackground(1,1,1)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetMultiSamples(0)
    window.SetSize(380,280)
    window.AddRenderer(scene)
    manager = AnnotationRenderer(scene)
    item = EspExtremum('', [.7,.4,0], height=.36, color='#AA0080', point=[.3,.1,0], value=-26.8)
    manager.set_annotations([item])
    camera = scene.GetActiveCamera()
    camera.SetPosition(0,0,8)
    camera.SetFocalPoint(0,0,0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(2.)
    bounds = []
    masks = []
    try:
        for index, (azimuth, roll) in enumerate([(0,0),(65,73)]):
            camera.Azimuth(azimuth)
            camera.Roll(roll)
            scene.ResetCameraClippingRange()
            # Export directly after moving the camera, before another interactive draw.
            path = tmp_path/f'view{index}.png'
            export_png(path,window,PngSettings(760,560,2))
            rgb = np.asarray(Image.open(path).convert('RGB')).astype(int)
            mask = (rgb[:,:,0]-rgb[:,:,1]>65) & (rgb[:,:,2]-rgb[:,:,1]>45)
            yy, xx = np.where(mask)
            bounds.append((xx.min(),yy.min(),xx.max(),yy.max()))
            masks.append(mask[yy.min():yy.max()+1, xx.min():xx.max()+1])
            assert manager.actors[0].GetTextProperty().GetFontSize() == 128
        a,b = np.array(bounds)
        assert np.linalg.norm(a[:2]-b[:2]) > 20
        np.testing.assert_allclose(a[2:]-a[:2], b[2:]-b[:2], atol=2)
        # The two projected anchors can land on different subpixels. Match each
        # stroke to ink within one output pixel at the native PNG resolution.
        height, width = np.max([mask.shape for mask in masks], axis=0) + 2
        aligned = [np.pad(mask, ((1, height - mask.shape[0] - 1),
                                 (1, width - mask.shape[1] - 1))) for mask in masks]
        for source, target in (aligned, aligned[::-1]):
            expanded = np.asarray(Image.fromarray(target.astype('uint8')).filter(ImageFilter.MaxFilter(3)))
            assert expanded[source].mean() > .99
    finally:
        manager.clear()
        window.Finalize()


def test_drag_label_after_roll_and_ignore_tilt_and_roll_gestures(gui):
    w=gui.window
    label=EspExtremum('', [.9,.2,.1], height=.3, point=[.5,.1,.1], value=14.81)
    w._append_annotation(label)
    camera = w.scene.GetActiveCamera()
    camera.Azimuth(75)
    camera.Roll(52)
    w.scene.InvokeEvent('StartEvent')
    before = deepcopy(label)
    count = len(w.undo_stack)
    for kind in ('orbit','roll'):
        w._fragment_begin(kind,10,20)
        w._fragment_move(kind,25,15)
        w._fragment_end(kind)
    assert label == before and len(w.undo_stack) == count
    w._fragment_begin('pan',10,20)
    w._fragment_move('pan',25,15)
    w._fragment_end('pan')
    assert label.position != before.position and label.point == before.point
    w.undo_edit()
    assert w.doc.annotations[0] == before
