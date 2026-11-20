from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtWidgets import QComboBox, QDialog
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.boundary_selection import AtomImage
from lele.core import Frame
from lele.fragment import mirrored_coordinate, rotation_about_axis
from lele.interaction import roll_camera
from lele.project_file import load_project, save_project
from lele.style_presets import snapshot, validate_preset
from test_periodic_fragment_ui_v171 import gui


def test_mirror_menu_flips_handedness_in_place_and_undoes(gui):
    w = gui.window
    frame = Frame(['C', 'H', 'F', 'Cl', 'Ni'],
                  [[3, 1, 0], [4, 1, 0], [3, 2, 0], [3, 1, 1], [8, 1, 0]],
                  np.diag([12., 12., 12.]), (True,)*3)
    gui.attach(frame)
    gui.select([0, 1, 2, 3])
    before = frame.positions.copy()
    assert w.mirror_action.isEnabled()
    with patch('lele.app.QDialog.exec', return_value=QDialog.DialogCode.Accepted):
        w.mirror_action.trigger()
    after = frame.positions
    np.testing.assert_array_equal(after[:4, 0], 2 * before[:4, 0].mean() - before[:4, 0])
    np.testing.assert_array_equal(after[:, 1:], before[:, 1:])
    np.testing.assert_array_equal(after[-1], before[-1])
    assert np.linalg.det(after[1:4] - after[0]) == -np.linalg.det(before[1:4] - before[0])
    np.testing.assert_array_equal(frame.cell, np.diag([12.]*3))
    assert len(w.undo_stack) == 1 and w.selection == [0, 1, 2, 3]
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions, before)
    with patch('lele.app.QDialog.exec', return_value=QDialog.DialogCode.Rejected):
        w.mirror_btn.click()
    assert not w.undo_stack


@pytest.mark.parametrize('axis', range(3))
def test_mirror_about_cartesian_origin(gui, axis):
    w = gui.window
    frame = Frame(['C', 'H', 'O'], [[2., 3., 4.], [3., 3., 4.], [5., 6., 7.]])
    gui.attach(frame)
    gui.select([0, 2])
    expected = frame.positions.copy()
    expected[[0, 2], axis] *= -1

    def choose(dialog):
        plane, center = dialog.findChildren(QComboBox)
        plane.setCurrentIndex(axis)
        center.setCurrentIndex(1)
        return QDialog.DialogCode.Accepted

    with patch('lele.app.QDialog.exec', choose):
        w.mirror_btn.click()
    np.testing.assert_array_equal(frame.positions, expected)


def test_mirror_uses_picked_images_across_periodic_face():
    frame = Frame(['O', 'H'], [[9.8, 0, 0], [.2, 0, 0]], np.eye(3)*10, (True,)*3)
    indices, result = mirrored_coordinate(frame, [AtomImage(0), AtomImage(1, (1, 0, 0))])
    assert indices == [0, 1]
    np.testing.assert_allclose(result, [10.2, -.2])
    with pytest.raises(ValueError, match='periodic image'):
        mirrored_coordinate(frame, [AtomImage(0), AtomImage(0, (1, 0, 0))])


def projected(scene, point):
    scene.SetWorldPoint(*point, 1.)
    scene.WorldToDisplay()
    return np.array(scene.GetDisplayPoint())


