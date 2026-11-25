"""Build POSCAR species blocks and the matching coordinate order."""
from itertools import groupby


def grouped_poscar_frame(frame, *, merge_same_elements=True):
    """Group original rows as requested, then append runs of newly added atoms.

    Called after occupancy projection. The source IDs survive pastes, index
    edits, deletion and project reload. Earlier frames without IDs consist
    entirely of original atoms.
    """
    from .atom_indices import reorder_atoms, source_order

    original = []
    added = []
    identities = source_order(frame)
    if len(identities) != len(frame.symbols):
        raise ValueError('Atom identities do not match the coordinates for POSCAR export.')
    for index, identity in enumerate(identities):
        if isinstance(identity, str) and identity.startswith(('added:', 'replica:')):
            added.append(index)
        else:
            original.append(index)
    if merge_same_elements:
        by_symbol = {}
        for index in original:
            by_symbol.setdefault(frame.symbols[index], []).append(index)
        original = [index for indices in by_symbol.values() for index in indices]

    # Count the two lists separately even if the touching elements match.
    groups = [(symbol, sum(1 for _ in run))
              for partition in (original, added)
              for symbol, run in groupby(partition, key=frame.symbols.__getitem__)]
    order = original + added
    exported = frame.clone()
    exported.info.pop('poscar_groups', None)
    exported.info.pop('poscar_block_ids', None)
    if any(old != new for new, old in enumerate(order)):
        reorder_atoms(exported, order)
    exported.info['poscar_groups'] = groups
    return exported
