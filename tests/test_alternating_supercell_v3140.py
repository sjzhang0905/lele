"""Origin-preserving ± replicas retain physical image links and export data."""
from pathlib import Path

import numpy as np
import pytest

from lele.atom_indices import source_order
from lele.core import Document, Frame
from lele.hydrogen_bonds import hydrogen_bond_links
from lele.lattice_tiles import axis_tiles, repeat_bounds, repeat_tiles
from lele.periodic_geometry import periodic_bonds
from lele.supercell import make_supercell


@pytest.mark.parametrize('count, expected', [
    (1, (0,)), (2, (0, 1)), (3, (0, 1, -1)),
    (4, (0, 1, -1, 2)), (5, (0, 1, -1, 2, -2)),
    (6, (0, 1, -1, 2, -2, 3)),
])
def test_repeat_counts_add_alternating_sides(count, expected):
    assert axis_tiles(count) == expected
    assert axis_tiles(count, 'forward') == tuple(range(count))
    assert repeat_tiles((count, 1, 1)) == tuple((i, 0, 0) for i in expected)
    assert repeat_bounds((count, 1, 1)) == ((min(expected), max(expected)+1), (0, 1), (0, 1))


@pytest.mark.parametrize('count, offsets, lower', [
    (2, [0, 1], 0), (3, [0, 1, -1], -1),
    (4, [0, 1, -1, 2], -1), (5, [0, 1, -1, 2, -2], -2),
])
def test_alternating_preserves_unwrapped_source_and_order(count, offsets, lower):
    cell = np.array([[4., 0., 0.], [1.1, 5., 0.], [.7, .8, 6.]])
    positions = np.array([[-.25, .3, .4], [1.1, .6, .7]]) @ cell
    source = Frame(['Si', 'O'], positions, cell, (True,)*3)
    identities = tuple(source_order(source))
    result = make_supercell(source, (count, 1, 1), growth='alternating')
    np.testing.assert_array_equal(result.positions[:2], positions)
    for block, offset in enumerate(offsets):
        np.testing.assert_allclose(result.positions[2*block:2*block+2], positions+offset*cell[0])
    np.testing.assert_array_equal(source.positions, positions)
    np.testing.assert_array_equal(source.cell, cell)
    assert result.symbols == source.symbols*count
    assert tuple(source_order(result)[:2]) == identities
    assert len(set(source_order(result))) == 2*count
    np.testing.assert_allclose(result.cell, np.diag([count, 1, 1]) @ cell)
    np.testing.assert_allclose(np.asarray(result.info['cell_origin_fractional']) @ result.cell,
                               lower*cell[0])
    assert result.info['supercell']['wrapped'] is False


def test_multi_axis_skew_growth_and_repeated_build_keep_cartesian_origin():
    cell = np.array([[4., 0., 0.], [.8, 5., 0.], [.3, .4, 6.]])
    source = Frame(['Si'], [[.3, .4, .5]], cell, (True,)*3)
    first = make_supercell(source, (3, 4, 1), growth='alternating')
    expected = np.array([source.positions[0]+a*cell[0]+b*cell[1]
                         for a in (0, 1, -1) for b in (0, 1, -1, 2)])
    np.testing.assert_allclose(first.positions, expected)
    np.testing.assert_allclose(np.asarray(first.info['cell_origin_fractional']) @ first.cell,
                               -cell[0]-cell[1])
    second = make_supercell(first, (3, 1, 1), growth='alternating')
    np.testing.assert_array_equal(second.positions[:len(first.symbols)], first.positions)
    np.testing.assert_allclose(np.asarray(second.info['cell_origin_fractional']) @ second.cell,
                               -4*cell[0]-cell[1])
    assert len(second.symbols) == 36


