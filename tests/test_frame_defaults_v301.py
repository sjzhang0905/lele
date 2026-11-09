"""Opening, navigating and paginating trajectories share stable frame defaults."""
import numpy as np

from lele.core import Document, Frame
from lele.formats import load_document
from lele.workflow_ui import PAGE_SIZE
from test_periodic_fragment_ui_v171 import gui
from test_vasp_v210 import HEADER, GEOMETRY, ENERGY


def outcar(tmp_path, count=3, *, truncated=False):
    text = HEADER.replace('IBRION = 5', 'IBRION = 2')
    for i in range(count):
        text += GEOMETRY.replace('0.0 0.0 1.0 ', f'0.0 0.0 {1 + i * .2:.8f} ')
        text += ENERGY.replace('-10.1', f'{-10.1 - i * .1:.8f}')
    if truncated:
        text += ' POSITION TOTAL-FORCE\n ----\n 0 0 0 0 0 0\n' + ENERGY
    else:
        text += ' reached required accuracy - stopping structural energy minimisation\n'
    path = tmp_path / 'OUTCAR'
    path.write_text(text)
    return load_document(path)


def attach_new(gui, document):
    window = gui.window
    window.files_tree.clear()
    window.documents = []
    window.current_doc = -1
    window._attach_loaded_document(document)
    return window


def test_outcar_rows_keep_step_names_energy_and_status_when_clicked(gui, tmp_path):
    document = outcar(tmp_path)
    window = attach_new(gui, document)
    rows = [window._frame_tree_items[0, i] for i in range(3)]
    labels = [row.text(0) for row in rows]
    assert all(label.startswith(f'Step {i + 1} · ') for i, label in enumerate(labels))
    assert all(' eV' in label for label in labels)
    assert labels[-1].endswith(' · converged')
    for i, row in enumerate(rows):
        window.files_tree.setCurrentItem(row)
        assert window.frame_index == i
        np.testing.assert_array_equal(window.frame.positions, document.frames[i].positions)
        assert [item.text(0) for item in rows] == labels


def test_opening_and_file_headers_choose_last_structure_but_child_steps_still_work(gui, tmp_path):
    document = outcar(tmp_path)
    window = attach_new(gui, document)
    assert window.frame_index == 2 and window.frame_spin.value() == 3
    assert window.files_tree.currentItem() is window._frame_tree_items[0, 2]
    np.testing.assert_array_equal(window.frame.positions, document.frames[-1].positions)
    window.files_tree.setCurrentItem(window._frame_tree_items[0, 0])
    assert window.frame_index == 0
    window.files_tree.setCurrentItem(window.files_tree.topLevelItem(0))
    assert window.frame_index == 2
    other = Document(tmp_path / 'trajectory.xyz', 'XYZ',
                     [Frame(['H'], [[0, 0, z]]) for z in (0., 1.)])
    window._attach_loaded_document(other)
    assert window.current_doc == 1 and window.frame_index == 1
    window.files_tree.setCurrentItem(window.files_tree.topLevelItem(0))
    assert window.doc is document and window.frame_index == 2


def test_long_outcar_opens_last_lazy_page_without_materializing_the_whole_tree(gui, tmp_path):
    count = PAGE_SIZE * 2 + 9
    document = outcar(tmp_path, count)
    window = attach_new(gui, document)
    head = window.files_tree.topLevelItem(0)
    pages = [head.child(i) for i in range(head.childCount())]
    assert len(pages) == 3
    assert all(page.text(0).startswith('Steps ') for page in pages)
    assert [page.childCount() for page in pages] == [0, 0, 9]
    assert window.frame_index == count - 1 and window.frame_spin.value() == count
    assert window.files_tree.currentItem().text(0).startswith(f'Step {count} · ')
    np.testing.assert_array_equal(window.frame.positions, document.frames[-1].positions)


def test_plain_xyz_keeps_frame_names_and_opens_last_frame(gui, tmp_path):
    document = Document(tmp_path / 'plain.xyz', 'XYZ',
                        [Frame(['H'], [[0, 0, z]]) for z in (0., 1., 2.)])
    window = attach_new(gui, document)
    rows = [window._frame_tree_items[0, i] for i in range(3)]
    assert window.frame_index == 2
    assert [row.text(0) for row in rows] == ['Frame 1', 'Frame 2', 'Frame 3']
    for row in rows:
        window.files_tree.setCurrentItem(row)
        assert [item.text(0) for item in rows] == ['Frame 1', 'Frame 2', 'Frame 3']


def test_a_printed_zero_cycle_is_not_replaced_by_a_one_based_frame_number(gui, tmp_path):
    document = Document(tmp_path / 'zero.xyz', 'XYZ', [
        Frame(['H'], [[0, 0, i]], info={'optimization_cycle': i}) for i in (0, 1)])
    window = attach_new(gui, document)
    first = window._frame_tree_items[0, 0]
    assert first.text(0) == 'Step 0'
    window.files_tree.setCurrentItem(first)
    assert first.text(0) == 'Step 0'


def test_truncated_last_ionic_record_defaults_to_last_available_structure(gui, tmp_path):
    document = outcar(tmp_path, truncated=True)
    assert len(document.frames) == 3
    assert document.calculation_results.steps[-1].geometry is None
    window = attach_new(gui, document)
    assert window.frame_index == 2
    np.testing.assert_array_equal(window.frame.positions, document.frames[-1].positions)


def test_energy_only_outcar_still_opens_as_results_without_a_structure(gui, tmp_path):
    path = tmp_path / 'OUTCAR_energy_only'
    path.write_text(ENERGY * 3)
    document = load_document(path)
    window = attach_new(gui, document)
    assert not document.frames and window.frame is None
    assert window.canvas_stack.currentWidget() is window.results_only_page
    assert window.frame_count_label.text() == 'No structure'


def test_boundary_default_is_active_and_explicit_disable_survives_step_navigation(gui, tmp_path):
    document = outcar(tmp_path)
    window = attach_new(gui, document)
    assert window.render_options.boundary_enabled
    assert window.boundary_panel.enabled.isChecked()
    assert window.renderer.options.boundary_enabled
    assert window.renderer.boundary_display is not None
    assert window.renderer.boundary_display.tiles == ((0, 0, 0),)
    assert window.boundary_panel.bounds() == ((0, 1),) * 3
    np.testing.assert_array_equal(window.frame.positions, document.frames[-1].positions)
    window._apply_boundary(False, ((0, 1),) * 3)
    window.change_frame(0)
    assert not window.render_options.boundary_enabled
    assert not window.boundary_panel.enabled.isChecked()
    assert not window.renderer.options.boundary_enabled
