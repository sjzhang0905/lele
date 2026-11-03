"""Check palette and legend against a two-stage lighten of the reference TCL."""
import csv,json,re,sys
from pathlib import Path
import numpy as np
from vtkmodules.vtkRenderingCore import vtkRenderer
from lele.atom_legend import legend_samples
from lele.core import Frame,colour
from lele.display_reference import SYMBOLS
from lele.renderer import MoleculeRenderer
from lele.style_presets import element_palette_color
tcl,out=map(Path,sys.argv[1:3])
text=tcl.read_text()
raw={int(i):tuple(round(float(x)*255) for x in (a,b,c)) for i,a,b,c in
     re.findall(r'^color change rgb (\d+) ([\d.]+) ([\d.]+) ([\d.]+)',text,re.M)}
e=re.search(r'set elem_color_list\s*\{([^}]+)\}',text).group(1).split()
source={s:raw[int(i)] for s,i in zip(e[::2],e[1::2])}
assert len(source)==111
source['D']=source['H']
slist=list(SYMBOLS)+['D']
draw=MoleculeRenderer(vtkRenderer())
frame=Frame(slist,np.array([[i*5.,0,0] for i in range(len(slist))]))
draw.set_scene(frame)
legend={s['symbol']:s for s in legend_samples(draw)}
assert len(legend)==119
def lighten(rgb,white):
    return tuple(round(x*(1-white)+255*white) for x in rgb)
vals={}
for i,s in enumerate(slist):
    base=source[s] if s in source else tuple(int(colour(s)[v:v+2],16) for v in (1,3,5))
    rgb=lighten(lighten(base,.10),.05)
    result='#'+''.join(f'{v:02X}' for v in rgb)
    assert result==draw.atom_color(frame,i)==draw.atom_color(frame,i,for_bond=True)==legend[s]['color']==element_palette_color(draw.options,s),(s,result)
    vals[s]=result
assert draw._atom_radius('H')==legend['H']['radius'] and abs(legend['H']['radius']-.17825)<1e-12
out.write_text(json.dumps(dict(elements=len(vals),radius_H=legend['H']['radius'],options={'bond_scale':draw.options.bond_scale,'atom_scale':draw.options.atom_scale,'palette':draw.options.atom_palette,'finish':draw.options.surface_finish,'background':draw.options.background},colors=vals),indent=2)+'\n')
print(len(vals),'colors verified')
