"""Run from outside the LELE source with the installed LELE on sys.path.
Pass the source examples directory, and an empty result directory.
Uses the production Save PNG action; automates only the file and options dialogs.
"""
import json
from unittest.mock import patch
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QDialog
from render_harness import app, out, samples, screenshot, w
import lele
from lele.png_dialog import PngExportDialog

report = {'package':lele.__file__, 'version':lele.__version__, 'scenes':{}}
def analyze(im):
    roi = im.crop((0,round(im.height*.75),round(im.width*.24),im.height))
    rgb = np.asarray(roi).astype(int)
    mask = rgb.max(2) - rgb.min(2) > 45
    def stats(m):
        y,x=np.nonzero(m)
        return dict(pixels=len(x), width=int(np.ptp(x))+1 if len(x) else 0,
                    height=int(np.ptp(y))+1 if len(y) else 0)
    return {key:stats(binary) for key,binary in [('all',mask),
        ('red',mask & (rgb.argmax(2)==0)),('green',mask & (rgb.argmax(2)==1)),
        ('blue',mask & (rgb.argmax(2)==2))]}

try:
    for scene, sample in [('molecule','water.xyz'),('crystal','Si_POSCAR')]:
        w._open_path_now(samples/sample)
        for _ in range(5):app.processEvents()
        assert w.render_options.axes_position=='Corner'
        window = w.vtk.GetRenderWindow()
        size = tuple(window.GetSize())
        base = screenshot(window)
        base.save(out/(scene+'_live.png'))
        stats = report['scenes'][scene] = {'size':size,'live':analyze(base)}
        for factor,smoothing in [(n,s) for n in (1,2,3,4) for s in (False,True)]:
            tag=f'{factor}x_'+('smooth' if smoothing else 'standard')
            path=out/f'{scene}_{tag}.png'
            def configure(dialog):
                dialog.scale_combo.setCurrentIndex(factor-1)
                dialog.smooth_check.setChecked(smoothing)
                settings=dialog.settings()
                assert settings.width==factor*size[0] and settings.height==factor*size[1]
                return QDialog.DialogCode.Accepted
            with patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(path),'')), \
                    patch.object(PngExportDialog,'exec',configure), \
                    patch('lele.app.QMessageBox.warning') as warning:
                w.save_png()
                assert not warning.called, warning.call_args
            with Image.open(path) as saved:
                assert saved.size==(factor*size[0],factor*size[1])
                at_canvas=saved.resize(size,Image.Resampling.LANCZOS)
                stats[tag]=analyze(at_canvas)
                # retain a pixel-for-pixel crop for human comparison
                at_canvas.crop((0,round(size[1]*.75),round(size[0]*.24),size[1])).save(out/(scene+'_'+tag+'_corner.png'))
            after=screenshot(window)
            assert np.array_equal(np.asarray(base),np.asarray(after))
        base.crop((0,round(size[1]*.75),round(size[0]*.24),size[1])).save(out/(scene+'_live_corner.png'))
        print(scene,stats,flush=True)
finally:
    for doc in w.documents:doc.modified=False
    w.close()
    app.processEvents()
    (out/'axis_probe.json').write_text(json.dumps(report,indent=2)+'\n')
