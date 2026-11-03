#!/usr/bin/env python3
"""Structure formula and conservative open-shell reporting."""
from __future__ import annotations

from collections import Counter


def molecular_formula(symbols):
    """Hill order with explicit counts, including 1, for molecules and cells."""
    counts = Counter(symbols)
    if not counts:
        return '-'
    if 'C' in counts:
        order = ['C'] + (['H'] if 'H' in counts else []) + sorted(k for k in counts if k not in ('C', 'H'))
    else:
        order = sorted(counts)
    return ''.join(f'{name}{counts[name]}' for name in order)


def spin_summary(info):
    """A spin calculation and the physical existence of radicals differ."""
    mult = info.get('converter_mult', info.get('multiplicity'))
    if mult is not None:
        try:
            mult = int(mult)
            if mult >= 2:
                return f'Yes (multiplicity {mult}; spin S={(mult-1)/2:g})'
            if mult == 1:
                return 'Not established (singlet; open-shell singlet possible)'
        except (TypeError, ValueError):
            pass
    spin_polarized = info.get('spin_polarized')
    if isinstance(spin_polarized, str):
        low = spin_polarized.strip().lower()
        if low in ('true', 'yes', 't', '.true.', '1'):
            return 'Unknown (spin-polarized calculation)'
        if low in ('false', 'no', 'f', '.false.', '0'):
            return 'No (non-spin-polarized model; not a physical proof)'
    if spin_polarized is True:
        return 'Unknown (spin-polarized calculation)'
    if spin_polarized is False:
        return 'No (non-spin-polarized model; not a physical proof)'
    return 'Unknown (no reliable spin information)'


def summary_text(frame):
    from .site_occupancy import composition
    system = 'Cell composition' if any(frame.pbc) else 'Formula'
    return f'{system}: {composition(frame)}    |    Unpaired electrons: {spin_summary(frame.info)}'
