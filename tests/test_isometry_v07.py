#!/usr/bin/env python3
"""Camera projection checks: an isometric view never transforms atoms."""
import unittest
import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer
from lele.renderer import set_isometric_view


class IsometricTests(unittest.TestCase):
    def test_projection_and_direction(self):
        renderer = vtkRenderer()
        camera = renderer.GetActiveCamera()
        camera.SetPosition(20, 0, 0)
        camera.SetParallelProjection(False)
        set_isometric_view(renderer)
        self.assertEqual(camera.GetParallelProjection(), 1)
        d = np.asarray(camera.GetPosition()) - np.asarray(camera.GetFocalPoint())
        d /= np.linalg.norm(d)
        self.assertTrue(np.allclose(d, np.ones(3) / np.sqrt(3)))
        self.assertAlmostEqual(np.dot(d, camera.GetViewUp()), 0, places=6)

    def test_repeat_isometric_is_stable(self):
        renderer = vtkRenderer()
        set_isometric_view(renderer)
        cam = renderer.GetActiveCamera()
        before = np.array(cam.GetPosition()) - np.array(cam.GetFocalPoint())
        set_isometric_view(renderer)
        after = np.array(cam.GetPosition()) - np.array(cam.GetFocalPoint())
        self.assertTrue(np.allclose(before, after))


if __name__ == '__main__':
    unittest.main()
