"""Scientific checks and integrated selection/trajectory workflows for 2.0."""
import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
from ase.units import Hartree
from PySide6.QtCore import Qt

from lele.core import Frame, Document, NormalMode
from lele.formats import load_document
from lele.trajectory_analysis import (GeometryParameter, DisplayAlignment,
    displacement_share, parameter_values)
from test_periodic_fragment_ui_v171 import gui

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def geometry():
    return Frame(['C', 'N', 'O', 'H'], [[0,1,0], [0,0,0], [1,0,0], [1,0,1]])


def attach_document(gui, doc):
    w = gui.window
    w.documents = [doc]; w.current_doc = 0; w.frame_index = 0; w.selection = []
    w.files_tree.clear(); w._add_document_tree(0, doc); w.change_frame(0)
    gui.addCleanup(lambda: [dialog.close() for dialog in list(w._analysis_windows)])
    return w


def test_displacement_share_is_normalization_invariant_and_not_mass_weighted():
    mode = NormalMode(1, -250, [[1,0,0], [0,2,0], [0,0,0]])
    assert displacement_share(mode, [0], 3) == pytest.approx(.2)
    assert displacement_share(mode, [1,1], 3) == pytest.approx(.8)
    assert displacement_share(mode, [0,1,2], 3) == pytest.approx(1.)
    mode.displacements *= -5
    assert displacement_share(mode, [1], 3) == pytest.approx(.8)


@pytest.mark.parametrize('data,selection', [(None,[0]), ([[0,0,0]], [0]), ([[1,0,0]], []), ([[1,0,0]], [1])])
def test_missing_or_undefined_participation_is_not_a_false_zero(data, selection):
    assert displacement_share(NormalMode(1, 100, data), selection, 1) is None


@pytest.mark.parametrize('parameter,expected', [
    (GeometryParameter('Distance', (0,1)), 1),
    (GeometryParameter('Angle', (0,1,2)), 90),
    (GeometryParameter('Dihedral', (0,1,2,3)), 90),
    (GeometryParameter('Plane angle', (0,1,2), (1,2,3)), 90),
    (GeometryParameter('Vector angle', (1,0), (2,3)), 90),
    (GeometryParameter('Point–plane distance', (3,), (0,1,2)), 1),
    (GeometryParameter('Point–line distance', (0,), (1,2)), 1),
    (GeometryParameter('Vector–plane angle', (2,3), (0,1,2)), 90),
])
def test_monitor_values_match_known_geometry(parameter, expected):
    assert parameter.value(geometry()) == pytest.approx(expected)


def test_nearest_images_are_explicit_and_do_not_change_source():
    f = Frame(['H','H'], [[.1,0,0], [9.8,0,0]], np.eye(3)*10, (True,True,True))
    original = f.positions.copy()
    assert GeometryParameter('Distance', (0,1)).value(f) == pytest.approx(9.7)
    assert GeometryParameter('Distance', (0,1), nearest_images=True).value(f) == pytest.approx(.3)
    np.testing.assert_array_equal(f.positions, original)


def test_undefined_and_changed_atom_sequence_leave_curve_gaps():
    a = geometry(); b = a.clone(); b.positions[0] = b.positions[1]
    c = a.clone(); c.symbols[0] = 'H'
    doc = Document(Path('test.xyz'), 'XYZ', [a,b,c])
    values = parameter_values(doc, [0,1,2], GeometryParameter('Angle', (0,1,2)), a.symbols)
    assert values[0] == pytest.approx(90) and np.isnan(values[1:]).all()


def test_unwrapped_dihedral_removes_boundary_jump():
    frames = []
    for degrees in (170, 179, 181, 190):
        theta = np.radians(degrees)
        frames.append(Frame(['C']*4, [[0,1,0], [0,0,0], [1,0,0], [1,np.cos(theta),np.sin(theta)]]))
    doc = Document(Path('dihedrals.xyz'), 'XYZ', frames)
    p = GeometryParameter('Dihedral', (0,1,2,3))
    np.testing.assert_allclose(parameter_values(doc, range(4), p, frames[0].symbols, unwrap=True), [170,179,181,190])


