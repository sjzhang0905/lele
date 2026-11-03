"""Run the real application with a VTK EGL target for Qt's offscreen plugin."""
import json
from pathlib import Path
import sys
import tempfile
import time
import traceback

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QLabel,QPushButton
from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy

import lele.app as application
from lele.atom_clipboard import paste_atoms
from lele.core import Frame
from lele.formats import export_frame,load_document

destination=Path(sys.argv[1]).resolve();destination.mkdir(parents=True,exist_ok=True)
result={'display':'Qt offscreen, production renderer with a native VTK EGL target'}
temporary=tempfile.TemporaryDirectory();base=Path(temporary.name)
frame=Frame(['O','C','H','Ni','Fe','S'],[[1,1,2],[2.2,1,2],[1,2,2],[5,3,3],[2,5,4],[4,5,4]],
            [[8,0,0],[1,9,0],[2,1,12]],(True,)*3)
export_frame(frame,base/'slab.POSCAR','poscar-cartesian')
(base/'water.xyz').write_text('3\nwater\nO 0 0 0\nH .8 .6 0\nH -.8 .6 0\n')


def run(w):
    w.resize(1400,850);QApplication.processEvents()
    page=w.welcome_page
    result['welcome']={
        'removed_open_button':not page.findChildren(QPushButton),
        'removed_drop_hint':not any('Drop a structure or calculation' in l.text() for l in page.findChildren(QLabel)),
        'glossy_options':w.render_options.surface_finish,'lighting_control':w.finish_combo.currentText(),
        'palette_control':w.atom_palette_combo.currentText(),'backend_ready':w._backend_state=='ready'}
    assert result['welcome']==dict(removed_open_button=True,removed_drop_hint=True,glossy_options='Glossy',lighting_control='Glossy',palette_control='Sibyl',backend_ready=True)
    w.grab().save(str(destination/'welcome.png'))
    w._open_path_now(base/'slab.POSCAR');QApplication.processEvents()
    draw=w.renderer
    result['periodic']={'basis_setting':w.render_options.axes_basis,'axis_labels':[a.GetInput() for a in draw.corner_labels],
                        'colors':{s:draw.atom_color(w.frame,i) for i,s in enumerate(w.frame.symbols)}}
    assert result['periodic']['axis_labels']==list('abc')
    assert result['periodic']['colors']=={'O':'#E50000','C':'#8E8E8E','H':'#CCCCCC','Ni':'#5B7AC1','Fe':'#7F7AC6','S':'#FFC628'}
    rw=w.vtk.GetRenderWindow();rw.Render()
    capture=vtkWindowToImageFilter();capture.SetInput(rw);capture.ReadFrontBufferOff();capture.Update()
    output=capture.GetOutput();size=output.GetDimensions()
    pixels=vtk_to_numpy(output.GetPointData().GetScalars()).reshape(size[1],size[0],-1)[::-1].copy()
    Image.fromarray(pixels).save(destination/'sibyl_slab.png')
    paste_atoms(w.frame,Frame(['Co','H'],[[0,0,0],[0,1,0]]),[6,6,6]);w.refresh_scene()
    path=base/'appended.POSCAR';export_frame(w.frame,path,'poscar-cartesian')
    result['export_order']=load_document(path).frames[0].symbols
    assert result['export_order']==['O','C','H','Ni','Fe','S','Co','H']
    w._open_path_now(base/'water.xyz');QApplication.processEvents()
    result['molecular_axis_labels']=[a.GetInput() for a in draw.corner_labels]
    assert result['molecular_axis_labels']==list('XYZ')
    w.change_frame(0,switch_doc=0);QApplication.processEvents()
    result['return_periodic_axis_labels']=[a.GetInput() for a in draw.corner_labels]
    assert result['return_periodic_axis_labels']==list('abc')
    w.doc.modified=False
    result['ok']=True


class OffscreenRenderWindow(vtkEGLRenderWindow):
    def SetWindowInfo(self,handle):self.SetOffScreenRendering(True)


class ObservedApplication(QApplication):
    def exec(self):
        started=time.monotonic()
        def poll():
            w=next((x for x in self.topLevelWidgets() if isinstance(x,application.LELEWindow)),None)
            if w is None or w._backend_state!='ready':
                if time.monotonic()-started<30:QTimer.singleShot(100,poll);return
                result['error']='Backend startup timeout'
            else:
                try:run(w)
                except BaseException:result['error']=traceback.format_exc()
            (destination/'display.json').write_text(json.dumps(result,indent=2)+'\n')
            if w:
                if w.doc:w.doc.modified=False
                w.close()
            self.quit()
        QTimer.singleShot(200,poll)
        return super().exec()


adapter.vtkRenderWindow=OffscreenRenderWindow
application.QApplication=ObservedApplication
application.main([])
print(json.dumps(result,indent=2))
sys.exit(0 if result.get('ok') else 1)
