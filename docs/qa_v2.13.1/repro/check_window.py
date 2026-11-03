"""Exercise the application event loop, native canvas, picker and modal dialogs."""
import sys, json, traceback, tempfile, os
from pathlib import Path
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtTest import QTest
from test_acceptance_extra import CIF
import numpy as np
from PIL import Image
import lele.app as application

result={}
destination=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
destination.mkdir(exist_ok=True)
tmp=tempfile.TemporaryDirectory()
sample=Path(tmp.name)/'mixture.cif';sample.write_text(CIF)
def capture(w,name):
    from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    rw=w.vtk.GetRenderWindow();rw.Render()
    image=vtkWindowToImageFilter();image.SetInput(rw);image.ReadFrontBufferOff();image.Update()
    output=image.GetOutput();size=output.GetDimensions()
    pixels=vtk_to_numpy(output.GetPointData().GetScalars()).reshape(size[1],size[0],-1)[::-1].copy()
    Image.fromarray(pixels).save(destination/(name+'.png'))
    return pixels

def projected(w,atom):
    pos=w.frame.positions[atom];s=w.scene;s.SetWorldPoint(*pos,1);s.WorldToDisplay();x,y,_=s.GetDisplayPoint()
    width,height=w.vtk.GetRenderWindow().GetSize()
    return QPoint(round(x*w.vtk.width()/width),round(w.vtk.height()-y*w.vtk.height()/height)),(round(x),round(height-1-y))

def run(w):
    result['startup']=[w.isVisible(),w._startup_painted,w._backend_state,w.frame.symbols]
    w.resize(1400,850);QtWidgets.QApplication.processEvents()
    w.render_options.labels='Index';w.refresh_scene(reset_camera=True)
    # Keep orientation and clipping identical across the two native captures.
    w.selection=[];w.refresh_scene()
    point,(x,y)=projected(w,0)
    before=capture(w,'before')
    QTest.mouseClick(w.vtk,Qt.MouseButton.LeftButton,pos=point)
    assert w.selection==[0],w.selection
    after=capture(w,'selected')
    delta=np.abs(after.astype(int)-before.astype(int)).max(axis=2)
    green=lambda a: (a[:,:,1].astype(int)>a[:,:,0].astype(int)+70)&(a[:,:,1].astype(int)>a[:,:,2].astype(int)+65)
    new_green=(green(after)&~green(before))
    result['render']={'size':list(after.shape[:2]),'selection_center_xy':[x,y],
                      'new_green_pixels':int(new_green.sum()),
                      'center_max_channel_delta_9px':int(delta[y-4:y+5,x-4:x+5].max()),
                      'ring_lines':w.renderer.atom_highlights[0].GetMapper().GetInput().GetNumberOfLines()}
    assert result['render']['new_green_pixels']>0 and result['render']['center_max_channel_delta_9px']==0
    deltas=[];layout=[]
    for width in (1100,1400,1600):
        w.resize(width,850);QTest.qWait(300)
        summary_x=w.summary_label.mapToGlobal(QPoint(0,0)).x();tabs_x=w.tabs.mapToGlobal(QPoint(0,0)).x()
        deltas.append(summary_x-tabs_x);layout.append([w.width(),summary_x,tabs_x])
    result['footer_offsets_px']=deltas;result['footer_layout']=layout
    QTest.qWait(3200);result['last_offset_after_3s']=w.summary_label.mapToGlobal(QPoint(0,0)).x()-w.tabs.mapToGlobal(QPoint(0,0)).x()
    for _ in range(3):
        w._align_summary_footer();QTest.qWait(50)
    result['last_offset_after_manual_sync']=w.summary_label.mapToGlobal(QPoint(0,0)).x()-w.tabs.mapToGlobal(QPoint(0,0)).x()
    order=w.frame.symbols.copy()
    def interact(callback,trigger):
        observed=[]
        def on_open():
            try:
                dlg=QtWidgets.QApplication.activeModalWidget();observed.append(dlg.windowTitle());callback(dlg)
            except BaseException:
                observed.append(traceback.format_exc())
                dlg=QtWidgets.QApplication.activeModalWidget()
                if dlg:dlg.reject()
        QTimer.singleShot(60,on_open);trigger()
        assert len(observed)==1,observed
        return observed[0]
    result['right_click']=interact(lambda d:(d.index.setValue(2),d.accept()),
                    lambda:QTest.mouseClick(w.vtk,Qt.MouseButton.RightButton,pos=projected(w,0)[0]))
    assert w.frame.symbols==list(reversed(order));w.undo_edit();assert w.frame.symbols==order
    # Add missing sites with real left clicks.
    for i in range(2):
        if i not in w.selection:QTest.mouseClick(w.vtk,Qt.MouseButton.LeftButton,pos=projected(w,i)[0])
    assert len(w.selection)==2,w.selection
    result['swap']=interact(lambda d:d.swap_button.click(),
                    lambda:QTest.mouseClick(w.vtk,Qt.MouseButton.RightButton,pos=projected(w,0)[0]))
    assert w.frame.symbols==list(reversed(order));w.undo_edit()
    old=w.frame.clone()
    result['vacuum_action']=interact(lambda d:(d.axis.setCurrentIndex(3), d.gap.setValue(12), d.accept()),w.vacuum_action.trigger)
    assert np.array_equal(w.frame.positions,old.positions) and w.frame.cell[2,2]==15
    w.undo_edit();assert np.array_equal(w.frame.cell,old.cell)
    # The dispersion between the two atomic planes is 3 Å.
    interact(lambda d:(d.axis.setCurrentIndex(3), d.gap.setValue(1), d.accept()),w.vacuum_action.trigger)
    def inspect_small(d):
        d.axis.setCurrentIndex(3)
        result['small_gap_dialog']={'entered':1.,'reopened':d.gap.value(),
            'apply_enabled':d.buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).isEnabled()}
        d.reject()
    interact(inspect_small,w.vacuum_action.trigger)
    w.undo_edit()
    result['summary']=w.summary_label.text()
    result['ok']=True
    result['footer_pass']=max(map(abs,deltas))<=1

class ObservedApplication(QtWidgets.QApplication):
    def exec(self):
        def poll():
            win=next((w for w in self.topLevelWidgets() if isinstance(w,application.LELEWindow)),None)
            if win is None or win.frame is None:
                QTimer.singleShot(100,poll);return
            try:run(win)
            except BaseException:result['error']=traceback.format_exc()
            finally:
                (destination/'window.json').write_text(json.dumps(result,indent=2))
                win.close();self.quit()
        QTimer.singleShot(200,poll)
        return super().exec()

if os.environ.get('QA_DETACH_OFFSCREEN_HANDLE'):
    from lele.interaction import InteractiveVTKView
    from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
    from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow
    class OffscreenRenderWindow(vtkEGLRenderWindow):
        def SetWindowInfo(self, handle):
            # The Qt offscreen plugin provides no native drawable.
            self.SetOffScreenRendering(True)
    adapter.vtkRenderWindow=OffscreenRenderWindow
    result['display']='Qt offscreen with native VTK EGL offscreen target'
application.QApplication=ObservedApplication
application.main([str(sample)])
print(json.dumps(result))
sys.exit(0 if result.get('ok') and result.get('footer_pass') else 1)
