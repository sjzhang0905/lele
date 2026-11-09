"""Boundary display copies must include finite CUBE meshes, not just atoms."""
import os
from itertools import product
from pathlib import Path

import numpy as np
import pytest
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import Volume
from lele.formats import load_document
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.field_mapping import sample_field
from test_periodic_fragment_ui_v171 import gui


def ordinary_cube(tmp_path, *, skew=False):
    """A finite signed field with deliberately nonmatching opposite faces."""
    shape = np.array([7, 8, 9])
    cell = np.array([[3., 0., 0.], [.7, 4., 0.], [.4, .3, 5.]]) if skew else np.diag([3., 4., 5.])
    spacing = cell / shape[:, None]
    origin = np.array([-.2, .15, -.1]) @ cell
    # Linear x is deliberately nonperiodic, so wrapping would add an extra
    # zero-crossing sheet at the far boundary of the grid.
    data = np.broadcast_to(np.linspace(-1., 1., shape[0])[:, None, None], shape).copy()
    atom = np.array([.25, .3, .35]) @ cell
    rows = ['Synthetic finite signed field', 'OUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z',
            '1 ' + ' '.join(map(str, origin))]
    rows += [str(-n) + ' ' + ' '.join(map(str, vector)) for n, vector in zip(shape, spacing)]
    rows += ['1 0 ' + ' '.join(map(str, atom))]
    rows += [' '.join(map(str, row)) for row in data.reshape(-1, 9)]
    path = tmp_path / 'ordinary.cube'
    path.write_text('\n'.join(rows) + '\n')
    document = load_document(path)
    assert document.frames[0].pbc == (True, True, True)
    assert not document.volume.periodic
    return document


def mesh_points(actor):
    mapper = actor.GetMapper()
    mapper.Update()
    return vtk_to_numpy(mapper.GetInput().GetPoints().GetData()).copy()


def render(document, **kwargs):
    draw = MoleculeRenderer(vtkRenderer())
    draw.options = RenderOptions(axes_position='Off', volume_iso=.25, **kwargs)
    draw.set_scene(document.frames[0], document.volume, volumes=document.volumes)
    return draw


def test_ordinary_cube_boundary_apply_updates_both_signs_and_custom_layers(gui, tmp_path):
    document = ordinary_cube(tmp_path)
    w = gui.window
    w._attach_loaded_document(document)
    w.iso_spin.setValue(.25)
    w.field_signs.setCurrentText('Both')
    assert len(w.renderer.field_actors) == 2
    # Exercise the actual panel signal, not only the renderer options.
    w.boundary_panel.set_values(True, ((0, 2), (0, 2), (0, 1)))
    w.boundary_panel.apply.click()
    assert len(w.renderer.boundary_display.tiles) == 4
    assert len(w.renderer.field_actors) == 8
    w._set_surface_option('volume_surfaces', [
        dict(value=-.4, color='#0000ff', opacity=.4, style='Surface', dataset=0),
        dict(value=.2, color='#ff0000', opacity=.7, style='Wireframe', dataset=0),
        dict(value=.5, color='#00ff00', opacity=.8, style='Points', dataset=0, visible=False),
    ])
    assert len(w.renderer.field_actors) == 8
    assert {round(a.GetProperty().GetOpacity(), 1) for a in w.renderer.field_actors} == {.4, .7}
    w.boundary_panel.reset.click()
    assert len(w.renderer.field_actors) == 2


@pytest.mark.parametrize('skew', [False, True])
def test_finite_meshes_translate_with_negative_bounds_without_wrap_padding(tmp_path, skew):
    document = ordinary_cube(tmp_path, skew=skew)
    volume = document.volume
    before = volume.data.copy()
    original = render(document, volume_signs='Positive', boundary_enabled=False)
    original_points = mesh_points(original.field_actors[0])
    bounds = ((-1, 1), (0, 2), (-1, 0))
    repeated = render(document, volume_signs='Positive', boundary_bounds=bounds)
    shifts = [np.asarray(t) @ document.frames[0].cell for t in product(*[range(*b) for b in bounds])]
    assert len(repeated.field_actors) == len(shifts) == 4
    for actor, shift in zip(repeated.field_actors, shifts):
        np.testing.assert_allclose(mesh_points(actor), original_points + shift, atol=7e-7)
        assert actor.GetMapper().GetNumberOfClippingPlanes() == 0
    grids = [entry[0] for entry in repeated._keepalive
             if isinstance(entry, tuple) and entry and hasattr(entry[0], 'IsA') and entry[0].IsA('vtkImageData')]
    assert len(grids) == 1 and grids[0].GetDimensions() == volume.data.shape
    np.testing.assert_array_equal(volume.data, before)
    assert not volume.periodic
    # Display replication must not change finite-domain sampling semantics.
    outside = volume.origin - volume.voxel_vectors[0]
    assert np.isnan(sample_field(volume, [outside])[0])