def test_forward_api_keeps_legacy_wrap_default_and_alternating_wrap_is_explicit():
    source = Frame(['Si'], [[-1., 0., 0.]], np.eye(3)*4, (True,)*3)
    np.testing.assert_allclose(make_supercell(source, (2, 1, 1)).positions[:, 0], [3., 7.])
    np.testing.assert_allclose(make_supercell(source, (3, 1, 1), growth='alternating').positions[:, 0],
                               [-1., 3., -5.])
    np.testing.assert_allclose(make_supercell(source, (3, 1, 1), growth='alternating', wrap=True).positions[:, 0],
                               [3., 7., -1.])


@pytest.mark.parametrize('growth, repeats, expected_origin', [
    ('forward', (2, 1, 1), [0., 0., 0.]),
    ('alternating', (3, 1, 1), [-12., 0., 0.]),
])
def test_explicit_wrap_resets_previous_shifted_box_before_new_growth(growth, repeats, expected_origin):
    from lele.cell_origin import cell_origin
    source = Frame(['Si'], [[.4, .5, .6]], np.diag([4., 5., 6.]), (True,)*3)
    centered = make_supercell(source, (3, 1, 1), growth='alternating')
    np.testing.assert_allclose(cell_origin(centered), [-4., 0., 0.])
    result = make_supercell(centered, repeats, growth=growth, wrap=True)
    np.testing.assert_allclose(cell_origin(result), expected_origin)
    np.testing.assert_allclose(result.positions[:3, 0], [.4, 4.4, 8.4])
    fractional = (result.positions-cell_origin(result)) @ np.linalg.inv(result.cell)
    assert np.all(fractional >= 0.) and np.all(fractional < 1.)


def test_complete_rotation_translation_moves_shifted_box_with_atoms():
    from lele.cell_origin import cell_origin
    from lele.coordinate_reorientation import transform_complete_frame
    from lele.boundary import boundary_view
    frame = make_supercell(seam_source(), (3, 1, 1), growth='alternating')
    origin = cell_origin(frame).copy()
    positions, cell = frame.positions.copy(), frame.cell.copy()
    before = boundary_view(frame, ((0, 1),)*3, preserve_origin=True)
    rotation = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])
    translation = np.array([2.3, -.7, 1.1])
    transform_complete_frame(frame, rotation, translation)
    np.testing.assert_allclose(frame.positions, positions @ rotation.T + translation, atol=1.e-12)
    np.testing.assert_allclose(frame.cell, cell @ rotation.T, atol=1.e-12)
    np.testing.assert_allclose(cell_origin(frame), origin @ rotation.T + translation, atol=1.e-12)
    after = boundary_view(frame, ((0, 1),)*3, preserve_origin=True)
    np.testing.assert_allclose(np.asarray(after.cell_lines),
                               np.asarray(before.cell_lines) @ rotation.T + translation, atol=1.e-12)
    np.testing.assert_allclose(raw_snapshot_lengths(frame), .2, atol=1.e-12)


@pytest.mark.parametrize('place_at_zero', [False, True])
def test_plane_alignment_rotates_and_translates_shifted_origin(place_at_zero):
    from lele.cell_origin import cell_origin
    from lele.selection_geometry import fit_selection_plane, align_plane_to_xy
    source = Frame(['C']*3, [[1., 2., 3.], [2., 2., 4.], [1., 3., 3.]],
                   np.array([[8., 0., 0.], [.8, 9., 0.], [.4, .7, 10.]]), (True,)*3)
    frame = make_supercell(source, (3, 1, 1), growth='alternating')
    origin, positions = cell_origin(frame).copy(), frame.positions.copy()
    plane = fit_selection_plane(frame, [0, 1, 2], nearest_images=False)
    rotation, translation = align_plane_to_xy(frame, plane, place_at_zero=place_at_zero)
    np.testing.assert_allclose(cell_origin(frame), origin @ rotation.T + translation, atol=1.e-12)
    np.testing.assert_allclose(frame.positions, positions @ rotation.T + translation, atol=1.e-12)
    if place_at_zero:
        assert abs(translation[2]) > 1.
        np.testing.assert_allclose(frame.positions[:3, 2], 0., atol=1.e-12)
    else:
        np.testing.assert_array_equal(translation, np.zeros(3))


