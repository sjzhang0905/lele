#!/usr/bin/env python3
"""Regression tests for style presets and non-destructive renderer changes."""
import unittest
from copy import deepcopy
from pathlib import Path
import numpy as np

from lele.core import Frame, visible_bonds
from lele.renderer import RenderOptions, MoleculeRenderer
from lele.style_presets import (
    BUILTIN_PRESETS, snapshot, apply_preset, validate_preset, mix_color,
)


class PresetTests(unittest.TestCase):
    def test_presets_complete_and_valid(self):
        self.assertGreaterEqual(len(BUILTIN_PRESETS), 8)
        options = RenderOptions()
        for name, preset in BUILTIN_PRESETS.items():
            with self.subTest(name=name):
                self.assertEqual(set(snapshot(options)), set(preset))
                self.assertEqual(validate_preset(preset), preset)
                apply_preset(options, preset)
                self.assertEqual(snapshot(options), preset)

    def test_presets_do_not_modify_geometry_or_chemical_bond_settings(self):
        frame = Frame(['O', 'H', 'H'], [[0., 0., 0.], [.8, .6, 0.], [-.8, .6, 0.]])
        frame.bond_removed.add((0, 1))
        pos_before = frame.positions.copy()
        cell_before = frame.cell.copy()
        bonds_before = set(visible_bonds(frame))
        options = RenderOptions()
        options.bond_cutoff = 1.39
        options.labels = 'VESTA (POSCAR groups)'
        options.hydrogen_bonds = True
        options.axes_basis = 'abc'
        options.axes_position = 'Origin'
        options.unit_cell = False
        for preset in BUILTIN_PRESETS.values():
            apply_preset(options, preset)
            np.testing.assert_array_equal(frame.positions, pos_before)
            np.testing.assert_array_equal(frame.cell, cell_before)
            self.assertEqual(set(visible_bonds(frame)), bonds_before)
            self.assertEqual(options.bond_cutoff, 1.39)
            self.assertEqual(options.labels, 'VESTA (POSCAR groups)')
            self.assertTrue(options.hydrogen_bonds)
            self.assertEqual(options.axes_basis, 'abc')
            self.assertEqual(options.axes_position, 'Origin')
            self.assertFalse(options.unit_cell)

    def test_pastel_and_invalid_saved_settings(self):
        self.assertEqual(mix_color('#000000', 1.), '#FFFFFF')
        self.assertEqual(mix_color('#F00000', 0.), '#F00000')
        source = deepcopy(BUILTIN_PRESETS['Classic ball and stick'])
        for change in ({'background': 'invalid'}, {'style': 'External'},
                       {'atom_scale': 7.5}, {'bonds': 1}):
            with self.subTest(change=change):
                item = {**source, **change}
                with self.assertRaises(ValueError):
                    validate_preset(item)

    def test_scene_for_every_preset(self):
        from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
        renderer = vtkRenderer()
        window = vtkRenderWindow()
        window.SetOffScreenRendering(True)
        window.SetSize(180, 160)
        window.AddRenderer(renderer)
        view = MoleculeRenderer(renderer)
        frame = Frame(['C', 'O', 'H'], [[0, 0, 0], [1.2, 0, 0], [0., 1.1, 0.]])
        try:
            for name, preset in BUILTIN_PRESETS.items():
                with self.subTest(name=name):
                    apply_preset(view.options, preset)
                    view.set_scene(frame, reset_camera=True)
                    window.Render()
                    self.assertGreater(renderer.GetActors().GetNumberOfItems(), 0)
                    self.assertEqual(tuple(renderer.GetBackground()),
                                     tuple(int(preset['background'][i:i+2], 16)/255.
                                           for i in (1, 3, 5)))
        finally:
            window.Finalize()


if __name__ == '__main__':
    unittest.main()
