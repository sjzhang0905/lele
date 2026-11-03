"""Run from the source root. Supply the earlier project POSCAR1 and 22.cif."""
import json, sys, tempfile
from pathlib import Path
import numpy as np
from ase.io import read
from lele.formats import load_document, export_frame
from lele.vacuum import change_vacuum, slab_vacuum
from lele.site_occupancy import composition
from lele.atom_indices import reorder_atoms,index_order

def flags(path):
    a=read(path,format='vasp')
    restricted=np.zeros((len(a),3),bool)
    for item in a.constraints:
        restricted[item.get_indices()] = getattr(item,'mask',[True,True,True])
    return {'fully_fixed':int(restricted.all(axis=1).sum()),'partially_fixed':int((restricted.any(axis=1)&~restricted.all(axis=1)).sum())}

def inspect(poscar,cif):
    out={}
    with tempfile.TemporaryDirectory() as t:
        temp=Path(t)
        f=load_document(poscar).frames[0]; d=slab_vacuum(f); original=f.clone()
        out['POSCAR1']={'atom_count':len(f.symbols),'before_flags':flags(poscar),
                       'source_order':list(dict.fromkeys(f.symbols)),'axis':d['axis'],'source_gap_A':d['gap'],'split':d['split']}
        for op in ('unchanged','vacuum','reindex'):
            g=original.clone()
            if op=='vacuum':change_vacuum(g,d['gap']+5,d['axis'])
            if op=='reindex':reorder_atoms(g,index_order(len(g.symbols),0,1,swap=1))
            p=temp/(op+'.POSCAR');export_frame(g,p,'poscar-direct')
            reread=load_document(p).frames[0]
            out['POSCAR1'][op]={'after_flags':flags(p),'order':list(dict.fromkeys(reread.symbols)),
                    'same_row_symbols_as_edited':reread.symbols==g.symbols,'in_memory_max_cart_delta':float(abs(g.positions-original.positions).max())}
        raw=cif.read_text()
        out['22.cif']={'declares_occupancy':'_atom_site_occupancy' in raw}
        try:load_document(cif);out['22.cif']['original']='OK'
        except Exception as exc:out['22.cif']['original']=str(exc)
        p=temp/'with_P1.cif'
        p.write_text(raw.replace('data_CIF','data_CIF\n_space_group_IT_number 1',1))
        f=load_document(p).frames[0]
        out['22.cif']['one_tag_control']={'atom_count':len(f.symbols),'composition':composition(f)}
        # Same failure on a small generated file with a real occupancy column.
        from test_acceptance_extra import CIF
        p=temp/'only_symops.cif';p.write_text(CIF.replace("_space_group_name_H-M_alt 'P 1'\n",''))
        try:load_document(p);out['22.cif']['synthetic_only_symops']='OK'
        except Exception as exc:out['22.cif']['synthetic_only_symops']=str(exc)
    return out

if __name__=='__main__':
    print(json.dumps(inspect(*(Path(x) for x in sys.argv[1:])),indent=2))
