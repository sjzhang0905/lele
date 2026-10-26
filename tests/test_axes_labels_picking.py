#!/usr/bin/env python3
"""Regression tests for axes, label indexing, and VTK mouse selection."""
import unittest
import numpy as np

from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkRenderWindowInteractor
from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget

from lele.core import Frame, axis_vectors, atom_label_texts, valid_lattice
from lele.renderer import MoleculeRenderer


class AxisAndLabelTests(unittest.TestCase):
    def setUp(self):
        self.molecule = Frame(['O', 'O', 'C', 'C', 'H', 'O'],
                              [[0, 0, 0], [0, 0, 1], [1, 0, 0], [2, 0, 0],
                               [0, 1, 0], [0, 2, 0]])
        self.crystal = Frame(self.molecule.symbols,
                             self.molecule.positions,
                             cell=[[4, 0, 0], [1.5, 5, 0], [1, 2, 7]],
                             pbc=(True, True, True))

    def test_atom_numbering_modes(self):
        syms = self.molecule.symbols
        self.assertEqual(atom_label_texts(syms, 'Index (1..N)'),
                         ['1', '2', '3', '4', '5', '6'])
        self.assertEqual(atom_label_texts(syms, 'Element + index (global)'),
                         ['O1', 'O2', 'C3', 'C4', 'H5', 'O6'])
        self.assertEqual(atom_label_texts(syms, 'VESTA (POSCAR groups)'),
                         ['O1', 'O2', 'C1', 'C2', 'H1', 'O3'])
        self.assertEqual(atom_label_texts(syms, 'Element'), syms)
        self.assertEqual(atom_label_texts(syms, 'None'), [])

    def test_xyz_and_true_nonorthogonal_abc(self):
        self.assertFalse(valid_lattice(self.molecule))
        self.assertTrue(valid_lattice(self.crystal))
        self.assertEqual(axis_vectors(self.molecule, 'abc'), [])
        basis = axis_vectors(self.crystal, 'abc')
        self.assertEqual([name for name, _ in basis], ['a', 'b', 'c'])
        for j, (_name, vec) in enumerate(basis):
            np.testing.assert_allclose(vec, self.crystal.cell[j])
        self.assertAlmostEqual(float(np.dot(basis[0][1], basis[1][1])), 6.)
        overlay = axis_vectors(self.crystal, 'abc', corner=True)
        for (_name, vec), (_name2, original) in zip(overlay, basis):
            self.assertAlmostEqual(np.linalg.norm(vec), 1.)
            np.testing.assert_allclose(vec, original / np.linalg.norm(original))
        xyz = axis_vectors(self.crystal, 'XYZ', length=3.)
        np.testing.assert_allclose(np.stack([v for _, v in xyz]), 3. * np.eye(3))


class InteractiveRendererTests(unittest.TestCase):
    def setUp(self):
        self.scene = vtkRenderer()
        self.window = vtkRenderWindow()
        self.window.SetOffScreenRendering(True)
        self.window.SetSize(500, 440)
        self.window.AddRenderer(self.scene)
        self.iren = vtkRenderWindowInteractor()
        self.iren.SetRenderWindow(self.window)
        self.iren.Initialize()
        self.draw = MoleculeRenderer(self.scene)

    def tearDown(self):
        self.window.Finalize()

    def click_at(self, p):
        self.scene.SetWorldPoint(*(float(x) for x in p), 1.)
        self.scene.WorldToDisplay()
        x, y, _ = self.scene.GetDisplayPoint()
        return self.draw.pick_index(round(x), round(y), 500, 440)

    def test_click_atoms_at_projected_centres_and_edges(self):
        frame = Frame(['O', 'H', 'H'], [[0,0,0], [1.3,.85,0], [-1.3,.85,0]])
        self.draw.set_scene(frame, reset_camera=True)
        self.window.Render()
        for i, p in enumerate(frame.positions):
            self.assertEqual(self.click_at(p), i)
        # A pixel 15 away from small H sphere's centre should still register
        # as long as the visible sphere projects beyond that pixel.
        self.scene.SetWorldPoint(0., 0., 0., 1.)
        self.scene.WorldToDisplay()
        x,y,_ = self.scene.GetDisplayPoint()
        self.assertEqual(self.draw.pick_index(round(x+15), round(y), 500, 440), 0)
        self.assertIsNone(self.draw.pick_index(5, 5, 500, 440))

    def test_overlap_picks_frontmost_atom(self):
        frame = Frame(['C', 'O'], [[0, 0, 0], [0, 0, 1]])
        self.draw.set_scene(frame, reset_camera=True)
        camera = self.scene.GetActiveCamera()
        camera.SetPosition(0., 0., 10.)
        camera.SetFocalPoint(0., 0., 0.)
        camera.SetViewUp(0, 1, 0)
        self.scene.ResetCameraClippingRange()
        self.window.Render()
        self.assertEqual(self.click_at([0,0,0]), 1)

    def test_world_axes_bonded_labels_and_corner_widget(self):
        f = Frame(['O','O','C'], [[0,0,0], [1,0,0],[0,1,0]],
                  cell=[[4,0,0],[2,3,0],[0,0,6]], pbc=(True,True,True))
        self.draw.options.axes_position = 'Origin'
        self.draw.options.axes_basis = 'abc'
        self.draw.options.labels = 'VESTA (POSCAR groups)'
        self.draw.options.label_font_size = 22
        self.draw.options.label_color = '#FF00CC'
        self.draw.set_scene(f, reset_camera=True)
        self.window.Render()
        self.assertEqual([a.GetInput() for a in self.draw._label_actors], ['O1', 'O2', 'C1'])
        self.assertEqual(self.draw._label_actors[0].GetTextProperty().GetFontSize(),22)
        self.assertEqual(self.draw._label_actors[0].GetTextProperty().GetJustificationAsString(), 'Centered')
        # XYZ/abc origin arrows have true displacement as matrix column 0.
        axis_actors = [a for a in self.draw.dynamic if a.IsA('vtkActor') and a.GetUserMatrix()]
        self.assertEqual(len(axis_actors),3)
        for i,a in enumerate(axis_actors):
            mat=a.GetUserMatrix()
            np.testing.assert_allclose([mat.GetElement(j,0) for j in range(3)], f.cell[i])
        marker=self.draw.make_corner_marker(f)
        self.assertEqual(marker.GetParts().GetNumberOfItems(),6)
        widget=vtkOrientationMarkerWidget()
        widget.SetInteractor(self.iren)
        widget.SetOrientationMarker(marker)
        widget.SetViewport(.01,.01,.22,.22)
        widget.SetEnabled(1)
        widget.InteractiveOff()
        self.window.Render()
        self.assertEqual(widget.GetEnabled(), 1)
        widget.SetEnabled(0)


if __name__ == '__main__':
    unittest.main()
