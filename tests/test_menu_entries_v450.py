from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QTreeWidgetItemIterator

from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui


def test_complete_tab_actions_removed_and_box_shortcut_still_works(gui):
    window = gui.window
    actions = {action.text() for menu in (window.edit_menu, window.view_menu, window.analysis_menu)
               for action in menu.actions()}
    assert not actions.intersection({
        'Fit selected plane','Align fitted plane to XY','Rotate about selected axis…','Set selected dihedral…',
        'Mirror selected fragment…','Modify slab vacuum…','Reorient complete structure / crystal…',
        'Box select atoms','Rotate by 45°','ORCA scan curve…','Geometry parameter curves…',
        'Trajectory display alignment…','Vibrational frequencies','NEB / NEB-TS paths…',
        'Coordination / polyhedron analysis…'})
    assert {'Crystal tools…','Build supercell…','VASP NEB from loaded outputs…','Simulate powder XRD…',
            'Assign QE phonon reference…','HOMO / LUMO and orbital energies…'} <= actions
    gui.select([0,1,2])
    assert window.fit_plane_btn.isEnabled()
    assert window.box_select_action in window.actions()
    window.show()
    window.activateWindow()
    window.files_tree.setFocus()
    gui.app.processEvents()
    QTest.keyClick(window.files_tree, Qt.Key.Key_B,
                   Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
    assert window.box_select_button.isChecked()
    QTest.keyClick(window.files_tree, Qt.Key.Key_Escape)
    assert not window.box_select_button.isChecked()
    window.hide()


@pytest.mark.parametrize('with_frames',[True,False])
def test_neb_dialog_from_files_with_and_without_coordinates(gui, with_frames):
    path = Path(__file__).resolve().parents[1]/'examples'/'synthetic_neb_v1100.out'
    document = load_document(path)
    if not with_frames:
        document.frames = []
    window = gui.window
    window._attach_loaded_document(document)
    items = QTreeWidgetItemIterator(window.files_tree)
    while items.value():
        item = items.value()
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[1:] == ('analysis','neb'):
            break
        items += 1
    assert items.value() is not None
    window.files_tree.setCurrentItem(items.value())
    dialog = window._analysis_windows[-1]
    assert 'NEB' in dialog.windowTitle() and dialog.isVisible()
    dialog.close()
