"""Map finite periodic fragments to the right atoms in a real supercell."""
import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.core import Frame
from lele.periodic_geometry import periodic_fragment, normalized_positions
from lele.supercell import make_fragment_supercell


@pytest.mark.parametrize('root', [0, 1])
def test_skew_two_direction_expansion_maps_positive_and_negative_image_shifts(root):
    cell = np.array([[10., 0, 0], [2., 10, 0], [0, 0, 15.]])
    center = np.array([.98, .98, .5]) @ cell
    positions = np.vstack([center, center + [.9, 0, 0], center + [0, .9, 0], [.5, .5, .5] @ cell])
    style = AtomAppearance(color='#123456', opacity=.4)
    source = Frame(['O', 'H', 'H', 'He'], positions, cell, (True, True, False), -12.,
                   {'converter_charge': 1, 'converter_mult': 2,
                    'poscar_groups': [('O', 1), ('H', 2), ('He', 1)]},
                   atom_appearance={1: style})
    source.positions, _ = normalized_positions(source)
    original = source.clone()
    preview = periodic_fragment(source, [root])
    assert preview.supercell_extent == (2, 2, 1)
    if root == 1:
        assert preview.supercell_min[0] == -1
    expanded, selected = make_fragment_supercell(source, preview)
    assert expanded.symbols == source.symbols * 4
    assert len(selected) == len(set(selected)) == 3
    expected = np.array([preview.image_positions[i] for i in preview.indices])
    expected -= np.asarray(preview.supercell_min) @ source.cell
    np.testing.assert_allclose(expanded.positions[selected], expected, atol=1e-12)
    np.testing.assert_allclose(expanded.cell, np.diag([2, 2, 1]) @ source.cell)
    assert expanded.pbc == source.pbc
    assert expanded.info['converter_charge'] == 4
    assert 'converter_mult' not in expanded.info and expanded.energy_ev is None
    assert expanded.info['poscar_groups'] == source.info['poscar_groups'] * 4
    assert expanded.atom_appearance == {i: style for i in (1, 5, 9, 13)}
    np.testing.assert_array_equal(source.positions, original.positions)
    np.testing.assert_array_equal(source.cell, original.cell)
    assert source.info == original.info and source.energy_ev == -12.


def test_single_direction_fragment_keeps_its_cross_boundary_manual_bond():
    source = Frame(['O', 'H', 'He'], [[9.7, 1, 1], [.58, 1, 1], [5, 5, 5]],
                   np.eye(3) * 10, (True,) * 3, bond_added={(0, 1)})
    preview = periodic_fragment(source, [0])
    expanded, selected = make_fragment_supercell(source, preview)
    assert selected == [0, 4]
    assert (0, 4) in expanded.bond_added
    assert np.isclose(np.linalg.norm(expanded.positions[4] - expanded.positions[0]), .88)


def test_internal_fragment_needs_no_repetition_or_metadata_changes():
    source = Frame(['O', 'H'], [[3, 3, 3], [3.9, 3, 3]], np.eye(3) * 10,
                   (True,) * 3, -12., {'converter_mult': 1})
    preview = periodic_fragment(source, [0])
    expanded, selected = make_fragment_supercell(source, preview)
    assert expanded is not source and selected == [0, 1]
    np.testing.assert_array_equal(expanded.positions, source.positions)
    assert expanded.energy_ev == -12. and expanded.info == source.info
