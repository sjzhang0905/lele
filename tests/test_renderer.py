#!/usr/bin/env python3
import unittest
import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
from lele.core import Frame, Volume
from lele.renderer import MoleculeRenderer

class VTKRenderTests(unittest.TestCase):
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
