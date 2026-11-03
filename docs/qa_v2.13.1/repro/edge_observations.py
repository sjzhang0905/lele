"""Generate the concrete inputs, exports and structured observations behind the findings."""
from pathlib import Path
import sys,json
import numpy as np
from ase.io.cif import parse_cif
from lele.core import Frame,Document
from lele.formats import load_document,export_frame
from lele.atom_clipboard import paste_atoms
from lele.atom_indices import reorder_atoms,index_order,source_order
from lele.selection_geometry import delete_selected_atoms
from lele.trajectory_analysis import GeometryParameter,parameter_values
from test_delta_213 import make_cif,POSCAR

root=Path(sys.argv[1]);root.mkdir(exist_ok=True,parents=True);out={}
def imported(p):
    try:return {'sites':load_document(p).frames[0].info['site_occupancies']}
    except Exception as exc:return {'error':str(exc)}
raw='Co1 Co 0 .5 .25 .6\nNi1 Ni 0 .5 .25 .4\nO1 O .4 .3 .2 1\n'
for key,ang,rows in [('orthogonal',(90,90,90),raw),('skew_face',(76,88,105),raw),('translated',(76,88,105),raw.replace('Ni1 Ni 0','Ni1 Ni 1'))]:
    p=make_cif(root/(key+'.cif'),rows,ang)
    atom=next(parse_cif(str(p))).get_atoms(fractional_occupancies=True)
    x=atom.get_scaled_positions(wrap=False)[0,0]
    out[key]={'x':float(x),'x_mod_1':float(x%1),**imported(p)}
rows='Co1 Co .25 .5 .25 .1666667\nNi1 Ni .25 .5 .25 .1666667\nFe1 Fe .25 .5 .25 .6666666\nO1 O .75 .5 .4 1\n'
p=make_cif(root/'thirds.cif',rows)
f=load_document(p).frames[0];export_frame(f,root/'thirds_exported.cif','cif')
out['thirds']={'before':f.info['site_occupancies'], 'after':imported(root/'thirds_exported.cif')}
rows='Co1 Co .1 .2 .3 .6\nNi1 Ni .1 .2 .3 .4\nO1 O .3 .4 .5 1\n'
p=make_cif(root/'mixed_before.cif',rows);f=load_document(p).frames[0]
paste_atoms(f,Frame(['H'],[[0,0,0]]),[2,3,3])
p=root/'mixed_appended.cif';export_frame(f,p,'cif');re=load_document(p).frames[0]
out['mixed_plus_h']={'written_rows':next(parse_cif(str(p)))['_atom_site_type_symbol'],'reread_sites':re.info['site_occupancies']}
p=root/'blocks.POSCAR';p.write_text(POSCAR);f=load_document(p).frames[0]
reorder_atoms(f,index_order(4,2,3,swap=3));p=root/'blocks_oxygen_swap.POSCAR';export_frame(f,p,'poscar-direct')
out['blocks']={'written_header':p.read_text().splitlines()[5:7]}
initial=Frame(['O','H','H','C'],[[0,0,0],[1,0,0],[0,2,0],[5,5,0]])
doc=Document(Path('same.xyz'),'XYZ',[initial.clone(),initial.clone()]);a,b=doc.frames
reorder_atoms(a,index_order(4,1,2,swap=2))
def monitor():return GeometryParameter('Distance',(0,1),reference_order=source_order(a),reference_symbols=tuple(a.symbols))
def measure(p):return parameter_values(doc,[0,1],p,a.symbols).tolist()
p=monitor();old=measure(p)
delete_selected_atoms(a,[3]);paste_atoms(a,Frame(['C'],[[0,0,0]]),[5,5,0])
out['distances']={'original':old,'after_replacing_C_existing_monitor':measure(p),'after_replacing_C_new_monitor':measure(monitor())}
print(json.dumps(out,indent=2))
