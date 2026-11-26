"""Lattice-only references for positions, linked energies and rendered periodic images."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from ase.geometry import cellpar_to_cell
from ase.units import Bohr
from vtkmodules.util.numpy_support import vtk_to_numpy

from lele.cell_reference import apply_cell_reference, read_cell_reference
from lele.core import Document, Frame
from lele.formats import load_document
from lele.project_file import load_project, save_project
from lele.trajectory_link import link_trajectory
from test_periodic_fragment_ui_v171 import gui
from test_trajectory_link_v3170 import cp2k, md, opt


def write_input(path, cell, run='GEO_OPT'):
    path.write_text(f'&GLOBAL\n RUN_TYPE {run}\n&END\n&FORCE_EVAL\n &SUBSYS\n'
                    '  &TOPOLOGY\n   COORD_FILE_NAME unavailable.cif\n  &END\n'
                    f'  &CELL\n{cell}\n  &END\n &END\n&END\n')
    return path


def write_xyz(path):
    path.write_text('2\ni = 1, E = -10\nFe 2 3 4\nO -7.6 3 5.65\n'
                    '2\ni = 2, E = -11\nFe 2 3 4\nO -7.5 3 5.6\n')
    return path


def test_cp2k_and_cif_without_coordinate_table(tmp_path):
    path = tmp_path / 'external.inp'
    ref = read_cell_reference(write_input(path, 'ABC [bohr] 12 13 17\n'
                                               'ALPHA_BETA_GAMMA 80 100 110\n'
                                               'MULTIPLE_UNIT_CELL 2 1 1\nPERIODIC XY'))
    base = cellpar_to_cell([12*Bohr, 13*Bohr, 17*Bohr, 80, 100, 110])
    np.testing.assert_allclose(ref['cell'], base * [[2], [1], [1]])
    assert ref['pbc'] == [True, True, False]

    cif = tmp_path / 'slab.cif'
    tags = ('_cell_length_a 10.0(1)\n_cell_length_b 11\n_cell_length_c 12\n'
            '_cell_angle_alpha 80\n_cell_angle_beta 90\n_cell_angle_gamma 120\n')
    cif.write_text('data_cell\n' + tags)
    ref = read_cell_reference(cif)
    np.testing.assert_allclose(ref['cell'], cellpar_to_cell([10, 11, 12, 80, 90, 120]))
    assert ref['pbc'] == [True] * 3
    cif.write_text(cif.read_text() + 'data_other\n' + tags.replace(' 11\n', ' 13\n'))
    with pytest.raises(ValueError, match='different unit cells'):
        read_cell_reference(cif)


@pytest.mark.parametrize('first', ['xyz', 'output', 'linked'])
def test_menu_association_updates_real_canvas_and_keeps_source(gui, tmp_path, first):
    w = gui.window
    w._add_document_tree(0, w.doc)
    log = cp2k(tmp_path, body=opt(1, -10, .02) + opt(2, -11, .01))
    xyz = write_xyz(tmp_path / 'positions.xyz')
    original = xyz.read_bytes()
    inp = write_input(tmp_path / 'external.inp', 'ABC 10 12 15\nPERIODIC XY')
    w._open_path_now(xyz if first == 'xyz' else log)
    if first == 'linked':
        assert w._associate_loaded_file(w.doc, xyz)
    menu = w._loaded_file_menu(w.doc)
    action = next(a for a in menu.actions() if a.text() == 'Associate unit cell…')
    with patch('lele.loaded_documents.QFileDialog.getOpenFileName', return_value=(str(inp), '')):
        action.trigger()
    assert w.doc.cell_reference['path'] == str(inp)
    if first != 'linked':
        assert w._associate_loaded_file(w.doc, log if first == 'xyz' else xyz)
    assert w.doc.trajectory_link['matched'] == 2 and len(w.documents) == 2
    assert not w.boundary_panel.preserve.isChecked()
    assert 'external.inp' in w.info_view.toPlainText()
    for i, raw_x in enumerate([-7.6, -7.5]):
        w.change_frame(i)
        assert w.frame.positions[1, 0] == raw_x
        assert w.frame.pbc == (True, True, False)
        assert float(w.atom_table.item(1, 1).text()) == pytest.approx(raw_x)
        shown = np.empty((2, 3))
        for points, ids in w.renderer.drag_atom_points:
            shown[ids] = vtk_to_numpy(points.GetData())
        np.testing.assert_allclose(shown[1], w.frame.positions[1] + [10, 0, 0], atol=1.e-6)
    assert xyz.read_bytes() == original
    project = tmp_path / 'scene.lele'
    save_project(project, dict(documents=[dict(document=w.doc, options=w.render_options, frame_index=1)],
                               current_document=0))
    for path in (inp, log, xyz):
        path.unlink()
    entry = load_project(project)['documents'][0]
    assert not entry['options'].boundary_preserve_origin
    doc = entry['document']
    assert doc.cell_reference == w.doc.cell_reference and doc.trajectory_link == w.doc.trajectory_link
    for step in doc.calculation_results.steps:
        np.testing.assert_equal(step.geometry.cell, doc.frames[step.frame_index].cell)
        assert step.geometry.pbc == (True, True, False)


def test_native_pbc_and_validation_before_any_update(tmp_path):
    ref = read_cell_reference(write_input(tmp_path / 'static.inp', 'ABC 10 11 12\nPERIODIC XYZ'))
    a = Frame(['H'], [[-1, 0, -1]], info={'cp2k_periodicity': (True, True, False)})
    b = Frame(['H'], [[-1, 0, -1]], np.diag([9, 11, 12]), (True, True, True))
    doc = Document(Path('positions.xyz'), 'XYZ', [a, b])
    with pytest.raises(ValueError, match='differs'):
        apply_cell_reference(doc, ref)
    assert not a.cell.any() and not doc.cell_reference
    b.cell[0, 0] = 10
    apply_cell_reference(doc, ref)
    assert a.pbc == (True, True, False) and b.pbc == (True, True, True)
    np.testing.assert_equal(a.cell, b.cell)
    doc.frames = [a]
    ref = read_cell_reference(write_input(tmp_path / 'other.inp', 'ABC 20 22 24\nPERIODIC NONE'))
    apply_cell_reference(doc, ref)
    np.testing.assert_equal(a.cell, np.diag([20, 22, 24]))
    assert a.pbc == (True, True, False)
    xyz = load_document(write_xyz(tmp_path / 'source.xyz'))
    apply_cell_reference(xyz, ref)
    assert not any(xyz.frames[0].pbc)


def test_reject_fixed_cell_for_npt_missing_boxes_and_keep_real_boxes(tmp_path):
    ref = read_cell_reference(write_input(tmp_path / 'static.inp', 'ABC 10 11 12'))
    p = cp2k(tmp_path, 'MD', ' MD_PAR| Ensemble type NPT_I\n' + md(1) + md(2))
    tr = tmp_path / 'npt.xyz'
    def write_boxes(native):
        with tr.open('w') as out:
            for i in [1, 2]:
                cell = f' Lattice="{10+i} 0 0 0 11 0 0 0 12" pbc="T T F"' if native or i == 1 else ''
                out.write(f'2\ni = {i}, E = {-10-i*.01}{cell}\nO 0 0 0\nH 0 0 1\n')
    write_boxes(False)
    with pytest.raises(ValueError, match='variable-cell'):
        link_trajectory(p, tr, cell_reference=ref)
    write_boxes(True)
    doc = link_trajectory(p, tr, cell_reference=ref)
    for i, frame in enumerate(doc.frames, 1):
        np.testing.assert_equal(frame.cell, np.diag([10+i, 11, 12]))
        assert frame.pbc == (True, True, False)
