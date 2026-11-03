"""CIF probabilities merged after symmetry expansion, including PBC aliases."""
import numpy as np
from ase.io.cif import parse_cif
from ase.spacegroup.spacegroup import parse_sitesym
from scipy.spatial import cKDTree


def unit_fractions(values):
    """Normalize into the half-open KD-tree box, including roundoff at 1."""
    wrapped=np.remainder(values,1.)
    wrapped[wrapped>=1.]=0.
    return wrapped


def read_cif_atoms(path):
    blocks=[block for block in parse_cif(str(path)) if block.has_structure()]
    if not blocks:raise ValueError('No CIF structure block found.')
    block=blocks[-1];sitesym=block._get_sitesym()
    if (sitesym and block._get_spacegroup_number() is None and block._get_spacegroup_name() is None):
        rotations,translations=parse_sitesym(sitesym)
        if (np.allclose(rotations,np.eye(3),atol=1.e-12,rtol=0)
                and np.allclose(translations,np.rint(translations),atol=1.e-12,rtol=0)):
            # Identity is explicit input evidence, not a guessed space group.
            block._tags['_space_group_it_number']=1
        else:
            raise ValueError('CIF has nonidentity symmetry operations but no space-group number or name.')
    atoms=block.get_atoms(fractional_occupancies=True)
    weights=block._get_fractional_occupancies()
    if weights is None or atoms.cell.rank!=3:return atoms
    raw=block.get_unsymmetrized_structure();group=block.get_spacegroup(subtrans_included=True)
    # ASE's occupancy dictionary compares unsymmetrized Cartesian positions;
    # it does not merge components written as different orbit representatives.
    # Match each original component's unique orbit to the actual expanded sites.
    fractions=unit_fractions(atoms.get_scaled_positions(wrap=False))
    tree=cKDTree(fractions,boxsize=1.)
    merged=[{} for _ in atoms];row_order=[]
    for symbol,position,weight in zip(raw.get_chemical_symbols(),raw.get_scaled_positions(wrap=False),weights):
        weight=float(weight)
        if not np.isfinite(weight) or weight<0 or weight>1+1.e-6:raise ValueError('Invalid CIF site occupancy.')
        orbit,_=group.equivalent_sites([position],onduplicates='keep',symprec=.001)
        distance,indices=tree.query(unit_fractions(orbit),p=np.inf)
        if np.any(distance>.001+1.e-10):raise ValueError('CIF symmetry orbit does not match the expanded structure.')
        for index in dict.fromkeys(int(i) for i in indices):
            previous=merged[index].get(symbol)
            if previous is not None and abs(previous-weight)>1.e-8:
                raise ValueError('Conflicting occupancies for equivalent CIF representatives of '+symbol)
            # Redundant representatives of the same elemental component are
            # not additional atoms or extra probability.
            if previous is None:row_order.append((index,symbol))
            merged[index][symbol]=weight
    if any(not values or sum(values.values())>1+1.e-6 for values in merged):
        raise ValueError('Invalid total occupancy at a symmetry-equivalent CIF site.')
    atoms.set_chemical_symbols([max(values,key=values.get) for values in merged])
    atoms.info['lele_site_occupancies']=merged
    atoms.info['lele_cif_row_order']=row_order
    return atoms