def test_vacuum_resize_preserves_cartesian_box_anchor_and_atoms():
    from lele.cell_origin import cell_origin
    from lele.vacuum import change_vacuum
    frame = Frame(['C', 'C'], [[.5, .5, 4.], [1.2, 1., 6.]],
                  np.array([[4., 0., 0.], [.7, 5., 0.], [.6, .9, 20.]]), (True,)*3,
                  info={'cell_origin_fractional': [-.25, -.25, -.25]})
    origin, positions, cell = cell_origin(frame).copy(), frame.positions.copy(), frame.cell.copy()
    old_fractional = list(frame.info['cell_origin_fractional'])
    result = change_vacuum(frame, 28., axis=2)
    assert result['changed']
    np.testing.assert_array_equal(frame.positions, positions)
    np.testing.assert_allclose(frame.cell[0:2], cell[0:2])
    np.testing.assert_allclose(frame.cell[2], cell[2]+[0., 0., 10.])
    np.testing.assert_allclose(cell_origin(frame), origin, atol=1.e-12)
    assert frame.info['cell_origin_fractional'] != old_fractional


def seam_source(*, moved=False):
    cell = np.array([[4., 0., 0.], [.8, 8., 0.], [.3, .7, 9.]])
    source = Frame(['H', 'O'], [[.1, 0., 0.], [3.9, 0., 0.]], cell, (True,)*3,
                   bond_added={(0, 1)})
    source.periodic_bond_snapshot = ((0, 1, (-1, 0, 0)),)
    source.hbond_added = {(0, 1): (-1, 0, 0)}
    if moved:
        source.positions[1] += cell[0]
        source.periodic_bond_snapshot = ((0, 1, (-2, 0, 0)),)
        source.hbond_added = {(0, 1): (-2, 0, 0)}
    return source


def raw_snapshot_lengths(frame):
    return [np.linalg.norm(frame.positions[j]+np.asarray(shift)@frame.cell-frame.positions[i])
            for i, j, shift in frame.periodic_bond_snapshot]


def test_negative_seam_uses_correct_outer_image_and_canonical_sign():
    result = make_supercell(seam_source(), (3, 1, 1), growth='alternating')
    assert result.periodic_bond_snapshot == ((0, 5, (0, 0, 0)),
                                              (1, 2, (0, 0, 0)),
                                              (3, 4, (1, 0, 0)))
    assert result.bond_added == {(0, 5), (1, 2), (3, 4)}
    assert result.hbond_added == {(0, 5): (0, 0, 0), (1, 2): (0, 0, 0), (3, 4): (1, 0, 0)}
    np.testing.assert_allclose(raw_snapshot_lengths(result), .2, atol=1.e-12)


@pytest.mark.parametrize('count', [2, 3, 4, 5])
@pytest.mark.parametrize('moved', [False, True])
def test_all_replicated_covalent_and_hydrogen_paths_keep_physical_length(count, moved):
    source = seam_source(moved=moved)
    result = make_supercell(source, (count, 1, 1), growth='alternating')
    assert len(result.periodic_bond_snapshot) == count
    np.testing.assert_allclose(raw_snapshot_lengths(result), .2, atol=1.e-12)
    links = hydrogen_bond_links(result, automatic=False)
    assert len(links) == count
    np.testing.assert_allclose([np.linalg.norm(link.end-link.start) for link in links], .2, atol=1.e-12)
    assert len(periodic_bonds(result)) == count


def test_locked_manual_path_is_not_retargeted_after_atom_moves():
    source = seam_source()
    source.positions[1, 0] = .4  # Frozen -a path remains long; the nearest pair is different.
    result = make_supercell(source, (3, 1, 1), growth='alternating')
    np.testing.assert_allclose(raw_snapshot_lengths(result), 3.7, atol=1.e-12)
    np.testing.assert_allclose([np.linalg.norm(link.end-link.start)
                               for link in hydrogen_bond_links(result, automatic=False)], 3.7, atol=1.e-12)


