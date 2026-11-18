"""Sidebar menus return the full top row to the canvas without losing actions."""
import numpy as np
from PySide6.QtCore import QPoint
from lele.core import Frame
from lele.render_options import RenderOptions
from lele.style_presets import BUILTIN_PRESETS
from test_periodic_fragment_ui_v171 import gui


def test_menu_is_inside_sidebar_and_canvas_starts_at_the_top(gui):
    w=gui.window;w.resize(1250,800);w.show();gui.app.processEvents()
    assert w.menuWidget() is None
    assert w.menuBar().parentWidget() is w.sidebar_column
    assert [a.text().replace('&','') for a in w.menuBar().actions()] == ['File','Edit','View','Analysis','Help']
    assert w.menuBar().width() == w.sidebar_tabs.width() == w.sidebar_column.width()
    canvas_top=w.canvas_stack.mapTo(w,QPoint(0,0)).y()
    menu_top=w.menuBar().mapTo(w,QPoint(0,0)).y()
    assert canvas_top == menu_top
    assert w.sidebar_tabs.mapTo(w,QPoint(0,0)).y() >= menu_top+w.menuBar().height()
    w.centralWidget().setSizes([380,850]);gui.app.processEvents()
    assert w.menuBar().width() == w.sidebar_tabs.width()
    assert w.canvas_stack.mapTo(w,QPoint(0,0)).y() == menu_top


def test_default_size_controls_are_two_and_one_steps_smaller(gui):
    options=RenderOptions();preset=BUILTIN_PRESETS['Classic ball and stick']
    assert options.atom_scale == preset['atom_scale'] == .45
    assert options.bond_scale == preset['bond_scale'] == .05
    assert gui.window.atom_slider.value()==45
    assert gui.window.bond_slider.value()==5
    assert options.bond_cutoff == .88


def test_alternating_supercell_keeps_coordinates_and_camera_then_undoes(gui):
    source=Frame(['C','O'], [[.8,1.,1.],[2.,1.,1.]],np.eye(3)*5,(True,True,True))
    gui.attach(source)
    w=gui.window
    w.scene.GetActiveCamera().SetPosition(12.,8.,9.)
    w.scene.GetActiveCamera().SetFocalPoint(0.,0.,0.)
    camera=w.scene.GetActiveCamera().GetPosition()
    assert w.apply_supercell((3,1,1),growth='alternating')
    np.testing.assert_array_equal(w.frame.positions[:2],source.positions)
    np.testing.assert_allclose(w.frame.positions[2:4],source.positions+[5,0,0])
    np.testing.assert_allclose(w.frame.positions[4:6],source.positions-[5,0,0])
    assert w.scene.GetActiveCamera().GetPosition()==camera
    assert w.scene.GetActiveCamera().GetFocalPoint()==(0.,0.,0.)
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions,source.positions)
    np.testing.assert_array_equal(w.frame.cell,source.cell)
