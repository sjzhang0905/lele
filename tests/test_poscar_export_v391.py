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
    expected = (['Fe', 'O', 'C'], [3, 2, 1]) if merge else (['Fe', 'O', 'Fe', 'C', 'O'], [2, 1, 1, 1, 1])
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
    assert grouped.info['poscar_groups'] == [('Fe', 3), ('O', 2), ('C', 1)]
    assert 'poscar_block_ids' not in grouped.info
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


@pytest.mark.parametrize('target', ['poscar-direct', 'poscar-cartesian'])
@pytest.mark.parametrize('merge', [True, False])
def test_separate_canvas_additions_share_runs_but_never_the_last_original_block(tmp_path, target, merge):
    from lele.atom_clipboard import paste_atoms
    from lele.selection_panel import SelectionTableModel
    path = tmp_path / 'POSCAR'
    flags = ['F T F', 'F F F', 'T T T', 'T F T', 'F T T', 'T T F', 'F F T']
    path.write_text('Fe3O4\n1\n15 0 0\n0 15 0\n0 0 15\nFe O\n3 4\nSelective dynamics\nCartesian\n'
                    + ''.join(f'{i} 0 0 {row}\n' for i, row in enumerate(flags)))
    frame = load_document(path).frames[0]
    model = SelectionTableModel()
    model.set_frame(frame, range(7))
    for i, row in enumerate(flags):
        assert [model.cell_text(i, model.headers.index('Free ' + a)) for a in 'XYZ'] == row.split()
    for i, symbol in enumerate(('O', 'O', 'H')):
        paste_atoms(frame, Frame([symbol], [[0, 0, 0]]), [i, 3, 2])
    before = deepcopy(frame)
    out = tmp_path / 'POSCAR_edited'
    export_frame(frame, out, target, merge_same_elements=merge)
    assert header(out) == (['Fe', 'O', 'O', 'H'], [3, 4, 2, 1])
    assert [row.split()[3:6] for row in out.read_text().splitlines()[9:]] == [
        row.split() for row in flags + ['T T T'] * 3]
    np.testing.assert_allclose(load_document(out).frames[0].positions, frame.positions, atol=1.e-12)
    assert_source_unchanged(frame, before)


@pytest.mark.parametrize('merge', [True, False])
def test_added_identity_survives_reindex_deletion_occupancy_projection_and_project_reload(tmp_path, merge):
    from lele.atom_clipboard import paste_atoms
    from lele.atom_indices import reorder_atoms
    from lele.render_options import RenderOptions
    from lele.selection_geometry import delete_selected_atoms
    from lele.site_occupancy import change_site_species
    from test_display_and_order_v2130 import project_roundtrip

    frame = source_frame()  # Fe Fe O Fe C O
    fragment = Frame(['N', 'O', 'H', 'O'], [[0,0,0], [1,0,0], [2,0,0], [3,0,0]])
    paste_atoms(frame, fragment, [1, 2, 3])
    change_site_species(frame, 6, [('O', .75), ('N', .25)])
    change_site_species(frame, 4, [('C', 0.)])
    delete_selected_atoms(frame, [1])
    reorder_atoms(frame, [5,0,6,1,7,2,8,3,4])  # interleave new and original atoms
    frame = project_roundtrip(tmp_path, frame, RenderOptions())[0]['document'].frames[0]
    before = deepcopy(frame)
    out = tmp_path / 'POSCAR'
    export_frame(frame, out, 'poscar-cartesian', occupancy_policy='maximum', merge_same_elements=merge)
    original = [1,5,3,8] if merge else [1,3,5,8]
    order = original + [0,2,4,6]
    original_blocks = (['Fe','O'], [2,2]) if merge else (['Fe','O','Fe','O'], [1,1,1,1])
    assert header(out) == (original_blocks[0] + ['O','H','O'], original_blocks[1] + [2,1,1])
    restored = load_document(out).frames[0]
    np.testing.assert_allclose(restored.positions, frame.positions[order], atol=1.e-12)
    assert restored.info['fixed_axes'] == [[bool(x) for x in frame.info['fixed_axes'][i]] for i in order]
    assert_source_unchanged(frame, before)
