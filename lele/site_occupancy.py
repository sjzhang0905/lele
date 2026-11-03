"""CIF site probabilities: one position per site, without integerization."""
from collections import Counter
import numpy as np


def site_species(frame,index):
    sites=frame.info.get('site_occupancies')
    return dict(sites[index]) if sites is not None else {frame.symbols[index]:1.}


def is_disordered(frame):
    return any(len(s)!=1 or abs(next(iter(s.values()),0.)-1.)>1.e-8
               for s in frame.info.get('site_occupancies',[]))


def from_ase(atoms):
    if 'lele_site_occupancies' in atoms.info:
        out={'site_occupancies':[dict(values) for values in atoms.info['lele_site_occupancies']]}
        if 'lele_cif_row_order' in atoms.info:out['cif_row_order']=list(atoms.info['lele_cif_row_order'])
        return out
    occupancy=atoms.info.get('occupancy')
    if not isinstance(occupancy,dict):return {}
    kinds=atoms.arrays.get('spacegroup_kinds',np.arange(len(atoms)))
    sites=[]
    for i,kind in enumerate(kinds):
        values={str(s):float(v) for s,v in occupancy.get(str(int(kind)),{atoms[i].symbol:1.}).items()}
        if any(not np.isfinite(v) or v<0 or v>1+1.e-6 for v in values.values()) or sum(values.values())>1+1.e-6:
            raise ValueError(f'Invalid CIF occupancy at expanded site {i+1}; values are retained only for physical site probabilities.')
        sites.append(values)
    return {'site_occupancies':sites}


def subset_info(info,indices):
    indices=list(map(int,indices))
    out=dict(info)
    for key in ('site_occupancies','atom_source_order','vasp_fixed_axes','poscar_block_ids'):
        if key in info:out[key]=[info[key][i] for i in indices]
    if 'cif_row_order' in info:
        rows=info['cif_row_order']
        if indices==sorted(set(indices)):
            remap={old:new for new,old in enumerate(indices)}
            out['cif_row_order']=[(remap[i],s) for i,s in rows if i in remap]
        else:
            # An explicit reindex or replica list defines a new site order;
            # keep each site's original component order within that order.
            by_site={}
            for i,s in rows:by_site.setdefault(i,[]).append(s)
            out['cif_row_order']=[(new,s) for new,old in enumerate(indices) for s in by_site.get(old,[])]
    return out


def component_rows(frame):
    """One row per distinct site component, in retained source/addition order."""
    sites=[site_species(frame,i) for i in range(len(frame.symbols))]
    rows=[];seen=set()
    for i,s in frame.info.get('cif_row_order',[]):
        if 0<=i<len(sites) and s in sites[i] and (i,s) not in seen:
            rows.append((i,s));seen.add((i,s))
    for i,values in enumerate(sites):
        for s in values:
            if (i,s) not in seen:rows.append((i,s));seen.add((i,s))
    return rows


def composition(frame):
    if 'site_occupancies' not in frame.info:
        from .structure_summary import molecular_formula
        return molecular_formula(frame.symbols)
    counts=Counter()
    for i in range(len(frame.symbols)):counts.update(site_species(frame,i))
    symbols=sorted(counts)
    if 'C' in symbols:symbols=['C']+(['H'] if 'H' in symbols else [])+[s for s in symbols if s not in ('C','H')]
    return ''.join(s+('' if abs(counts[s]-1)<1.e-8 else f'{counts[s]:.6g}') for s in symbols if counts[s]>1.e-12)


def description(frame,index):
    values=site_species(frame,index)
    text=', '.join(f'{s} {v:.6g}' for s,v in values.items())
    vacancy=max(0.,1-sum(values.values()))
    if vacancy>1.e-8:text+=f'; vacancy {vacancy:.6g}'
    return text
