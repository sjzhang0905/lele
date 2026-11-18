"""NEB image provenance, fixed-cell geometry and display-composite invariants."""
import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from lele.core import Document, Frame, visible_bonds
from lele.vasp_neb import (build_neb_path, caterpillar_frame, export_path_csv,
                           is_vasp_output, natural_path_key, parse_atom_indices,
                           suggested_atom_indices)


def document(number, positions, energy=-10., *, cell=None, symbols=None, pbc=(True,)*3):
    positions = np.asarray(positions, float).reshape(-1, 3)
    frame = Frame(symbols or ['H'] * len(positions), positions,
                  np.eye(3)*10 if cell is None else cell, pbc, energy_ev=energy,
                  info={'source_kind': 'vasp_out', 'vasp_energy_sigma0_ev': energy,
                        'vasp_free_energy_ev': energy-.2, 'source_line': 17})
    return Document(Path(f'/calculation/{number:02d}/OUTCAR'), 'VASP OUTCAR', [frame])


def test_path_energies_are_last_frames_and_relative_first_not_minimum():
    documents = [document(0, [[0, 0, 0]], -10.), document(1, [[.3, 0, 0]], -9.5),
                 document(2, [[.6, 0, 0]], -10.4)]
    documents[0].frames.insert(0, document(0, [[9, 0, 0]], -100.).frames[0])
    path = build_neb_path(documents)
    np.testing.assert_allclose(path.energies, [-10, -9.5, -10.4])
    np.testing.assert_allclose(path.relative_energies, [0, .5, -.4])
    np.testing.assert_allclose(path.distances, [0, .3, .6])
    assert path.forward_barrier == pytest.approx(.5)
    assert path.reverse_barrier == pytest.approx(.9)
    assert path.frame_indices == (1, 0, 0)
    assert path.energy_kind == 'E0'
    documents[0].frames[-1].positions[:] = 8
    np.testing.assert_allclose(path.frames[0].positions, [[0, 0, 0]])
    with pytest.raises(ValueError):path.positions[0] = 1


def test_common_energy_convention_never_falls_back_per_image():
    first = document(0, [[0, 0, 0]])
    second = document(1, [[.3, 0, 0]], -9.)
    second.frames[0].info.pop('vasp_energy_sigma0_ev');second.frames[0].energy_ev = None
    with pytest.raises(ValueError, match='no printed E0'):build_neb_path([first, second])
    path = build_neb_path([first, second], 'TOTEN')
    np.testing.assert_allclose(path.energies, [-10.2, -9.2])
    assert path.energy_label == 'Free energy TOTEN'
    first.frames[0].info.pop('vasp_free_energy_ev')
    with pytest.raises(ValueError, match='same energy convention'):build_neb_path([first, second], 'TOTEN')


@pytest.mark.parametrize('change', ['unknown_modified', 'cleared', 'positions'])
def test_stale_raw_energy_cannot_revive_edited_frame(change):
    first = document(0, [[0, 0, 0]])
    second = document(1, [[.3, 0, 0]])
    step = SimpleNamespace(geometry=second.frames[0].clone(), frame_index=0, source_line=17)
    second.calculation_results = SimpleNamespace(program='VASP', steps=[step])
    if change == 'unknown_modified':
        second.modified = True
        second.calculation_results = None
    elif change == 'cleared':second.frames[0].energy_ev = None
    else:second.frames[0].positions[0, 0] = 1
    for kind in ('E0', 'TOTEN'):
        with pytest.raises(ValueError, match='modified|edited|invalidated'):build_neb_path([first, second], kind)


def test_fragment_only_modified_document_keeps_verified_energy():
    from lele.saved_fragments import add_fragment
    first = document(0, [[0, 0, 0]])
    second = document(1, [[.3, 0, 0]], -9.5)
    step = SimpleNamespace(geometry=second.frames[0].clone(), frame_index=0, source_line=17)
    second.calculation_results = SimpleNamespace(program='VASP', steps=[step])
    add_fragment(second.frames[0], [0])
    second.modified = True
    np.testing.assert_allclose(build_neb_path([first, second]).energies, [-10., -9.5])
    np.testing.assert_allclose(build_neb_path([first, second], 'TOTEN').energies, [-10.2, -9.7])
    second.frames[0].energy_ev = None
    with pytest.raises(ValueError, match='invalidated'):build_neb_path([first, second])


