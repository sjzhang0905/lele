import unittest
from pathlib import Path
import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer
from lele.core import Document, Frame, Volume
from lele.field_actions import select_field
from lele.renderer import MoleculeRenderer


class FieldViewTests(unittest.TestCase):
    def make_document(self):
        a=Volume(np.ones((3,3,3)),[0,0,0],np.eye(3),label='A')
        b=Volume(np.ones((4,4,4)),[-1,-1,-1],np.eye(3)*.5,label='B')
        return Document(Path('dummy'), 'test', [Frame(['H'],[[0,0,0]])], a, volumes=[a,b])

    def test_field_switch_preserves_affine_transform_and_grid_spacing(self):
        doc=self.make_document();a,b=doc.volumes
        rotation=np.array([[0,1,0],[-1,0,0],[0,0,1.]])
        a.origin=np.array([4.,5.,6.]);a.voxel_vectors=a.voxel_vectors@rotation
        select_field(doc,1)
        np.testing.assert_allclose(b.origin, np.array([-1.,-1.,-1.])@rotation+[4,5,6])
        np.testing.assert_allclose(b.voxel_vectors,.5*rotation)
        select_field(doc,0)
        np.testing.assert_allclose(a.origin,[4,5,6]);np.testing.assert_allclose(a.voxel_vectors,rotation)

    def test_detached_volume_does_not_revive(self):
        doc=self.make_document();doc.volume=None
        with self.assertRaisesRegex(ValueError,'detached'): select_field(doc,1)
        doc.__post_init__();self.assertIsNone(doc.volume)

    def test_skew_contour_world_coordinates_and_signs(self):
        data=np.indices((3,3,3))[0].astype(float)-1.
        volume=Volume(data,[2,3,4],[[1,0,0],[.2,1,0],[.1,.3,1]])
        draw=MoleculeRenderer(vtkRenderer());draw.options.volume_iso=.5;draw.options.volume_signs='Positive'
        draw._volume(volume)
        contours=[x for x in draw._keepalive if isinstance(x,tuple) and x[0].IsA('vtkContourFilter')]
        self.assertEqual(len(contours),1)
        transform=contours[0][2];transform.Update();points=transform.GetOutput().GetPoints()
        positions=np.array([points.GetPoint(i) for i in range(points.GetNumberOfPoints())])
        fractional=(positions-volume.origin)@np.linalg.inv(volume.voxel_vectors)
        np.testing.assert_allclose(fractional[:,0],1.5,atol=1e-6)

    def test_large_grid_not_silently_omitted(self):
        data=np.zeros((128,128,128),dtype=np.float32);data[64:]=1.
        draw=MoleculeRenderer(vtkRenderer());draw.options.volume_iso=.5
        draw._volume(Volume(data,[0,0,0],np.eye(3)))
        self.assertEqual(len(draw.dynamic),1)

    def test_periodic_endpoint_closure(self):
        volume=Volume(np.indices((3,3,3))[0].astype(float),[0,0,0],np.eye(3),periodic=True)
        draw=MoleculeRenderer(vtkRenderer());draw._volume(volume)
        grid=draw._keepalive[0][0]
        self.assertEqual(grid.GetDimensions(),(4,4,4))

if __name__=='__main__': unittest.main()

class FieldControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_select_detach_and_metadata_only_wavefunction(self):
        from PySide6.QtWidgets import QWidget,QFormLayout
        from lele.field_actions import FieldActions
        from lele.render_options import RenderOptions
        class Host(FieldActions,QWidget):
            def __init__(self):
                super().__init__();self.doc=None;self.render_options=RenderOptions()
                self._build_field_controls(QFormLayout(self))
            def _set_option(self,key,value): setattr(self.render_options,key,value)
            def refresh_scene(self): self._refresh_field_controls()
        host=Host();host._refresh_field_controls()
        self.assertFalse(host.field_combo.isEnabled())
        host.doc=FieldViewTests().make_document();host.doc.wavefunction=object()
        host._refresh_field_controls()
        self.assertEqual(host.field_combo.count(),2)
        self.assertFalse(host.mo_generate.isEnabled())
        host.field_combo.setCurrentIndex(1)
        self.assertIs(host.doc.volume,host.doc.volumes[1])
        host.doc.volume=None;host._refresh_field_controls()
        self.assertFalse(host.field_combo.isEnabled())
        self.assertIn('detached',host.field_note.text())
        host.close()
