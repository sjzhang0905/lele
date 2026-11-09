"""CIF site probabilities: one position per site, without integerization."""
from collections import Counter
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import numpy as np


def site_species(frame,index):
    sites=frame.info.get('site_occupancies')
    return dict(sites[index]) if sites is not None else {frame.symbols[index]:1.}


def validate_site_species(rows):
    """Validate user-entered fractions without rounding an excess down to one."""
    from .chemical_analysis import ATOMIC_NUMBERS
    values={};total=Fraction(0);stored_numbers=True
    for row,(symbol,weight) in enumerate(rows.items() if isinstance(rows,dict) else rows,1):
        symbol=str(symbol).strip().capitalize()
        if symbol not in ATOMIC_NUMBERS:
            raise ValueError(f'Row {row}: enter a chemical element symbol, for example Fe or Ni.')
        if symbol in values:raise ValueError(f'Row {row}: {symbol} already has a row.')
        try:value=Decimal(str(weight).strip())
        except (InvalidOperation,ValueError):raise ValueError(f'Row {row}: occupancy must be a number from 0 to 1.') from None
        if not value.is_finite() or not 0<=value<=1:
            raise ValueError(f'Row {row}: occupancy must be a finite number from 0 to 1.')
        number=float(value)
        if value and number==0:raise ValueError(f'Row {row}: occupancy is too small to represent.')
        if value:total+=Fraction(value)
        values[symbol]=number
        stored_numbers=stored_numbers and not isinstance(weight,str)
    if not values:raise ValueError('Enter at least one element and its occupancy.')
    # Source values already stored as floats can have a decimal rendering just
    # above 1 while their stable floating-point sum is 1. Preserve those values
    # on a no-op edit; new text entry still gets the exact decimal check.
    from math import fsum
    if total>1 and not (stored_numbers and fsum(values.values())<=1):
        raise ValueError('Total occupancy must be less than or equal to 1. The remaining fraction is vacancy.')
    # Zero-weight components do not make an otherwise ordered site mixed.
    # A fully vacant site retains one zero-weight element as its site identity.
    return {s:v for s,v in values.items() if v>0} or {next(iter(values)):0.}


def change_site_species(frame,index,rows):
    """Edit one site's chemistry, keeping coordinates, IDs and other sites intact."""
    if not isinstance(index,(int,np.integer)) or isinstance(index,bool) or not 0<=index<len(frame.symbols):
        raise ValueError('Atom index is outside 1…N.')
    values=validate_site_species(rows)
    old=site_species(frame,index)
    maximum=max(values.values())
    representative=(frame.symbols[index] if values.get(frame.symbols[index])==maximum else
                    max(values,key=values.get))
    if list(values.items())==list(old.items()) and representative==frame.symbols[index]:return False
    sites=[site_species(frame,i) for i in range(len(frame.symbols))]
    sites[index]=values
    row_order=[];inserted=False
    for i,symbol in component_rows(frame):
        if i!=index:row_order.append((i,symbol))
        elif not inserted:
            row_order.extend((index,s) for s in values);inserted=True
    info={**frame.info,'site_occupancies':sites,'cif_row_order':row_order,'composition_edited':True}
    symbols=list(frame.symbols);symbols[index]=representative
    if 'poscar_groups' in info:
        from .poscar_labels import block_ids,groups_from_ids
        ids=block_ids(frame.info,frame.symbols)
        info['poscar_block_ids']=ids
        info['poscar_groups']=groups_from_ids(symbols,ids)
    # A probability change matters even when the representative element stays
    # the same. Old energy/force/spin values cannot describe this edited site.
    for key in tuple(info):
        if (key in ('energy_source','energy_source_line','optimization_converged',
                    'converter_mult','multiplicity','spin_polarized','vasp_free_energy_ev')
                or key.startswith(('qe_total_energy_','qe_energy_source_','qe_forces_',
                                   'cartesian_max_force_','cartesian_rms_force_','vasp_energy_'))):
            info.pop(key)
    frame.symbols=symbols;frame.info=info;frame.energy_ev=None
    return True


def is_disordered(frame):
    return any(len(s)!=1 or abs(next(iter(s.values()),0.)-1.)>1.e-8
               for s in frame.info.get('site_occupancies',[]))


def site_is_disordered(frame,index):
    values=site_species(frame,index)
    return len(values)!=1 or abs(next(iter(values.values()),0.)-1.)>1.e-8


def compact_species(frame,index):
    values=site_species(frame,index)
    parts=[f'{symbol}{value:.6g}' for symbol,value in values.items()]
    vacancy=max(0.,1-sum(values.values()))
    if vacancy>1.e-8:parts.append(f'□{vacancy:.6g}')
    return '/'.join(parts)


def occupied_elements(frame):
    """Include minority components when choosing an element's display colour."""
    return sorted({symbol for i in range(len(frame.symbols))
                   for symbol,value in site_species(frame,i).items() if value>0})


def maximum_occupancy_frame(frame):
    """An ordered export copy; never change the editable fractional model.

    Choose only among elements with positive occupancy, keep the current
    representative on ties, and omit sites that are completely vacant.
    """
    choices=[];omitted=[]
    for i in range(len(frame.symbols)):
        values=validate_site_species(site_species(frame,i))
        positive={symbol:value for symbol,value in values.items() if value>0}
        if not positive:
            omitted.append(i);continue
        maximum=max(positive.values())
        choices.append(frame.symbols[i] if positive.get(frame.symbols[i])==maximum else max(positive,key=positive.get))
    if not choices:raise ValueError('No occupied atomic sites to export; all sites are completely vacant.')
    from .poscar_labels import block_ids,groups_from_ids
    ids=(block_ids(frame.info,frame.symbols) if 'poscar_groups' in frame.info or 'poscar_block_ids' in frame.info else None)
    projected=frame.clone()
    from .selection_geometry import delete_selected_atoms
    delete_selected_atoms(projected,omitted)
    projected.symbols=choices;projected.energy_ev=None
    for key in ('site_occupancies','cif_row_order','poscar_groups','poscar_block_ids'):
        projected.info.pop(key,None)
    if ids is not None:
        removed=set(omitted);ids=[identity for i,identity in enumerate(ids) if i not in removed]
        projected.info['poscar_block_ids']=ids
        projected.info['poscar_groups']=groups_from_ids(choices,ids)
    return projected


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
