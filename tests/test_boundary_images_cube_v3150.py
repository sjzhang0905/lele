"""Periodic picks retain image coordinates; molecular CUBE boxes stay finite."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lele.boundary_selection import AtomImage, image_measurement, selected_images, toggle_atom_image
from lele.core import Frame, Document, Volume
from lele.cube_input import read_cube_file
from lele.formats import load_document
from lele.render_options import RenderOptions
from test_periodic_fragment_ui_v171 import gui


def cube_file(tmp_path, comment='OUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z'):
    path = tmp_path / 'molecule.cube'
    path.write_text('Molecular density\n' + comment + '\n'
                    '2 0 0 0\n3 1 0 0\n3 0 1 0\n3 0 0 1\n'
                    '8 0 0 0 0\n1 0 1 1 1\n' + ' '.join(['0.1'] * 27) + '\n')
    return path


def test_generic_cube_grid_does_not_create_periodic_atoms_or_cell_box(tmp_path):
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.renderer import MoleculeRenderer
    document = load_document(cube_file(tmp_path))
    frame = document.frames[0]
    assert frame.pbc == (False,) * 3
    assert not document.volume.periodic
    assert np.linalg.det(frame.cell) > 0  # sampling box retained for interchange
    draw = MoleculeRenderer(vtkRenderer())
    draw.options = RenderOptions(boundary_enabled=True, boundary_bounds=((0, 2),) * 3)
    draw.set_scene(frame, document.volume, volumes=document.volumes)
    assert draw.boundary_display is None
    assert len(draw.displayed_atoms()) == 2
    segments = []
    draw._tube_segments = lambda *args: segments.append(args)
    draw._cell(frame)
    assert segments == []


def test_explicit_castep_periodicity_and_duplicate_plane_handling(tmp_path):
    path = cube_file(tmp_path, 'castep2cube')
    parsed = read_cube_file(path)
    assert all(parsed['atoms'].pbc)
    assert parsed['periodic']
    assert parsed['data'].shape == (2, 2, 2)
    document = load_document(path)
    assert document.volume.periodic
    assert all(document.frames[0].pbc)


def test_generic_cube_attached_to_periodic_structure_keeps_target_cell(tmp_path):
    from lele.field_mapping import attach_field_document
    incoming = load_document(cube_file(tmp_path))
    frame = incoming.frames[0].clone()
    frame.pbc = (True, True, True)
    target = Document(Path('POSCAR'), 'VASP', [frame])
    assert attach_field_document(target, frame, incoming) == 1
    assert frame.pbc == (True, True, True)
    np.testing.assert_allclose(frame.cell, incoming.frames[0].cell)
    assert not target.volume.periodic  # finite grid semantics are not guessed


def test_exported_cube_preserves_explicit_periodicity(tmp_path):
    from lele.field_export import export_active_cube
    frame = Frame(['C'], [[0, 0, 0]], np.eye(3) * 3, (True, True, False))
    volume = Volume(np.ones((3, 3, 3)), np.zeros(3), np.eye(3), periodic=True)
    document = Document(Path('source.cube'), 'CUBE', [frame], volume)
    path = tmp_path / 'explicit.cube'
    export_active_cube(path, document, frame)
    restored = load_document(path)
    assert restored.frames[0].pbc == frame.pbc
    assert restored.volume.periodic


def test_distance_and_angle_use_exact_images_in_skew_cell():
    cell = np.array([[10., 0., 0.], [3., 8., 0.], [0., 0., 9.]])
    frame = Frame(['H', 'O'], [[.5, 2, 2], [9.5, 2, 2]], cell, (True,) * 3)
    assert image_measurement(frame, [AtomImage(1), AtomImage(0, (1, 0, 0))]) == ('distance', 1.)
    assert image_measurement(frame, [AtomImage(0), AtomImage(0, (1, 0, 0))]) == ('distance', 10.)
    records = [AtomImage(0), AtomImage(0, (1, 0, 0)), AtomImage(0, (1, 1, 0))]
    quantity, angle = image_measurement(frame, records)
    assert quantity == 'angle'
    assert angle == pytest.approx(np.degrees(np.arccos(-3 / np.sqrt(73))))


def test_image_selection_survives_refresh_but_not_frame_or_boundary_change():
    frame = Frame(['C'], [[.5, 2, 2]], np.eye(3) * 10, (True,) * 3)
    renderer = SimpleNamespace(boundary_display=object(), display_translation=np.zeros(3), display_rotation=np.eye(3))
    window = SimpleNamespace(frame=frame, selection=[], render_options=RenderOptions(), renderer=renderer)
    toggle_atom_image(window, 0, [10.5, 2, 2])
    toggle_atom_image(window, 0, [.5, 2, 2])
    assert window.selection == [0]
    assert selected_images(window) == [AtomImage(0, (1, 0, 0)), AtomImage(0)]
    toggle_atom_image(window, 0, [10.5, 2, 2])
    assert selected_images(window) == [AtomImage(0)]
    toggle_atom_image(window, 0, [10.5, 2, 2])
    window.render_options.boundary_bounds = ((0, 2),) * 3
    assert selected_images(window) == [AtomImage(0)]
    toggle_atom_image(window, 0, [10.5, 2, 2])
    window.frame = frame.clone()
    assert selected_images(window) == [AtomImage(0)]
    toggle_atom_image(window, 0, [10.5, 2, 2])
    assert len(selected_images(window)) == 2
    window.render_options.boundary_preserve_origin = not window.render_options.boundary_preserve_origin
    assert selected_images(window) == [AtomImage(0)]


def click_world(window, position):
    scene = window.scene
    scene.SetWorldPoint(*position, 1.)
    scene.WorldToDisplay()
    x, y, _ = scene.GetDisplayPoint()
    width, height = window.vtk.GetRenderWindow().GetSize()
    window._pick_from_canvas(x * window.vtk.width() / width,
                             window.vtk.height() - y * window.vtk.height() / height)


def test_canvas_picks_cross_cell_distance_and_only_highlights_clicked_images(gui):
    frame = Frame(['H', 'O'], [[.5, 2, 2], [9.5, 2, 2]], np.eye(3) * 10, (True,) * 3)
    gui.attach(frame)
    window = gui.window
    window.render_options.boundary_bounds = ((0, 2), (0, 1), (0, 1))
    window.vtk.GetRenderWindow().SetSize(900, 500)
    window.refresh_scene(reset_camera=True)
    camera = window.scene.GetActiveCamera()
    camera.SetPosition(10., 2., 50.)
    camera.SetFocalPoint(10., 2., 2.)
    camera.SetViewUp(0., 1., 0.)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(7.)
    click_world(window, [9.5, 2, 2])
    click_world(window, [10.5, 2, 2])
    assert window.selection == [1, 0]
    assert window.measurement_value.value() == pytest.approx(1.)
    assert window.measurement_value.isReadOnly()
    assert '[1,0,0]' in window.measurement_label.text()
    positions = [actor.GetPosition() for actor in window.renderer.atom_highlights]
    np.testing.assert_allclose(positions, [[9.5, 2, 2], [10.5, 2, 2]])
    # A second image of the same atom remains a separate measurement point.
    window.clear_selection()
    click_world(window, [.5, 2, 2])
    click_world(window, [10.5, 2, 2])
    assert window.selection == [0]
    assert window.measurement_value.value() == pytest.approx(10.)
    assert len(window.renderer.atom_highlights) == 2
    # Explicit source-row selection replaces the image picks, even if the
    # resulting unique source IDs happen to be unchanged.
    window._coordinate_atom_activated(window.atom_table.item(0, 0))
    assert len(selected_images(window)) == 1
    assert window.measurement_value.isHidden()
    window.clear_selection()
    assert window._selected_atom_images is None
