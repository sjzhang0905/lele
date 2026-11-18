"""Live angle controls never mutate the source until a single guarded commit."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QStyle, QStyleOptionSlider

from lele.axis_rotation import plan_axis_rotation
from lele.core import Document, Frame, visible_bonds, measure
from lele.rotation_dialog import RotationDialog
from lele.rotation_preview import RotationPreview
from test_axis_rotation_v3110 import molecule, periodic_molecule
from test_periodic_fragment_ui_v171 import gui


def prepare(gui, frame=None, *, selection=(1, 2)):
    frame = molecule() if frame is None else frame
    gui.attach(frame, second_frame=frame.clone())
    gui.select(list(selection))
    return gui.window


def preview(gui, w, *, dihedral=False):
    value = measure(w.frame, w.selection)[1] if dihedral else None
    dialog = RotationDialog(w.frame, w.selection, dihedral=value, parent=w)
    controller = RotationPreview(w, dialog, dihedral=dihedral)
    dialog.show()
    controller.start()
    gui.app.processEvents()
    return dialog, controller


def finish(dialog, controller, accepted=False):
    try:
        return controller.finish(accepted)
    finally:
        dialog.reject()
        dialog.deleteLater()


def test_slider_and_fine_numeric_angles_preview_from_immutable_base(gui):
    w = prepare(gui)
    original = w.frame.clone()
    dialog, controller = preview(gui, w)
    try:
        assert not controller.base.positions.flags.writeable
        assert not any('ORCA' in item.text() for item in dialog.findChildren(QLabel))
        for angle in (90., -120., 13.7, 179.9, -90., 0., 90.):
            dialog.slider.setValue(round(angle * 10))
            assert dialog.value() == pytest.approx(angle)
            expected = plan_axis_rotation(original, w.selection, angle)
            np.testing.assert_allclose(w.renderer.frame.positions, expected.positions, atol=1.e-12)
            np.testing.assert_array_equal(w.renderer.frame.positions[[1, 2]], original.positions[[1, 2]])
            np.testing.assert_array_equal(w.frame.positions, original.positions)
            assert not w.undo_stack and not w.doc.modified
        dialog.angle.setValue(725.1234)
        assert dialog.value() == pytest.approx(725.1234)
        assert dialog.slider.value() == 1800
        np.testing.assert_allclose(w.renderer.frame.positions,
            plan_axis_rotation(original, w.selection, 725.1234).positions, atol=1.e-12)
    finally:
        finish(dialog, controller)
    assert w.renderer.source_frame is w.frame
    np.testing.assert_array_equal(w.frame.positions, original.positions)
    assert w.frame.energy_ev == -20. and not w.undo_stack and not w.doc.modified


def test_preview_accept_creates_one_undo_and_cancel_afterwards_is_idempotent(gui):
    w = prepare(gui)
    original = w.frame.clone()
    other = w.doc.frames[1].positions.copy()
    dialog, controller = preview(gui, w)
    dialog.slider.setValue(450)
    dialog.slider.setValue(900)
    assert finish(dialog, controller, True)
    assert not controller.finish(False)
    assert len(w.undo_stack) == 1 and w.doc.modified and w.frame.energy_ev is None
    np.testing.assert_allclose(w.frame.positions, plan_axis_rotation(original, [1, 2], 90).positions)
    np.testing.assert_array_equal(w.doc.frames[1].positions, other)
    assert w.renderer.source_frame is w.frame
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions, original.positions)
    assert w.frame.energy_ev == -20. and not w.undo_stack


def test_mouse_drag_updates_canvas_before_release(gui):
    w = prepare(gui)
    original = w.frame.positions.copy()
    dialog, controller = preview(gui, w)
    try:
        slider = dialog.slider
        option = QStyleOptionSlider()
        slider.initStyleOption(option)
        handle = slider.style().subControlRect(QStyle.ComplexControl.CC_Slider,
            option, QStyle.SubControl.SC_SliderHandle, slider)
        start = handle.center()
        end = QPoint(slider.width() - handle.width(), start.y())
        before = w.renderer.frame.positions.copy()
        QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(slider, end, delay=10)
        assert slider.isSliderDown()
        assert dialog.value() > 15.
        assert not np.allclose(w.renderer.frame.positions, before)
        np.testing.assert_array_equal(w.frame.positions, original)
        QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=end)
    finally:
        finish(dialog, controller)


def test_preview_preserves_inferred_connectivity_without_freezing_source(gui):
    w = prepare(gui)
    w.frame.bond_snapshot = None
    initial_bonds = visible_bonds(w.frame, w.render_options.bond_cutoff)
    dialog, controller = preview(gui, w)
    try:
        for angle in (140., -150., 0.):
            dialog.angle.setValue(angle)
            assert visible_bonds(w.renderer.frame, w.render_options.bond_cutoff) == initial_bonds
            assert w.frame.bond_snapshot is None
    finally:
        finish(dialog, controller)
    assert w.frame.bond_snapshot is None and not w.undo_stack


@pytest.mark.parametrize('angle', [0., 360., -720.])
def test_periodic_full_turn_restores_exact_representatives_and_no_undo(gui, angle):
    w = prepare(gui, periodic_molecule(), selection=(0, 1))
    original = w.frame.clone()
    dialog, controller = preview(gui, w)
    dialog.slider.setValue(900)
    expected = plan_axis_rotation(original, [0, 1], 90)
    assert w.renderer.frame.periodic_bond_snapshot == expected.periodic_edges
    assert w.renderer.frame.hbond_added == expected.hbond_added
    dialog.angle.setValue(angle)
    np.testing.assert_array_equal(w.renderer.frame.positions, original.positions)
    assert w.renderer.frame.periodic_bond_snapshot == original.periodic_bond_snapshot
    assert w.renderer.frame.hbond_added == original.hbond_added
    assert not finish(dialog, controller, True)
    assert not w.undo_stack and not w.doc.modified
    np.testing.assert_array_equal(w.frame.positions, original.positions)


def test_global_scene_refresh_and_style_changes_keep_live_preview_and_camera(gui):
    w = prepare(gui)
    dialog, controller = preview(gui, w)
    try:
        dialog.slider.setValue(900)
        expected = w.renderer.frame.positions.copy()
        camera = w.scene.GetActiveCamera()
        camera.Azimuth(26)
        pose = camera.GetPosition()
        w.render_options.labels = 'Element'
        w.refresh_scene()
        assert w.renderer.source_frame is controller.display_frame
        np.testing.assert_array_equal(w.renderer.frame.positions, expected)
        np.testing.assert_allclose(camera.GetPosition(), pose)
    finally:
        finish(dialog, controller)


@pytest.mark.parametrize('change', ['selection', 'geometry', 'frame', 'document', 'bonds', 'hydrogen_bonds', 'cutoff'])
def test_external_changes_reject_preview_without_overwriting_any_source(gui, change):
    w = prepare(gui)
    source = w.frame
    original = source.positions.copy()
    dialog, controller = preview(gui, w)
    dialog.slider.setValue(900)
    if change == 'selection':
        w.selection = [2, 1]
    elif change == 'geometry':
        source.positions[0] += [4, 2, 1]
    elif change == 'frame':
        w.frame_index = 1
    elif change == 'document':
        other = molecule(); other.positions += [12, 5, 1]
        w.documents.append(Document(Path('other.xyz'), 'XYZ', [other]))
        w.current_doc = 1
    elif change == 'bonds':
        source.bond_added.add((0, 5))
    elif change == 'hydrogen_bonds':
        source.hbond_added[(0, 5)] = (0, 0, 0)
    elif change == 'cutoff':
        w.render_options.bond_cutoff += .1
    after = source.positions.copy()
    current = w.frame.positions.copy()
    assert not controller._check_source()
    assert not dialog.isVisible()
    assert not finish(dialog, controller, True)
    np.testing.assert_array_equal(source.positions, after)
    np.testing.assert_array_equal(w.frame.positions, current)
    assert w.renderer.source_frame is w.frame and not w.undo_stack
    if change != 'geometry':
        np.testing.assert_array_equal(source.positions, original)


def test_modeless_axis_workflow_accepts_own_preview_and_commits_once(gui):
    w = prepare(gui)
    original = w.frame.clone()
    errors = []

    def exercise():
        try:
            dialog = next(d for d in gui.app.topLevelWidgets()
                          if isinstance(d, RotationDialog) and d.isVisible())
            controller = w._rotation_preview
            dialog.slider.setValue(-750)
            assert dialog.windowModality() == Qt.WindowModality.NonModal
            assert gui.app.activeModalWidget() is None
            assert controller.is_current()
            np.testing.assert_array_equal(w.frame.positions, original.positions)
            dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        except BaseException as exc:
            errors.append(exc)
            for dialog in gui.app.topLevelWidgets():
                if isinstance(dialog, RotationDialog): dialog.reject()

    QTimer.singleShot(20, exercise)
    assert w.rotate_about_selected_axis()
    if errors:
        raise errors[0]
    assert len(w.undo_stack) == 1
    np.testing.assert_allclose(w.frame.positions,
                               plan_axis_rotation(original, [1, 2], -75).positions)


def test_source_edit_immediately_before_accept_is_rejected_by_modeless_guard(gui):
    w = prepare(gui)
    source = w.frame
    expected = source.positions.copy()
    expected[0] += [1, 2, 3]
    errors = []

    def exercise():
        try:
            dialog = next(d for d in gui.app.topLevelWidgets()
                          if isinstance(d, RotationDialog) and d.isVisible())
            dialog.slider.setValue(900)
            source.positions[:] = expected
            dialog.accept()  # Guard must reject even before the polling timer.
        except BaseException as exc:
            errors.append(exc)
            for dialog in gui.app.topLevelWidgets():
                if isinstance(dialog, RotationDialog): dialog.reject()

    QTimer.singleShot(20, exercise)
    with patch('lele.dialog_policy.QMessageBox.information'):
        assert not w.rotate_about_selected_axis()
    if errors:
        raise errors[0]
    np.testing.assert_array_equal(source.positions, expected)
    assert w.renderer.source_frame is source and not w.undo_stack


def test_switching_documents_and_redrawing_does_not_redraw_or_restore_old_source(gui):
    w = prepare(gui)
    source = w.frame
    original = source.positions.copy()
    dialog, controller = preview(gui, w)
    other = molecule(); other.positions += [6, 4, 1]
    w.documents.append(Document(Path('other.xyz'), 'XYZ', [other]))
    w.current_doc = 1
    w.refresh_scene()
    assert w.renderer.source_frame is other
    with patch.object(w, 'refresh_scene', wraps=w.refresh_scene) as refresh:
        assert not finish(dialog, controller, True)
    refresh.assert_not_called()
    np.testing.assert_array_equal(source.positions, original)
    assert w.renderer.source_frame is other and not w.undo_stack


def test_external_geometry_commit_survives_preview_cancel_with_its_own_undo(gui):
    w = prepare(gui)
    original = w.frame.clone()
    dialog, controller = preview(gui, w)
    dialog.slider.setValue(900)
    assert w.apply_axis_rotation(20.)
    expected = plan_axis_rotation(original, [1, 2], 20.).positions
    assert not finish(dialog, controller, True)
    np.testing.assert_allclose(w.frame.positions, expected)
    assert len(w.undo_stack) == 1
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions, original.positions)


@pytest.mark.parametrize('change', ['rules', 'rules_only', 'bond_model'])
def test_inferred_graph_rule_changes_invalidate_preview_even_without_snapshot_change(gui, change):
    from lele.element_rules import default_rule, install_rules
    frame = Frame(['C'] * 4, [[0, 0, 0], [1.4, 0, 0], [2.8, 0, 0], [2.8, 1.4, 0]])
    w = prepare(gui, frame, selection=(0, 1))
    original = frame.positions.copy()
    dialog, controller = preview(gui, w)
    assert controller.edit is not None and frame.bond_snapshot is None
    if change == 'rules':
        install_rules(frame, [{**default_rule(), 'a1': 'C', 'a2': 'C', 'maximum': 3.}])
    elif change == 'rules_only':
        frame.info['pair_rules_only'] = True
    else:
        frame.info['bond_model'] = 'Covalent radii'
    assert frame.bond_snapshot is None
    assert not controller.is_current()
    assert controller.frame_for_scene(frame) is frame
    assert not finish(dialog, controller, True)
    np.testing.assert_array_equal(frame.positions, original)
    assert not w.undo_stack and frame.bond_snapshot is None


def test_second_rotation_dialog_replaces_preview_without_committing_first(gui):
    w = prepare(gui, selection=(0, 1, 2, 3))
    original = w.frame.positions.copy()
    first, old = preview(gui, w)
    second, current = preview(gui, w, dihedral=True)
    try:
        assert old.closed and not first.isVisible()
        assert w._rotation_preview is current
        second.slider.setValue(-350)
        assert not old.finish(True)
        assert w.renderer.source_frame is current.display_frame
        np.testing.assert_array_equal(w.frame.positions, original)
    finally:
        finish(first, old)
        finish(second, current)
    assert not w.undo_stack


def test_dihedral_numeric_and_slider_preview_target_then_cancel(gui):
    w = prepare(gui, selection=(0, 1, 2, 3))
    original = w.frame.clone()
    dialog, controller = preview(gui, w, dihedral=True)
    try:
        dialog.angle.setValue(-65.1234)
        assert measure(w.renderer.frame, w.selection)[1] == pytest.approx(-65.1234)
        dialog.slider.setValue(350)
        assert measure(w.renderer.frame, w.selection)[1] == pytest.approx(35.)
        np.testing.assert_array_equal(w.frame.positions, original.positions)
    finally:
        finish(dialog, controller)
    np.testing.assert_array_equal(w.frame.positions, original.positions)


def test_ambiguous_ring_disables_accept_and_does_not_change_scene(gui):
    frame = molecule(); frame.bond_snapshot |= {(0, 3)}
    w = prepare(gui, frame)
    original = w.frame.positions.copy()
    dialog, controller = preview(gui, w)
    assert 'ring' in dialog.preview_error.text().lower()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert not finish(dialog, controller, True)
    np.testing.assert_array_equal(w.frame.positions, original)
    assert not w.undo_stack