def test_alignment_removes_rigid_motion_without_mutating_coordinates_cell_or_energy():
    a = geometry(); a.cell = np.eye(3)*10; a.energy_ev = -123
    b = a.clone(); rotation = np.array([[0,-1,0], [1,0,0], [0,0,1.]])
    b.positions = a.positions @ rotation + [4,5,6]; b.cell = a.cell @ rotation
    raw = b.positions.copy(); cell = b.cell.copy()
    displayed, r, t = DisplayAlignment(a.clone(), (0,1,2,3)).apply(b)
    np.testing.assert_allclose(displayed.positions, a.positions, atol=1e-12)
    np.testing.assert_allclose(displayed.cell, a.cell, atol=1e-12)
    assert np.linalg.det(r) == pytest.approx(1)
    assert displayed.energy_ev == b.energy_ev == -123
    np.testing.assert_array_equal(b.positions, raw); np.testing.assert_array_equal(b.cell, cell)


def test_selected_scaffold_fit_preserves_real_internal_motion():
    a = geometry(); b = a.clone(); b.positions[3] += [0,0,2]
    b.positions += [8,2,-6]
    displayed, _, _ = DisplayAlignment(a.clone(), (0,1,2)).apply(b)
    np.testing.assert_allclose(displayed.positions[:3], a.positions[:3], atol=1e-12)
    assert displayed.positions[3,2] == pytest.approx(3)


@pytest.mark.parametrize('positions', [[[0,0,0]], [[0,0,0], [1,0,0]], [[0,0,0],[1,0,0],[2,0,0]]])
def test_linear_and_single_atom_alignment_remain_finite(positions):
    a = Frame(['H']*len(positions), positions); b = a.clone()
    b.positions = a.positions @ np.array([[0,-1,0],[1,0,0],[0,0,1]]) + [4,5,6]
    displayed, r, _ = DisplayAlignment(a, tuple(range(len(positions)))).apply(b)
    np.testing.assert_allclose(displayed.positions, a.positions, atol=1e-12)
    assert np.linalg.det(r) == pytest.approx(1)


def test_alignment_never_reflects_a_chiral_structure():
    a = geometry(); b = a.clone(); b.positions[:,0] *= -1
    displayed, r, _ = DisplayAlignment(a, (0,1,2,3)).apply(b)
    assert np.linalg.det(r) == pytest.approx(1)
    assert np.linalg.norm(displayed.positions - a.positions) > .1


def test_energy_only_tree_exposes_every_step_and_selection_never_creates_geometry(gui):
    doc = load_document(EXAMPLES / 'synthetic_xtb_energy_only_v1111.out'); w = attach_document(gui, doc)
    group = w.files_tree.topLevelItem(0).child(0)
    assert group.childCount() == len(doc.calculation_results.steps) == 3
    for k in (2,0,1):
        item = group.child(k); w.files_tree.setCurrentItem(item)
        assert w.files_tree.currentItem() is item
        assert w.frame is None and w.atom_table.rowCount() == 0
        assert w.canvas_stack.currentWidget() is w.results_only_page
        assert f'Selected energy step: {k+1}' in w.results_only_info.toPlainText()
        assert f'{doc.calculation_results.steps[k].energy_ev/Hartree:.12f} Eh' in w.results_only_info.toPlainText()
        assert 'kcal/mol' in item.text(0)
    assert not w.geometry_curve_action.isEnabled() and not w.trajectory_align_check.isEnabled()


def test_unmatched_energy_in_file_with_final_geometry_does_not_display_that_geometry(gui):
    doc = load_document(EXAMPLES / 'synthetic_gxtb_v1110.out'); w = attach_document(gui, doc)
    head = w.files_tree.topLevelItem(0)
    group = next(head.child(i) for i in range(head.childCount()) if 'energies without coordinates' in head.child(i).text(0))
    w.files_tree.setCurrentItem(group.child(0))
    assert w.frame is None and doc.frames and 'Selected energy step' in w.results_only_info.toPlainText()
    w.change_frame(0)
    assert w.frame is doc.frames[0] and w._energy_only_context is None


