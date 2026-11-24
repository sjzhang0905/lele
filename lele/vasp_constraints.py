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
    from .atom_constraints import export_fixed_mask
    flags=export_fixed_mask(info, len(atoms))
    if flags is None:return
    fixed=np.flatnonzero(flags.all(axis=1));partial=np.flatnonzero(flags.any(axis=1)&~flags.all(axis=1))
    basis = info.get('fixed_axes_basis', 'direct' if 'vasp_fixed_axes' in info else 'cartesian')
    if len(partial) and basis == 'cartesian':
        # VASP flags constrain fractional coordinates, even for Cartesian POSCAR.
        # Free lattice vectors must span exactly the Cartesian free subspace.
        cell=atoms.cell.array
        lengths=np.linalg.norm(cell, axis=1)
        if np.linalg.matrix_rank(cell) != 3:
            raise ValueError('A full cell is required to convert partial Cartesian constraints to POSCAR.')
        for index in partial:
            fixed_cart=flags[index]
            free_direct=np.all(np.abs(cell[:,fixed_cart])/lengths[:,None] < 1.e-10, axis=1)
            if free_direct.sum() != (~fixed_cart).sum():
                raise ValueError(f'Atom {index+1}: this partial Cartesian constraint cannot be represented by the current POSCAR lattice axes.')
            flags[index]=~free_direct
    constraints=([FixAtoms(indices=fixed)] if len(fixed) else [])
    constraints += [FixScaled(int(i),mask=flags[i]) for i in partial]
    # An explicitly present all-free Selective Dynamics header is preserved too.
    if not constraints:constraints=[FixScaled(0,mask=(False,False,False))] if len(atoms) else []
    atoms.set_constraint(constraints)
