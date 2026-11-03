"""Real atom-order changes; every index-bearing frame property follows atoms."""
import numpy as np
from .site_occupancy import subset_info


def source_order(frame):
    return tuple(frame.info.get('atom_source_order',range(len(frame.symbols))))


def mapping_from_order(symbols,order,target,*,allow_partial=False):
    """Reference row → target row, using known identities and element checks."""
    try:
        if len(order)!=len(symbols):return None
        other=source_order(target)
        if len(other)!=len(target.symbols) or len(set(order))!=len(order) or len(set(other))!=len(other):return None
        if not allow_partial and (len(symbols)!=len(target.symbols) or set(order)!=set(other)):return None
        rows={identity:i for i,identity in enumerate(other)}
        mapping=tuple(rows.get(identity) for identity in order)
        mapping=tuple(j if j is not None and symbol==target.symbols[j] else None for symbol,j in zip(symbols,mapping))
    except (TypeError,KeyError):return None
    return mapping if allow_partial or all(j is not None for j in mapping) else None


def atom_mapping(reference,target,*,allow_partial=False):
    if reference is target:return tuple(range(len(reference.symbols)))
    return mapping_from_order(reference.symbols,source_order(reference),target,allow_partial=allow_partial)


def reorder_atoms(frame,order):
    order=[int(i) for i in order];n=len(frame.symbols)
    if sorted(order)!=list(range(n)):raise ValueError('Atom order must be a permutation of all atom indices.')
    remap={old:new for new,old in enumerate(order)}
    def pair(p):return tuple(sorted((remap[p[0]],remap[p[1]])))
    def edge(i,j,s):
        a,b=remap[i],remap[j];shift=np.asarray(s,dtype=int)
        if a>b:a,b=b,a;shift=-shift
        return a,b,tuple(int(v) for v in shift)
    base_info=dict(frame.info)
    if 'poscar_groups' in base_info:
        from .poscar_labels import block_ids
        base_info['poscar_block_ids']=block_ids(base_info,frame.symbols)
    info=subset_info(base_info,order)
    source_order=frame.info.get('atom_source_order',list(range(n)))
    info['atom_source_order']=[source_order[i] for i in order]
    info['atom_order_edited']=True
    for key in ('qe_forces_ev_ang',):
        if key in info:info[key]=np.asarray(info[key])[order].copy()
    for key in ('plane_alignment','coordinate_reorientation'):info.pop(key,None)
    symbols=[frame.symbols[i] for i in order]
    if 'poscar_groups' in info:
        from .poscar_labels import groups_from_ids
        info['poscar_groups']=groups_from_ids(symbols,info['poscar_block_ids'])
    frame.positions=frame.positions[order].copy();frame.symbols=symbols;frame.info=info
    frame.bond_added={pair(p) for p in frame.bond_added};frame.bond_removed={pair(p) for p in frame.bond_removed}
    frame.atom_appearance={remap[i]:s for i,s in frame.atom_appearance.items()}
    if frame.bond_snapshot is not None:frame.bond_snapshot=frozenset(pair(p) for p in frame.bond_snapshot)
    if frame.periodic_bond_snapshot is not None:frame.periodic_bond_snapshot=tuple(edge(i,j,s) for i,j,s in frame.periodic_bond_snapshot)
    frame.hbond_added={e[:2]:e[2] for (i,j),s in frame.hbond_added.items() for e in [edge(i,j,s)]}
    frame.hbond_removed={pair(p) for p in frame.hbond_removed}
    return remap


def index_order(count,atom,target,*,swap=None):
    if not 0<=atom<count or not 0<=target<count:raise ValueError('Atom index is outside 1…N.')
    order=list(range(count))
    if swap is not None:
        if not 0<=swap<count:raise ValueError('Atom index is outside 1…N.')
        order[atom],order[swap]=order[swap],order[atom]
    else:order.insert(target,order.pop(atom))
    return order
