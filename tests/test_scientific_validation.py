"""Exercise the reader, analysis, and display paths with open reference cases."""

from fractions import Fraction
import json
from types import SimpleNamespace

import numpy as np
import pytest

from lele.boundary import boundary_view
from lele.boundary_selection import AtomImage, image_measurement, selected_images, toggle_atom_image
from lele.core import Frame
from lele.element_rules import default_rule, install_rules
from lele.formats import load_document
from lele.periodic_geometry import (minimum_image, normalized_positions, periodic_basis,
                                    periodic_bonds, periodic_fragment, periodic_neighbors,
                                    short_contact_details)
from lele.selection_expression import evaluate_selection_expression
from lele.supercell import make_fragment_supercell
from lele.trajectory_analysis import GeometryParameter
from verification.scientific.reference import ROOT, evaluate, read_fixture


CASES = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))['cases']
EXPECTED = json.loads((ROOT / 'expected.json').read_text(encoding='utf-8'))


def native_frame(name):
    case = next(entry for entry in CASES if entry['id'] == name)
    return load_document(ROOT / case['source']).frames[0]


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_periodic_geometry_reference(case):
    known = EXPECTED[case['id']]
    assert evaluate(case) == known

    path = ROOT / case['source']
    frame, = load_document(path).frames
    symbols, positions, cell, pbc = read_fixture(path)
    assert frame.symbols == symbols and frame.pbc == pbc
    np.testing.assert_array_equal(frame.positions, np.asarray(positions, dtype=float))
    np.testing.assert_array_equal(frame.cell, np.asarray(cell, dtype=float))
    assert (periodic_basis(frame) is not None) == known['valid_periodic_lattice']

    for query in known['minimum_images']:
        i, j = query['pair']
        delta = frame.positions[j] - frame.positions[i]
        vector, shift = minimum_image(delta, frame)
        assert list(shift) in query['shifts']
        assert float(vector @ vector) == pytest.approx(float(Fraction(query['distance_squared'])), abs=1.e-11)
        np.testing.assert_allclose(vector, delta + np.asarray(shift) @ frame.cell, atol=1.e-12, rtol=0)
        measured = GeometryParameter('Distance', (i, j), nearest_images=True).value(frame)
        assert measured == pytest.approx(np.linalg.norm(vector), abs=1.e-11)

    cutoff = float(case['cutoff_angstrom'])
    first, second, vectors, shifts = periodic_neighbors(frame, cutoff)
    distances = {(i, j, tuple(s)): float(v @ v) for i, j, v, s in zip(first, second, vectors, shifts)}
    reference = {(i, j, tuple(s)): float(Fraction(d2)) for i, j, s, d2 in known['neighbors']}
    assert len(distances) == len(first)
    assert distances == pytest.approx(reference, abs=1.e-11)
    np.testing.assert_allclose(vectors, frame.positions[second] - frame.positions[first] + shifts @ frame.cell,
                               atol=1.e-12, rtol=0)

    contacts = {(item.first, item.second): item for item in short_contact_details(frame, cutoff)}
    assert set(contacts) == {tuple(item['pair']) for item in known['short_contacts']}
    for item in known['short_contacts']:
        contact = contacts[tuple(item['pair'])]
        assert list(contact.image_shift) in item['shifts']
        assert contact.distance**2 == pytest.approx(float(Fraction(item['distance_squared'])), abs=1.e-11)

    minimum, maximum = map(float, case['bond_window_angstrom'])
    rule = dict(default_rule(), a1='*', a2='*', minimum=minimum, maximum=maximum)
    install_rules(frame, [rule], only=True)
    wrapped, cell_shifts = normalized_positions(frame)
    np.testing.assert_allclose(wrapped + cell_shifts @ frame.cell, frame.positions, atol=1.e-12, rtol=0)
    assert not np.any(cell_shifts[:, ~np.asarray(frame.pbc)])
    raw_bonds = {(i, j, tuple(s + cell_shifts[i] - cell_shifts[j])) for i, j, s in periodic_bonds(frame)}
    assert raw_bonds == {(i, j, tuple(s)) for i, j, s in known['bonds']}

    root = [case['fragment_root']]
    if known['fragment']['infinite']:
        with pytest.raises(ValueError, match='infinite periodic network'):
            periodic_fragment(frame, root)
    else:
        preview = periodic_fragment(frame, root)
        expected_images = known['fragment']['images']
        assert preview.indices == [i for i, _ in expected_images]
        for i, shift in expected_images:
            assert list(np.asarray(preview.shifts[i]) - cell_shifts[i]) == shift
            np.testing.assert_allclose(preview.image_positions[i], frame.positions[i] + np.asarray(shift) @ frame.cell,
                                       atol=1.e-12, rtol=0)
    np.testing.assert_array_equal(frame.positions, np.asarray(positions, dtype=float))
    np.testing.assert_array_equal(frame.cell, np.asarray(cell, dtype=float))


