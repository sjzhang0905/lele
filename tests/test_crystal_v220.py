"""HKL geometry, periodic coordination, native clipping and Qt controls."""
from copy import deepcopy
from itertools import product
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lele.core import Frame, Document, Volume
from lele.render_options import RenderOptions
from lele.crystal_planes import (default_plane, miller_plane, prepare_planes,
                                plane_polygon, inside_cuts, validate_planes)
from lele.polyhedra import coordination_polyhedra, convex_faces
from lele.renderer import MoleculeRenderer
from lele.trajectory_analysis import DisplayAlignment
from test_periodic_fragment_ui_v171 import gui


def octahedron():
    return Frame(['Ti', 'O', 'O', 'O'], [[0, 0, 0], [2, 0, 0], [0, 2, 0], [0, 0, 2]],
                 np.eye(3)*4, (True, True, True))


def plane(**values):
    return {**default_plane(), **values}


def draw(frame=None):
    from vtkmodules.vtkRenderingCore import vtkRenderer
    view = MoleculeRenderer(vtkRenderer());view.options.axes_position = 'Off'
    if frame is not None:view.set_scene(frame)
    return view


def test_miller_plane_uses_reciprocal_normal_for_skew_cell():
    cell = np.array([[4, 0, 0], [3, 4, 0], [1, 2, 6.]])
    p = miller_plane(cell, (1, 0, 0), .75)
    assert np.dot(p.normal, cell[1]) == pytest.approx(0)
    assert np.dot(p.normal, cell[2]) == pytest.approx(0)
    assert not np.allclose(p.normal, cell[0]/np.linalg.norm(cell[0]))
    assert p.distance/p.spacing == pytest.approx(.75)
    for fractional in ([.75, 0, 0], [.75, 1, 2], [.75, -1, 4]):
        assert np.dot(np.asarray(fractional) @ cell-p.origin, p.normal) == pytest.approx(0)


def test_hkl_multiples_and_signed_distance_are_not_reduced():
    a = miller_plane(np.eye(3)*4, (1, 0, 0), 1.)
    b = miller_plane(np.eye(3)*4, (2, 0, 0), 1.)
    assert a.spacing == 4 and b.spacing == 2
    c = miller_plane(np.eye(3)*4, (-1, 0, 0), -2., 'Å')
    np.testing.assert_allclose(c.origin, [2, 0, 0])


@pytest.mark.parametrize('hkl', [(0, 0, 0), (1.5, 0, 0), (1, 2), (1, np.nan, 0)])
def test_invalid_miller_indices_rejected(hkl):
    with pytest.raises(ValueError):validate_planes([plane(hkl=hkl)])


def test_below_above_slab_and_intersecting_cuts():
    points = [[1, 1, 0], [1, 1, 2], [1, 1, 3]]
    _, below = prepare_planes(np.eye(3)*4, [plane()])
    assert inside_cuts(points, below).tolist() == [True, True, False]
    _, above = prepare_planes(np.eye(3)*4, [plane(mode='Keep above')])
    assert inside_cuts(points, above).tolist() == [False, True, True]
    _, slab = prepare_planes(np.eye(3)*4, [plane(mode='Slab', thickness=.25)])
    assert inside_cuts([[1, 1, 1.49], [1, 1, 1.5], [1, 1, 2.5], [1, 1, 2.51]], slab).tolist() == [False, True, True, False]
    _, cuts = prepare_planes(np.eye(3)*4, [plane(), plane(hkl=(1, 0, 0), mode='Keep above')])
    assert inside_cuts([[1, 1, 1], [3, 1, 1], [3, 1, 3]], cuts).tolist() == [False, True, False]


def test_units_disabled_planes_and_clip_face_limit():
    _, cuts = prepare_planes(np.eye(3)*4, [plane(offset=2., unit='Å'), plane(enabled=False, mode='Slab')])
    assert len(cuts) == 1
    with pytest.raises(ValueError, match='six'):
        validate_planes([plane(mode='Slab')]*4)
    _, cuts = prepare_planes(np.eye(3)*4, [plane(mode='Show only')])
    assert cuts == []