def test_find_vibrations_filters_selection_plays_real_mode_and_exports_shown_rows(gui, tmp_path):
    doc = load_document(EXAMPLES / 'synthetic_opt_freq.log'); w = attach_document(gui, doc)
    gui.select([1]); dialog = w.show_vibration_analysis()
    assert dialog.selected == (1,) and dialog.rows
    shares = [row[2] for row in dialog.rows]
    assert shares == sorted(shares, reverse=True)
    dialog.imaginary_only.setChecked(True)
    assert len(dialog.rows) == 1 and dialog.rows[0][1].imaginary
    dialog.play_button.click()
    assert w._active_vibration == (0,0,dialog.rows[0][0]) and w.vibration_timer.isActive()
    dialog.arrows_button.click()
    assert not w.vibration_timer.isActive() and w.vibration_controls.arrows_check.isChecked()
    assert len(w.renderer.mode_arrow_actors) == 3
    w.vibration_controls.selected_arrows_check.setChecked(True)
    assert len(w.renderer.mode_arrow_actors) == 1
    path = tmp_path / 'modes.csv'; dialog.write_csv(path)
    with path.open(encoding='utf-8-sig') as stream: rows = list(csv.DictReader(stream))
    assert len(rows) == 1 and rows[0]['selected_atoms_1based'] == '2'
    assert float(rows[0]['selected_cartesian_displacement_share']) == pytest.approx(dialog.rows[0][2])
    w.change_frame(0); assert w.renderer.mode_vectors is None and not w.renderer.mode_arrow_actors


def test_missing_mode_vectors_remain_visible_without_fabricated_participation(gui):
    doc = load_document(EXAMPLES / 'synthetic_opt_freq.log')
    doc.vibrations[0].modes[0].displacements = None
    w = attach_document(gui, doc); gui.select([0]); dialog = w.show_vibration_analysis()
    dialog.selected_only.setChecked(False); dialog.sort_combo.setCurrentIndex(2)
    assert dialog.table.item(0,2).text() == '—'
    dialog.table.selectRow(0)
    assert not dialog.play_button.isEnabled() and not dialog.arrows_button.isEnabled()


def test_geometry_curves_keep_multiple_monitors_and_click_their_actual_source_frame(gui, tmp_path):
    a = geometry(); b = a.clone(); b.positions *= 2
    gui.attach(a, second_frame=b); w = gui.window; gui.select([0,1])
    gui.addCleanup(lambda: [dialog.close() for dialog in list(w._analysis_windows)])
    dialog = w.show_geometry_curves()
    np.testing.assert_allclose(dialog.values[0], [1,2])
    gui.select([0,1,2]); dialog.add_selection_button.click()
    assert len(dialog.parameters) == 2
    np.testing.assert_allclose(dialog.values[1], [90,90])
    line = next(iter(dialog.line_frames))
    dialog.pick_point(SimpleNamespace(artist=line, ind=[1]))
    assert w.frame_index == 1 and w._navigation_indices() == [0,1]
    path = tmp_path / 'monitor.csv'; dialog.write_csv(path)
    with path.open(encoding='utf-8-sig') as stream: rows = list(csv.reader(stream))
    assert len(rows) == 3 and rows[-1][1] == '2'
    assert float(rows[-1][5]) == pytest.approx(2)
    dialog.close(); reopened = w.show_geometry_curves()
    assert len(reopened.parameters) == 2


def test_geometry_monitor_stays_in_current_neb_image_history(gui):
    a = geometry(); b = a.clone(); c = a.clone()
    for i, f in enumerate((a,b,c)): f.info.update(series_key=f'path:{i}', neb_image=2, neb_iteration=i)
    doc = Document(Path('neb.xyz'), 'ORCA', [a,b,c]); w = attach_document(gui, doc)
    w._jump_to_result_sequence(doc, 0, (0,2), 'Image 2 history'); gui.select([0,1])
    dialog = w.show_geometry_curves()
    assert dialog.sequence == (0,2)
    line = next(iter(dialog.line_frames)); dialog.pick_point(SimpleNamespace(artist=line, ind=[1]))
    assert w.frame_index == 2 and w._navigation_indices() == [0,2]