@pytest.mark.parametrize('name', ['slab-zero-c', 'slab-dependent-c'])
def test_cross_boundary_image_picking_and_display(name):
    frame = native_frame(name)
    bounds = ((-1, 1), (0, 1), (-2, 3))
    display = boundary_view(frame, bounds, preserve_origin=True)
    assert display.tiles == ((0, 0, 0), (-1, 0, 0))
    assert len(display.cell_lines) == 7
    assert all(np.linalg.norm(q - p) in (8.0, 10.0) for p, q in display.cell_lines)
    copies = dict(zip(zip(display.source_indices, map(tuple, display.shifts)), display.frame.positions))
    window = SimpleNamespace(frame=frame, selection=[], renderer=SimpleNamespace(
        boundary_display=display, display_rotation=np.eye(3), display_translation=np.zeros(3)),
        render_options=SimpleNamespace(boundary_enabled=True, boundary_bounds=bounds, boundary_preserve_origin=True))
    assert toggle_atom_image(window, 0, copies[0, (0, 0, 0)]) == AtomImage(0)
    assert toggle_atom_image(window, 1, copies[1, (-1, 0, 0)]) == AtomImage(1, (-1, 0, 0))
    assert image_measurement(frame, selected_images(window))[1] == pytest.approx(.45)
    assert evaluate_selection_expression(frame, 'element H and distance < 0.6', selected=[0]) == [1]

    # Use the normal distance-based bond model for the finite-fragment action.
    expanded, ids = make_fragment_supercell(frame, periodic_fragment(frame, [0]))
    assert expanded.pbc == frame.pbc
    assert len(expanded.symbols) == 2 * len(frame.symbols)
    assert np.linalg.norm(expanded.positions[ids[1]] - expanded.positions[ids[0]]) == pytest.approx(.45)
    assert np.linalg.det(expanded.cell) == 0.


def test_cp2k_inline_geometry_preserves_partial_periodicity(tmp_path):
    source = tmp_path / 'slab.inp'
    source.write_text('''&GLOBAL
  RUN_TYPE ENERGY
&END GLOBAL
&FORCE_EVAL
  METHOD Quickstep
  &SUBSYS
    &CELL
      A 10 0 0
      B 0 8 0
      C 0 0 0
      PERIODIC XY
    &END CELL
    &COORD
      O 0.15 1 2
      H 9.7 1 2
    &END COORD
  &END SUBSYS
&END FORCE_EVAL
''', encoding='ascii')
    frame, = load_document(source).frames
    assert frame.pbc == (True, True, False)
    np.testing.assert_array_equal(frame.cell[2], [0., 0., 0.])
    assert short_contact_details(frame)[0].image_shift == (-1, 0, 0)


def test_singular_slab_keeps_full_cell_operations_guarded():
    from vtkmodules.vtkRenderingCore import vtkRenderer

    from lele.crystal_planes import default_plane, miller_plane
    from lele.plane_field import fitted_plane_polygon
    from lele.renderer import MoleculeRenderer
    from lele.selection_geometry import fit_selection_plane

    frame = native_frame('slab-zero-c')
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.lattice_planes = [default_plane()]
    renderer.set_scene(frame)
    assert not renderer.lattice_plane_data and not renderer.crystal_cuts
    with pytest.raises(ValueError, match='non-singular'):
        miller_plane(frame.cell, (0, 0, 1))
    fitted = fit_selection_plane(frame, [0, 1, 2], nearest_images=True)
    assert len(fitted_plane_polygon(frame, fitted)) == 4


def test_lattice_rank_cache_tracks_cell_and_mask_edits():
    frame = Frame(['He'], [[0., 0., 0.]], np.diag([10., 8., 0.]), (True, True, False))
    assert periodic_basis(frame) is not None
    frame.cell[1] = frame.cell[0]
    assert periodic_basis(frame) is None
    frame.pbc = (True, False, False)
    assert periodic_basis(frame) is not None


def test_rank_two_cell_remains_rank_two_through_edits_and_project(tmp_path):
    from lele.core import Document, align_pair_to_axis
    from lele.project_file import load_project, save_project
    from test_projects_v230 import state_for

    frame = native_frame('slab-zero-c')
    frame.info['cell_origin_fractional'] = [0.0, 0.0, 0.0]
    _, _, cell_rotated = align_pair_to_axis(frame, 0, 1, 'y')
    assert cell_rotated
    delta, _ = minimum_image(frame.positions[1] - frame.positions[0], frame)
    np.testing.assert_allclose(delta, [0., .45, 0.], atol=1.e-12)
    state = state_for(Document(tmp_path / 'slab.xsf', 'XSF', [frame]))
    stored = tmp_path / 'slab.lele'
    save_project(stored, state)
    reread = load_project(stored)['documents'][0]['document'].frames[0]
    assert reread.pbc == (True, True, False)
    np.testing.assert_array_equal(reread.cell, frame.cell)
    np.testing.assert_array_equal(reread.cell[2], [0., 0., 0.])
    assert short_contact_details(reread)[0].distance == pytest.approx(.45)
