"""Cross-feature entry points and safe pointer-mode transitions."""
import numpy as np
from lele.core import Frame, Volume
from test_periodic_fragment_ui_v171 import gui


def test_single_crystal_menu_entry_under_edit_and_neb_entry(gui):
    w = gui.window
    edit = [a.text() for a in w.edit_menu.actions()]
    view = [a.text() for a in w.view_menu.actions()]
    assert edit.count('Crystal tools…') == 1
    assert not {'Crystal tools…', 'Lattice planes / cuts…', 'Coordination polyhedra…'} & set(view)
    assert w.crystal_action.isEnabled()
    assert w.vasp_neb_action in w.analysis_menu.actions()


def test_none_to_visible_enables_hide_and_delete_does_not_remove_atoms(gui):
    w = gui.window
    data = np.indices((8, 8, 8))[0].astype(float) / 7 - .5
    field = Volume(data, [0, 0, 0], np.eye(3) / 7)
    frame = Frame(['H', 'H', 'H'], [[0, 0, .5], [1, 0, .5], [0, 1, .5]])
    gui.attach(frame, volume=field)
    w.field_signs.setCurrentText('None')
    assert not w.renderer.field_actors and not w.surface_hide_check.isEnabled()
    w.field_signs.setCurrentText('Both')
    assert w.renderer.field_actors and w.surface_hide_check.isEnabled()
    gui.select([0, 1, 2])
    w.surface_hide_check.setChecked(True)
    w.vtk.setFocus()
    w._delete_shortcut()
    assert len(w.frame.symbols) == 3 and w.doc.volume is field
    w.box_select_action.setChecked(True)
    assert not w.surface_hide_check.isChecked()
    w.surface_hide_check.setChecked(True)
    assert not w.box_select_action.isChecked()
    w.cancel_pointer_action()
    assert not w.surface_hide_check.isChecked() and not w.box_select_action.isChecked()