def test_finite_surface_color_pattern_repeats_in_source_coordinates(tmp_path):
    document = ordinary_cube(tmp_path, skew=True)
    volume = document.volume
    indices = np.moveaxis(np.indices(volume.data.shape), 0, -1)
    points = indices @ volume.voxel_vectors + volume.origin
    color = Volume(points @ [.2, -.1, .3], volume.origin, volume.voxel_vectors,
                   'Finite potential', 'source units', False)
    document.volumes.append(color)
    layer = dict(value=.25, color='#ffffff', opacity=1., style='Surface', dataset=0,
                 map_dataset=1, map_palette='Red-white-blue', map_range=[-3., 3.], map_legend=True)
    draw = render(document, boundary_bounds=((-1, 2), (0, 1), (0, 1)), volume_surfaces=[layer])
    assert len(draw.field_actors) == 3
    assert len(draw.field_scalar_bars) == 1
    shifts = [np.asarray([i, 0, 0]) @ document.frames[0].cell for i in (-1, 0, 1)]
    for actor, shift in zip(draw.field_actors, shifts):
        poly = actor.GetMapper().GetInput()
        values = vtk_to_numpy(poly.GetPointData().GetScalars())
        local_points = mesh_points(actor) - shift
        assert np.isfinite(values).all()
        np.testing.assert_allclose(values, local_points @ [.2, -.1, .3], atol=2e-7)
    assert not draw.field_warnings


def test_molecular_frame_still_has_one_finite_mesh(tmp_path):
    document = ordinary_cube(tmp_path)
    document.frames[0].pbc = (False, False, False)
    draw = render(document, volume_signs='Positive', boundary_bounds=((0, 2),) * 3)
    assert draw.boundary_display is None
    assert len(draw.field_actors) == 1


def test_mismatched_finite_grid_is_not_repeated_and_explains_why(tmp_path):
    document = ordinary_cube(tmp_path)
    document.volume.voxel_vectors *= .8
    draw = render(document, volume_signs='Positive', boundary_bounds=((0, 2),) * 3)
    assert len(draw.boundary_display.tiles) == 8
    assert len(draw.field_actors) == 1
    assert any('differs' in note and 'repetition is disabled' in note for note in draw.field_warnings)


def test_default_one_cell_preserves_shifted_finite_mesh_and_rigid_transform(tmp_path):
    document = ordinary_cube(tmp_path, skew=True)
    original = render(document, volume_signs='Positive', boundary_enabled=False)
    points = mesh_points(original.field_actors[0])
    normal = render(document, volume_signs='Positive')
    assert len(normal.field_actors) == 1
    np.testing.assert_allclose(mesh_points(normal.field_actors[0]), points)
    rotation = np.array([[0., 1., 0.], [-1., 0., 0.], [0., 0., 1.]])
    shift = np.array([2., -3., .5])
    volume = document.volume
    volume.origin = volume.origin @ rotation + shift
    volume.voxel_vectors = volume.voxel_vectors @ rotation
    frame = document.frames[0]
    frame.positions = frame.positions @ rotation + shift
    frame.cell = frame.cell @ rotation
    moved = render(document, volume_signs='Positive')
    assert len(moved.field_actors) == 1
    np.testing.assert_allclose(mesh_points(moved.field_actors[0]), points @ rotation + shift, atol=7e-7)
    assert moved.field_actors[0].GetMapper().GetNumberOfClippingPlanes() == 0


def test_actual_chgcar_periodic_meshes_keep_boundary_repetition():
    path = os.environ.get('LELE_CHGCAR_EXAMPLE')
    if not path or not Path(path).is_file():
        pytest.skip('Set LELE_CHGCAR_EXAMPLE to test the supplied CHGCAR')
    document = load_document(path)
    assert document.volume.periodic
    one = render(document, volume_signs='Positive', boundary_bounds=((0, 1),) * 3)
    four = render(document, volume_signs='Positive', boundary_bounds=((0, 2), (0, 2), (0, 1)))
    assert len(one.field_actors) == 1
    assert len(four.field_actors) == 4
    assert not four.field_warnings