def test_plane_box_polygon_and_alignment_transform():
    cell = np.eye(3)*4
    p = miller_plane(cell, (1, 1, 1), 1.)
    vertices = plane_polygon(cell, p.normal, p.origin)
    assert len(vertices) == 3
    np.testing.assert_allclose(np.sort(vertices, axis=0), np.sort([[4, 0, 0], [0, 4, 0], [0, 0, 4]], axis=0))
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.]])
    shift = np.array([4., 2, -3])
    transformed = miller_plane(cell @ rotation, (1, 1, 1), 1., translation=shift)
    np.testing.assert_allclose(transformed.normal, p.normal @ rotation)
    np.testing.assert_allclose(transformed.origin, p.origin @ rotation+shift)


def test_periodic_octahedron_has_six_images_eight_faces_and_twelve_edges():
    f = octahedron();before = f.clone();polys = coordination_polyhedra(f, RenderOptions())
    assert len(polys) == 1
    p = polys[0]
    assert p.center == 0 and len(p.ligand_indices) == 6
    assert len(p.faces) == 8 and len(p.edges) == 12
    assert any(np.any(shift) for shift in p.image_shifts)
    assert set(p.ligand_indices) == {1, 2, 3}
    np.testing.assert_array_equal(f.positions, before.positions)
    np.testing.assert_array_equal(f.cell, before.cell)


def test_cube_edges_exclude_triangulation_diagonals():
    faces, edges, planar = convex_faces(list(product((-1, 1), repeat=3)))
    assert len(faces) == 12 and len(edges) == 12 and not planar


def test_planar_coordination_and_collinear_shells():
    faces, edges, planar = convex_faces([[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]])
    assert planar and len(faces) == 1 and len(edges) == 4
    assert convex_faces([[0, 0, 0], [1, 0, 0], [2, 0, 0]])[0] == []


def test_explicit_centers_ligands_and_distance_selection():
    options = RenderOptions(polyhedra_centers='Ti', polyhedra_ligands='O', polyhedra_search='Distance range')
    assert len(coordination_polyhedra(octahedron(), options)) == 1
    options.polyhedra_min_distance = 2.1
    assert not coordination_polyhedra(octahedron(), options)
    options.polyhedra_min_distance = 0;options.polyhedra_ligands = 'N'
    assert not coordination_polyhedra(octahedron(), options)


def test_distance_upper_bound_includes_an_exact_neighbor_shell():
    options = RenderOptions(polyhedra_search='Distance range', polyhedra_max_distance=2.)
    assert len(coordination_polyhedra(octahedron(), options)[0].ligand_indices) == 6
    options.polyhedra_min_distance = 2.;options.polyhedra_max_distance = 2.1
    assert len(coordination_polyhedra(octahedron(), options)[0].ligand_indices) == 6


def test_clip_planes_reach_bond_and_isosurface_mappers():
    f = Frame(['C', 'C'], [[1, 1, 1], [2.4, 1, 1]], np.eye(3)*4, (True, True, True))
    field = Volume(np.linspace(-1, 1, 125).reshape(5, 5, 5), [0, 0, 0], np.eye(3))
    view = draw();view.options.unit_cell = False
    view.options.lattice_planes = [plane(mode='Slab', show=False)];view.set_scene(f, field)
    mapped = [actor.GetMapper() for actor in view.dynamic if hasattr(actor, 'GetMapper')]
    assert len(mapped) == 4
    assert all(mapper.GetNumberOfClippingPlanes() == 2 for mapper in mapped)


def test_zero_matching_polyhedra_is_a_valid_rendered_structure():
    view = draw();view.options.style = 'Polyhedral';view.options.polyhedra_centers = 'Fe'
    view.set_scene(octahedron())
    assert not view.polyhedra and len(view.displayed_atoms()) == 4


