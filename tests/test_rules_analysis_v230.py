"""Element-pair rules preserve editing contracts and quantify source shells."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import csv
import numpy as np
import pytest

from lele.core import Frame, Document, visible_bonds, freeze_bonds
from lele.render_options import RenderOptions
from lele.element_rules import default_rule, validate_rules, install_rules, matching_rule
from lele.periodic_geometry import periodic_bonds
from lele.polyhedra import coordination_shells, coordination_polyhedra
from lele.polyhedron_analysis import analyze_polyhedra, polyhedron_series
from lele.renderer import MoleculeRenderer
from test_periodic_fragment_ui_v171 import gui
from test_crystal_v220 import octahedron


def rule(**values):return {**default_rule(), **values}


def test_pair_rules_extend_bond_distances_and_keep_unlisted_fallback():
    f = Frame(['Fe', 'O', 'H'], [[0, 0, 0], [2.8, 0, 0], [3.7, 0, 0]])
    install_rules(f, [rule(a1='Fe', a2='O', maximum=3.)])
    assert visible_bonds(f) == [(0, 1), (1, 2)]
    f.symbols[:2] = ['O', 'Fe']
    assert (0, 1) in visible_bonds(f)


def test_specificity_disabled_rows_and_last_equal_match():
    rows = [rule(a1='*', a2='*', bonds=False), rule(a1='Fe', a2='O'),
            rule(a1='Fe', a2='O', maximum=2.7, enabled=False)]
    assert matching_rule(rows, 'O', 'Fe')['maximum'] == 2.5
    rows[-1]['enabled'] = True
    assert matching_rule(rows, 'Fe', 'O')['maximum'] == 2.7
    assert matching_rule(rows, 'O', 'Fe', polyhedra=True)['a1'] == '*'


@pytest.mark.parametrize('values', [dict(a1='Fake'), dict(minimum=-1), dict(maximum=0), dict(maximum=np.nan), dict(maximum=21)])
def test_invalid_pair_rules_rejected(values):
    with pytest.raises(ValueError):validate_rules([rule(**values)])


def test_polyhedron_only_rule_and_periodic_image_identities():
    f = octahedron();rows = [rule(maximum=2., bonds=False)]
    install_rules(f, rows, True)
    assert visible_bonds(f) == [] and periodic_bonds(f) == []
    options = RenderOptions(element_pair_rules=rows, pair_rules_only=True)
    shell = coordination_polyhedra(f, options)[0]
    assert shell.center == 0 and len(shell.ligand_indices) == 6
    assert set(shell.ligand_indices) == {1, 2, 3}
    assert np.any(shell.image_shifts)


def test_explicit_pair_range_includes_long_edges_without_occlusion_pruning():
    f = Frame(['Fe', 'O', 'O'], [[0, 0, 0], [2, 0, 0], [4, 0, 0]])
    install_rules(f, [rule(a1='Fe', a2='O', maximum=4.)], True)
    assert visible_bonds(f) == [(0, 1), (0, 2)]


def test_rules_only_and_manual_overrides_are_independent():
    f = Frame(['C', 'H', 'O'], [[0, 0, 0], [.9, 0, 0], [4, 0, 0]])
    install_rules(f, [rule(a1='C', a2='O', maximum=5., bonds=False)], True)
    f.bond_added.add((0, 2))
    assert visible_bonds(f) == [(0, 2)]


def test_editing_freezes_rule_based_bonds():
    f = Frame(['Fe', 'O', 'O'], [[0, 0, 0], [2.8, 0, 0], [8, 0, 0]])
    install_rules(f, [rule(a1='Fe', a2='O', maximum=3.)], True);freeze_bonds(f)
    f.positions[1] = [10, 0, 0];f.positions[2] = [1, 0, 0]
    assert visible_bonds(f) == [(0, 1)]


def test_rules_update_boundary_cache_without_moving_atoms():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    f = Frame(['Fe', 'O'], [[0, 0, 0], [2.8, 0, 0]], np.eye(3)*10, (True, True, True))
    view = MoleculeRenderer(vtkRenderer());view.options.boundary_enabled = True
    view.set_scene(f);assert not view.boundary_display.bonds
    install_rules(f, [rule(a1='Fe', a2='O', maximum=3.)]);view.set_scene(f)
    assert len(view.boundary_display.bonds) == 4
    for a,b in view.boundary_display.bonds:
        assert sorted(view.boundary_display.source_indices[[a,b]]) == [0,1]
        assert np.linalg.norm(view.boundary_display.frame.positions[a]-view.boundary_display.frame.positions[b]) == pytest.approx(2.8)
    np.testing.assert_array_equal(f.positions, [[0, 0, 0], [2.8, 0, 0]])


def test_apply_rules_all_frames_and_undo_after_geometry_undo(gui):
    f = Frame(['C']*3, [[0, 0, 0], [3, 0, 0], [9, 0, 0]])
    f.bond_added.add((0, 2));gui.attach(f, second_frame=f.clone());w = gui.window
    assert w._apply_element_pair_rules([rule(a1='C', a2='C', maximum=4.)], True)
    assert all(visible_bonds(frame) == [(0, 1), (0, 2)] for frame in w.doc.frames)
    w.atom_table.item(1, 1).setText('8')
    assert visible_bonds(w.frame) == [(0, 1), (0, 2)]
    w.undo_edit();w.undo_edit()
    assert not w.render_options.element_pair_rules
    assert all(visible_bonds(frame) == [(0, 2)] for frame in w.doc.frames)


def test_rule_panel_applies_and_new_documents_inherit_rules(gui, tmp_path):
    gui.attach(Frame(['C', 'C'], [[0, 0, 0], [3, 0, 0]]));w = gui.window;p = w.crystal_panel.rules
    p.add.click();p.first.setText('C');p.second.setText('C');p.maximum.setValue(4.);p.apply.click()
    assert visible_bonds(w.frame) == [(0, 1)]
    path = tmp_path/'new.xyz';path.write_text('2\nnew\nC 0 0 0\nC 3.5 0 0\n')
    w._open_path_now(path)
    assert visible_bonds(w.frame) == [(0, 1)]


def test_rule_panel_fits_normal_sidebar_width(gui):
    from lele.crystal_panel import CrystalPanel
    panel = CrystalPanel();gui.addCleanup(panel.deleteLater)
    panel.resize(354, 900);panel.set_values(RenderOptions(element_pair_rules=[rule()]))
    panel.tabs.setCurrentIndex(2);panel.show();gui.app.processEvents()
    assert panel.tabs.currentWidget().horizontalScrollBar().maximum() == 0
    assert not panel.grab().isNull()


def test_ideal_octahedron_metrics():
    shell, data = analyze_polyhedra(octahedron(), RenderOptions())[0]
    assert data['coordination'] == 6 and data['shape'] == 'Octahedron'
    assert data['mean_length_A'] == 2 and data['volume_A3'] == pytest.approx(32/3)
    assert data['distortion_index'] == 0 and data['effective_coordination'] == 6
    assert data['quadratic_elongation'] == pytest.approx(1) and data['angle_variance_deg2'] == 0


def tetrahedron(scale=1.):
    return Frame(['C']+['H']*4, np.asarray([[0, 0, 0], [1, 1, 1], [-1, -1, 1], [1, -1, -1], [-1, 1, -1]])*scale)


def test_tetrahedron_metrics_and_uniform_scaling():
    options = RenderOptions(polyhedra_centers='C', polyhedra_ligands='H', polyhedra_search='Distance range', polyhedra_max_distance=10.)
    a = analyze_polyhedra(tetrahedron(), options)[0][1]
    b = analyze_polyhedra(tetrahedron(2), options)[0][1]
    assert a['shape'] == b['shape'] == 'Tetrahedron'
    assert a['volume_A3'] == pytest.approx(8/3) and b['volume_A3'] == pytest.approx(a['volume_A3']*8)
    assert b['mean_length_A'] == pytest.approx(2*a['mean_length_A'])
    assert a['quadratic_elongation'] == pytest.approx(1)
    assert b['quadratic_elongation'] == pytest.approx(1)
    assert a['angle_variance_deg2'] == pytest.approx(0, abs=1.e-24)


def test_bond_length_distortion_does_not_invent_angle_distortion():
    f = Frame(['Ti']+['O']*6, [[0, 0, 0], [2, 0, 0], [-2, 0, 0], [0, 2, 0], [0, -2, 0], [0, 0, 2.4], [0, 0, -2.4]])
    options = RenderOptions(polyhedra_search='Distance range')
    data = analyze_polyhedra(f, options)[0][1]
    assert data['distortion_index'] > 0 and data['quadratic_elongation'] > 1
    assert data['volume_A3'] == pytest.approx(12.8) and data['angle_variance_deg2'] == 0
    f.positions[-1, 0] = .3
    assert analyze_polyhedra(f, options)[0][1]['angle_variance_deg2'] > 0


def test_planar_shell_and_missing_polyhedron_have_explicit_metrics():
    options = RenderOptions(polyhedra_centers='Ti', polyhedra_ligands='O', polyhedra_search='Distance range')
    f = Frame(['Ti']+['O']*3, [[0, 0, 0], [1, 0, 0], [0, 1, 0], [-1, 0, 0]])
    data = analyze_polyhedra(f, options)[0][1]
    assert data['shape'] == 'Planar' and data['volume_A3'] == 0 and data['quadratic_elongation'] is None
    f.positions[1:] += [10, 0, 0]
    data = analyze_polyhedra(f, options)[0][1]
    assert data['coordination'] == 0 and data['mean_length_A'] is None and data['volume_A3'] is None


def test_source_metrics_ignore_boundary_repeats_and_display_cuts():
    options = RenderOptions(boundary_enabled=True, boundary_bounds=((0, 3),)*3,
        lattice_planes=[dict(hkl=(1, 1, 1), offset=0.)])
    data = analyze_polyhedra(octahedron(), options)[0][1]
    assert data['coordination'] == 6 and data['volume_A3'] == pytest.approx(32/3)


def test_trajectory_keeps_zero_coordination_and_atom_sequence_gaps():
    first = Frame(['Ti', 'O'], [[0, 0, 0], [2, 0, 0]])
    second = first.clone();second.positions[1] = [8, 0, 0]
    third = first.clone();third.symbols = ['O', 'Ti']
    doc = Document(Path('trajectory.xyz'), 'XYZ', [first, second, third])
    rows = polyhedron_series(doc, RenderOptions(), 0)
    assert [r['coordination'] for r in rows] == [1, 0, None]
    assert rows[2]['status'] == 'Atom sequence differs'
    rows = polyhedron_series(doc, RenderOptions(polyhedra_centers='O', polyhedra_ligands='Ti'),
                             0, reference_symbols=third.symbols)
    assert [r['status'] for r in rows] == ['Atom sequence differs', 'Atom sequence differs', 'OK']


def test_polyhedron_dialog_ligand_csv_and_frame_link(gui, tmp_path):
    from lele.polyhedron_dialog import PolyhedronCurveDialog
    first = octahedron();second = first.clone();second.positions[1, 0] += .1
    gui.attach(first, second_frame=second);w = gui.window
    dialog = w.show_polyhedron_analysis();gui.addCleanup(lambda:[x.close() for x in list(w._analysis_windows)])
    assert dialog.table.rowCount() == 1 and dialog.ligands.rowCount() == 6
    output = tmp_path/'ligands.csv'
    with patch('lele.polyhedron_dialog.QFileDialog.getSaveFileName', return_value=(str(output), 'CSV')):dialog.export_ligands()
    rows = list(csv.DictReader(output.open(encoding='utf-8-sig')))
    assert len(rows) == 6 and len({r['ligand'] for r in rows}) == 3
    records = polyhedron_series(w.doc, w.render_options, 0)
    curve = w._show_analysis_window(PolyhedronCurveDialog(w.doc, records, w))
    curve.show();gui.app.processEvents()
    assert not curve.grab().isNull()  # QPaintDevice.metric must remain callable.
    curve.pick_point(SimpleNamespace(artist=curve.line, ind=[1]))
    assert w.frame_index == 1 and w.selection == [0]
    output = tmp_path/'curve.csv'
    with patch('lele.polyhedron_dialog.QFileDialog.getSaveFileName', return_value=(str(output), 'CSV')):curve.export_data()
    assert len(list(csv.DictReader(output.open(encoding='utf-8-sig')))) == 2
