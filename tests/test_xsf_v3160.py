from pathlib import Path

import numpy as np
import pytest
from vtkmodules.util.numpy_support import vtk_to_numpy

from lele.field_mapping import prepare_field_attachment, sample_field
from lele.formats import load_document
from lele.legacy_converter import read_structure
from lele.output_text import LoadCancelled
from lele.xsf_input import read_xsf_document
from test_periodic_fragment_ui_v171 import gui

GEOMETRY = """DIM-GROUP
 3 1
 PRIMVEC
 4 0 0
 1 3 0
 0.3 -0.4 5
 PRIMCOORD
 2 1
 Sn 0.4 0.6 1.2
 53 2.7 1.8 2.3
"""
ORIGIN = np.array([1., -2., 0.5])
CELL = np.array([[4., 0., 0.], [1., 3., 0.], [.3, -.4, 5.]])


def grid(label, data, origin=ORIGIN, spans=CELL, begin='BEGIN_DATAGRID_3D_'):
    rows = [' '.join(map(str, row)) for row in (data.shape, origin, *spans)]
    values = data.ravel(order='F')
    rows.extend(' '.join(map(str, values[i:i+5])) for i in range(0, len(values), 5))
    return '\n'.join([begin + label, *rows, 'END_DATAGRID_3D', ''])


def write(path, data, *, header=GEOMETRY):
    path.write_text(header + 'BEGIN_BLOCK_DATAGRID_3D\nfields\n' + data + 'END_BLOCK_DATAGRID_3D\n')
    return path


def test_dim_group_matches_converter_and_modern_xsf(tmp_path):
    path = tmp_path/'sheet.xsf'
    path.write_bytes(('# old header\n\n' + GEOMETRY).replace('\n', '\r\n').encode('utf-8-sig'))
    doc = load_document(path)
    atoms, _ = read_structure(path)
    frame = doc.frames[0]
    assert frame.symbols == atoms.get_chemical_symbols() == ['Sn', 'I']
    assert frame.pbc == (True,)*3 and atoms.pbc.all()
    assert doc.volumes == [] and doc.volume is None
    np.testing.assert_array_equal(frame.cell, CELL)
    np.testing.assert_array_equal(frame.positions, atoms.positions)
    path.write_text(GEOMETRY.replace('DIM-GROUP\n 3 1','CRYSTAL'))
    np.testing.assert_array_equal(load_document(path).frames[0].positions, frame.positions)


def test_xsf_animation_preserves_all_frames_and_final_converter_geometry(tmp_path):
    path = tmp_path/'movie.xsf'
    path.write_text('ANIMSTEPS 2\n' + GEOMETRY + 'PRIMCOORD 2\n2 1\nSn 1 2 3\nI 4 5 6\n')
    doc = load_document(path)
    assert len(doc.frames) == 2
    np.testing.assert_array_equal(doc.frames[1].cell, CELL)
    np.testing.assert_array_equal(read_structure(path)[0].positions, doc.frames[1].positions)
    with pytest.raises(ValueError, match='exceeds 1'):
        load_document(path, max_frames=1)


def test_nonorthogonal_multifield_xsf_gui_and_mesh(tmp_path, gui):
    x, y, z = np.indices((5, 4, 3))
    a, b = x-2., x+10*y+100*z
    path = write(tmp_path/'charged.XSF', grid('signed', a) + grid('rho', b, begin='DATAGRID_3D_'))
    w = gui.window
    w._open_path_now(path)
    assert w.doc.format_name == 'XCrySDen XSF'
    assert [v.label for v in w.doc.volumes] == ['signed', 'rho']
    assert w.field_combo.count() == 2
    first, second = w.doc.volumes
    assert not first.periodic and not second.periodic
    np.testing.assert_array_equal(second.data, b)
    np.testing.assert_allclose(second.voxel_vectors*(np.array(b.shape)[:, None]-1), CELL)
    np.testing.assert_allclose(sample_field(second, [ORIGIN + np.array([3., 2., 1.]) @ second.voxel_vectors]), [123.])
    w._set_option('volume_iso', .5)
    assert len(w.renderer.field_actors) == 2
    levels = []
    for actor in w.renderer.field_actors:
        mapper = actor.GetMapper()
        mapper.Update()
        poly = mapper.GetInput()
        assert poly.GetNumberOfCells() > 0
        points = vtk_to_numpy(poly.GetPoints().GetData())
        vals = sample_field(first, points)
        assert np.ptp(vals) < 2e-5
        levels.append(round(float(np.mean(vals)), 4))
    assert sorted(levels) == [-.5, .5]
    w.field_combo.setCurrentIndex(1)
    assert w.doc.volume is second
    other = tmp_path/'same.xsf'
    other.write_text(GEOMETRY)
    target = load_document(other)
    added = prepare_field_attachment(target, target.frames[0], w.doc)
    assert len(added) == 2


