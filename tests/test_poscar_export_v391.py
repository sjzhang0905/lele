"""Optional POSCAR grouping follows exported species and preserves atom identity."""
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from lele.core import Frame
from lele.formats import export_frame, load_document
from lele.poscar_export import grouped_poscar_frame
from lele.atom_appearance import AtomAppearance


def source_frame():
    flags = [[True, False, False], [False, True, False], [False, False, True],
             [True, True, True], [False, False, False], [True, False, True]]
    # Deliberately nonalphabetical first occurrence, with adjacent duplicate Fe blocks.
    return Frame(['Fe', 'Fe', 'O', 'Fe', 'C', 'O'],
        np.array([[.2, .3, .4], [1.1, .3, .4], [2., .3, .4],
                  [2.8, .3, .4], [3.6, .3, .4], [4.4, .3, .4]]),
        [[7., 0., 0.], [1., 6., 0.], [.2, .3, 8.]], (True, True, True),
        info={'poscar_groups': [('Fe', 1), ('Fe', 1), ('O', 1), ('Fe', 1), ('C', 1), ('O', 1)],
              'vasp_fixed_axes': deepcopy(flags), 'fixed_axes': deepcopy(flags),
              'fixed_axes_basis': 'direct', 'atom_source_order': [10, 11, 12, 13, 14, 15],
              'saved_fragments': [{'name': 'fragment1', 'indices': [1, 2, 4]}]},
        bond_added={(1, 2)}, bond_removed={(2, 4)},
        atom_appearance={2: AtomAppearance(color='#12ab34')},
        bond_snapshot=frozenset({(0, 1), (2, 3)}),
        periodic_bond_snapshot=((2, 3, (1, 0, 0)),),
        hbond_added={(2, 3): (1, 0, 0)}, hbond_removed={(0, 5)})


def header(path):
    lines = Path(path).read_text().splitlines()
    return lines[5].split(), list(map(int, lines[6].split()))


def assert_source_unchanged(frame, before):
    assert frame.symbols == before.symbols
    np.testing.assert_array_equal(frame.positions, before.positions)
    np.testing.assert_array_equal(frame.cell, before.cell)
    assert frame.info == before.info
    assert frame.bond_added == before.bond_added and frame.bond_removed == before.bond_removed
    assert frame.bond_snapshot == before.bond_snapshot
    assert frame.periodic_bond_snapshot == before.periodic_bond_snapshot
    assert frame.atom_appearance == before.atom_appearance
    assert frame.hbond_added == before.hbond_added and frame.hbond_removed == before.hbond_removed


@pytest.mark.parametrize('target', ['poscar-direct', 'poscar-cartesian'])
@pytest.mark.parametrize('merge', [False, True])
def test_actual_poscar_roundtrip_stable_order_groups_and_constraints(tmp_path, target, merge):
    frame = source_frame()
    before = deepcopy(frame)
    path = tmp_path / 'POSCAR'
    export_frame(frame, path, target, merge_same_elements=merge)
    restored = load_document(path).frames[0]
    order = [0, 1, 3, 2, 5, 4] if merge else list(range(6))
    assert restored.symbols == [frame.symbols[i] for i in order]
    np.testing.assert_allclose(restored.positions, frame.positions[order], atol=1e-12)
    np.testing.assert_allclose(restored.cell, frame.cell, atol=1e-12)
    assert restored.info['vasp_fixed_axes'] == [frame.info['vasp_fixed_axes'][i] for i in order]
    assert restored.info['fixed_axes'] == [frame.info['fixed_axes'][i] for i in order]
    expected = (['Fe', 'O', 'C'], [3, 2, 1]) if merge else (['Fe', 'Fe', 'O', 'Fe', 'C', 'O'], [1]*6)
    assert header(path) == expected
    assert ('Direct' if target == 'poscar-direct' else 'Cartesian') in path.read_text().splitlines()[8]
    assert_source_unchanged(frame, before)


