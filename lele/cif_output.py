"""P1 CIF output with stable component rows and round-trip occupancy precision."""
from pathlib import Path
import numpy as np
from ase.io.cif import CIFLoop,autolabel,format_cell,format_generic_spacegroup_info
from .site_occupancy import component_rows,site_species


def write_frame_cif(frame,atoms,path):
    rows=component_rows(frame)
    sites=[site_species(frame,i) for i in range(len(frame.symbols))]
    for values in sites:
        if (not values or any(not np.isfinite(v) or not 0<=v<=1+1.e-6 for v in values.values())
                or sum(values.values())>1+1.e-6):raise ValueError('Invalid CIF site occupancy.')
    if atoms.cell.rank==3:
        kind='fract';positions=atoms.get_scaled_positions(wrap=False)
        header=format_cell(atoms.cell)+'\n'+format_generic_spacegroup_info()+'\n'
    elif atoms.cell.rank==0:
        kind='Cartn';positions=atoms.positions;header=''
    else:raise ValueError('CIF output requires zero or three lattice vectors.')
    symbols=[s for _,s in rows]
    loop=CIFLoop()
    loop.add('_atom_site_type_symbol',symbols,'{}')
    loop.add('_atom_site_label',autolabel(symbols),'{}')
    loop.add('_atom_site_symmetry_multiplicity',[1]*len(rows),'{}')
    for axis,name in enumerate('xyz'):
        loop.add(f'_atom_site_{kind}_{name}',[positions[i,axis] for i,_ in rows],'{:.17g}')
    loop.add('_atom_site_occupancy',[sites[i][s] for i,s in rows],'{:.17g}')
    # A fixed safe block name avoids filename quoting and encoding surprises.
    Path(path).write_text('data_lele\n'+header+loop.tostring(),encoding='utf-8')