def test_plane_slab_surface_has_two_faces_and_preserves_cell_volume():
    f = octahedron();view = draw();view.options.lattice_planes = [plane(mode='Slab', thickness=.25)]
    view.set_scene(f)
    assert len(view.lattice_plane_actors) == 2
    for actor in view.lattice_plane_actors:
        points = actor.GetMapper().GetInput().GetPoints()
        assert points.GetNumberOfPoints() == 4
    assert abs(np.linalg.det(f.cell)) == pytest.approx(64)


def test_nonperiodic_tetrahedron_and_hidden_center():
    from lele.atom_appearance import AtomAppearance
    f = Frame(['C']+['H']*4, [[0, 0, 0], [1, 1, 1], [-1, -1, 1], [1, -1, -1], [-1, 1, -1]])
    options = RenderOptions(polyhedra_centers='C', polyhedra_ligands='H', polyhedra_search='Distance range')
    assert len(coordination_polyhedra(f, options)) == 1
    f.atom_appearance[0] = AtomAppearance(visible=False)
    assert not coordination_polyhedra(f, options)


def test_boundary_repeats_complete_polyhedra_and_keeps_source_ids():
    f = octahedron();view = draw();view.options.style = 'Polyhedral'
    view.options.boundary_enabled = True;view.options.boundary_bounds = ((0, 2), (0, 1), (0, 1))
    view.set_scene(f)
    assert len(view.polyhedra) == 2 and len(view.polyhedron_actors) == 2
    assert all(len(p['source'].ligand_indices) == 6 for p in view.polyhedra)
    assert view.polyhedra_extra_atoms
    assert all(0 <= i < 4 for i, _ in view.displayed_atoms())
    assert len(f.symbols) == 4


def test_polyhedral_atoms_can_be_hidden_and_clipping_applies_to_faces():
    view = draw();view.options.style = 'Polyhedral';view.options.polyhedra_show_atoms = False
    view.options.lattice_planes = [plane(hkl=(1, 0, 0), offset=0., show=False)]
    view.set_scene(octahedron())
    assert view.displayed_atoms() == []
    assert view.polyhedron_actors[0].GetMapper().GetNumberOfClippingPlanes() == 1


def test_polyhedral_style_keeps_frozen_long_bonds_and_manual_removals():
    from lele.core import freeze_bonds, visible_bonds
    f = Frame(['Ti']+['O']*6, [[0, 0, 0], [2, 0, 0], [-2, 0, 0],
        [0, 2, 0], [0, -2, 0], [0, 0, 2], [0, 0, -2]])
    freeze_bonds(f);f.positions[1] = [8, 0, 0];f.bond_removed.add((0, 2))
    view = draw();view.options.style = 'Polyhedral';view.options.unit_cell = False;view.options.polyhedra_edges = False
    view.set_scene(f)
    assert len(view.polyhedra[0]['source'].ligand_indices) == 5
    assert (0, 1) in visible_bonds(f) and (0, 2) not in visible_bonds(f)
    tubes = [x for x in view._keepalive if isinstance(x, tuple) and len(x) == 6 and x[3].IsA('vtkTubeFilter')]
    assert len(tubes) == 1
    points = np.asarray([tubes[0][0].GetPoint(i) for i in range(tubes[0][0].GetNumberOfPoints())])
    assert np.any(np.all(points == [8, 0, 0], axis=1))
    assert not np.any(np.all(points == [-2, 0, 0], axis=1))


def test_clipped_atom_centers_labels_and_picking_are_filtered():
    f = Frame(['O', 'O'], [[1, 1, 1], [3, 1, 1]], np.eye(3)*4, (True, True, True))
    view = draw();view.options.labels = 'Index';view.options.lattice_planes = [plane(hkl=(1, 0, 0), show=False)]
    view.set_scene(f)
    assert [i for i, _ in view.displayed_atoms()] == [0]
    assert len(view._label_actors) == 1
    assert len(view._vtk_clip_planes) == 1


