"""Loaded-file actions preserve surviving views and never rename/delete files."""
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt
from shiboken6 import isValid

from lele.core import Document, Frame
from lele.loaded_documents import remap_undo_after_unload
from test_periodic_fragment_ui_v171 import gui


def add_files(gui, tmp_path, count=3):
    w = gui.window
    w._add_document_tree(0, w.doc)
    docs = []
    for i in range(count):
        path = tmp_path / f'source_{i}.xyz'
        path.write_text('1\n\nHe 0 0 0\n')
        doc = Document(path, 'XYZ', [Frame(['He'], [[i, 0, 0]]), Frame(['He'], [[i, 1, 0]])])
        w._attach_loaded_document(doc)
        docs.append(doc)
    return w, docs


def test_context_menu_rename_is_display_only_and_project_retains_name(gui, tmp_path):
    from lele.project_file import load_project, save_project
    w, docs = add_files(gui, tmp_path, 1)
    doc = docs[0]
    original = doc.path.read_bytes()
    menu = w._loaded_file_menu(doc)
    assert [a.text() for a in menu.actions() if not a.isSeparator()] == [
        'Associate file…', 'Associate unit cell…', 'Rename…', 'Remove from loaded files', 'Open containing folder']
    assert w._rename_loaded_document(doc, 'Density surface')
    assert w.files_tree.topLevelItem(1).text(0).startswith('Density surface  (')
    assert doc.path.name == 'source_0.xyz' and doc.path.read_bytes() == original
    assert not w._rename_loaded_document(doc, '   ')
    state = w._project_state()
    assert state['documents'][1]['display_name'] == 'Density surface'
    project = tmp_path / 'named.lele'
    save_project(project, state)
    assert load_project(project)['documents'][1]['display_name'] == 'Density surface'
    count = len(w.documents)
    assert w._load_project_path(project)
    assert w.files_tree.topLevelItem(count + 1).text(0).startswith('Density surface  (')
    menu.deleteLater()


def test_unload_inactive_reindexes_lazy_tree_and_retains_active_view_selection_undo(gui, tmp_path):
    w, docs = add_files(gui, tmp_path)
    active = docs[-1]
    w.change_frame(1, switch_doc=3)
    w.render_options.background = '#123456'
    gui.select([0])
    w._record_selection_undo()
    camera = w.scene.GetActiveCamera()
    camera.SetPosition(8, 7, 6)
    tree_item = w.files_tree.currentItem()
    assert tree_item.data(0, Qt.ItemDataRole.UserRole)[0] == 3
    assert w._unload_document(docs[0])
    assert docs[0].path.exists()
    assert w.doc is active and w.current_doc == 2 and w.frame_index == 1
    assert w.selection == [0] and w.render_options.background == '#123456'
    assert camera.GetPosition() == (8, 7, 6)
    assert w.undo_stack[-1][1] == 2
    assert w.files_tree.currentItem().data(0, Qt.ItemDataRole.UserRole)[0] == 2
    # A surviving child must point at the same source after index compaction.
    item = w._frame_tree_items[1, 0]
    w.files_tree.setCurrentItem(item)
    assert w.doc is docs[1] and w.frame_index == 0


def test_unload_active_restores_next_saved_frame_then_last_returns_welcome(gui, tmp_path):
    w, docs = add_files(gui, tmp_path, 2)
    first, second = docs
    w.change_frame(0, switch_doc=1)
    w.render_options.background = '#abcdef'
    w.change_frame(1, switch_doc=2)
    from lele.dialog_policy import QDialog
    result_window = w._show_analysis_window(QDialog(w))
    assert result_window.isVisible()
    assert w._unload_document(second)
    assert not isValid(result_window) or not result_window.isVisible()
    assert w.doc is first and w.frame_index == 0
    assert w.render_options.background == '#abcdef'
    for doc in list(w.documents):
        assert w._unload_document(doc)
    assert not w.documents and w.current_doc == -1 and w.doc is None and w.frame is None
    assert w.files_tree.topLevelItemCount() == 0
    assert w.canvas_stack.currentWidget() is w.welcome_page
    assert not w.save_project_action.isEnabled() and not w.export_png_all_action.isEnabled()
    assert not w.playback.isActive() and not w.vibration_timer.isActive()
    assert all(doc.path.exists() for doc in docs)
    # Opening a new file after an empty session must not restore a removed view.
    w._attach_loaded_document(first)
    assert w.doc is first and w.files_tree.topLevelItemCount() == 1


def test_open_folder_uses_source_directory_without_shell_command(gui, tmp_path):
    w, docs = add_files(gui, tmp_path, 1)
    with patch('lele.loaded_documents.QDesktopServices.openUrl', return_value=True) as opened:
        assert w._open_document_folder(docs[0])
    assert opened.call_args.args[0].toLocalFile() == str(tmp_path)


def test_undo_remap_handles_vibration_references_and_all_supported_kinds():
    frame = object()
    rows = [
        (0, 4, frame, None, [0], None, None),
        (2, 4, frame, None, [0], None, (2, 1, 0)),
        ('selection', 2, 4, [0], (2, 1, 0)),
        ('appearance', 2, 4, [0], (2, 1, 0), [('preview', (2, 1), {})]),
        ('annotation', 2, 4, [], None),
        ('pair_rules', 2, [], False, [], False, 4, (2, 1, 0), [0]),
    ]
    changed = remap_undo_after_unload(rows, 0)
    assert len(changed) == 5
    assert changed[0][0] == 1 and changed[0][6] == (1, 1, 0)
    assert changed[1][1] == 1 and changed[1][4] == (1, 1, 0)
    assert changed[2][5][0][1] == (1, 1)
    assert changed[3][1] == 1
    assert changed[4][1] == 1 and changed[4][7] == (1, 1, 0)