def test_live_display_alignment_preserves_raw_coordinates_measurements_and_document_state(gui):
    a = geometry(); b = a.clone(); b.positions = a.positions @ np.array([[0,-1,0],[1,0,0],[0,0,1]]) + [5,4,3]
    raw = b.positions.copy(); gui.attach(a, second_frame=b); w = gui.window
    w.trajectory_align_check.setChecked(True); w.change_frame(1)
    np.testing.assert_allclose(w.renderer.frame.positions, a.positions, atol=1e-12)
    np.testing.assert_array_equal(w.frame.positions, raw)
    assert not w.doc.modified and not w.undo_stack
    gui.select([0,1]); assert '1.0000 Å' in w.measurement_label.text()
    assert not w._geometry_edit_allowed()
    w.trajectory_align_check.setChecked(False)
    np.testing.assert_array_equal(w.renderer.frame.positions, raw)


def test_alignment_reports_atom_order_mismatch_and_does_not_apply_wrong_mapping(gui):
    a = geometry(); b = a.clone(); b.symbols[0] = 'H'
    gui.attach(a, second_frame=b); w = gui.window
    w.trajectory_align_check.setChecked(True); w.change_frame(1)
    assert 'Atom count/order differs' in w.renderer.alignment_note
    np.testing.assert_array_equal(w.renderer.frame.positions, b.positions)


def test_alignment_configuration_uses_selected_scaffold(gui):
    from lele.trajectory_actions import AlignmentDialog
    gui.attach(geometry(), second_frame=geometry()); gui.select([0,1,2])
    dialog = AlignmentDialog(gui.window); dialog.atoms_combo.setCurrentIndex(1); dialog.apply()
    assert dialog.spec.indices == (0,1,2) and dialog.spec.reference is not gui.window.frame


def test_gif_renderer_receives_display_alignment_and_leaves_source_untouched(tmp_path):
    from lele.animation_export import GifSettings, export_animation_gif
    from lele.render_options import RenderOptions
    from PIL import Image
    a = geometry(); b = a.clone(); b.positions += [8,4,3]
    doc = Document(Path('trajectory.xyz'), 'XYZ', [a,b]); spec = DisplayAlignment(a.clone(), (0,1,2,3))
    captured = []
    class FakeScene:
        def __init__(self, *_): self.draw = SimpleNamespace()
        def render(self, frame, volume):
            displayed = self.draw.alignment.apply(frame)[0]
            captured.append(displayed.positions.copy())
            return Image.new('RGB', (64,48), (10+len(captured),20,30))
        def close(self): pass
    with patch('lele.animation_export._OffscreenScene', FakeScene):
        export_animation_gif(tmp_path/'aligned.gif', doc, GifSettings(width=64,height=48,last_frame=2),
                             RenderOptions(), alignment=spec)
    for positions in captured: np.testing.assert_allclose(positions, a.positions, atol=1e-12)
    np.testing.assert_array_equal(b.positions, a.positions + [8,4,3])


def test_aligned_gif_corner_axes_use_the_displayed_cell():
    from lele.animation_export import GifSettings, _OffscreenScene
    from lele.render_options import RenderOptions
    a = geometry(); a.cell = np.eye(3)*10
    b = a.clone(); rotation = np.array([[0,-1,0],[1,0,0],[0,0,1]])
    b.positions = a.positions @ rotation; b.cell = a.cell @ rotation
    options = RenderOptions(); options.axes_position = 'Corner'; options.axes_basis = 'abc'
    renderer = _OffscreenScene(GifSettings(width=96,height=72), options, None, (), None)
    renderer.draw.alignment = DisplayAlignment(a.clone(), (0,1,2,3))
    try:
        with patch.object(renderer.draw, 'make_corner_marker', wraps=renderer.draw.make_corner_marker) as marker:
            picture = renderer.render(b, None); picture.close()
            displayed = marker.call_args.args[0]
            np.testing.assert_allclose(displayed.cell, a.cell, atol=1e-12)
        np.testing.assert_allclose(b.cell, a.cell @ rotation, atol=1e-12)
    finally: renderer.close()