@pytest.mark.parametrize('change', ['symbols', 'cell', 'pbc', 'nonfinite', 'empty'])
def test_incompatible_images_rejected(change):
    first = document(0, [[0, 0, 0]])
    second = document(1, [[.3, 0, 0]])
    if change == 'symbols':second.frames[0].symbols[0] = 'He'
    elif change == 'cell':second.frames[0].cell[0, 0] += .1
    elif change == 'pbc':second.frames[0].pbc = (False, False, False)
    elif change == 'nonfinite':second.frames[0].positions[0, 0] = np.nan
    else:second.frames[0].symbols = [];second.frames[0].positions = np.empty((0, 3))
    with pytest.raises(ValueError):build_neb_path([first, second])


def test_only_vasp_outputs_and_unique_documents_are_accepted():
    first = document(0, [[0, 0, 0]])
    assert is_vasp_output(first)
    with pytest.raises(ValueError, match='two'):build_neb_path([first])
    with pytest.raises(ValueError, match='once'):build_neb_path([first, first])
    for kind in ('vasp_xdatcar', 'vasp_poscar', 'cp2k_out'):
        other = document(1, [[1, 0, 0]]);other.frames[0].info['source_kind'] = kind
        assert not is_vasp_output(other)
        with pytest.raises(ValueError, match='VASP output'):build_neb_path([first, other])
    with pytest.raises(ValueError, match='cannot be mixed'):build_neb_path([first, document(1, [[1, 0, 0]])], 'Auto')


def test_numeric_sort_preserves_source_image_directory_order():
    documents = [document(i, [[0, 0, 0]]) for i in (10, 2, 1)]
    documents[0].path = Path('/calc/10/OUTCAR')
    documents[1].path = Path('/calc/2/OUTCAR')
    documents[2].path = Path('/calc/1/OUTCAR')
    assert [d.path.parent.name for d in sorted(documents, key=natural_path_key)] == ['1', '2', '10']
    assert natural_path_key(r'C:\NEB\02\OUTCAR') == natural_path_key('c:/neb/2/outcar')


def test_periodic_path_crosses_boundary_continuously():
    path = build_neb_path([document(0, [[9.8, 0, 0], [3, 3, 3]]),
                           document(1, [[.1, 0, 0], [3.01, 3, 3]], -9.),
                           document(2, [[.4, 0, 0], [3.02, 3, 3]], -10.1)])
    np.testing.assert_allclose(path.positions[:, 0, 0], [9.8, 10.1, 10.4])
    np.testing.assert_allclose(path.distances, np.arange(3)*np.hypot(.3, .01))
    assert suggested_atom_indices(path) == (0,)
    composite = caterpillar_frame(path, (0,), reference=1)
    np.testing.assert_allclose(composite.positions[0], [3.01, 3, 3])
    np.testing.assert_allclose(composite.positions[1:, 0], [-.2, .1, .4])
    assert composite.info['neb_reference_image'] == 1
    assert composite.info['neb_caterpillar_atoms'] == [
        {'index': 1, 'source_atom': 0, 'image': 0},
        {'index': 2, 'source_atom': 0, 'image': 1},
        {'index': 3, 'source_atom': 0, 'image': 2}]


def test_skew_cell_uses_true_minimum_image_not_fractional_rounding():
    cell = np.array([[4., 0, 0], [3.8, 1., 0], [0, 0, 8.]])
    delta = np.array([.49, .49, 0]) @ cell
    path = build_neb_path([document(0, [[0, 0, 0]], cell=cell),
                           document(1, [delta], cell=cell)])
    brute = min((delta + np.array([i, j, 0]) @ cell for i in range(-2, 3) for j in range(-2, 3)), key=np.linalg.norm)
    np.testing.assert_allclose(path.positions[1, 0], brute, atol=1.e-10)
    assert path.distances[1] < np.linalg.norm(delta)/2


def test_nonperiodic_and_partial_periodic_axes_are_not_wrapped():
    cell = np.eye(3)*10
    path = build_neb_path([document(0, [[0, 0, 0]], cell=cell, pbc=(True, False, False)),
                           document(1, [[9, 9, 0]], cell=cell, pbc=(True, False, False))])
    np.testing.assert_allclose(path.positions[1, 0], [-1, 9, 0])
    finite = build_neb_path([document(0, [[0, 0, 0]], pbc=(False,)*3),
                             document(1, [[9, 9, 0]], pbc=(False,)*3)])
    np.testing.assert_allclose(finite.positions[1, 0], [9, 9, 0])


