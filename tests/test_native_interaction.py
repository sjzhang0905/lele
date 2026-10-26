#!/usr/bin/env python3
"""Qt event-flow checks using a tiny Qt/QVTK substitute.

These exercise the actual InteractiveVTKView methods, not a reimplementation
of picking. They do not replace a Windows desktop acceptance test.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


class _Signal:
    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, inst, cls):
        if inst is None:
            return self
        key = '_signal_' + self.name
        if key not in inst.__dict__:
            inst.__dict__[key] = SimpleNamespace(emit=lambda *args: inst.emissions.append(args))
        return inst.__dict__[key]


class _Pos:
    def __init__(self, x, y):
        self._x, self._y = x, y
    def x(self): return self._x
    def y(self): return self._y


class _Event:
    def __init__(self, button, x, y, modifiers=0):
        self._button, self._pos = button, _Pos(x, y)
        self._modifiers = modifiers
        self.accepted = False
    def button(self): return self._button
    def modifiers(self): return self._modifiers
    def position(self): return self._pos
    def accept(self): self.accepted = True


class _Camera:
    def __init__(self):
        self.rolls = []
        self.orthogonalized = 0
    def Roll(self, angle): self.rolls.append(angle)
    def OrthogonalizeViewUp(self): self.orthogonalized += 1


class _RenderWindow:
    def __init__(self): self.render_count = 0
    def Render(self): self.render_count += 1


class _QVTK:
    def __init__(self, *_args, **_kw):
        self.calls = []
        self.emissions = []
        self.render_window = _RenderWindow()
    def setFocusPolicy(self, *_): pass
    def setFocus(self, *_): pass
    def width(self): return 600
    def height(self): return 400
    def GetRenderWindow(self): return self.render_window
    def mousePressEvent(self, e): self.calls.append(('press', e.button()))
    def mouseMoveEvent(self, e): self.calls.append(('move', e.button()))
    def mouseReleaseEvent(self, e): self.calls.append(('release', e.button()))
    def focusOutEvent(self, e): self.calls.append(('blur', None))


class NativeInteractionTests(TestCase):
    @classmethod
    def setUpClass(cls):
        qt = ModuleType('PySide6')
        core = ModuleType('PySide6.QtCore')
        core.Qt = SimpleNamespace(
            MouseButton=SimpleNamespace(LeftButton=1, RightButton=2, MiddleButton=4),
            KeyboardModifier=SimpleNamespace(AltModifier=8),
            FocusPolicy=SimpleNamespace(StrongFocus=3),
            FocusReason=SimpleNamespace(MouseFocusReason=4),
        )
        core.Signal = lambda *_: _Signal()
        adapter = ModuleType('vtkmodules.qt.QVTKRenderWindowInteractor')
        adapter.QVTKRenderWindowInteractor = _QVTK
        source = Path(__file__).resolve().parents[1] / 'lele' / 'interaction.py'
        with patch.dict(sys.modules, {
            'PySide6': qt, 'PySide6.QtCore': core,
            'vtkmodules.qt.QVTKRenderWindowInteractor': adapter,
        }):
            spec = importlib.util.spec_from_file_location('_test_interaction', source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        cls.interaction = module

    def test_screen_coordinates_with_125_percent_windows_scaling(self):
        convert = self.interaction.vtk_display_from_qt
        self.assertEqual(convert(100, 40, 400, 200, 500, 250), (125, 200))
        self.assertEqual(convert(0, 0, 400, 200, 500, 250), (0, 250))
        with self.assertRaises(ValueError):
            convert(0, 0, 0, 200, 500, 250)

    def test_left_click_emits_after_vtk_release(self):
        view = self.interaction.InteractiveVTKView()
        view.mousePressEvent(_Event(1, 100, 120))
        view.mouseReleaseEvent(_Event(1, 102, 125))
        self.assertEqual(view.calls, [('press', 1), ('release', 1)])
        self.assertEqual(view.emissions, [(102.0, 125.0)])

    def test_left_drag_does_not_pick_and_preserves_trackball(self):
        view = self.interaction.InteractiveVTKView()
        view.mousePressEvent(_Event(1, 100, 120))
        view.mouseMoveEvent(_Event(1, 130, 120))
        view.mouseReleaseEvent(_Event(1, 130, 120))
        self.assertEqual(view.emissions, [])
        self.assertEqual(len(view.calls), 3)

    def test_right_drag_rolls_without_vtk_dolly(self):
        view = self.interaction.InteractiveVTKView()
        camera = _Camera()
        view.scene_renderer = SimpleNamespace(GetActiveCamera=lambda: camera)
        start = _Event(2, 120, 130)
        move = _Event(2, 170, 130)
        done = _Event(2, 170, 130)
        view.mousePressEvent(start)
        view.mouseMoveEvent(move)
        view.mouseReleaseEvent(done)
        self.assertEqual(view.calls, [])
        self.assertTrue(start.accepted and move.accepted and done.accepted)
        self.assertEqual(len(camera.rolls), 1)
        self.assertAlmostEqual(camera.rolls[0], -32.5)
        self.assertEqual(view.render_window.render_count, 1)
        self.assertEqual(camera.orthogonalized, 1)
        self.assertIsNone(view._right_last)

    def test_right_click_clears_but_right_drag_does_not(self):
        view = self.interaction.InteractiveVTKView()
        camera = _Camera()
        view.scene_renderer = SimpleNamespace(GetActiveCamera=lambda: camera)
        view.mousePressEvent(_Event(2, 10, 10))
        view.mouseReleaseEvent(_Event(2, 10, 10))
        self.assertEqual(view.emissions, [()])
        view.emissions.clear()
        view.mousePressEvent(_Event(2, 10, 10))
        view.mouseMoveEvent(_Event(2, 50, 10))
        view.mouseReleaseEvent(_Event(2, 50, 10))
        self.assertEqual(view.emissions, [])
        self.assertEqual(len(camera.rolls), 1)
        self.assertEqual(view.calls, [])

    def test_no_duplicate_label_option_or_old_vtk_pick_observers(self):
        src = (Path(__file__).resolve().parents[1] / 'lele' / 'app.py').read_text()
        self.assertNotIn('Element + index (per element)', src)
        self.assertIn('files_tree.currentItemChanged.connect(self._tree_current_changed)', src)
        self.assertIn('self.vtk.atomClick.connect(self._pick_from_canvas)', src)
        self.assertNotIn("AddObserver('LeftButtonReleaseEvent'", src)


class FragmentGestureNativeTests(NativeInteractionTests):
    def test_alt_left_drag_does_not_change_camera(self):
        view = self.interaction.InteractiveVTKView()
        view.mousePressEvent(_Event(1, 20, 20, 8))
        view.mouseMoveEvent(_Event(1, 50, 40, 8))
        view.mouseReleaseEvent(_Event(1, 50, 40, 8))
        self.assertEqual(view.calls, [])
        self.assertEqual(view.emissions, [
            ('orbit', 20.0, 20.0), ('orbit', 30.0, 20.0), ('orbit',)])

    def test_alt_right_drag_is_not_camera_roll_or_selection_clear(self):
        view = self.interaction.InteractiveVTKView()
        camera = _Camera()
        view.scene_renderer = SimpleNamespace(GetActiveCamera=lambda: camera)
        view.mousePressEvent(_Event(2, 30, 30, 8))
        view.mouseMoveEvent(_Event(2, 50, 30, 8))
        view.mouseReleaseEvent(_Event(2, 50, 30, 8))
        self.assertEqual(camera.rolls, [])
        self.assertEqual(view.emissions, [
            ('roll', 30.0, 30.0), ('roll', 20.0, 0.0), ('roll',)])
        self.assertEqual(view.calls, [])

    def test_alt_middle_pan_and_ordinary_right_click(self):
        view = self.interaction.InteractiveVTKView()
        view.mousePressEvent(_Event(4, 10, 10, 8))
        view.mouseMoveEvent(_Event(4, 20, 16, 8))
        view.mouseReleaseEvent(_Event(4, 20, 16, 8))
        self.assertEqual(view.emissions, [('pan', 10.0, 10.0), ('pan', 10.0, 6.0), ('pan',)])
        view.emissions.clear()
        view.mousePressEvent(_Event(2, 10, 10))
        view.mouseReleaseEvent(_Event(2, 10, 10))
        self.assertEqual(view.emissions, [()])

    def test_alt_click_without_drag_not_edit_or_clear(self):
        view = self.interaction.InteractiveVTKView()
        view.mousePressEvent(_Event(2, 20, 20, 8))
        view.mouseReleaseEvent(_Event(2, 20, 20, 8))
        self.assertEqual(view.emissions, [('roll', 20.0, 20.0), ('roll',)])
