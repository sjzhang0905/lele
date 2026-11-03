"""Portable per-site VASP selective-dynamics flags (True means fixed)."""
import numpy as np
from ase.constraints import FixAtoms,FixScaled


def read_fixed_axes(atoms):
    flags=np.zeros((len(atoms),3),dtype=bool);seen=False
    for constraint in atoms.constraints:
        if isinstance(constraint,FixAtoms):flags[constraint.get_indices()]=True;seen=True
        elif isinstance(constraint,FixScaled):
            flags[constraint.get_indices()]|=constraint.mask;seen=True
    return flags.tolist() if seen else None


def attach_fixed_axes(atoms,info):
    values=info.get('vasp_fixed_axes')
    if values is None:return
    flags=np.asarray(values,dtype=bool)
    if flags.shape!=(len(atoms),3):raise ValueError('VASP selective-dynamics flags do not match the atom order.')
    fixed=np.flatnonzero(flags.all(axis=1));partial=np.flatnonzero(flags.any(axis=1)&~flags.all(axis=1))
    constraints=([FixAtoms(indices=fixed)] if len(fixed) else [])
    constraints += [FixScaled(int(i),mask=flags[i]) for i in partial]
    # An explicitly present all-free Selective Dynamics header is preserved too.
    if not constraints:constraints=[FixScaled(0,mask=(False,False,False))] if len(atoms) else []
    atoms.set_constraint(constraints)