def test_export_copy_reindexes_all_supported_properties_and_drops_old_blocks():
    frame = source_frame()
    before = deepcopy(frame)
    grouped = grouped_poscar_frame(frame)
    order = [0, 1, 3, 2, 5, 4]
    assert grouped is not frame and grouped.info is not frame.info
    assert grouped.info['atom_source_order'] == [10, 11, 13, 12, 15, 14]
    assert grouped.info['fixed_axes'] == [frame.info['fixed_axes'][i] for i in order]
    assert grouped.info['saved_fragments'] == [{'name': 'fragment1', 'indices': [1, 3, 5]}]
    assert grouped.bond_added == {(1, 3)} and grouped.bond_removed == {(3, 5)}
    assert grouped.atom_appearance == {3: frame.atom_appearance[2]}
    assert grouped.bond_snapshot == frozenset({(0, 1), (2, 3)})
    assert grouped.periodic_bond_snapshot == ((2, 3, (-1, 0, 0)),)
    assert grouped.hbond_added == {(2, 3): (-1, 0, 0)}
    assert grouped.hbond_removed == {(0, 4)}
    assert 'poscar_groups' not in grouped.info and 'poscar_block_ids' not in grouped.info
    assert_source_unchanged(frame, before)


@pytest.mark.parametrize('target', ['poscar-direct', 'poscar-cartesian'])
@pytest.mark.parametrize('merge', [False, True])
def test_grouping_uses_maximum_occupancy_species_after_omitting_vacancies(tmp_path, target, merge):
    frame = source_frame()
    # Keep representative labels distinct from the maximum-occupancy species:
    # grouping must use the projected export identities, not the original labels.
    frame.info['site_occupancies'] = [{'Ni': .6, 'Fe': .4}, {'Fe': 0.},
        {'O': 1.}, {'Fe': 1.}, {'Ni': .8, 'C': .2}, {'O': 1.}]
    before = deepcopy(frame)
    path = tmp_path / 'POSCAR'
    export_frame(frame, path, target, occupancy_policy='maximum', merge_same_elements=merge)
    restored = load_document(path).frames[0]
    order = [0, 4, 2, 5, 3] if merge else [0, 2, 3, 4, 5]
    assert restored.symbols == (['Ni', 'Ni', 'O', 'O', 'Fe'] if merge else ['Ni', 'O', 'Fe', 'Ni', 'O'])
    np.testing.assert_allclose(restored.positions, frame.positions[order], atol=1e-12)
    assert restored.info['vasp_fixed_axes'] == [frame.info['vasp_fixed_axes'][i] for i in order]
    assert header(path) == ((['Ni', 'O', 'Fe'], [2, 2, 1]) if merge else (['Ni', 'O', 'Fe', 'Ni', 'O'], [1]*5))
    assert_source_unchanged(frame, before)


@pytest.mark.parametrize('target,extension', [('xyz', '.xyz'), ('gjf', '.gjf'), ('cif', '.cif')])
def test_merge_option_has_no_effect_on_other_formats(tmp_path, target, extension):
    frame = source_frame()
    first = tmp_path / ('preserved' + extension)
    second = tmp_path / ('requested' + extension)
    export_frame(frame, first, target)
    export_frame(frame, second, target, merge_same_elements=True)
    a = load_document(first).frames[0]
    b = load_document(second).frames[0]
    assert a.symbols == b.symbols == frame.symbols
    np.testing.assert_array_equal(a.positions, b.positions)


def test_default_option_preserves_order_without_declared_poscar_groups(tmp_path):
    frame = source_frame()
    frame.info.pop('poscar_groups')
    path = tmp_path / 'POSCAR'
    export_frame(frame, path, 'poscar-direct')
    assert load_document(path).frames[0].symbols == frame.symbols
    assert header(path) == (['Fe', 'O', 'Fe', 'C', 'O'], [2, 1, 1, 1, 1])
