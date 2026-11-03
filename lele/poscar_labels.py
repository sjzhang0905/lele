#!/usr/bin/env python3
"""Parse VASP5 POSCAR species-block boundaries without requiring ASE.

Block boundaries matter when the header intentionally repeats a symbol:
Li Li Fe / 10 5 14 -> Li1..Li10, Li1..Li5, Fe1..Fe14.
"""
from pathlib import Path


def block_ids(info,symbols):
    """Per-atom original block membership, independent of element identity."""
    stored=info.get('poscar_block_ids')
    if stored is not None:
        if len(stored)!=len(symbols):raise ValueError('POSCAR block identities do not match the atoms.')
        return list(stored)
    groups=info.get('poscar_groups',[])
    expanded=[(s,i) for i,(s,count) in enumerate(groups) for _ in range(int(count))]
    if [s for s,_ in expanded]!=list(symbols):raise ValueError('POSCAR species blocks do not match the atoms.')
    return [i for _,i in expanded]


def groups_from_ids(symbols,identities):
    from itertools import groupby
    return [(s,len(list(rows))) for (s,_),rows in groupby(zip(symbols,identities))]


def read_poscar_groups(path: str | Path, symbols: list[str]):
    """Preserve POSCAR's *declared* species blocks, including duplicate labels.

    ASE returns only the expanded element list and loses boundaries such as
    ``Li Li Fe / 10 5 14``; these boundaries are needed for VESTA numbering.
    Return None for non-VASP5 headers, inconsistencies, and nonmatching data.
    This routine never modifies coordinates, ordering or chemical identity.
    """
    try:
        with Path(path).open('r', encoding='utf-8-sig', errors='replace') as fh:
            lines = [next(fh).strip() for _ in range(7)]
        names = lines[5].split()
        counts_raw = lines[6].split()
        if not names or len(names) != len(counts_raw):
            return None
        if any(not n[:1].isalpha() for n in names):
            return None
        counts = [int(x) for x in counts_raw]
        if any(x < 0 for x in counts) or sum(counts) != len(symbols):
            return None
        # Some POSCAR group labels include suffixes (e.g. Fe_pv). Use the
        # normalized ASE chemical symbols to annotate each block, but retain
        # the exact block boundary and its ordinal position.
        groups = []
        offset = 0
        for count in counts:
            block = symbols[offset:offset + count]
            if count and any(x != block[0] for x in block):
                return None
            element = block[0] if block else names[len(groups)]
            groups.append((element, count))
            offset += count
        return groups
    except (OSError, ValueError, StopIteration):
        return None


