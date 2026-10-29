"""Per-atom overrides across model edits, rendering, labels and picking."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow

from lele.atom_appearance import AtomAppearance, appearance
from lele.core import Frame, visible_bonds
from lele.periodic_geometry import periodic_fragment
from lele.renderer import MoleculeRenderer, rgb
from lele.selection_geometry import delete_selected_atoms


class AtomAppearanceModelTests(unittest.TestCase):
    def test_clone_and_delete_keep_overrides_on_the_correct_survivors(self):
        frame = Frame(['C', 'H', 'O', 'C'], [[0, 0, 0], [1, 0, 0], [3, 0, 0], [5, 0, 0]])
        frame.atom_appearance[1] = AtomAppearance(visible=False)
        frame.atom_appearance[3] = AtomAppearance(color='#ff00aa', opacity=.35,
                                                 label_mode='Custom', label_text='site A')
        saved = frame.clone()
        delete_selected_atoms(frame, [0, 2])
        self.assertEqual(frame.symbols, ['H', 'C'])
        self.assertFalse(appearance(frame, 0).visible)
        self.assertEqual(appearance(frame, 1).label_text, 'site A')
        self.assertEqual(set(saved.atom_appearance), {1, 3})
        frame.atom_appearance[1] = replace(appearance(frame, 1), color='#abcdef')
        self.assertEqual(appearance(saved, 3).color, '#ff00aa')

    def test_display_visibility_does_not_change_bond_graph_or_atom_count(self):
        frame = Frame(['O', 'H'], [[0, 0, 0], [.97, 0, 0]])
        original = visible_bonds(frame)
        frame.atom_appearance[0] = AtomAppearance(visible=False)
        self.assertEqual(visible_bonds(frame), original)
        self.assertEqual(len(frame.symbols), 2)


class AtomAppearanceRendererTests(unittest.TestCase):
    def setUp(self):
        self.scene = vtkRenderer()
        self.window = vtkRenderWindow()
        self.window.SetOffScreenRendering(True)
        self.window.SetSize(400, 320)
        self.window.AddRenderer(self.scene)
        self.draw = MoleculeRenderer(self.scene)
        self.draw.options.unit_cell = False

    def tearDown(self):
        self.window.Finalize()

    def glyphs(self):
        return [a for a in self.draw.dynamic if a.IsA('vtkActor')
                and a.GetMapper().IsA('vtkGlyph3DMapper')]

    def test_same_element_can_have_independent_colour_opacity_and_label(self):
        frame = Frame(['C', 'C', 'C'], [[-2, 0, 0], [0, 0, 0], [2, 0, 0]])
        frame.atom_appearance[1] = AtomAppearance(color='#ff00aa', opacity=.3,
                                                 label_mode='Index (1..N)')
        frame.atom_appearance[2] = AtomAppearance(visible=False)
        self.draw.options.labels = 'None'
        self.draw.set_scene(frame, reset_camera=True)
        self.window.Render()
        glyphs = self.glyphs()
        self.assertEqual(sum(a.GetMapper().GetInput().GetNumberOfPoints() for a in glyphs), 2)
        custom = next(a for a in glyphs if a.GetProperty().GetOpacity() < 1)
        np.testing.assert_allclose(custom.GetProperty().GetColor(), rgb('#ff00aa'))
        self.assertAlmostEqual(custom.GetProperty().GetOpacity(), .3)
        self.assertEqual([a.GetInput() for a in self.draw._label_actors], ['2'])
        self.assertAlmostEqual(self.draw._label_actors[0].GetTextProperty().GetOpacity(), .3)
        self.draw.options.atom_palette = 'Monochrome'
        self.draw.set_scene(frame)
        self.assertEqual(self.draw.atom_color(frame, 1), '#ff00aa')

    def test_hidden_and_fully_transparent_atoms_have_no_bonds_labels_highlights_or_picks(self):
        frame = Frame(['C', 'C', 'C'], [[0, 0, 1], [0, 0, 0], [1.4, 0, 0]])
        frame.atom_appearance[0] = AtomAppearance(visible=False)
        frame.atom_appearance[2] = AtomAppearance(opacity=0)
        self.draw.options.labels = 'Index (1..N)'
        self.draw.selected = [0, 2]
        self.draw.set_scene(frame, reset_camera=True)
        camera = self.scene.GetActiveCamera()
        camera.SetPosition(0, 0, 10)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(0, 1, 0)
        self.scene.ResetCameraClippingRange()
        self.window.Render()
        self.assertEqual(len(self.draw.dynamic), 2)  # One sphere group and one label.
        self.assertEqual(self.draw.atom_highlights, [])
        self.scene.SetWorldPoint(0, 0, 0, 1)
        self.scene.WorldToDisplay()
        x, y, _ = self.scene.GetDisplayPoint()
        self.assertEqual(self.draw.pick_index(x, y), 1)
        frame.atom_appearance[1] = AtomAppearance(visible=False)
        self.draw.set_scene(frame)
        self.assertIsNone(self.draw.pick_index(x, y))

    def test_bonds_follow_endpoint_colour_visibility_and_transparency(self):
        frame = Frame(['C', 'C'], [[0, 0, 0], [1.4, 0, 0]])
        frame.atom_appearance[0] = AtomAppearance(color='#aabbcc', opacity=.4)
        with patch.object(self.draw, '_tube_segments') as tube:
            self.draw._bonds(frame)
        segments, _, opacity = tube.call_args.args
        self.assertEqual(segments[0][2], '#aabbcc')
        self.assertAlmostEqual(opacity, .4**2)
        frame.atom_appearance[1] = AtomAppearance(visible=False)
        with patch.object(self.draw, '_tube_segments') as tube:
            self.draw._bonds(frame)
        tube.assert_not_called()

    def test_periodic_replicas_and_fragment_bonds_share_atom_overrides(self):
        frame = Frame(['O', 'H'], [[9.65, 0, 0], [.53, 0, 0]],
                      np.eye(3) * 10, (True, True, True))
        preview = periodic_fragment(frame, [0])
        self.draw.periodic_preview = preview
        frame.atom_appearance[0] = AtomAppearance(visible=False)
        frame.atom_appearance[1] = AtomAppearance(color='#12ab34', opacity=.5)
        self.draw.set_scene(frame)
        glyphs = self.glyphs()
        self.assertEqual(sum(a.GetMapper().GetInput().GetNumberOfPoints() for a in glyphs),
                         1 + len(preview.extra_tiles))
        for actor in glyphs:
            np.testing.assert_allclose(actor.GetProperty().GetColor(), rgb('#12ab34'))
            self.assertEqual(actor.GetProperty().GetOpacity(), .5)
        with patch.object(self.draw, '_tube_segments') as tube:
            self.draw._periodic_fragment_bonds(frame)
        tube.assert_not_called()

    def test_custom_and_suppressed_labels_override_global_labels(self):
        frame = Frame(['O', 'H', 'H'], [[0, 0, 0], [.97, 0, 0], [-.3, .9, 0]])
        self.draw.options.labels = 'Element + index (global)'
        frame.atom_appearance[0] = AtomAppearance(label_mode='Custom', label_text='active O')
        frame.atom_appearance[1] = AtomAppearance(label_mode='None')
        self.draw.set_scene(frame)
        self.assertEqual([a.GetInput() for a in self.draw._label_actors], ['active O', 'H3'])

    def test_hidden_hydrogen_bond_endpoint_suppresses_dashes(self):
        frame = Frame(['O', 'H', 'O'], [[0, 0, 0], [.97, 0, 0], [2.83, 0, 0]])
        frame.atom_appearance[2] = AtomAppearance(opacity=.2)
        with patch.object(self.draw, '_tube_segments') as tube:
            self.draw._hydrogen_bonds(frame)
        self.assertEqual(len(tube.call_args.args[0]), 6)
        self.assertAlmostEqual(tube.call_args.args[2], .2**2)
        frame.atom_appearance[2] = AtomAppearance(visible=False)
        with patch.object(self.draw, '_tube_segments') as tube:
            self.draw._hydrogen_bonds(frame)
        tube.assert_not_called()


if __name__ == '__main__':
    unittest.main()
