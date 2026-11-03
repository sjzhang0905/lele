"""Open repaired PQR/CUBE inputs in the actual application and render them."""
import json
import sys
import time
import traceback
from pathlib import Path
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy
import lele.app as application
import lele

samples=Path(sys.argv[1]).resolve();destination=Path(sys.argv[2]).resolve();destination.mkdir(parents=True,exist_ok=True)
result={'version':lele.__version__,'module':lele.__file__,'cases':{}}


class OffscreenRenderWindow(vtkEGLRenderWindow):
    def SetWindowInfo(self,handle):self.SetOffScreenRendering(True)


def run(window):
    for filename in ('A1_pqr_single_space.pqr','A1_pqr_double_space.pqr','A1_pqr_hetatm.pqr',
                     'A2_cube_negative.cube','control_cube_positive.cube'):
        window._open_path_now(samples/filename);QApplication.processEvents()
        assert window.frame.symbols==['O'],(filename,window.frame.symbols)
        row={'symbols':window.frame.symbols,'positions':window.frame.positions.tolist(),
             'atoms_table_rows':window.atom_table.rowCount()}
        assert row['atoms_table_rows']==1
        if filename.endswith('cube'):
            volume=window.doc.volume
            assert volume is not None and window.renderer.volume is volume
            assert volume.data.shape==(2,2,2)
            row.update(origin=volume.origin.tolist(),voxel_vectors=volume.voxel_vectors.tolist(),shape=list(volume.data.shape))
            if filename.startswith('A2'):
                np.testing.assert_allclose(window.frame.positions,[[1.25,2.25,3.25]],atol=1.e-12)
                np.testing.assert_allclose(volume.origin,[1,2,3],atol=1.e-12)
                np.testing.assert_allclose(volume.voxel_vectors,np.eye(3)*.5,atol=1.e-12)
        render=window.vtk.GetRenderWindow();render.Render()
        capture=vtkWindowToImageFilter();capture.SetInput(render);capture.ReadFrontBufferOff();capture.Update()
        data=capture.GetOutput();width,height,_=data.GetDimensions()
        pixels=vtk_to_numpy(data.GetPointData().GetScalars()).reshape(height,width,-1)[::-1].copy()
        assert pixels.std()>0
        Image.fromarray(pixels).save(destination/(filename+'.png'))
        result['cases'][filename]=row
    result['ok']=True


class ObservedApplication(QApplication):
    def exec(self):
        start=time.monotonic()
        def poll():
            window=next((w for w in self.topLevelWidgets() if isinstance(w,application.LELEWindow)),None)
            if window is None or window._backend_state!='ready':
                if time.monotonic()-start<30:QTimer.singleShot(100,poll);return
                result['error']='Backend startup timeout'
            else:
                try:run(window)
                except BaseException:result['error']=traceback.format_exc()
            (destination/'repaired_formats.json').write_text(json.dumps(result,indent=2)+'\n')
            if window:
                for doc in window.documents:doc.modified=False
                window.close()
            self.quit()
        QTimer.singleShot(200,poll)
        return super().exec()


adapter.vtkRenderWindow=OffscreenRenderWindow
application.QApplication=ObservedApplication
application.main([])
print(json.dumps(result,indent=2))
sys.exit(0 if result.get('ok') else 1)