def test_periodic_endpoints_only_collapsed_for_complete_matching_cell(tmp_path):
    base = np.arange(24).reshape(2, 3, 4)
    wrapped = np.pad(base, ((0,1),)*3, mode='wrap')
    path = write(tmp_path/'periodic.xsf', grid('periodic', wrapped) + grid('subbox', wrapped, spans=CELL/2))
    a, b = load_document(path).volumes
    assert a.periodic and not b.periodic
    np.testing.assert_array_equal(a.data, base)
    np.testing.assert_array_equal(b.data, wrapped)
    np.testing.assert_allclose(sample_field(a, [ORIGIN+CELL[1]]), [0], atol=1e-6)
    np.testing.assert_allclose(a.voxel_vectors*np.array(base.shape)[:, None], CELL)
    wrapped[-1, 1, 1] += 2
    field = load_document(write(path, grid('different_faces', wrapped))).volume
    assert not field.periodic
    np.testing.assert_array_equal(field.data, wrapped)


def test_atoms_with_standalone_grid_and_fortran_exponents(tmp_path):
    path = tmp_path/'molecule.xsf'
    data = grid('orbit', np.arange(8).reshape(2, 2, 2)).replace('0 4 2 6 1', '0 4D0 2 6 1')
    path.write_text('ATOMS\nC 0 0 0\nH .9 0 0\n' + data)
    doc = load_document(path)
    assert doc.frames[0].symbols == ['C','H'] and not any(doc.frames[0].pbc)
    np.testing.assert_array_equal(doc.volume.data, np.arange(8).reshape(2, 2, 2))


@pytest.mark.parametrize('malform', ['short', 'extra', 'nonfinite', 'no_end', 'memory', 'bad_basis'])
def test_invalid_xsf_grid_retains_only_complete_geometry(tmp_path, malform):
    text = grid('field', np.arange(8).reshape(2, 2, 2))
    if malform == 'short':
        text = text.replace('5 3 7\n', '5 3\n')
    elif malform == 'extra':
        text = text.replace('END_DATAGRID_3D', '9\nEND_DATAGRID_3D')
    elif malform == 'nonfinite':
        text = text.replace('5 3 7\n', '5 nan 7\n')
    elif malform == 'no_end':
        text = text.replace('END_DATAGRID_3D','')
    elif malform == 'bad_basis':
        text = text.replace('1.0 3.0 0.0', '0 0 0')
    doc = read_xsf_document(write(tmp_path/'bad.xsf', text), max_points=7 if malform == 'memory' else 8)
    assert doc.frames[0].symbols == ['Sn', 'I'] and doc.volume is None and not doc.volumes
    assert 'unavailable' in doc.note


def test_interrupted_xsf_propagates_cancellation(tmp_path):
    path = write(tmp_path/'cancel.xsf', grid('rho', np.ones((5, 4, 3))))
    with pytest.raises(LoadCancelled):
        load_document(path, cancelled=lambda: True)


def test_small_xsf_field_opens_with_a_visible_default_contour(tmp_path, gui):
    w = gui.window
    data = np.indices((5, 4, 3))[0] * .0004
    path = write(tmp_path/'small.xsf', grid('charge', data))
    w._open_path_now(path)
    assert 0 < w.render_options.volume_iso < data.max()
    assert w.iso_spin.value() == pytest.approx(w.render_options.volume_iso)
    assert w.renderer.field_actors[0].GetMapper().GetInput().GetNumberOfCells() > 0


def test_boundary_repeats_whole_finite_boxes_and_leaves_subboxes_at_input_origin(gui, tmp_path):
    data = np.indices((4, 4, 4))[0].astype(float)
    path = write(tmp_path/'boxes.xsf', grid('density', data, origin=[0,0,0]) +
                 grid('density', data, origin=[0,0,0], spans=CELL * .75))
    w = gui.window
    w._open_path_now(path)
    assert [v.label for v in w.doc.volumes] == ['density', 'density (2)']
    w.render_options.volume_signs = 'Positive'
    w.render_options.boundary_bounds = ((0,2),(0,1),(0,1))
    w.refresh_scene()
    assert len(w.renderer.field_actors) == 2
    w.field_combo.setCurrentIndex(1)
    assert len(w.renderer.field_actors) == 1


def test_distributed_signed_example_opens_with_two_real_surface_meshes(gui):
    w = gui.window
    path = Path(__file__).resolve().parents[1] / 'examples' / 'signed_field.xsf'
    w._open_path_now(path)
    assert w.doc.volume.label == 'signed_demo'
    assert w.doc.volume.data.shape == (19, 17, 15)
    assert len(w.renderer.field_actors) == 2
    for actor in w.renderer.field_actors:
        actor.GetMapper().Update()
        assert actor.GetMapper().GetInput().GetNumberOfCells() > 0