@pytest.mark.parametrize('parallel', [True, False])
def test_whole_roll_preserves_projected_centroid_after_pan(gui, parallel):
    w = gui.window
    frame = Frame(['Fe', 'H', 'H', 'C'], [[1, 0, 0], [1, 2, 0], [1, 0, 1], [6, 1, 0]],
                  np.eye(3)*9, (True,)*3)
    gui.attach(frame)
    w.render_options.boundary_bounds = ((0, 3), (0, 1), (0, 1))
    gui.select([3])
    center = frame.positions.mean(axis=0)
    np.testing.assert_allclose(w.vtk.rotation_center(), center)
    assert len(w.renderer.boundary_display.source_indices) > len(frame.symbols)
    scene = w.scene
    w.vtk.GetRenderWindow().SetSize(800, 600)
    camera = scene.GetActiveCamera()
    camera.SetPosition(5, 3, 16)
    camera.SetFocalPoint(-1, 1, 0)
    camera.SetViewUp(0, 1, 0)
    camera.OrthogonalizeViewUp()
    camera.SetParallelProjection(parallel)
    camera.SetParallelScale(8.)
    scene.ResetCameraClippingRange()
    before = frame.positions.copy()
    distance, angle = camera.GetDistance(), camera.GetViewAngle()
    centroid_pixel = projected(scene, center)
    assert np.linalg.norm(centroid_pixel[:2] - [400, 300]) > 30
    # A camera roll must produce the same image as a rigid model roll about the centroid.
    rotated = rotation_about_axis(camera.GetDirectionOfProjection(), 39.)
    expected = [projected(scene, center + rotated @ (p - center)) for p in before]
    for dx in [20., 40.]:
        roll_camera(camera, w.vtk.rotation_center(), dx)
    np.testing.assert_allclose(projected(scene, center), centroid_pixel, atol=1e-8)
    np.testing.assert_allclose([projected(scene, p) for p in before], expected, atol=1e-8)
    np.testing.assert_array_equal(frame.positions, before)
    assert camera.GetDistance() == pytest.approx(distance)
    assert camera.GetParallelScale() == 8. and camera.GetViewAngle() == angle


def test_fragment_roll_uses_only_moving_atom_centroid_from_any_press(gui):
    w = gui.window
    frame = Frame(['O', 'H', 'H', 'Ni'], [[2, 0, 0], [2.95, 0, 0], [1.8, .9, 0], [8, 0, 0]])
    gui.attach(frame)
    before = frame.positions.copy()
    center = before[:3].mean(axis=0)
    outputs = []
    for press in [(5., 15.), (280., 180.)]:
        gui.select([0])
        w._fragment_begin('roll', *press)
        np.testing.assert_allclose(w._fragment_gesture['pivot'], center)
        w._fragment_move('roll', 45., 0.)
        w._fragment_end('roll')
        outputs.append(w.frame.positions.copy())
        np.testing.assert_allclose(w.frame.positions[:3].mean(axis=0), center, atol=1e-12)
        np.testing.assert_array_equal(w.frame.positions[-1], before[-1])
        w.undo_edit()
    np.testing.assert_allclose(outputs[0], outputs[1])
    assert not np.allclose(outputs[0][:3], before[:3])


def test_highlight_slider_updates_materials_in_place_and_survives_projects(gui, tmp_path):
    w = gui.window
    gui.attach(Frame(['C', 'O'], [[0, 0, 0], [1.25, 0, 0]]))
    props = tuple(w.renderer._finished_properties)
    assert props and all(prop.GetSpecularPower() == 60 for prop in props)
    intensity = [light.GetIntensity() for light in w.renderer._lights]
    with patch.object(w.renderer, 'set_scene', side_effect=AssertionError('rebuilt geometry')):
        for size, power in [(100, 1.), (0, 128.), (50, 60.)]:
            w.highlight_slider.setValue(size)
            assert all(prop.GetSpecularPower() == pytest.approx(power) for prop in props)
            assert all(prop.GetSpecular() == pytest.approx(.78) for prop in props)
        w.finish_combo.setCurrentText('Matte')
        assert all(prop.GetSpecularPower() == 9 for prop in props)
        w.highlight_slider.setValue(77)
    assert intensity == [light.GetIntensity() for light in w.renderer._lights]
    old_preset = snapshot(w.render_options)
    old_preset.pop('highlight_size')
    assert validate_preset(old_preset)['highlight_size'] == 50.
    path = tmp_path / 'highlight.lele'
    save_project(path, dict(documents=[dict(document=w.doc, options=w.render_options)], current_document=0))
    assert load_project(path)['documents'][0]['options'].highlight_size == 77
    from lele.atom_legend import AtomLegend, legend_samples
    legend = AtomLegend(vtkRenderer())
    legend.set_samples(legend_samples(w.renderer), w.render_options)
    assert legend.actors[0].GetProperty().GetSpecularPower() == props[0].GetSpecularPower()