def test_removed_links_remain_removed_at_negative_and_outer_seams():
    source = Frame(['C', 'C'], [[.4, 0., 0.], [3.6, 0., 0.]],
                   np.diag([4., 8., 9.]), (True,)*3, bond_removed={(0, 1)})
    source.hbond_removed = {(0, 1)}
    result = make_supercell(source, (3, 1, 1), growth='alternating')
    assert result.bond_removed == {(0, 5), (1, 2), (3, 4)}
    assert result.hbond_removed == {(0, 5), (1, 2), (3, 4)}
    assert periodic_bonds(result) == []
    assert hydrogen_bond_links(result, automatic=False) == []


def test_project_preserves_negative_coordinates_origin_and_image_links(tmp_path):
    from lele.project_file import save_project, load_project
    from lele.render_options import RenderOptions
    frame = make_supercell(seam_source(moved=True), (3, 1, 1), growth='alternating')
    document = Document(Path('source.xyz'), 'XYZ', [frame], modified=True)
    state = dict(documents=[dict(document=document, options=RenderOptions(), frame_index=0)],
                 current_document=0, selection=[0, 5])
    path = tmp_path/'alternating.lele'
    save_project(path, state)
    restored = load_project(path)['documents'][0]['document'].frames[0]
    np.testing.assert_array_equal(restored.positions, frame.positions)
    np.testing.assert_array_equal(restored.cell, frame.cell)
    assert restored.info['cell_origin_fractional'] == frame.info['cell_origin_fractional']
    assert restored.info['supercell'] == frame.info['supercell']
    assert restored.periodic_bond_snapshot == frame.periodic_bond_snapshot
    assert restored.bond_added == frame.bond_added
    assert restored.hbond_added == frame.hbond_added


@pytest.mark.parametrize('preserve_origin', [False, True])
def test_new_project_preserves_explicit_boundary_origin_policy(tmp_path, preserve_origin):
    from lele.project_file import save_project, load_project
    from lele.render_options import RenderOptions
    document = Document(Path('source.xyz'), 'XYZ', [seam_source()])
    options = RenderOptions(boundary_preserve_origin=preserve_origin)
    state = dict(documents=[dict(document=document, options=options, frame_index=0)],
                 current_document=0, selection=[])
    path = tmp_path/'boundary-policy.lele'
    save_project(path, state)
    assert load_project(path)['documents'][0]['options'].boundary_preserve_origin is preserve_origin


def test_older_project_without_origin_policy_retains_wrapped_boundary_display(tmp_path):
    import json
    import zipfile
    from lele.boundary import boundary_view
    from lele.project_file import save_project, load_project
    from lele.render_options import RenderOptions
    frame = Frame(['Si'], [[-1., .5, .6]], np.diag([4., 5., 6.]), (True,)*3)
    document = Document(Path('source.xyz'), 'XYZ', [frame])
    state = dict(documents=[dict(document=document, options=RenderOptions(), frame_index=0)],
                 current_document=0, selection=[])
    path = tmp_path/'new.lele'
    save_project(path, state)
    with zipfile.ZipFile(path) as archive:
        payload = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(payload['manifest.json'])
    changed = 0
    for node in manifest['nodes']:
        if node.get('type') == 'lele.render_options:RenderOptions':
            del node['attributes']['boundary_preserve_origin']
            changed += 1
    assert changed == 1
    payload['manifest.json'] = json.dumps(manifest).encode()
    old = tmp_path/'before-origin-option.lele'
    with zipfile.ZipFile(old, 'w') as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    restored = load_project(old)['documents'][0]
    assert restored['options'].boundary_preserve_origin is False
    restored_frame = restored['document'].frames[0]
    shown = boundary_view(restored_frame, restored['options'].boundary_bounds,
                          preserve_origin=restored['options'].boundary_preserve_origin)
    np.testing.assert_allclose(shown.frame.positions[0], [3., .5, .6])
    np.testing.assert_array_equal(restored_frame.positions, frame.positions)