def test_alignment_rotates_planes_and_polyhedra_without_modifying_source():
    source = octahedron()
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.]])
    reference = source.clone();reference.positions = source.positions @ rotation+[4, 3, 2]
    reference.cell = source.cell @ rotation
    view = draw();view.options.style = 'Polyhedral';view.alignment = DisplayAlignment(reference, (0, 1, 2, 3))
    view.options.lattice_planes = [plane(hkl=(1, 0, 0))];view.set_scene(source)
    expected = miller_plane(source.cell, (1, 0, 0), .5)
    actual = view.lattice_plane_data[0][1]
    np.testing.assert_allclose(actual.normal, expected.normal @ rotation, atol=1.e-12)
    np.testing.assert_allclose(view.polyhedra[0]['vertices'],
        view.polyhedra[0]['source'].vectors @ rotation+view.frame.positions[0], atol=1.e-12)
    np.testing.assert_array_equal(source.positions[0], [0, 0, 0])


def test_native_glyph_clipping_removes_pixels_on_the_excluded_side():
    from vtkmodules.vtkRenderingCore import vtkRenderWindow, vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    f = Frame(['O', 'O'], [[1, 1, 1], [3, 1, 1]], np.eye(3)*4, (True, True, True))
    view = draw();view.options.background = '#FFFFFF';view.options.unit_cell = False;view.options.bonds = False
    win = vtkRenderWindow();win.SetOffScreenRendering(True);win.SetSize(240, 160);win.AddRenderer(view.renderer)
    try:
        view.set_scene(f)
        camera = view.renderer.GetActiveCamera();camera.ParallelProjectionOn();camera.SetParallelScale(2.)
        camera.SetPosition(2, 1, 12);camera.SetFocalPoint(2, 1, 1);camera.SetViewUp(0, 1, 0)
        def image():
            win.Render();capture = vtkWindowToImageFilter();capture.SetInput(win);capture.ReadFrontBufferOff();capture.Update()
            data = capture.GetOutput();return vtk_to_numpy(data.GetPointData().GetScalars()).reshape(160, 240, -1).copy()
        before = image();view.options.lattice_planes = [plane(hkl=(1, 0, 0), show=False)]
        view.set_scene(f);after = image()
        red = lambda a: (a[:, :, 0].astype(float) > a[:, :, 1].astype(float)+35) & (a[:, :, 0].astype(float) > a[:, :, 2].astype(float)+35)
        assert red(before)[:, :120].sum() > 100 and red(before)[:, 120:].sum() > 100
        assert red(after)[:, :120].sum() > 100 and red(after)[:, 120:].sum() == 0
    finally:win.Finalize()


def attach(gui, frame=None):
    frame = frame or octahedron();gui.attach(frame)
    return gui.window


def test_crystal_panel_apply_planes_normal_view_and_clear(gui):
    w = attach(gui);panel = w.crystal_panel.planes
    assert panel.isEnabled() and w.lattice_planes_action.isEnabled()
    panel.add.click();panel.hkl[0].setValue(1);panel.hkl[2].setValue(0);panel.center.click()
    assert panel.offset.value() == .5
    panel.apply.click();assert w.render_options.lattice_planes[0]['hkl'] == (1, 0, 0)
    assert len(w.renderer.crystal_cuts) == 1
    panel.view_normal.click()
    np.testing.assert_allclose(w.scene.GetActiveCamera().GetDirectionOfProjection(), [-1, 0, 0], atol=1.e-9)
    panel.clear.click();assert not w.render_options.lattice_planes and not w.renderer.crystal_cuts


def test_invalid_plane_keeps_the_previous_applied_cut(gui):
    w = attach(gui);assert w._apply_lattice_planes([plane()])
    previous = deepcopy(w.render_options.lattice_planes)
    with patch('lele.crystal_actions.QMessageBox.warning') as warning:
        assert w._apply_lattice_planes([plane(hkl=(0, 0, 0))]) is False
    warning.assert_called_once();assert w.render_options.lattice_planes == previous


