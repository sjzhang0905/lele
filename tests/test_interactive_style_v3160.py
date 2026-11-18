from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from vtkmodules.util.numpy_support import vtk_to_numpy

from lele.core import Frame, Volume
from lele.fragment import apply_fragment_rotation, screen_rotation
from lele.style_presets import DEFAULT_ELEMENT_COLORS, element_palette_color
from lele.window_caption import PanelCaption, caption_colors
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('periodic', [False, True])
def test_roll_updates_existing_atoms_bonds_and_labels_once_per_paint(gui, periodic):
    frame = Frame(['O', 'H', 'H', 'He'], [[1.,1.,1.], [1.94,1.,1.], [.8,1.9,1.], [5.,5.,5.]],
                  np.eye(3)*8, (periodic,)*3)
    frame.hbond_added[(1, 3)] = (0,0,0)
    field = Volume(np.indices((5,5,5))[0]-2., np.zeros(3), np.eye(3))
    gui.attach(frame, volume=field)
    w = gui.window
    w.render_options.labels = 'Index (1..N)'
    if periodic:
        w.render_options.boundary_bounds = ((-1,2),(0,1),(0,1))
    gui.select([0])
    renderer = w.renderer
    actors = list(renderer.field_actors)
    assert len(actors) == 2
    cell = frame.cell.copy()
    original = frame.clone()
    source_ids = renderer.boundary_display.source_indices if periodic else np.arange(4)
    atom_start = [vtk_to_numpy(points.GetData()).copy() for points, _ in renderer.drag_atom_points]
    line_start = [vtk_to_numpy(points.GetData()).reshape(-1,2,3).copy() for points, _, _ in renderer.drag_bond_points]
    label_start = np.asarray(renderer._label_positions)
    expected = frame.clone()
    pivot = np.mean(frame.positions[:3], axis=0)
    apply_fragment_rotation(expected, [0,1,2], screen_rotation(w.scene.GetActiveCamera(), 'roll', 18, 0), pivot)
    with patch.object(w, 'refresh_scene', wraps=w.refresh_scene) as refresh:
        w._fragment_begin('roll', 0, 0)
        with patch.object(renderer, 'set_scene', side_effect=AssertionError('rebuilt scene during rotation')):
            for _ in range(6):
                w._fragment_move('roll', 3., 0.)
            preview = w._fragment_gesture['preview']
            with patch.object(preview, 'update', wraps=preview.update) as paint:
                gui.app.processEvents()
                assert paint.call_count == 1
            delta = expected.positions - original.positions
            np.testing.assert_allclose(frame.positions, expected.positions, atol=2e-12)
            for (points, ids), start in zip(renderer.drag_atom_points, atom_start):
                np.testing.assert_allclose(vtk_to_numpy(points.GetData()), start+delta[source_ids[ids]], atol=2e-6)
            for (points, pairs, fractions), start in zip(renderer.drag_bond_points, line_start):
                ids = source_ids[pairs]
                left, right = delta[ids[:,0],None,:], delta[ids[:,1],None,:]
                np.testing.assert_allclose(vtk_to_numpy(points.GetData()).reshape(-1,2,3),
                                           start+left+fractions[:,:,None]*(right-left), atol=2e-6)
            np.testing.assert_allclose(renderer._label_positions, label_start+delta[source_ids[renderer.label_indices]])
            assert renderer.field_actors == actors and refresh.call_count == 0
            assert len(w.undo_stack) == 1
        w._fragment_end('roll')
        assert preview.closed and refresh.call_count == 1
    np.testing.assert_array_equal(frame.cell, cell)
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions, original.positions)


def test_release_flushes_geometry_when_paint_still_queued(gui):
    w = gui.window
    gui.attach(Frame(['C', 'H'], [[0,0,0],[1,0,0]]))
    gui.select([0])
    expected = w.frame.clone()
    apply_fragment_rotation(expected, [0, 1], screen_rotation(w.scene.GetActiveCamera(), 'roll', 33, 0),
                            expected.positions.mean(axis=0))
    with patch.object(w, 'refresh_scene', wraps=w.refresh_scene) as redraw:
        w._fragment_begin('roll', 0, 0)
        w._fragment_move('roll', 33, 0)
        w._fragment_end('roll')
        gui.app.processEvents()
        assert redraw.call_count == 1
    np.testing.assert_allclose(w.frame.positions, expected.positions, atol=1e-12)
    assert len(w.undo_stack) == 1


