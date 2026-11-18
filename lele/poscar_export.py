"""Optional stable POSCAR species grouping, confined to an export copy."""


def grouped_poscar_frame(frame):
    """Group equal elements in first-appearance order without changing the model.

    Call after any fractional-occupancy projection so group identities match
    the elements actually written. Existing POSCAR block boundaries are dropped
    deliberately; every supported atom-indexed field follows the permutation.
    """
    from .atom_indices import reorder_atoms

    groups = {}
    for index, symbol in enumerate(frame.symbols):
        groups.setdefault(symbol, []).append(index)
    order = [index for indices in groups.values() for index in indices]
    exported = frame.clone()
    exported.info.pop('poscar_groups', None)
    exported.info.pop('poscar_block_ids', None)
    reorder_atoms(exported, order)
    return exported
