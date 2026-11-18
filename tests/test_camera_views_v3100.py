"""Direct-lattice camera axes retain scientific coordinates and display rotation."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkRenderer

from lele.camera_views import (
    align_window_camera, axis_camera_basis, has_crystal_axes,
    orient_camera_to_axis, refresh_crystal_view_actions,
)
from lele.core import Document, Frame
from lele.trajectory_analysis import DisplayAlignment
from test_periodic_fragment_ui_v171 import gui


def crystal():
    return Frame(['C', 'N', 'O', 'H'],
        [[0, 0, 0], [1, .2, .1], [.2, 1.2, .3], [.3, .1, 1.4]],
        [[4, 0, 0], [1.3, 5, 0], [.8, 1.6, 6]], (True,) * 3)


@pytest.mark.parametrize('axis,index', [('a', 0), ('b', 1), ('c', 2)])
def test_oblique_views_follow_direct_vector_not_reciprocal_normal(axis, index):
    frame = crystal()
    original_cell = frame.cell.copy()
    direction, up = axis_camera_basis(axis, frame)
    expected = frame.cell[index] / np.linalg.norm(frame.cell[index])
    np.testing.assert_allclose(direction, expected, atol=1.e-14)
    reciprocal = np.linalg.inv(frame.cell).T[index]
    reciprocal /= np.linalg.norm(reciprocal)
    assert not np.allclose(direction, reciprocal)
    assert np.dot(direction, up) == pytest.approx(0., abs=1.e-14)
    assert np.linalg.norm(up) == pytest.approx(1.)
    right = np.cross(up, direction)
    assert np.linalg.det(np.array([right, up, direction])) == pytest.approx(1.)
    np.testing.assert_array_equal(frame.cell, original_cell)


def test_orthogonal_cell_matches_existing_xyz_roll_and_near_parallel_up_is_stable():
    frame = crystal()
    frame.cell = np.diag([4., 5., 6.])
    for abc, xyz in zip('abc', 'XYZ'):
        actual = axis_camera_basis(abc, frame)
        expected = axis_camera_basis(xyz)
        np.testing.assert_allclose(actual, expected)
    frame.cell = np.array([[1.e8, 0, 0], [0, 1.e8, 0], [1.e8, 0, .0001]])
    direction, up = axis_camera_basis('a', frame)
    np.testing.assert_allclose(direction, [1, 0, 0])
    np.testing.assert_allclose(up, [0, 1, 0])


def test_lattice_view_uses_row_vector_display_rotation_once():
    frame = crystal()
    rotation = np.array([[0., 1, 0], [-1, 0, 0], [0, 0, 1]])
    for index, axis in enumerate('abc'):
        direction, up = axis_camera_basis(axis, frame, display_rotation=rotation)
        expected = frame.cell[index] @ rotation
        np.testing.assert_allclose(direction, expected / np.linalg.norm(expected), atol=1.e-14)
        original_direction, original_up = axis_camera_basis(axis, frame)
        np.testing.assert_allclose(up, original_up @ rotation, atol=1.e-14)
    # Cartesian labels describe world axes, regardless of trajectory alignment.
    np.testing.assert_allclose(axis_camera_basis('X', frame, display_rotation=rotation)[0], [1, 0, 0])
    with pytest.raises(ValueError, match='rotation'):
        axis_camera_basis('a', frame, display_rotation=np.eye(3) * 2)


def test_cell_validation_disables_molecules_singular_cells_and_missing_frames():
    assert not has_crystal_axes(None)
    frame = crystal()
    frame.pbc = (False,) * 3
    assert not has_crystal_axes(frame)
    with pytest.raises(ValueError, match='periodic'):
        axis_camera_basis('a', frame)
    frame.pbc = (True, True, False)
    assert has_crystal_axes(frame)
    frame.cell[2] = frame.cell[1]
    assert not has_crystal_axes(frame)
    frame.cell[2, 0] = np.nan
    assert not has_crystal_axes(frame)


@pytest.mark.parametrize('parallel', [False, True])
def test_orientation_only_keeps_focal_distance_zoom_and_projection(parallel):
    frame = crystal()
    original = frame.clone()
    camera = vtkRenderer().GetActiveCamera()
    camera.SetFocalPoint(7., -3., 2.)
    camera.SetPosition(12., -1., 4.)
    camera.SetParallelProjection(parallel)
    camera.SetParallelScale(4.56)
    camera.SetViewAngle(29.)
    focal, distance = camera.GetFocalPoint(), camera.GetDistance()
    orient_camera_to_axis(camera, 'b', frame)
    np.testing.assert_allclose(camera.GetFocalPoint(), focal)
    assert camera.GetDistance() == pytest.approx(distance)
    assert camera.GetParallelProjection() == parallel
    assert camera.GetParallelScale() == pytest.approx(4.56)
    assert camera.GetViewAngle() == pytest.approx(29.)
    np.testing.assert_array_equal(frame.positions, original.positions)
    np.testing.assert_array_equal(frame.cell, original.cell)


def test_gui_adapter_fit_uses_displayed_scene_bounds_and_does_not_modify_document():
    frame = crystal()
    original = frame.clone()
    scene = vtkRenderer()
    source = vtkSphereSource()
    source.SetCenter(10., -2., 1.)
    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(source.GetOutputPort())
    actor = vtkActor()
    actor.SetMapper(mapper)
    scene.AddActor(actor)
    rotation = np.array([[0., 1, 0], [-1, 0, 0], [0, 0, 1]])
    checked, renders = [], []
    window = SimpleNamespace(frame=frame, scene=scene,
        renderer=SimpleNamespace(display_rotation=rotation), doc=SimpleNamespace(modified=False),
        projection_actions={'Orthographic': SimpleNamespace(setChecked=lambda value: checked.append(value))},
        vtk=SimpleNamespace(GetRenderWindow=lambda: SimpleNamespace(Render=lambda: renders.append(1))))
    assert align_window_camera(window, 'b', fit=True)
    camera = scene.GetActiveCamera()
    expected = frame.cell[1] @ rotation
    np.testing.assert_allclose(-np.asarray(camera.GetDirectionOfProjection()), expected / np.linalg.norm(expected))
    np.testing.assert_allclose(camera.GetFocalPoint(), [10., -2., 1.])
    assert camera.GetParallelProjection() and checked == [True] and renders == [1]
    assert not window.doc.modified
    np.testing.assert_array_equal(frame.positions, original.positions)
    np.testing.assert_array_equal(frame.cell, original.cell)


def test_action_enable_refresh_tracks_valid_frame_not_stale_renderer():
    class Action:
        def setEnabled(self, value): self.enabled = value
    window = SimpleNamespace(frame=crystal(), axis_actions={axis: Action() for axis in 'abc'})
    assert refresh_crystal_view_actions(window)
    assert all(action.enabled for action in window.axis_actions.values())
    window.frame = Frame(['H'], [[0, 0, 0]])
    assert not refresh_crystal_view_actions(window)
    assert not any(action.enabled for action in window.axis_actions.values())
    window.frame = None
    assert not refresh_crystal_view_actions(window)


def test_menu_actions_track_frame_and_document_changes_and_keep_geometry(gui):
    first = crystal()
    molecule = Frame(['He'], [[0., 0., 0.]])
    gui.attach(first, second_frame=molecule)
    window = gui.window
    original = first.clone()
    assert all(window.axis_actions[axis].isEnabled() for axis in 'abc')
    for index, axis in enumerate('abc'):
        window.axis_actions[axis].trigger()
        direction = -np.asarray(window.scene.GetActiveCamera().GetDirectionOfProjection())
        np.testing.assert_allclose(direction, first.cell[index] / np.linalg.norm(first.cell[index]), atol=1.e-12)
        assert window.scene.GetActiveCamera().GetParallelProjection()
        assert window.projection_actions['Orthographic'].isChecked()
    assert not window.doc.modified
    np.testing.assert_array_equal(first.positions, original.positions)
    np.testing.assert_array_equal(first.cell, original.cell)
    window.change_frame(1)
    assert not any(window.axis_actions[axis].isEnabled() for axis in 'abc')
    window.change_frame(0)
    assert all(window.axis_actions[axis].isEnabled() for axis in 'abc')
    window._attach_loaded_document(Document(Path('molecule.xyz'), 'XYZ', [molecule.clone()]))
    assert not any(window.axis_actions[axis].isEnabled() for axis in 'abc')
    window.change_frame(0, switch_doc=0)
    assert all(window.axis_actions[axis].isEnabled() for axis in 'abc')
    from lele.nmr import NMRNucleus, NMRResult
    result = NMRResult('CP2K', 'SHIFT', 1, [NMRNucleus(1, 'C', 50.)])
    window._attach_loaded_document(Document(Path('results.out'), 'Results only', [], nmr_results=[result]))
    assert not any(window.axis_actions[axis].isEnabled() for axis in 'abc')


def test_menu_uses_actual_render_alignment_rotation_not_unrotated_source_cell(gui):
    frame = crystal()
    gui.attach(frame)
    window = gui.window
    rotation = np.array([[0., 1, 0], [-1, 0, 0], [0, 0, 1]])
    reference = frame.clone()
    reference.positions = frame.positions @ rotation + [3., -2., 1.]
    reference.cell = frame.cell @ rotation
    window._trajectory_alignments[id(window.doc)] = DisplayAlignment(reference, tuple(range(4)))
    window._aligned_documents.add(id(window.doc))
    window.refresh_scene()
    np.testing.assert_allclose(window.renderer.display_rotation, rotation, atol=1.e-12)
    before = frame.clone()
    window.axis_actions['b'].trigger()
    direction = -np.asarray(window.scene.GetActiveCamera().GetDirectionOfProjection())
    expected = frame.cell[1] @ window.renderer.display_rotation
    np.testing.assert_allclose(direction, expected / np.linalg.norm(expected), atol=1.e-12)
    np.testing.assert_array_equal(frame.positions, before.positions)
    np.testing.assert_array_equal(frame.cell, before.cell)
