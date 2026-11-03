"""Selected atom clipboard: XYZ text plus optional LELE display metadata."""
from dataclasses import asdict
from itertools import groupby
from uuid import uuid4
import json
import numpy as np
from .core import Frame, visible_bonds, freeze_bonds, canonical_pair
from .atom_appearance import AtomAppearance

MIME='application/x-lele-atoms+json'


def copy_atoms(frame,selection,cutoff=1.0):
    indices=list(dict.fromkeys(int(i) for i in selection))
    if not indices or any(i<0 or i>=len(frame.symbols) for i in indices):raise ValueError('Select atoms first')
    positions=frame.positions[indices].copy()
    if any(frame.pbc):
        from .periodic_geometry import periodic_fragment,minimum_image
        try:
            preview=periodic_fragment(frame,indices,cutoff)
            positions=np.array([preview.image_positions[i] for i in indices])
        except ValueError:
            anchor=positions[0].copy();positions=np.array([anchor+minimum_image(p-anchor,frame)[0] for p in positions])
    positions-=positions.mean(axis=0)
    remap={old:new for new,old in enumerate(indices)}
    fragment=Frame([frame.symbols[i] for i in indices],positions,
        bond_added={(remap[a],remap[b]) for a,b in frame.bond_added if a in remap and b in remap},
        bond_removed={(remap[a],remap[b]) for a,b in frame.bond_removed if a in remap and b in remap},
        atom_appearance={remap[i]:style for i,style in frame.atom_appearance.items() if i in remap})
    from .site_occupancy import subset_info
    subset=subset_info(frame.info,indices)
    for key in ('site_occupancies','cif_row_order'):
        if key in subset:fragment.info[key]=subset[key]
    if any(frame.pbc):
        from .periodic_geometry import periodic_bonds
        pairs = {(i,j) for i,j,_ in periodic_bonds(frame,cutoff) if i != j}
    else:
        pairs = set(visible_bonds(frame,cutoff))
    fragment.bond_snapshot = frozenset(tuple(sorted((remap[a],remap[b])))
                                      for a,b in pairs if a in remap and b in remap)
    fragment.hbond_added = {canonical_pair(remap[a],remap[b]): (0,0,0)
                            for a,b in frame.hbond_added if a in remap and b in remap}
    fragment.hbond_removed = {canonical_pair(remap[a],remap[b])
                              for a,b in frame.hbond_removed if a in remap and b in remap}
    text=str(len(indices))+'\nLELE selected atoms; centroid at origin\n'
    text+='\n'.join(f'{s} {p[0]:.12f} {p[1]:.12f} {p[2]:.12f}' for s,p in zip(fragment.symbols,positions))+'\n'
    metadata=json.dumps(dict(symbols=fragment.symbols,positions=positions.tolist(),
        info=fragment.info,
        added=sorted(fragment.bond_added),removed=sorted(fragment.bond_removed),
        bonds=sorted(fragment.bond_snapshot),
        hbonds=[[a,b,list(s)] for (a,b),s in sorted(fragment.hbond_added.items())],
        hbonds_removed=sorted(fragment.hbond_removed),
        styles={str(i):asdict(style) for i,style in fragment.atom_appearance.items()}))
    return text,metadata


def read_atoms(text,metadata=None):
    if metadata:
        data=json.loads(metadata)
        if not 0<len(data['symbols'])<=50000:raise ValueError('Invalid copied atom count')
        return Frame(data['symbols'],data['positions'],info=data.get('info',{}),bond_added={tuple(p) for p in data.get('added',[])},
            bond_removed={tuple(p) for p in data.get('removed',[])},
            atom_appearance={int(i):AtomAppearance(**style) for i,style in data.get('styles',{}).items()},
            bond_snapshot=None if 'bonds' not in data else frozenset(tuple(p) for p in data['bonds']),
            hbond_added={(a,b):tuple(s) for a,b,s in data.get('hbonds',[])},
            hbond_removed={tuple(p) for p in data.get('hbonds_removed',[])})
    lines=text.strip().splitlines();count=int(lines[0])
    if not 0<count<=50000 or len(lines)<count+2:raise ValueError('Clipboard must contain XYZ atom coordinates')
    from .chemical_analysis import ATOMIC_NUMBERS
    symbols=[];positions=[]
    for line in lines[2:count+2]:
        fields=line.split()
        if len(fields)<4 or fields[0] not in ATOMIC_NUMBERS:raise ValueError('Invalid XYZ atom row')
        symbols.append(fields[0]);positions.append([float(v) for v in fields[1:4]])
    positions=np.asarray(positions);positions-=positions.mean(axis=0)
    return Frame(symbols,positions)


def paste_atoms(target,fragment,point,cutoff=1.0):
    freeze_bonds(target,cutoff)
    internal = visible_bonds(fragment,cutoff)
    n=len(target.symbols);count=len(fragment.symbols)
    from .atom_indices import source_order
    identities=list(source_order(target))+['added:'+uuid4().hex for _ in range(count)]
    from .site_occupancy import component_rows
    ordered_rows=None
    if any(k in f.info for f in (target,fragment) for k in ('site_occupancies','cif_row_order')):
        ordered_rows=component_rows(target)+[(n+i,s) for i,s in component_rows(fragment)]
    block_membership=None
    if 'poscar_groups' in target.info:
        from .poscar_labels import block_ids
        old_blocks=block_ids(target.info,target.symbols);start=max(old_blocks,default=-1)+1
        fragment_groups=[(s,len(list(g))) for s,g in groupby(fragment.symbols)]
        block_membership=old_blocks+[start+i for i,(_,size) in enumerate(fragment_groups) for _ in range(size)]
    if 'vasp_fixed_axes' in target.info:
        target.info['vasp_fixed_axes']=[list(v) for v in target.info['vasp_fixed_axes']]+[[False]*3 for _ in range(count)]
    from .site_occupancy import site_species
    occupancies=([site_species(target,i) for i in range(n)]+[site_species(fragment,i) for i in range(count)]
                 if 'site_occupancies' in target.info or 'site_occupancies' in fragment.info else None)
    target.symbols+=fragment.symbols
    target.positions=np.concatenate((target.positions,fragment.positions+np.asarray(point)),axis=0)
    if occupancies is not None:target.info['site_occupancies']=occupancies
    target.info['atom_source_order']=identities
    if ordered_rows is not None:target.info['cif_row_order']=ordered_rows
    for name in ('bond_added','bond_removed'):
        getattr(target,name).update((a+n,b+n) for a,b in getattr(fragment,name))
    target.atom_appearance.update({n+i:style for i,style in fragment.atom_appearance.items()})
    target.hbond_added.update({(n+i,n+j):shift for (i,j),shift in fragment.hbond_added.items()})
    target.hbond_removed.update((n+i,n+j) for i,j in fragment.hbond_removed)
    target.bond_snapshot = target.bond_snapshot | frozenset((n+i,n+j) for i,j in internal)
    if target.periodic_bond_snapshot is not None:
        target.periodic_bond_snapshot += tuple((n+i,n+j,(0,0,0)) for i,j in internal)
    if 'poscar_groups' in target.info:
        from .poscar_labels import groups_from_ids
        target.info['poscar_block_ids']=block_membership
        target.info['poscar_groups']=groups_from_ids(target.symbols,block_membership)
    target.energy_ev=None;target.info.pop('energy_source',None);target.info.pop('plane_alignment',None)
    target.info.pop('optimization_converged',None)
    return list(range(n,n+count))
