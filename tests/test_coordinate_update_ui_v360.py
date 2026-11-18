"""Apply input templates through the live multi-document Qt workflow."""
from pathlib import Path
from unittest.mock import patch

import numpy as np

from lele.core import Document, Frame
from lele.coordinate_update import prepare_coordinate_update
from lele.coordinate_update_actions import CoordinateUpdateDialog
from lele.saved_fragments import add_fragment, fragments
from test_periodic_fragment_ui_v171 import gui


INPUT = '%mem=2GB\n# hf/sto-3g\n\nkeep this title\n\n0 1\nO 0 0 0\nH 0 0 1\nH 0 1 0\n\n'


def setup_documents(gui, tmp_path, *, duplicate=False):
    w = gui.window
    w.documents = []
    w.current_doc = -1
    w._view_document = w._scene_document = None
    w._document_views.clear()
    w.files_tree.clear()
    w._frame_tree_items.clear()
    path = tmp_path / 'target.gjf'
    path.write_text(INPUT)
    w._open_path_now(path)
    target = w.doc
    if duplicate:
        w._open_path_now(path)
    source = Document(tmp_path / 'edited.xyz', 'XYZ', [Frame(['O', 'H', 'H'], [[1, 2, 3], [1, 2, 4], [1, 3, 3]])])
    w._attach_loaded_document(source)
    return w, path, target, source


def test_apply_updates_loaded_target_without_changing_active_source_or_parameters(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path, duplicate=True)
    original = path.read_bytes()
    plan = prepare_coordinate_update(path, source.frames[0])
    assert w.apply_coordinate_update(plan, target)
    assert w.doc is source and w.files_tree.topLevelItemCount() == 3
    for document in w.documents[:2]:
        np.testing.assert_allclose(document.frames[0].positions, source.frames[0].positions)
        assert not document.modified
        assert document.path == path
    assert path.read_text().startswith('%mem=2GB\n# hf/sto-3g\n\nkeep this title\n\n0 1\n')
    assert path.with_name('target.gjf.lele.bak').read_bytes() == original
    w.change_frame(0, switch_doc=0)
    assert w.atom_table.item(0, 1).text().startswith('1.000')
    assert w.doc is target and w.atom_table.rowCount() == len(source.frames[0].symbols)
    assert w.apply_coordinates_action.isEnabled()


def test_self_apply_retains_named_fragments_and_refreshes_selection(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path)
    w.change_frame(0, switch_doc=0)
    w.frame.positions += [2, 0, 0]
    add_fragment(w.frame, [0, 2])
    w.selection = [0, 2]
    w.refresh_scene()
    plan = prepare_coordinate_update(path, w.frame)
    assert w.apply_coordinate_update(plan, target)
    assert w.doc is target
    assert fragments(w.frame) == [{'name': 'fragment1', 'indices': [0, 2]}]
    assert w.selection_panel.model.indices == [0, 2]
    model = w.selection_panel.model
    assert '2.00000000' == model.data(model.index(0, model.headers.index('Cartesian X')))


def test_stale_plan_keeps_external_edit_and_loaded_document(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path)
    plan = prepare_coordinate_update(path, w.frame)
    before = target.frames[0].positions.copy()
    path.write_text(INPUT.replace('%mem=2GB', '%mem=8GB'))
    with patch('lele.coordinate_update_actions.QMessageBox.warning') as warning:
        assert not w.apply_coordinate_update(plan, target)
    assert warning.call_count == 1
    assert path.read_text().startswith('%mem=8GB')
    np.testing.assert_array_equal(target.frames[0].positions, before)


def test_dialog_shows_diff_and_cancel_does_not_write(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path)
    original = path.read_bytes()
    dialog = CoordinateUpdateDialog([target], w.frame, w)
    assert dialog.plan is not None and dialog.apply_button.isEnabled()
    assert '(updated)' in dialog.preview.toPlainText()
    dialog.reject()
    assert path.read_bytes() == original
    assert not list(tmp_path.glob('*.bak*'))


def test_unsupported_geometry_disables_apply_without_touching_file(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path)
    path.write_text(INPUT + '--Link1--\n' + INPUT)
    original = path.read_bytes()
    dialog = CoordinateUpdateDialog([target], w.frame, w)
    assert dialog.plan is None and not dialog.apply_button.isEnabled()
    assert dialog.summary.text()
    assert path.read_bytes() == original
    dialog.reject()


def test_coordinate_dialog_pauses_trajectory_and_disposes_cancelled_preview(gui, tmp_path):
    from PySide6.QtWidgets import QDialog
    w, path, target, source = setup_documents(gui, tmp_path)
    w.playback.setInterval(100000)
    w.playback.start()
    disposed = []
    class CancelDialog:
        plan = None
        def __init__(self, candidates, frame, parent):
            assert not w.playback.isActive()
            assert candidates == [target]
            assert frame is source.frames[0]
        def exec(self): return QDialog.DialogCode.Rejected
        def deleteLater(self): disposed.append(True)
    with patch('lele.coordinate_update_actions.CoordinateUpdateDialog', CancelDialog):
        assert not w.apply_new_coordinates_dialog()
    assert disposed == [True] and w.playback.isActive()
    w.playback.stop()


def test_reader_validation_error_is_shown_without_enabling_apply(gui, tmp_path):
    w, path, target, source = setup_documents(gui, tmp_path)
    with patch('lele.coordinate_update.prepare_coordinate_update', side_effect=RuntimeError('Unsupported input detail')):
        dialog = CoordinateUpdateDialog([target], w.frame, w)
    assert dialog.plan is None and not dialog.apply_button.isEnabled()
    assert dialog.summary.text() == 'Unsupported input detail'
    assert path.read_text() == INPUT
    dialog.reject()