def test_slider_centers_keyboard_and_exact_cutoff_roundtrip(gui):
    w = gui.window
    for slider, physical, low, high in ((w.atom_slider,45,20,180),(w.bond_slider,5,3,35),(w.cutoff_slider,88,10,500)):
        assert slider.value() == physical
        assert 2*slider.track.value() == slider.track.maximum() + slider.track.minimum()
        slider.track.setValue(slider.track.minimum())
        assert slider.value() == low
        slider.track.setValue(slider.track.maximum())
        assert slider.value() == high
        slider.setValue(physical)
        QTest.keyClick(slider.track, Qt.Key.Key_Left)
        assert slider.value() < physical
        QTest.keyClick(slider.track, Qt.Key.Key_Right)
        assert slider.value() == physical
    w.bond_slider.track.setValue(w.bond_slider.HALF//2)
    assert w.render_options.bond_scale == pytest.approx(.04)
    for percent in range(10, 501):
        w.cutoff_slider.setValue(percent)
        assert w.cutoff_slider.value() == percent and w.cutoff_spin.value() == percent/100
    w.style_combo.setCurrentText('Space filling')
    assert w.atom_slider.value() == 100 and w.atom_slider.track.value() == w.atom_slider.HALF


def test_default_common_elements_and_overrides_reach_draw_and_selection_tab(gui):
    from lele.sibyl_palette import SIBYL_COLORS
    from lele.style_presets import mix_color
    protected = {'C':'#ADADAD','H':'#DADADA','O':'#EC4646','N':'#5858EC'}
    old = {mix_color(mix_color(mix_color(c,.10),.05),.15) for c in SIBYL_COLORS.values()}
    assert not set(DEFAULT_ELEMENT_COLORS.values()).intersection(old)
    assert len(set(DEFAULT_ELEMENT_COLORS.values())) == len(DEFAULT_ELEMENT_COLORS)
    w = gui.window
    gui.attach(Frame(['Fe', 'Ni'], [[0,0,0],[2,0,0]]))
    for symbol, color in {**protected, **DEFAULT_ELEMENT_COLORS}.items():
        assert element_palette_color(w.render_options, symbol) == color
        assert element_palette_color(w.render_options, symbol, for_bond=True) == color
    assert w.atoms_selection_panel._swatches['Ni'].property('elementColor') == DEFAULT_ELEMENT_COLORS['Ni']
    w._set_option('element_colors', {'Ni':'#123456'})
    assert w.renderer.atom_color(w.frame, 1) == '#123456'
    assert w.atoms_selection_panel._swatches['Ni'].property('elementColor') == '#123456'


def test_panel_caption_tracks_title_and_window_state(gui):
    w = gui.window
    caption = PanelCaption(w)
    w.show()
    gui.app.processEvents()
    w.setWindowTitle('LELE caption test')
    assert caption.title.text() == w.windowTitle()
    background, _ = caption_colors(w.palette())
    assert background.red() == background.green() == background.blue() < 255
    assert caption.palette().color(QPalette.ColorRole.Window) == background
    assert caption.geometry().bottom() < w.centralWidget().geometry().top()
    caption.maximize.click()
    gui.app.processEvents()
    assert w.isMaximized() and caption.maximize.toolTip() == 'Restore'
    assert all(not grip.isVisible() for grip in caption.grips)
    caption.maximize.click()
    gui.app.processEvents()
    assert not w.isMaximized() and all(grip.isVisible() for grip in caption.grips)


def test_native_windows_caption_api_uses_full_handle_and_colorrefs(gui, monkeypatch):
    import ctypes
    from ctypes import wintypes
    from types import SimpleNamespace
    from unittest.mock import Mock
    from lele.window_caption import _native_colors

    calls = []
    def record(hwnd, attribute, pointer, size):
        assert size == ctypes.sizeof(wintypes.DWORD)
        calls.append((hwnd, attribute, ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value))
        return 0
    apply = Mock(side_effect=record)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(dwmapi=SimpleNamespace(DwmSetWindowAttribute=apply)), raising=False)
    handle = 2**36 + 0x2345
    window = SimpleNamespace(winId=lambda: handle, palette=gui.window.palette)
    assert _native_colors(window)
    bg, fg = caption_colors(window.palette())
    assert calls == [(handle, attr, q.red() | q.green()<<8 | q.blue()<<16) for attr, q in [(35, bg), (36, fg)]]
    apply.side_effect = lambda *args: -1
    assert not _native_colors(window)
