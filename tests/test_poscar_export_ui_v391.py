"""POSCAR naming and explicit export-only element grouping through the GUI."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtWidgets import QMessageBox
from lele.core import Frame
from lele.export_paths import structure_export_path
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('target', ['poscar-direct', 'poscar-cartesian'])
@pytest.mark.parametrize('name,expected', [
    ('sample', 'POSCARsample'), ('POSCAR', 'POSCAR'),
    ('POSCAR42', 'POSCAR42'), ('poscar42', 'POSCAR42'),
    ('PosCar_test', 'POSCAR_test'), ('sample.v1', 'POSCARsample.v1'),
])
def test_poscar_prefix_preserves_directory_and_remainder(tmp_path, target, name, expected):
    actual = structure_export_path(tmp_path / name, target)
    assert actual == tmp_path / expected


def sample():
    return Frame(['O', 'C', 'O', 'H', 'C'],
        [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0]],
        np.eye(3) * 12, (True,) * 3,
        info={'poscar_groups': [('O', 1), ('C', 1), ('O', 1), ('H', 1), ('C', 1)],
              'saved_fragments': [{'name': 'fragment1', 'indices': [1, 2]}]})


@pytest.mark.parametrize('mode', ['Direct', 'Cartesian'])
@pytest.mark.parametrize('merge', [True, False])
def test_gui_export_asks_and_writes_expected_group_order(gui, tmp_path, mode, merge):
    frame = sample()
    gui.attach(frame)
    w = gui.window
    original_selection = [1, 2]
    gui.select(original_selection)
    before = deepcopy(frame.info)
    destination = tmp_path / 'sample'
    with patch('lele.app.QInputDialog.getItem', return_value=(f'POSCAR {mode} (POSCAR)', True)), \
         patch('lele.app.QFileDialog.getSaveFileName', return_value=(str(destination), '')) as picker, \
         patch('lele.structure_edit_dialogs.choose_poscar_grouping', return_value=merge) as question, \
         patch('lele.app.QMessageBox.warning') as warning:
        w.export_dialog()
    warning.assert_not_called()
    question.assert_called_once_with(w)
    assert Path(picker.call_args.args[2]).name.startswith('POSCAR')
    path = tmp_path / 'POSCARsample'
    restored = load_document(path).frames[0]
    order = [0, 2, 1, 4, 3] if merge else list(range(5))
    assert restored.symbols == [frame.symbols[i] for i in order]
    np.testing.assert_allclose(restored.positions, frame.positions[order], atol=1e-10)
    assert path.read_text().splitlines()[5].split() == (['O', 'C', 'H'] if merge else frame.symbols)
    assert not destination.exists()
    assert w.frame is frame and frame.info == before
    assert w.selection == original_selection and not w.doc.modified


def test_cancel_after_normalized_overwrite_confirmation_preserves_file(gui, tmp_path):
    gui.attach(sample())
    output = tmp_path / 'POSCARsample'
    output.write_text('existing contents')
    with patch('lele.app.QInputDialog.getItem', return_value=('POSCAR Direct (POSCAR)', True)), \
         patch('lele.app.QFileDialog.getSaveFileName', return_value=(str(tmp_path / 'sample'), '')), \
         patch('lele.app.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes) as question, \
         patch('lele.structure_edit_dialogs.choose_poscar_grouping', return_value=None) as grouping, \
         patch('lele.formats.export_frame') as export:
        gui.window.export_dialog()
    assert [call.args[1] for call in question.call_args_list] == ['Replace file?']
    grouping.assert_called_once_with(gui.window)
    export.assert_not_called()
    assert output.read_text() == 'existing contents'


def test_declining_normalized_overwrite_does_not_open_merge_prompt(gui, tmp_path):
    gui.attach(sample())
    output = tmp_path / 'POSCARsample'
    output.write_text('existing contents')
    with patch('lele.app.QInputDialog.getItem', return_value=('POSCAR Direct (POSCAR)', True)), \
         patch('lele.app.QFileDialog.getSaveFileName', return_value=(str(tmp_path / 'sample'), '')), \
         patch('lele.app.QMessageBox.question', return_value=QMessageBox.StandardButton.No) as question:
        gui.window.export_dialog()
    question.assert_called_once()
    assert output.read_text() == 'existing contents'


@pytest.mark.parametrize('caption,expected', [('Merge all', True), ('Merge adjacent', False), ('Cancel', None)])
def test_named_grouping_buttons(gui, caption, expected):
    from PySide6.QtCore import QTimer
    from lele.structure_edit_dialogs import choose_poscar_grouping

    def click_button():
        message = next(box for box in gui.window.findChildren(QMessageBox) if box.isVisible())
        next(button for button in message.buttons() if button.text().replace('&', '') == caption).click()

    QTimer.singleShot(0, click_button)
    assert choose_poscar_grouping(gui.window) is expected