def test_boundary_of_alternating_supercell_preserves_negative_atoms_and_shifted_box():
    from lele.boundary import boundary_view
    source = seam_source()
    result = make_supercell(source, (3, 1, 1), growth='alternating')
    shown = boundary_view(result, ((0, 1),)*3, preserve_origin=True)
    np.testing.assert_array_equal(shown.frame.positions[:len(result.symbols)], result.positions)
    corners = np.array([point for edge in shown.cell_lines for point in edge])
    fractional = corners @ np.linalg.inv(result.cell)
    np.testing.assert_allclose(fractional.min(axis=0), [-1/3, 0., 0.], atol=1.e-12)
    np.testing.assert_allclose(fractional.max(axis=0), [2/3, 1., 1.], atol=1.e-12)
    np.testing.assert_allclose([np.linalg.norm(shown.frame.positions[j]-shown.frame.positions[i])
                               for i, j in shown.bonds], .2, atol=1.e-12)
    assert shown.bonds
    assert all(np.linalg.norm(link.end-link.start) == pytest.approx(.2)
               for link in hydrogen_bond_links(shown.frame, automatic=False))


def test_boundary_raw_copies_are_zero_first_and_keep_source_image_paths():
    from lele.boundary import boundary_view
    source = seam_source(moved=True)
    shown = boundary_view(source, ((-1, 2), (0, 1), (0, 1)), preserve_origin=True)
    assert shown.tiles == ((0, 0, 0), (1, 0, 0), (-1, 0, 0))
    np.testing.assert_array_equal(shown.frame.positions[:2], source.positions)
    np.testing.assert_allclose(shown.frame.positions[2:4], source.positions+source.cell[0])
    np.testing.assert_allclose(shown.frame.positions[4:6], source.positions-source.cell[0])
    assert shown.bonds
    np.testing.assert_allclose([np.linalg.norm(shown.frame.positions[j]-shown.frame.positions[i])
                               for i, j in shown.bonds], .2, atol=1.e-12)
    links = hydrogen_bond_links(shown.frame, automatic=False)
    assert links
    np.testing.assert_allclose([np.linalg.norm(link.end-link.start) for link in links], .2, atol=1.e-12)


@pytest.mark.parametrize('target, filename', [('xyz', 'atoms.xyz'),
                                             ('poscar-direct', 'POSCAR'),
                                             ('poscar-cartesian', 'Cartesian.POSCAR'),
                                             ('cif', 'atoms.cif')])
def test_exports_keep_atoms_and_periodic_geometry(tmp_path, target, filename):
    from lele.formats import export_frame, load_document
    cell = np.array([[4., 0., 0.], [.8, 5., 0.], [.3, .4, 6.]])
    source = Frame(['Si', 'O'], np.array([[.1, .2, .3], [.7, .6, .5]]) @ cell,
                   cell, (True,)*3)
    result = make_supercell(source, (3, 2, 1), growth='alternating')
    path = tmp_path/filename
    export_frame(result, path, target)
    loaded = load_document(path).frames[0]
    assert len(loaded.symbols) == len(result.symbols)
    if target == 'xyz':
        assert loaded.symbols == result.symbols
        np.testing.assert_allclose(loaded.positions, result.positions, atol=1.e-10)
    elif target.startswith('poscar'):
        assert loaded.symbols == result.symbols
        np.testing.assert_allclose(loaded.positions, result.positions, atol=1.e-10)
        np.testing.assert_allclose(loaded.cell, result.cell, atol=1.e-10)
    else:
        np.testing.assert_allclose(loaded.cell @ loaded.cell.T, result.cell @ result.cell.T,
                                   rtol=2.e-7, atol=2.e-7)
        # CIF symmetry expansion may choose different periodic representatives.
        def sites(frame):
            frac = np.mod(frame.positions @ np.linalg.inv(frame.cell), 1.)
            return sorted((symbol, *np.round(point, 7)) for symbol, point in zip(frame.symbols, frac))
        assert sites(loaded) == sites(result)
