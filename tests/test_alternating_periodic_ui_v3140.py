"""Counts grow around the unchanged source; real-cell edits remain undoable."""
from unittest.mock import patch

import numpy as np

from lele.core import Frame
from lele.boundary_panel import BoundaryPanel
from lele.supercell_dialog import SupercellDialog
from test_periodic_fragment_ui_v171 import gui


def source():
    cell=np.array([[4.,0.,0.],[.7,5.,0.],[.2,.3,6.]])
    return Frame(['Si'],np.array([[.2,.3,.4]])@cell,cell,(True,)*3)


def test_boundary_counts_alternate_and_manual_ranges_remain_available(gui):
    panel=BoundaryPanel();panel.setEnabled(True)
    try:
        assert panel.preserve.isChecked() and panel.growth.currentIndex()==0
        for count,bounds in ((2,(0,2)),(3,(-1,2)),(4,(-1,3))):
            panel.repeat_spins[0].setValue(count)
            assert panel.bounds()[0]==bounds
        panel.growth.setCurrentIndex(1)
        panel.spins[0][0].setValue(-3);panel.spins[0][1].setValue(1)
        assert panel.bounds()[0]==(-3,1)
        assert panel.spins[0][0].isEnabled()
        panel.set_values(True,((-2,3),(0,1),(0,1)),False)
        assert panel.repeat_spins[0].value()==5 and panel.growth.currentIndex()==0
        assert not panel.preserve.isChecked()
        for bounds in (((-12,13),(0,1),(0,1)),((-100,101),(0,1),(0,1)),((200,205),(0,1),(0,1))):
            panel.set_values(True,bounds,True)
            assert panel.bounds()==bounds
        assert panel.growth.currentIndex()==1
    finally:panel.deleteLater()


def test_supercell_dialog_defaults_and_build_action_pass_alternating(gui):
    gui.attach(source())
    window=gui.window
    dialog=SupercellDialog(window.frame,parent=window)
    try:
        assert dialog.growth()=='alternating'
        assert not dialog.wrap.isChecked() and not dialog.wrap.isEnabled()
        dialog.spins[0].setValue(3)
        assert 'a: 0, +1, -1' in dialog.preview.text()
        with patch('lele.supercell_dialog.SupercellDialog',return_value=dialog), \
             patch.object(dialog,'exec',return_value=dialog.DialogCode.Accepted), \
             patch.object(window,'apply_supercell') as apply:
            window.build_supercell()
        apply.assert_called_once_with(dialog.repeats(),wrap=False,growth='alternating')
        dialog.growth_combo.setCurrentIndex(1)
        assert dialog.growth()=='forward' and dialog.wrap.isChecked() and dialog.wrap.isEnabled()
    finally:dialog.deleteLater()


def test_negative_real_supercell_render_origin_and_undo(gui):
    original=source();gui.attach(original)
    window=gui.window
    positions=original.positions.copy();cell=original.cell.copy()
    assert window.apply_supercell((3,1,1),growth='alternating',wrap=False)
    np.testing.assert_array_equal(window.frame.positions[:1],positions)
    np.testing.assert_array_equal(window.renderer.boundary_display.frame.positions[:3],window.frame.positions)
    lines=np.asarray(window.renderer.boundary_display.cell_lines)
    fractions=lines.reshape(-1,3)@np.linalg.inv(cell)
    np.testing.assert_allclose(fractions.min(axis=0),[-1,0,0],atol=1.e-10)
    np.testing.assert_allclose(fractions.max(axis=0),[2,1,1],atol=1.e-10)
    window.render_options.boundary_enabled=False
    window.refresh_scene()
    captured=[]
    with patch.object(window.renderer,'_tube_segments',side_effect=lambda edges,width:captured.extend(edges)):
        window.renderer._cell(window.renderer.frame)
    np.testing.assert_allclose(np.asarray([p for edge in captured for p in edge[:2]])@np.linalg.inv(cell),
        lines.reshape(-1,3)@np.linalg.inv(cell),atol=1.e-10)
    window.undo_edit()
    np.testing.assert_array_equal(window.frame.positions,positions)
    np.testing.assert_array_equal(window.frame.cell,cell)
    assert 'cell_origin_fractional' not in window.frame.info


def test_boundary_growth_preserves_current_camera_and_original_atom(gui):
    frame=source();gui.attach(frame)
    window=gui.window
    camera=window.scene.GetActiveCamera()
    before=(camera.GetPosition(),camera.GetFocalPoint(),camera.GetViewUp(),camera.GetParallelScale())
    window.boundary_panel.repeat_spins[0].setValue(3)
    window.boundary_panel.apply.click()
    assert window.renderer.boundary_display.tiles==((0,0,0),(1,0,0),(-1,0,0))
    np.testing.assert_array_equal(window.renderer.boundary_display.frame.positions[:1],frame.positions)
    after=(camera.GetPosition(),camera.GetFocalPoint(),camera.GetViewUp(),camera.GetParallelScale())
    assert after==before
