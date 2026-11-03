"""Reference appearance values and ordinary-bond distance limits.

Colors are Chemcraft's GaussView-style compatibility palette. Radii come
from VESTA 3.5.8. Bond upper limits come from Chemcraft b816bt's ordinary
records; hydrogen-bond records and inferred bond orders are kept separate.
"""
from functools import lru_cache
from math import sqrt
from ._display_reference_values import (
    CHEMCRAFT_LIMITS_SQUARED, GAUSSVIEW_STYLE_COLORS, VESTA_RADII,
)

SYMBOLS = ('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn '
           'Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag '
           'Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm '
           'Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa '
           'U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh '
           'Fl Mc Lv Ts Og').split()
ATOMIC_NUMBER = {symbol: index + 1 for index, symbol in enumerate(SYMBOLS)}
ATOMIC_NUMBER['D'] = 1
GAUSSVIEW_COMPAT_COLORS = dict(zip(SYMBOLS, GAUSSVIEW_STYLE_COLORS))
GAUSSVIEW_COMPAT_COLORS['D'] = GAUSSVIEW_COMPAT_COLORS['H']
BOND_MODELS = ('Chemcraft pair ranges', 'Covalent radii')
RADIUS_TYPES = ('Atomic', 'Ionic', 'van der Waals')


def vesta_radius(symbol, kind='Atomic'):
    """Unscaled radius in Angstrom; unsupported species use VESTA's XX row."""
    column = {'Atomic': 0, 'van der Waals': 1, 'Ionic': 2}[kind]
    return VESTA_RADII.get(symbol, VESTA_RADII['XX'])[column]


@lru_cache(maxsize=16384)
def chemcraft_limit(first, second):
    """Upper ordinary-bond distance, or None outside the source table.

    A zero is a supported element pair with no ordinary-bond record. Limits
    are the union of all ordinary types; this function assigns no bond order.
    """
    a, b = sorted((ATOMIC_NUMBER.get(first, 0), ATOMIC_NUMBER.get(second, 0)))
    if a < 1 or b > 105:
        return None
    squared = CHEMCRAFT_LIMITS_SQUARED[a - 1][b - a]
    return sqrt(squared) if squared is not None else 0.


def bond_limits(symbols, multiplier=1., model=BOND_MODELS[0]):
    """Precompute only the species pairs present in the current structure."""
    from .core import radius
    species = sorted(set(symbols))
    limits = {}
    for i, first in enumerate(species):
        for second in species[i:]:
            limit = chemcraft_limit(first, second) if model == BOND_MODELS[0] else None
            # Unlisted species retain the documented covalent-radius fallback.
            limit = (radius(first) + radius(second)) * 1.18 if limit is None and model == BOND_MODELS[0] else limit
            if limit is None:
                limit = radius(first) + radius(second)
            limits[first, second] = float(limit * multiplier)
    return limits


def pair_limit(limits, first, second):
    return limits[tuple(sorted((first, second)))]
