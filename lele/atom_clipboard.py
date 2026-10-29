"""Selected atom clipboard: XYZ text plus optional LELE display metadata."""
from dataclasses import asdict
from itertools import groupby
import json
import numpy as np
from .core import Frame, visible_bonds, freeze_bonds, canonical_pair
from .atom_appearance import AtomAppearance

MIME='application/x-lele-atoms+json'


def copy_atoms(frame,selection,cutoff=1.18):
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
        return Frame(data['symbols'],data['positions'],bond_added={tuple(p) for p in data.get('added',[])},
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


def paste_atoms(target,fragment,point,cutoff=1.18):
    freeze_bonds(target,cutoff)
    internal = visible_bonds(fragment,cutoff)
    n=len(target.symbols);count=len(fragment.symbols)
    target.symbols+=fragment.symbols
    target.positions=np.concatenate((target.positions,fragment.positions+np.asarray(point)),axis=0)
    for name in ('bond_added','bond_removed'):
        getattr(target,name).update((a+n,b+n) for a,b in getattr(fragment,name))
    target.atom_appearance.update({n+i:style for i,style in fragment.atom_appearance.items()})
    target.hbond_added.update({(n+i,n+j):shift for (i,j),shift in fragment.hbond_added.items()})
    target.hbond_removed.update((n+i,n+j) for i,j in fragment.hbond_removed)
    target.bond_snapshot = target.bond_snapshot | frozenset((n+i,n+j) for i,j in internal)
    if target.periodic_bond_snapshot is not None:
        target.periodic_bond_snapshot += tuple((n+i,n+j,(0,0,0)) for i,j in internal)
    if 'poscar_groups' in target.info:
        target.info['poscar_groups']=list(target.info['poscar_groups'])+[(s,len(list(g))) for s,g in groupby(fragment.symbols)]
    target.energy_ev=None;target.info.pop('energy_source',None);target.info.pop('plane_alignment',None)
    return list(range(n,n+count))
