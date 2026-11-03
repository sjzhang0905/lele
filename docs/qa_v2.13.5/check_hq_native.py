"""Inspect the production PNG action, annotations and restored live view."""
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog
from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow


class OffscreenRenderWindow(vtkEGLRenderWindow):
    def SetWindowInfo(self, _handle):
        self.SetOffScreenRendering(True)


adapter.vtkRenderWindow = OffscreenRenderWindow
import lele
from lele.app import LELEWindow
from lele.png_dialog import PngExportDialog
from lele.png_export import PngSettings, export_png

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
app = QApplication(['LELE PNG validation'])
app.setStyle('Fusion')
w = LELEWindow()
w.show()


def settle():
    for _ in range(6):
        app.processEvents()


def state():
    cam = w.scene.GetActiveCamera()
    return dict(canvas=[w.vtk.width(), w.vtk.height()], render_size=w.vtk.GetRenderWindow().GetSize(),
                position=cam.GetPosition(), focal=cam.GetFocalPoint(), up=cam.GetViewUp(),
                scale=cam.GetParallelScale(), tile=w.vtk.GetRenderWindow().GetTileScale(),
                props=w.scene.GetViewProps().GetNumberOfItems(),
                font_sizes=[a.GetTextProperty().GetFontSize() for a in w.renderer._label_actors],
                annotation_fonts=[prop.GetTextProperty().GetFontSize()
                                  for renderer in w.vtk.GetRenderWindow().GetRenderers()
                                  for prop in renderer.GetViewProps() if hasattr(prop, 'GetTextProperty')])


start = time.monotonic()
while w._backend_state not in ('ready', 'failed') and time.monotonic() - start < 30:
    settle()
    time.sleep(.005)
assert w._backend_state == 'ready', w._backend_state
result = dict(version=lele.__version__)
try:
    sample = Path(lele.__file__).parent.parent / 'examples/synthetic_properties.log'
    w._open_path_now(sample)
    w.change_frame(len(w.doc.frames)-1)
    w._set_option('labels', 'Index (1..N)')
    w._set_option('label_color', '#FF00CC')
    w._set_option('dipole_mode', 'Total')
    settle()
    assert w.renderer.dipole_vector is not None
    assert w.atom_palette_combo.currentText() == 'Default'
    assert w.bond_slider.value() == 7
    initial = state()
    window = w.vtk.GetRenderWindow()
    source_size = window.GetSize()
    export_png(root/'native_1x.png', window, PngSettings(*source_size, supersample=1), mesh_items=w.renderer._keepalive)
    assert state() == initial

    settings_seen = []
    def accept_options(dialog):
        settings_seen.append(dialog.settings())
        assert dialog.settings().supersample == 2
        dialog.show()
        settle()
        dialog.grab().save(str(root/'png_quality_options.png'))
        dialog.hide()
        return QDialog.DialogCode.Accepted

    with patch('lele.app.QFileDialog.getSaveFileName', return_value=(str(root/'native_hq_3x.png'), '')), \
            patch.object(PngExportDialog, 'exec', accept_options), \
            patch('lele.app.QMessageBox.warning') as warning:
        w.save_png()
        assert not warning.called, warning.call_args
    settle()
    assert state() == initial, (initial, state())
    with Image.open(root/'native_hq_3x.png') as im:
        assert im.size == (source_size[0]*3, source_size[1]*3)
        assert im.info['dpi'][0] > 299
        thumb = im.resize(source_size, Image.Resampling.LANCZOS)
        thumb.save(root/'native_hq_at_canvas_size.png')
        pixels = np.asarray(thumb)
        # Verify colored molecular labels and corner-axis arrows survive tiling.
        assert np.count_nonzero((pixels[:,:,0] > 160) & (pixels[:,:,2] > 110) & (pixels[:,:,1] < 130)) > 10
        corner = pixels[-round(pixels.shape[0]*.3):, :round(pixels.shape[1]*.3)]
        assert np.count_nonzero(np.max(corner,axis=2)-np.min(corner,axis=2) > 80) > 30
        def green_text_bounds(image):
            rgb=np.asarray(image)[:65].astype(float)
            mask=(rgb[:,:,1]>80)&(rgb[:,:,1]>rgb[:,:,0]*1.5)&(rgb[:,:,1]>rgb[:,:,2]*1.25)
            yy,xx=np.nonzero(mask)
            assert len(xx)>20
            return int(xx.max()-xx.min()+1),int(yy.max()-yy.min()+1)
        with Image.open(root/'native_1x.png') as original:
            old_text=green_text_bounds(original)
        new_text=green_text_bounds(thumb)
        assert all(.8<=new/old<=1.2 for new,old in zip(new_text,old_text)),(old_text,new_text)
        result['converged_text_bounds_at_canvas_size']={'before':old_text,'export':new_text}
    export_png(root/'native_after_export.png', window, PngSettings(*source_size, supersample=1), mesh_items=w.renderer._keepalive)
    with Image.open(root/'native_1x.png') as before, Image.open(root/'native_after_export.png') as after:
        difference=np.mean(abs(np.asarray(before).astype(float)-np.asarray(after).astype(float)))
        assert difference<.5,difference
        result['live_view_mean_rgb_difference_after_export']=float(difference)
    result.update(source_size=source_size, output_size=(settings_seen[0].width, settings_seen[0].height),
                  smooth_edges=True, png_action_ok=True, live_view_unchanged=True,
                  labels_and_corner_axes_present=True, dipole_vector=w.renderer.dipole_vector.tolist(),
                  default_h_radius=w.renderer._atom_radius('H'), ok=True)
finally:
    for document in w.documents:
        document.modified=False
    w.close()
    app.processEvents()
    loader=getattr(app, '_lele_backend_loader', None)
    if loader is not None:loader.wait()
    (root/'native_png.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