def test_caterpillar_has_only_stationary_bonds_and_does_not_edit_sources():
    positions = [[0, 0, 0], [0, 0, .7], [2, 0, 0]]
    docs = [document(0, positions), document(1, [[0, 0, .1], [0, 0, .8], [2.2, 0, 0]])]
    path = build_neb_path(docs)
    composite = caterpillar_frame(path, [2])
    assert len(composite.symbols) == 4
    assert composite.bond_snapshot == frozenset({(0, 1)})
    assert visible_bonds(composite) == [(0, 1)]
    assert composite.energy_ev is None
    assert docs[0].frames[0].bond_snapshot is None
    np.testing.assert_allclose(docs[0].frames[0].positions, positions)
    assert all(i < 2 and j < 2 for i, j, _ in composite.periodic_bond_snapshot)
    assert composite.info['neb_display_only']


def test_all_atoms_can_be_paths_without_substrate():
    path = build_neb_path([document(0, [[0, 0, 0]]), document(1, [[.2, 0, 0]])])
    frame = caterpillar_frame(path, [0])
    assert len(frame.symbols) == 2 and frame.bond_snapshot == frozenset()
    assert not visible_bonds(frame)


@pytest.mark.parametrize('text,result', [('1, 2, 5-8, 2', (0, 1, 4, 5, 6, 7)),
                                        ('3 1;2', (2, 0, 1)), ('2 - 4', (1, 2, 3))])
def test_atom_range_parser(text, result):
    assert parse_atom_indices(text, 10) == result


@pytest.mark.parametrize('text', ['', '0', '11', '-1', '4-2', '1.5', '1-x'])
def test_invalid_atom_range_parser(text):
    with pytest.raises(ValueError):parse_atom_indices(text, 10)


def test_csv_contains_exact_energy_and_source_provenance(tmp_path):
    path = build_neb_path([document(0, [[0, 0, 0]]), document(1, [[.3, 0, 0]], -9.7)])
    destination = tmp_path/'neb.csv';export_path_csv(path, destination)
    with destination.open(encoding='utf-8-sig', newline='') as stream:rows = list(csv.DictReader(stream))
    assert rows[0]['source'] == '/calculation/00/OUTCAR'
    assert rows[0]['source_frame_1based'] == '1' and rows[0]['source_line'] == '17'
    assert rows[0]['energy_convention'] == 'E0 (σ→0)'
    assert float(rows[1]['relative_energy_eV']) == pytest.approx(.3)


def test_csv_cancel_preserves_destination(tmp_path):
    from lele.output_text import LoadCancelled, output_read_session
    path = build_neb_path([document(0, [[0, 0, 0]]), document(1, [[.3, 0, 0]])])
    destination = tmp_path/'neb.csv';destination.write_text('original')
    with pytest.raises(LoadCancelled), output_read_session(cancelled=lambda:True):
        export_path_csv(path, destination)
    assert destination.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [destination]


def test_actual_outcar_parser_pairs_final_ionic_energy_with_its_geometry(tmp_path):
    from lele.formats import load_document
    header = '''vasp.6.3.0
 POTCAR: PAW_PBE H 08Apr2002
 ions per type = 1
 NIONS = 1
 IBRION = 3
 direct lattice vectors reciprocal lattice vectors
 10 0 0 0 0 0
 0 10 0 0 0 0
 0 0 10 0 0 0
'''
    def ionic(x, energy):
        return f''' POSITION TOTAL-FORCE (eV/Angst)
 ------------------
 {x} 0 0 0 0 0
 ------------------
 FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)
 free energy TOTEN = {energy-.2} eV
 energy without entropy = {energy+.1} energy(sigma->0) = {energy}
'''
    documents = []
    for image, (position, energy) in enumerate(((9.8, -10.), (.1, -9.5), (.4, -10.1))):
        directory = tmp_path/str(image);directory.mkdir();file = directory/'OUTCAR'
        file.write_text(header + ionic(2., -99.) + ionic(position, energy))
        documents.append(load_document(file))
    path = build_neb_path(documents)
    np.testing.assert_allclose(path.energies, [-10., -9.5, -10.1])
    np.testing.assert_allclose(path.positions[:, 0, 0], [9.8, 10.1, 10.4])
    assert path.frame_indices == (1, 1, 1)
    from lele.saved_fragments import add_fragment
    add_fragment(documents[-1].frames[-1], [0])
    documents[-1].modified = True
    np.testing.assert_allclose(build_neb_path(documents).energies, path.energies)
    documents[-1].frames[-1].positions[0, 0] = 1.
    with pytest.raises(ValueError, match='edited'):build_neb_path(documents)
