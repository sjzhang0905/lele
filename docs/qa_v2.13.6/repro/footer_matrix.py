"""Run once per style/point size. Use an empty output directory per invocation."""
import json, os
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from render_harness import app, out, w

def settle():
    for _ in range(5):app.processEvents()

def dims():
    return [w.width(),w.height(),w.vtk.width(),w.vtk.height(),w.footer_row.height()]

results=[]
try:
    path=out/'layout.xyz'
    path.write_text('5\nfooter layout\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\nHe 3 2 1\nNe 3 -2 2\n')
    w._open_path_now(path)
    for width,height in ((1024,768),(1380,850),(1920,1080)):
        w.resize(width,height)
        settle()
        base=dims()
        seq=[]
        for n in (0,1,2,3,4,0,2,0):
            w.atom_table.clearSelection()
            for k in range(n):
                pt=w.atom_table.visualItemRect(w.atom_table.item(k,0)).center()
                QTest.mouseClick(w.atom_table.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,pt)
            settle()
            assert w.selection==list(range(n))
            assert dims()==base,(base,dims(),n)
            if n==2: assert w.measurement_value.isVisible() and w.measurement_set.isVisible()
            seq.append([n,*dims()])
        results.append({'requested':[width,height],'states':seq})
finally:
    (out/'footer_matrix.json').write_text(json.dumps({'style':app.style().objectName(),'point_size':app.font().pointSize(),'windows':results},indent=2))
    for d in w.documents:d.modified=False
    w.close()
    app.processEvents()
