"""Named selections stored with a frame; indices are always zero-based.

Updates replace nested values so a Frame.clone() undo snapshot remains intact.
"""
from __future__ import annotations

import re
from operator import index as integer_index


FRAGMENTS_KEY = 'saved_fragments'
NEXT_ID_KEY = 'fragment_next_id'


def selected_indices(frame, selection):
    """Deduplicate a selection in the frame's current atom order."""
    try:
        indices = sorted(set(integer_index(index) for index in selection))
    except TypeError:
        raise ValueError('Selected atom indices must be integers.') from None
    if any(index < 0 or index >= len(frame.symbols) for index in indices):
        raise ValueError('Selected atom index is outside 1…N.')
    return indices


def fragments(frame):
    """Return valid, independent fragment records, including loaded projects."""
    if frame is None:
        return []
    result = []
    names = set()
    for record in frame.info.get(FRAGMENTS_KEY, []):
        if not isinstance(record, dict):
            continue
        name = str(record.get('name', '')).strip()
        try:
            indices = selected_indices(frame, record.get('indices', []))
        except (TypeError, ValueError, OverflowError):
            continue
        if name and name not in names and indices:
            result.append({'name': name, 'indices': indices})
            names.add(name)
    return result


def get_fragment(frame, name):
    for record in fragments(frame):
        if record['name'] == name:
            return record
    raise ValueError('This fragment no longer exists in the current frame.')


def add_fragment(frame, selection):
    indices = selected_indices(frame, selection)
    if not indices:
        raise ValueError('Select one or more atoms to save a fragment.')
    records = fragments(frame)
    existing_numbers = [int(match[1]) for record in records
                        if (match := re.fullmatch(r'fragment(\d+)', record['name']))]
    try:
        next_id = max(1, int(frame.info.get(NEXT_ID_KEY, 1)))
    except (TypeError, ValueError, OverflowError):
        next_id = 1
    next_id = max([next_id, *(number + 1 for number in existing_numbers)])
    record = {'name': f'fragment{next_id}', 'indices': indices}
    frame.info = {**frame.info, FRAGMENTS_KEY: [*records, record], NEXT_ID_KEY: next_id + 1}
    return {'name': record['name'], 'indices': list(indices)}


def fragment_slot_name(slot):
    """The nine canvas shortcuts address these ordinary named fragments."""
    try:
        slot = integer_index(slot)
    except TypeError:
        raise ValueError('Fragment shortcut must be a number from 1 to 9.') from None
    if not 1 <= slot <= 9:
        raise ValueError('Fragment shortcut must be a number from 1 to 9.')
    return f'fragment{slot}'


def save_fragment_slot(frame, slot, selection, *, append=False):
    """Save/replace a numbered fragment or merge atoms into it, copy-on-write.

    Return (record, changed). An empty selection is a no-op and never removes
    an existing fragment. Ordinary Save continues assigning monotonic names.
    """
    name = fragment_slot_name(slot)
    records = fragments(frame)
    previous = next((record for record in records if record['name'] == name), None)
    indices = selected_indices(frame, selection)
    if not indices:
        return previous, False
    if append and previous is not None:
        indices = sorted(set(previous['indices']) | set(indices))
    if previous is not None and previous['indices'] == indices:
        return previous, False
    record = {'name': name, 'indices': indices}
    if previous is None:
        records.append(record)
    else:
        records = [record if item['name'] == name else item for item in records]
    try:
        next_id = max(1, int(frame.info.get(NEXT_ID_KEY, 1)))
    except (TypeError, ValueError, OverflowError):
        next_id = 1
    next_id = max(next_id, integer_index(slot) + 1)
    frame.info = {**frame.info, FRAGMENTS_KEY: records, NEXT_ID_KEY: next_id}
    return {'name': name, 'indices': list(indices)}, True


def remove_fragment(frame, name):
    records = fragments(frame)
    kept = [record for record in records if record['name'] != name]
    if len(kept) == len(records):
        return False
    frame.info = {**frame.info, FRAGMENTS_KEY: kept}
    return True


def fragment_order(frame, name, destination):
    """Move the named atoms as one stable block; keep both internal orders."""
    from .atom_indices import fragment_order as stable_order
    return stable_order(len(frame.symbols), get_fragment(frame, name)['indices'], destination)


def subset_fragments(records, indices):
    """Map old atom identities into a subset, permutation, or replica list."""
    result = []
    indices = list(indices)
    for record in records:
        if not isinstance(record, dict) or not record.get('name'):
            continue
        members = set(record.get('indices', []))
        mapped = [new_index for new_index, old_index in enumerate(indices) if old_index in members]
        if mapped:
            result.append({'name': str(record['name']), 'indices': mapped})
    return result


def index_summary(selection, *, base=1):
    """Atom numbers with explicit base, compacting runs of at least three."""
    if base not in (0, 1):
        raise ValueError("Atom numbering base must be 0 or 1.")
    values = sorted(set(int(index) + base for index in selection))
    groups = []
    cursor = 0
    while cursor < len(values):
        end = cursor
        while end + 1 < len(values) and values[end + 1] == values[end] + 1:
            end += 1
        if end - cursor >= 2:
            groups.append(f'{values[cursor]}-{values[end]}')
        else:
            groups.extend(str(value) for value in values[cursor:end + 1])
        cursor = end + 1
    return ', '.join(groups)
