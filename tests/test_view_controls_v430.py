import numpy as np
import pytest
from copy import copy
from PIL import Image
from PySide6.QtWidgets import QToolButton
from scipy.spatial.transform import Rotation
from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkRenderer

from lele.core import Frame
from lele.crystal_planes import default_plane
from lele.png_export import PngSettings, export_png
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from test_camera_views_v3100 import crystal
from test_field_mapping_v340 import analytic_pair, options, draw_pair
from test_periodic_fragment_ui_v171 import gui
from test_plane_fields_v370 import linear_volume
from test_dialog_policy_v3130 import app


def test_stacked_surface_bar_lengths_in_canvas_and_export(tmp_path):
    doc = analytic_pair()
    esp = copy(doc.volumes[1])
    esp.provenance = {'pair_role': 'ESP'}  # The filenames need not identify the field.
    doc.volumes.append(esp)
    opts = options()
    opts.volume_surfaces.append(dict(opts.volume_surfaces[0], map_dataset=2))
    draw, _ = draw_pair(doc, opts)
    scene = draw.renderer
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(800, 500)
    window.SetMultiSamples(0)
    window.AddRenderer(scene)
    scene.ResetCamera()
    try:
        window.Render()
        path = tmp_path / 'color-bars.png'
        export_png(path, window, PngSettings(800, 500, 1))
        with Image.open(path) as image:
            pixels = np.array(image.convert('RGB')).astype(int)
        lengths = []
        assert len(draw.field_scalar_bars) == 2
        for row, (bar, width) in enumerate(zip(draw.field_scalar_bars, (.76, .38))):
            assert bar.GetPosition() == pytest.approx(((1.-width)/2., .02 + row*.09))
            assert (bar.GetWidth(), bar.GetHeight()) == pytest.approx((width, .08))
            assert bar.GetNumberOfLabels() == 5
            assert bar.GetLookupTable().GetRange() == pytest.approx((-.6, .6))
            rect = [0, 0, 0, 0]
            bar.GetScalarBarRect(rect, scene)
            x, y, w, h = rect
            scan = pixels[499 - y - h//2]
            colored = np.flatnonzero(abs(scan[:, 0] - scan[:, 2]) > 100)
            assert colored[0] == pytest.approx(x, abs=2)
            assert colored[-1] == pytest.approx(x+w-1, abs=2)
            lengths.append(colored[-1] - colored[0] + 1)
        assert lengths[1] == pytest.approx(lengths[0]/2, abs=3)
    finally:
        window.Finalize()


@pytest.mark.parametrize('esp, width', [(False, .76), (True, .38)])
def test_plane_slice_uses_the_displayed_field_for_legend_size(esp, width):
    field = linear_volume()
    if esp:
        field.label, field.unit = 'Electrostatic potential', 'Hartree/e'
    cell = (np.array(field.data.shape) - 1)[:, None] * field.voxel_vectors
    frame = Frame(['H'], [field.origin + [.3, .3, .3] @ cell], cell, (True,)*3)
    draw = MoleculeRenderer(vtkRenderer())
    draw.options = RenderOptions(volume_signs='None', show_volume=False,
        lattice_planes=[dict(default_plane(), offset=.5)])
    draw.set_scene(frame, field)
    bar, = draw.plane_field_bars
    assert bar.GetWidth() == pytest.approx(width)
    assert bar.GetPosition() == pytest.approx(((1.-width)/2., .02))


def test_2d_slice_vertical_esp_bar_halves_length_and_preserves_thickness(app):
    from lele.field_slice_dialog import FieldSliceDialog

    volume = linear_volume()
    dialog = FieldSliceDialog(volume)
    dialog.figure.set_layout_engine('none')
    try:
        sizes = []
        for role in ('Density', 'ESP'):
            volume.provenance['pair_role'] = role
            dialog.redraw()
            dialog.canvas.draw()
            bounds = dialog.figure.axes[-1].get_window_extent()
            sizes.append([bounds.width, bounds.height])
        np.testing.assert_allclose(sizes[1], np.array(sizes[0])*[1., .5], atol=1.)
    finally:
        dialog.close()
        dialog.deleteLater()


def view_matrix(camera):
    matrix = camera.GetViewTransformMatrix()
    return np.array([[matrix.GetElement(i, j) for j in range(4)] for i in range(4)])


@pytest.mark.parametrize('parallel', [True, False])
def test_rotation_buttons_turn_about_panned_centroid(gui, parallel):
    frame = crystal()
    gui.attach(frame)
    w = gui.window
    controls = w.rotation_controls
    camera = w.scene.GetActiveCamera()
    camera.SetPosition(7., 2., 9.)
    camera.SetFocalPoint(1., -1., .4)
    camera.SetViewUp(-.1, 1., .2)
    camera.SetParallelProjection(parallel)
    camera.SetParallelScale(1.77)
    camera.SetViewAngle(42.)
    original = view_matrix(camera)
    center = frame.positions.mean(axis=0)
    positions, cell = frame.positions.copy(), frame.cell.copy()
    buttons = {b.text(): b for b in controls.findChildren(QToolButton)}
    for basis, axes in [('Screen', 'XYZ'), ('Cartesian', 'XYZ'), ('Lattice', 'abc')]:
        for i, axis in enumerate(axes):
            direction = {'Screen': original[:3, :3], 'Cartesian': np.eye(3), 'Lattice': cell}[basis][i]
            rot = Rotation.from_rotvec(np.pi/4 * direction / np.linalg.norm(direction)).as_matrix()
            transform = np.eye(4)
            transform[:3, :3] = rot
            transform[:3, 3] = center - rot @ center
            controls.axis.setCurrentText(f'{basis} {axis}')
            buttons['+45°'].click()
            np.testing.assert_allclose(view_matrix(camera), original @ transform, atol=1.e-11)
            assert controls.axis.currentText() == f'{basis} {axis}'
            buttons['−45°'].click()
            np.testing.assert_allclose(view_matrix(camera), original, atol=1.e-11)
    for _ in range(8):
        buttons['+45°'].click()
    np.testing.assert_allclose(view_matrix(camera), original, atol=1.e-11)
    assert camera.GetParallelProjection() == parallel
    assert (camera.GetParallelScale(), camera.GetViewAngle()) == pytest.approx((1.77, 42.))
    np.testing.assert_array_equal(frame.positions, positions)
    np.testing.assert_array_equal(frame.cell, cell)
    assert not w.doc.modified


def test_rotation_controls_track_current_structure(gui):
    gui.attach(crystal(), second_frame=Frame(['He'], [[0, 0, 0]]))
    w = gui.window
    controls = w.rotation_controls
    controls.axis.setCurrentText('Lattice b')
    lattice_b = controls.axis.model().item(controls.axis.currentIndex())
    assert lattice_b.isEnabled()
    w.change_frame(1)
    assert controls.isEnabled() and not lattice_b.isEnabled()
    assert controls.axis.currentText() == 'Screen X'
    assert not controls.axis.model().item(controls.axis.findText('Lattice b')).isEnabled()
    w.change_frame(0)
    assert lattice_b.isEnabled()
    w._unload_document(w.doc)
    assert not controls.isEnabled()


def test_partial_periodic_cell_and_aligned_lattice_steps(gui):
    from lele.trajectory_analysis import DisplayAlignment

    frame = crystal()
    frame.cell[2] = 0
    frame.pbc = (True, True, False)
    gui.attach(frame)
    w = gui.window
    controls = w.rotation_controls
    enabled = [axis for axis, index in controls.lattice_choices if controls.axis.model().item(index).isEnabled()]
    assert enabled == ['a', 'b']
    rotation = np.array([[0., 1, 0], [-1, 0, 0], [0, 0, 1]])
    reference = frame.clone()
    reference.positions = frame.positions @ rotation + [2., -1., .3]
    reference.cell = frame.cell @ rotation
    w._trajectory_alignments[id(w.doc)] = DisplayAlignment(reference, tuple(range(4)))
    w._aligned_documents.add(id(w.doc))
    w.refresh_scene()
    camera = w.scene.GetActiveCamera()
    before = view_matrix(camera)
    controls.axis.setCurrentText('Lattice b')
    next(b for b in controls.findChildren(QToolButton) if b.text() == '+45°').click()
    after = view_matrix(camera)
    center = reference.positions.mean(axis=0)
    axis = reference.cell[1]
    for point in (center, center + axis):
        np.testing.assert_allclose(after @ [*point, 1], before @ [*point, 1], atol=1.e-11)
    assert not np.allclose(after, before)
