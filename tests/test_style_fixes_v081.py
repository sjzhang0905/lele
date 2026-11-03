#!/usr/bin/env python3
"""Regression coverage for persistent colours, bond visibility and labels."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import ELEMENT_COLORS, Frame, colour
from lele.periodic_geometry import periodic_fragment
from lele.renderer import MoleculeRenderer, RenderOptions, rgb
from lele.style_presets import (
    BUILTIN_PRESETS, CUSTOM_KEY, STYLE_MODES, apply_preset, snapshot,
    validate_preset,
)


class StyleStateTests(unittest.TestCase):
    def test_v080_saved_presets_remain_readable(self):
        legacy = deepcopy(BUILTIN_PRESETS['Classic ball and stick'])
        legacy.pop('element_colors')
        options = RenderOptions(element_colors={'O': '#123456'})
        apply_preset(options, json.loads(json.dumps(legacy)))
        self.assertEqual(options.element_colors, {})
        self.assertEqual(options.background, legacy['background'])

    def test_colours_are_independent_across_snapshots_and_presets(self):
        options = RenderOptions(element_colors={'O': '#123456'})
        saved = snapshot(options)
        options.element_colors['O'] = '#ABCDEF'
        self.assertEqual(saved['element_colors']['O'], '#123456')
        apply_preset(options, saved)
        saved['element_colors']['O'] = '#987654'
        self.assertEqual(options.element_colors['O'], '#123456')
        self.assertEqual(RenderOptions().element_colors, {})
        apply_preset(options, BUILTIN_PRESETS['Classic ball and stick'])
        options.element_colors['O'] = '#112233'
        self.assertEqual(BUILTIN_PRESETS['Classic ball and stick']['element_colors'], {})

    def test_invalid_saved_element_colours_are_rejected(self):
        source = BUILTIN_PRESETS['Classic ball and stick']
        for colors in ([], {'O': 'red'}, {'O': '#XYZXYZ'}, {'oxygen': '#112233'}):
            with self.subTest(colors=colors):
                with self.assertRaises(ValueError):
                    validate_preset({**source, 'element_colors': colors})


class RendererStyleFixTests(unittest.TestCase):
    def test_custom_colours_reach_atom_and_bond_actors(self):
        view = MoleculeRenderer(vtkRenderer())
        view.options.element_colors = {'O': '#123456'}
        view.options.unit_cell = False
        frame = Frame(['O', 'H'], [[0, 0, 0], [.97, 0, 0]])
        view.set_scene(frame)
        np.testing.assert_allclose(view.dynamic[0].GetProperty().GetColor(), rgb('#123456'))
        bond = view.dynamic[-1]
        bond.GetMapper().Update()
        colors = bond.GetMapper().GetInput().GetPointData().GetScalars()
        self.assertIn((18., 52., 86.),
                      [colors.GetTuple3(i) for i in range(colors.GetNumberOfTuples())])
        self.assertEqual(colour('O'), ELEMENT_COLORS['O'])

    def test_display_bonds_controls_normal_and_periodic_bonds_in_every_mode(self):
        frame = Frame(['O', 'H', 'H'],
                      [[9.7, 1, 1], [.58, 1, 1], [9.4, 1.89, 1]],
                      cell=np.eye(3) * 10, pbc=(True, True, True))
        original = frame.positions.copy()
        preview = periodic_fragment(frame, [0])
        view = MoleculeRenderer(vtkRenderer())
        view.options.unit_cell = False
        for context in (None, preview):
            view.periodic_preview = context
            for mode in STYLE_MODES:
                with self.subTest(periodic_preview=context is not None, mode=mode):
                    view.options.style = mode
                    view.options.bonds = False
                    view.set_scene(frame)
                    tubes = [actor for actor in view.dynamic
                             if actor.GetMapper().IsA('vtkPolyDataMapper')]
                    self.assertEqual(tubes, [])
                    view.options.bonds = True
                    view.set_scene(frame)
                    tubes = [actor for actor in view.dynamic
                             if actor.GetMapper().IsA('vtkPolyDataMapper')]
                    self.assertEqual(bool(tubes), mode != 'Space filling')
                    self.assertIs(view.periodic_preview, context)
        np.testing.assert_array_equal(frame.positions, original)
        self.assertEqual(frame.bond_added, set())
        self.assertEqual(frame.bond_removed, set())

    def test_labels_survive_all_presets_including_wireframe(self):
        view = MoleculeRenderer(vtkRenderer())
        view.options.labels = 'Element + index (global)'
        view.options.label_font_size = 23
        view.options.label_color = '#123456'
        frame = Frame(['O', 'H', 'H'], [[0, 0, 0], [.8, .6, 0], [-.8, .6, 0]])
        for name, preset in BUILTIN_PRESETS.items():
            with self.subTest(preset=name):
                apply_preset(view.options, preset)
                view.set_scene(frame)
                self.assertEqual([a.GetInput() for a in view._label_actors], ['O1', 'H2', 'H3'])
                for actor in view._label_actors:
                    prop = actor.GetTextProperty()
                    self.assertEqual(prop.GetFontSize(), 23)
                    np.testing.assert_allclose(prop.GetColor(), rgb('#123456'))
                if preset['style'] == 'Wireframe':
                    for actor, pos in zip(view._label_actors, frame.positions):
                        self.assertLess(np.linalg.norm(np.asarray(actor.GetPosition()) - pos), .1)
        view.options.labels = 'None'
        view.set_scene(frame)
        self.assertEqual(view._label_actors, [])


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class StyleQtWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.platform.startswith('linux') and not os.environ.get('DISPLAY'):
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        cls.qt_app = QApplication.instance() or QApplication(['LELEStyleTests'])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'style_presets.json'
        from lele.app import LELEWindow
        self.addCleanup(patch.stopall)
        patch.object(LELEWindow, '_style_storage_path', return_value=self.path).start()
        self.window = self.make_window()

    def make_window(self):
        from PySide6.QtWidgets import QMainWindow
        from lele.app import LELEWindow
        # Build real Qt controls without initializing the native OpenGL window.
        window = LELEWindow.__new__(LELEWindow)
        QMainWindow.__init__(window)
        window.documents = []
        window.current_doc = -1
        window.frame_index = 0
        window.selection = []
        window._ignore_table = False
        window._ignore_tree = False
        window._user_style_presets = window._read_user_style_presets()
        window._build_ui()
        self.addCleanup(window.deleteLater)
        window.element_combo.addItem('O')
        window.element_combo.setCurrentText('O')
        return window

    @staticmethod
    def oxygen_colour(window):
        from types import SimpleNamespace
        return MoleculeRenderer._display_color(SimpleNamespace(options=window.render_options), 'O')

    def choose(self, window, name):
        window.preset_combo.setCurrentIndex(window.preset_combo.findData(name))

    def edit_oxygen(self, window, value):
        from lele.app import QColor, QColorDialog
        with patch.object(QColorDialog, 'getColor', return_value=QColor(value)) as dialog:
            window.pick_element_colour()
        return dialog.call_args.args[0].name()

    def save(self, window, name):
        from lele.app import QInputDialog
        with patch.object(QInputDialog, 'getText', return_value=(name, True)):
            window._save_style_preset()

    def test_edit_save_restart_and_custom_restore_keep_element_colour(self):
        window = self.window
        original_defaults = dict(ELEMENT_COLORS)
        self.assertEqual(self.edit_oxygen(window, '#123456'), '#e92525')
        self.assertEqual(window.preset_combo.currentData(), CUSTOM_KEY)
        saved_custom = snapshot(window.render_options)
        self.choose(window, 'Soft pastel')
        self.choose(window, CUSTOM_KEY)
        self.assertEqual(snapshot(window.render_options), saved_custom)
        self.save(window, 'Blue oxygen')
        data = json.loads(self.path.read_text())
        self.assertEqual(data['Blue oxygen']['element_colors'], {'O': '#123456'})
        restarted = self.make_window()
        self.choose(restarted, 'Blue oxygen')
        self.assertEqual(self.oxygen_colour(restarted), '#123456')
        self.assertEqual(ELEMENT_COLORS, original_defaults)

    def test_switching_saved_styles_keeps_colours_independent(self):
        window = self.window
        self.edit_oxygen(window, '#123456')
        self.save(window, 'Blue oxygen')
        self.assertEqual(self.edit_oxygen(window, '#ABCDEF'), '#123456')
        self.assertEqual(window.preset_combo.currentData(), CUSTOM_KEY)
        self.save(window, 'Pale oxygen')
        self.choose(window, 'Blue oxygen')
        self.assertEqual(self.oxygen_colour(window), '#123456')
        self.choose(window, 'Pale oxygen')
        self.assertEqual(self.oxygen_colour(window), '#abcdef')
        self.choose(window, 'Classic ball and stick')
        self.assertEqual(self.oxygen_colour(window), '#E92525')

    def test_legacy_presets_load_alongside_new_presets(self):
        legacy = deepcopy(BUILTIN_PRESETS['Soft pastel'])
        legacy.pop('element_colors')
        self.path.write_text(json.dumps({'Legacy style': legacy}), encoding='utf-8')
        restarted = self.make_window()
        self.choose(restarted, 'Legacy style')
        self.assertEqual(restarted.render_options.atom_palette, 'Pastel')
        self.assertEqual(restarted.render_options.element_colors, {})

    def test_all_preset_widgets_stay_in_sync(self):
        window = self.window
        for name, preset in BUILTIN_PRESETS.items():
            with self.subTest(preset=name):
                self.choose(window, name)
                self.assertEqual(snapshot(window.render_options), preset)
                self.assertEqual(window.style_combo.currentText(), preset['style'])
                self.assertEqual(window.bond_check.isChecked(), preset['bonds'])
                self.assertEqual(window.atom_slider.value(), round(preset['atom_scale'] * 100))


if __name__ == '__main__':
    unittest.main()
