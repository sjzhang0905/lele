"""Restored views must redraw immediately, without a corrective mouse gesture."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from lele.core import Document, Frame
from lele.document_view import DocumentViewActions
from lele.interaction import InteractiveVTKView
from test_periodic_fragment_ui_v171 import gui


def pixels(window):
    """Read the framebuffer without WindowToImageFilter invalidating caches."""
    from vtkmodules.vtkCommonCore import vtkUnsignedCharArray
    from vtkmodules.util.numpy_support import vtk_to_numpy
    width, height = window.GetSize()
    data = vtkUnsignedCharArray()
    assert window.GetRGBACharPixelData(0, 0, width - 1, height - 1, 0, data)
    return vtk_to_numpy(data).copy()


def sample_frame():
    return Frame(['O', 'C', 'N', 'H'],
                 [[0, 0, 0], [1.5, 0, 0], [1.5, 1.4, 0], [-.5, -.8, .5]])


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(['CameraRestoreTests'])
    yield app
    app.processEvents()


def set_view(camera, parallel):
    camera.SetParallelProjection(parallel)
    camera.SetPosition(4, 5, 8)
    camera.SetFocalPoint(.6, .5, 0)
    camera.SetViewUp(0, 1, 0)
    camera.SetParallelScale(2.5)
    camera.SetViewAngle(32)
    camera.SetWindowCenter(.04, -.06)
    camera.SetClippingRange(.1, 100.)


@pytest.mark.parametrize('saved_parallel,other_parallel', [(True, True), (True, False),
                                                          (False, True), (False, False)])
def test_restored_camera_redraws_saved_pixels_before_any_mouse_move(saved_parallel, other_parallel):
    import vtkmodules.vtkRenderingOpenGL2
    from vtkmodules.vtkRenderingCore import vtkCamera, vtkRenderer, vtkRenderWindow
    from lele.renderer import MoleculeRenderer
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(480, 360)
    window.SetMultiSamples(0)
    scene = vtkRenderer()
    window.AddRenderer(scene)
    draw = MoleculeRenderer(scene)
    try:
        draw.set_scene(sample_frame(), reset_camera=True)
        camera = scene.GetActiveCamera()
        set_view(camera, saved_parallel)
        window.Render()
        expected = pixels(window)
        saved = vtkCamera()
        saved.DeepCopy(camera)
        camera.Azimuth(95)
        camera.Elevation(28)
        camera.SetParallelProjection(other_parallel)
        window.Render()
        previous = pixels(window)
        assert np.count_nonzero(expected != previous) > 1000
        stamp = camera.GetMTime()
        host = SimpleNamespace(scene=scene, _pending_view_camera=saved,
                               _view_fit_pending=False, doc=object(),
                               projection_actions={'Orthographic': Mock(), 'Perspective': Mock()})
        DocumentViewActions._apply_document_camera(host, False)
        assert scene.GetActiveCamera() is camera
        assert camera.GetMTime() > stamp
        window.Render()
        np.testing.assert_array_equal(pixels(window), expected)
        assert host._pending_view_camera is None
        # An unrelated subsequent paint must not change the restored view.
        window.Render()
        np.testing.assert_array_equal(pixels(window), expected)
    finally:
        window.Finalize()


def test_document_switch_after_intermediate_paint_keeps_first_render_and_gesture(gui):
    from vtkmodules.vtkRenderingCore import vtkRenderWindow
    w = gui.window
    frame = sample_frame()
    docs = [Document(Path(gui.temp.name) / name, 'XYZ', [frame.clone()]) for name in ('a.xyz', 'b.xyz')]
    w.documents = docs
    w.files_tree.clear()
    for i, doc in enumerate(docs):
        w._add_document_tree(i, doc)
    canvas = w.vtk
    window = canvas.GetRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(480, 360)
    window.SetMultiSamples(0)
    window.Render = lambda: vtkRenderWindow.Render(window)
    canvas._left_start = canvas._right_last = canvas._right_start = None
    canvas._right_dragged = False
    canvas._fragment_mode = None
    canvas.cancel_interaction = lambda: InteractiveVTKView.cancel_interaction(canvas)
    w.change_frame(0, switch_doc=0, reset_camera=True)
    camera = w.scene.GetActiveCamera()
    set_view(camera, True)
    window.Render()
    expected = pixels(window)
    w.change_frame(0, switch_doc=1)
    camera.Azimuth(95)
    camera.Elevation(28)
    window.Render()
    before = pixels(window)
    assert np.count_nonzero(expected != before) > 1000
    # A long scene build can process a Qt paint before restoring the camera.
    # Warm the cache at precisely this point, which used to cause the jump.
    set_scene = w.renderer.set_scene
    def build_and_paint(*args, **kwargs):
        set_scene(*args, **kwargs)
        window.Render()
    w.renderer.set_scene = build_and_paint
    style = window.GetInteractor().GetInteractorStyle()
    style.SetCurrentRenderer(w.scene)
    style.StartRotate()  # An outgoing drag whose release was lost.
    assert style.GetState() != 0
    try:
        w.change_frame(0, switch_doc=0)
        assert style.GetState() == 0
        np.testing.assert_array_equal(pixels(window), expected)
        position = camera.GetPosition()
        interactor = window.GetInteractor()
        interactor.SetEventInformation(300, 200)
        interactor.MouseMoveEvent()  # First move after switching, no press.
        assert camera.GetPosition() == position
        window.Render()
        np.testing.assert_array_equal(pixels(window), expected)
    finally:
        w.renderer.set_scene = set_scene
        window.Render = lambda: None
        window.Finalize()


def test_native_focus_loss_ends_trackball_before_next_pointer_move(qapp):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QFocusEvent, QMouseEvent
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
    from vtkmodules.vtkRenderingCore import vtkRenderer
    view = InteractiveVTKView()
    view.resize(600, 400)
    window = view.GetRenderWindow()
    window.SetOffScreenRendering(True)
    scene = vtkRenderer()
    window.AddRenderer(scene)
    view.scene_renderer = scene
    style = vtkInteractorStyleTrackballCamera()
    window.GetInteractor().SetInteractorStyle(style)
    view.Initialize()
    camera = scene.GetActiveCamera()
    camera.SetPosition(5, 5, 10)
    camera.SetFocalPoint(0, 0, 0)
    try:
        view.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(300, 200),
            QPointF(300, 200), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        assert style.GetState() != 0
        view.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        assert style.GetState() == 0 and view._ActiveButton == Qt.MouseButton.NoButton
        before = camera.GetPosition()
        view.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, QPointF(350, 220),
            QPointF(350, 220), Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))
        assert camera.GetPosition() == before
    finally:
        view.TerminateApp()
        view.Finalize()
        view.deleteLater()