def test_polyhedral_style_panel_and_distance_controls(gui):
    w = attach(gui);panel = w.crystal_panel.polyhedra
    panel.centers.setText('Ti');panel.ligands.setText('O');panel.search.setCurrentText('Distance range')
    panel.maximum.setValue(2.1);panel.opacity.setValue(.42);panel.apply.click()
    assert w.style_combo.currentText() == 'Polyhedral'
    assert len(w.renderer.polyhedra) == 1 and 'CN 6' in panel.info.text()
    assert w.renderer.polyhedron_actors[0].GetProperty().GetOpacity() == pytest.approx(.42)
    panel.maximum.setValue(1.9);panel.apply.click();assert not w.renderer.polyhedra


def test_document_switch_restores_hkl_and_polyhedron_settings(gui):
    w = attach(gui);w._apply_lattice_planes([plane(hkl=(1, 0, 0))])
    values = w.crystal_panel.polyhedra.values();values.update(polyhedra_centers='Ti', polyhedra_opacity=.61)
    w._apply_polyhedra(values);first = w.doc
    second = Document(Path('second.xyz'), 'XYZ', [octahedron()]);w.documents.append(second)
    w.change_frame(0, switch_doc=1);w._apply_lattice_planes([])
    values['polyhedra_opacity'] = .15;w._apply_polyhedra(values)
    w.change_frame(0, switch_doc=0)
    assert w.doc is first and w.render_options.polyhedra_opacity == .61
    assert w.crystal_panel.planes.selected_plane()['hkl'] == (1, 0, 0)
    assert w.crystal_panel.polyhedra.opacity.value() == .61
    w.change_frame(0, switch_doc=1);assert not w.render_options.lattice_planes
    assert w.render_options.polyhedra_opacity == .15


def test_nonperiodic_structure_has_polyhedra_but_disables_hkl(gui):
    w = attach(gui, Frame(['O', 'H', 'H'], [[0, 0, 0], [.7, .5, 0], [-.7, .5, 0]]))
    assert not w.crystal_panel.planes.isEnabled() and not w.lattice_planes_action.isEnabled()
    assert w.crystal_panel.polyhedra.isEnabled()


def test_bad_polyhedra_parameters_cannot_change_the_applied_style(gui):
    w = attach(gui);before = w.render_options.style
    values = w.crystal_panel.polyhedra.values();values['polyhedra_centers'] = 'NotAnElement'
    with patch('lele.crystal_actions.QMessageBox.warning') as warning:
        assert w._apply_polyhedra(values) is False
    assert w.render_options.style == before
    warning.assert_called_once()


def test_trajectory_gif_uses_polyhedra_and_miller_cuts(tmp_path):
    from lele.animation_export import export_animation_gif, GifSettings
    from PIL import Image
    f = octahedron();second = f.clone();second.positions[1, 0] += .15
    doc = Document(Path('polyhedra.xyz'), 'VASP', [f, second])
    options = RenderOptions(style='Polyhedral', axes_position='Off',
        lattice_planes=[plane(hkl=(1, 1, 1), offset=.75)])
    output = tmp_path/'polyhedra.gif'
    settings = GifSettings(width=180, height=140, fps=5, first_frame=1, last_frame=2, supersample=1)
    assert export_animation_gif(output, doc, settings, options) == 2
    with Image.open(output) as gif:assert gif.n_frames == 2


def test_clipping_does_not_change_structure_export_or_coordinates(tmp_path):
    from lele.formats import export_frame, load_document
    f = octahedron();before = f.clone();view = draw();view.options.lattice_planes = [plane()];view.set_scene(f)
    p = tmp_path/'full.POSCAR';export_frame(f, p, 'poscar-direct')
    result = load_document(p)
    assert len(result.frames[0].symbols) == 4
    np.testing.assert_array_equal(f.positions, before.positions)
