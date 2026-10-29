#!/usr/bin/env python3
import unittest
import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
from lele.core import Frame, Volume
from lele.renderer import MoleculeRenderer

class VTKRenderTests(unittest.TestCase):
    def test_vibration_connectivity_keeps_reference_bond_without_inventing_new_one(self):
        draw = MoleculeRenderer(vtkRenderer())
        # The preview has moved atom 1 far from its bonded partner, while
        # atom 2 is now close; only the reference bond 0--1 should be drawn.
        frame = Frame(['C'] * 3, [[0, 0, 0], [10, 0, 0], [1.2, 0, 0]])
        draw.fixed_bonds = [(0, 1)]
        draw.set_scene(frame)
        tubes = [item for item in draw._keepalive if isinstance(item, tuple) and len(item) == 6
                 and item[3].IsA('vtkTubeFilter')]
        self.assertEqual(len(tubes), 1)
        points = tubes[0][0]
        self.assertEqual(points.GetNumberOfPoints(), 4)
        np.testing.assert_allclose([points.GetPoint(i) for i in range(4)],
                                   [[0, 0, 0], [5, 0, 0], [5, 0, 0], [10, 0, 0]])
        draw.fixed_bonds = None
        draw.set_scene(frame)
        tubes = [item for item in draw._keepalive if isinstance(item, tuple) and len(item) == 6
                 and item[3].IsA('vtkTubeFilter')]
        self.assertAlmostEqual(tubes[0][0].GetPoint(3)[0], 1.2, places=5)

    def test_small_exact_isovalue_reaches_both_contour_filters(self):
        draw = MoleculeRenderer(vtkRenderer())
        draw.options.volume_iso = 1.25e-9
        grid = Volume(np.linspace(-1e-8, 1e-8, 64).reshape(4, 4, 4),
                      [0, 0, 0], np.eye(3))
        draw.set_scene(Frame(['C'], [[0, 0, 0]]), grid)
        contours = [item[0] for item in draw._keepalive if isinstance(item, tuple)
                    and item[0].IsA('vtkContourFilter')]
        self.assertEqual(len(contours), 2)
        np.testing.assert_allclose(sorted(c.GetValue(0) for c in contours),
                                   [-1.25e-9, 1.25e-9], rtol=0, atol=1e-18)

    def test_atoms_bonds_and_signed_volume_offscreen(self):
        r = vtkRenderer()
        window = vtkRenderWindow()
        window.SetOffScreenRendering(True)
        window.SetSize(260, 220)
        window.AddRenderer(r)
        draw = MoleculeRenderer(r)
        frame = Frame(['O','H','H'], [[0,0,0],[.76,.59,0],[-.76,.59,0]])
        x = np.linspace(-2., 2., 12)
        a,b,c = np.meshgrid(x,x,x,indexing='ij')
        grid = Volume(np.exp(-((a-1)**2+b*b+c*c)) - np.exp(-((a+1)**2+b*b+c*c)),
                      [-2.,-2.,-2.], np.eye(3) * (4/11))
        draw.set_scene(frame, grid, reset_camera=True)
        window.Render()
        self.assertGreaterEqual(r.GetActors().GetNumberOfItems(), 3)
        self.assertEqual(window.GetSize(), (260, 220))
        window.Finalize()

if __name__ == '__main__':
    unittest.main()
