"""Independent acceptance probes; run with LELE source on PYTHONPATH."""
import itertools
from unittest.mock import patch
import numpy as np
import pytest
from lele.core import Frame, unit_cell_edges
from lele.periodic_geometry import short_contact_details, minimum_image
from lele.trajectory_analysis import GeometryParameter, DisplayAlignment


def sheared_pair():
    cell = np.array([[3., 0, 0], [24., 3., 0], [0, 0, 8.]])
    positions = np.array([[.1, .1, .5], [.95, .25, .5]]) @ cell
    return Frame(['C', 'O'], positions, cell, (True, True, True))


def test_contact_count_invariant_under_equivalent_lattice_basis():
    frame = sheared_pair()
    orthogonal = frame.clone()
    orthogonal.cell = np.diag([3., 3., 8.])  # b' = b - 8a, same lattice
    reference = short_contact_details(orthogonal)
    assert len(reference) == 1
    assert reference[0].distance == pytest.approx(np.sqrt(.15**2 + .45**2))
    actual = short_contact_details(frame)
    assert len(actual) == 1, '0.474342 A contact requires image (-2, 0, 0), outside the fixed image stencil'


def test_geometry_curve_nearest_image_on_equivalent_sheared_cell():
    frame = sheared_pair()
    frame.positions = np.array([[0., 0, 0], [.45, .4, 0]]) @ frame.cell
    parameter = GeometryParameter('Distance', (0, 1), nearest_images=True)
    delta = frame.positions[1] - frame.positions[0]
    shifts = np.array(list(itertools.product(range(-12, 13), range(-3, 4), [0])))
    distances = np.linalg.norm(delta + shifts @ frame.cell, axis=1)
    expected = float(distances.min())
    assert expected == pytest.approx(np.sqrt(1.05**2 + 1.2**2))
    assert parameter.value(frame) == pytest.approx(expected)


def test_aligned_unit_cell_follows_the_same_translation_as_atoms():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.renderer import MoleculeRenderer
    reference = Frame(['C', 'N', 'O'], [[1., 1, 1], [2., 1, 1], [1., 2, 1]], np.eye(3)*10, (True,)*3)
    source = reference.clone()
    source.positions += [4., 0, 0]
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.bonds = False
    renderer.options.axes_position = 'Off'
    renderer.alignment = DisplayAlignment(reference, (0, 1, 2))
    with patch.object(renderer, '_tube_segments') as capture:
        renderer.set_scene(source)
    np.testing.assert_allclose(renderer.frame.positions, reference.positions, atol=1e-12)
    np.testing.assert_allclose(renderer.display_translation, [-4., 0, 0], atol=1e-12)
    actual = np.array([[p, q] for p, q, color in capture.call_args.args[0]])
    expected = np.array(unit_cell_edges(source.cell)) @ renderer.display_rotation + renderer.display_translation
    np.testing.assert_allclose(actual, expected, atol=1e-12,
                               err_msg='Cell outline remains at zero while atoms are translated')


@pytest.mark.parametrize('pbc', [(True, True, True), (True, True, False), (True, False, False), (False, False, False)])
def test_contacts_against_brute_force_for_ordinary_cells(pbc):
    rng = np.random.default_rng(201)
    cell = np.array([[4., 0, 0], [1., 3., 0], [.2, .3, 5.]])
    xyz = rng.random((12, 3)) @ cell
    xyz[1] = xyz[0] + [.1, -.2, .05]
    if pbc[0]: xyz[1] += 2*cell[0]
    frame = Frame(['C']*len(xyz), xyz, cell, pbc)
    shifts = np.array(list(itertools.product(*[range(-4, 5) if use else [0] for use in pbc])))
    expected = {}
    for i, j in itertools.combinations(range(len(xyz)), 2):
        distance = np.linalg.norm(xyz[j] - xyz[i] + shifts @ cell, axis=1).min()
        if distance < .6: expected[(i, j)] = distance
    actual = {(r.first, r.second): r for r in short_contact_details(frame)}
    assert set(actual) == set(expected)
    for pair, row in actual.items():
        assert row.distance == pytest.approx(expected[pair])
        displacement = xyz[row.second] + np.array(row.image_shift) @ cell - xyz[row.first]
        assert np.linalg.norm(displacement) == pytest.approx(row.distance)
