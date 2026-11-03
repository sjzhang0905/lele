"""Measure native corner glyphs, each against the same renderer without labels.
Uses axis_probe.py's headless bootstrap. The 80% anchor is a diagnostic control.
Run with the same arguments as axis_probe.py.
"""
import json
import numpy as np
from render_harness import app, out, samples, screenshot, w
result={}
try:
    for scene,sample in [('molecule','water.xyz'),('crystal','Si_POSCAR')]:
        w._open_path_now(samples/sample)
        for _ in range(5):app.processEvents()
        window=w.vtk.GetRenderWindow()
        overlay=w.axes_widget.GetRenderer()
        labels=w.renderer.corner_labels
        vw,vh=window.GetSize()
        viewport=list(overlay.GetViewport())
        top=(1-viewport[3])*vh
        result[scene]={'viewport':viewport,'canvas':[vw,vh],'viewport_top_in_image':top,'letters':{}}
        for a in labels:a.VisibilityOff()
        blank=np.asarray(screenshot(window)).astype(int)
        for a in labels:
            a.VisibilityOn()
            pos=np.array(a.GetPosition())
            letter=a.GetInput()
            row=result[scene]['letters'][letter]={}
            for tag,factor in [('original',1),('inset_control',.80)]:
                a.SetPosition(*(pos*factor))
                im=screenshot(window)
                pixels=np.asarray(im).astype(int)
                mask=(abs(pixels-blank).max(axis=2)>30)
                y,x=np.nonzero(mask)
                row[tag]={'x':int(x.min()),'y':int(y.min()),'width':int(np.ptp(x))+1,
                          'height':int(np.ptp(y))+1,'pixels':int(len(x))} if len(x) else {'pixels':0}
                if letter==labels[-1].GetInput():
                    im.crop((0,int(top)-16,round(vw*.24),vh)).save(out/(scene+'_'+tag+'_lastlabel.png'))
            a.SetPosition(*pos)
            a.VisibilityOff()
        for a in labels:a.VisibilityOn()
    (out/'live_label_probe.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
finally:
    for doc in w.documents:doc.modified=False
    w.close()
    app.processEvents()
