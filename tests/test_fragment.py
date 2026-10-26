#!/usr/bin/env python3
"""Regression tests for finite visible-bond components and rigid gestures."""
import unittest
from types import SimpleNamespace
import numpy as np

from lele.core import Frame, canonical_pair
from lele.fragment import (
    selected_fragments, rotation_about_axis, apply_fragment_rotation,
    apply_fragment_translation, camera_basis, screen_rotation, screen_translation)


class CameraStub:
    def __init__(self):
        self.parallel = True
    def GetDirectionOfProjection(self): return (0, 0, -1)
    def GetViewUp(self): return (0, 1, 0)
    def GetParallelProjection(self): return self.parallel
    def GetParallelScale(self): return 5
    def GetPosition(self): return (0, 0, 20)
    def GetViewAngle(self): return 30


class FragmentTests(unittest.TestCase):
    def create(self):
        return Frame(['O', 'H', 'H', 'O', 'H', 'H'],
                     [[0,0,0],[.96,0,0],[-.24,.92,0],
                      [10,0,0],[10.96,0,0],[9.76,.92,0]])

    def test_two_water_molecules_are_separate(self):
        f = self.create()
        self.assertEqual(selected_fragments(f, [0]), [0,1,2])
        self.assertEqual(selected_fragments(f, [3]), [3,4,5])
        self.assertEqual(selected_fragments(f, [0,3]), [0,1,2,3,4,5])

    def test_manual_bond_is_respected_even_when_far(self):
        f = self.create()
        f.bond_added.add(canonical_pair(1,4))
        self.assertEqual(selected_fragments(f,[0]), [0,1,2,3,4,5])

    def test_manual_bond_removal_changes_components(self):
        f = self.create()
        f.bond_removed.update({canonical_pair(0,1),canonical_pair(0,2)})
        self.assertEqual(selected_fragments(f,[0]), [0])

    def test_isolated_atom_and_invalid_selection(self):
        f = Frame(['H','He'], [[0,0,0],[5,0,0]])
        self.assertEqual(selected_fragments(f,[1]), [1])
        self.assertEqual(selected_fragments(f,[]), [])
        with self.assertRaises(IndexError): selected_fragments(f,[2])

    def test_fragment_rotation_preserves_other_atoms_and_geometry(self):
        f = self.create()
        original = f.positions.copy()
        R = rotation_about_axis([0,0,-1], 90)
        apply_fragment_rotation(f,[0,1,2],R,[0,0,0])
        np.testing.assert_array_equal(f.positions[3:],original[3:])
        self.assertAlmostEqual(np.linalg.norm(f.positions[1]-f.positions[0]), .96)
        np.testing.assert_allclose(f.positions[1], [0,-.96,0], atol=1e-12)

    def test_fragment_pan_alters_only_target_atoms(self):
        f = self.create()
        original = f.clone()
        apply_fragment_translation(f,[0,1,2],[3,-4,5])
        np.testing.assert_allclose(f.positions[:3],original.positions[:3]+[3,-4,5])
        np.testing.assert_array_equal(f.positions[3:],original.positions[3:])
        np.testing.assert_array_equal(f.cell,original.cell)

    def test_alt_pan_world_scale_uses_parallel_camera(self):
        c = CameraStub()
        np.testing.assert_allclose(screen_translation(c,100,50,500,[0,0,0]), [2,-1,0])
        c.parallel = False
        self.assertTrue(np.isfinite(screen_translation(c,30,0,500,[0,0,0])).all())

    def test_alt_roll_clockwise_and_orbit_orthogonal(self):
        c = CameraStub()
        R = screen_rotation(c,'roll',90,0,sensitivity=1.)
        np.testing.assert_allclose(np.array([1.,0.,0.]) @ R.T, [0,-1,0], atol=1e-12)
        O = screen_rotation(c,'orbit',22,-19)
        np.testing.assert_allclose(O @ O.T, np.eye(3), atol=1e-12)

    def test_periodic_cell_does_not_infer_image_bonds(self):
        f = Frame(['O','H'], [[.1,0,0],[9.9,0,0]], np.eye(3)*10, (True,True,True))
        self.assertEqual(selected_fragments(f,[0]),[0])

    def test_camera_isometric_projection(self):
        import vtkmodules.vtkRenderingOpenGL2
        from vtkmodules.vtkRenderingCore import vtkRenderer
        from vtkmodules.vtkFiltersSources import vtkSphereSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper
        from lele.renderer import set_isometric_view
        renderer = vtkRenderer()
        sphere = vtkSphereSource()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(sphere.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        renderer.AddActor(actor)
        set_isometric_view(renderer)
        cam = renderer.GetActiveCamera()
        self.assertTrue(cam.GetParallelProjection())
        view = np.asarray(cam.GetPosition()) - np.asarray(cam.GetFocalPoint())
        view /= np.linalg.norm(view)
        np.testing.assert_allclose(view, np.ones(3)/np.sqrt(3), atol=1e-6)
