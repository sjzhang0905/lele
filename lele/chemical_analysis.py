#!/usr/bin/env python3
"""Lightweight charge parity, close-contact and hydrogen-bond diagnostics.

Hydrogen bonds are geometric proposals, not inferred bond orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .core import Frame
from .periodic_geometry import short_contacts, periodic_basis, normalized_positions, translations
from scipy.spatial import cKDTree

ELEMENTS = (
    'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn '
    'Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La '
    'Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi '
    'Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt '
    'Ds Rg Cn Nh Fl Mc Lv Ts Og'
).split()
ATOMIC_NUMBERS = {symbol: idx for idx, symbol in enumerate(ELEMENTS, 1)}


def known_net_charge(frame: Frame):
    for key in ('charge_override', 'converter_charge', 'net_charge', 'total_charge', 'charge'):
        if key not in frame.info:
            continue
        try:
            numeric = float(frame.info[key])
        except (TypeError, ValueError):
            continue
        if abs(numeric - round(numeric)) < 1e-6:
            return int(round(numeric))
    return None


def electron_parity(frame: Frame):
    """Neutral is an explicit default if no net charge was parsed/set.

    A parity statement is not evidence for a specific spin state.
    """
    missing = sorted(set(frame.symbols).difference(ATOMIC_NUMBERS))
    if missing:
        return f'Unknown (unsupported elements: {", ".join(missing)})'
    charge = known_net_charge(frame)
    assumed_neutral = charge is None
    if assumed_neutral:
        charge = 0
    electrons = sum(ATOMIC_NUMBERS[s] for s in frame.symbols) - charge
    note = '; assumed charge 0' if assumed_neutral else f'; charge {charge:+d}'
    return f'{"Odd" if electrons % 2 else "Even"} ({electrons} electrons{note})'


def short_contact_summary(frame: Frame):
    number, nearest = short_contacts(frame, threshold=0.6)
    if not number:
        return 'Short contacts <0.60 Å: None'
    i, j, distance = nearest
    return (f'Short contacts <0.60 Å: {number} pair(s); closest '
            f'{frame.symbols[i]}{i+1}–{frame.symbols[j]}{j+1} {distance:.3f} Å')


@dataclass(frozen=True)
class HydrogenBond:
    donor: int
    hydrogen: int
    acceptor: int
    hydrogen_pos: np.ndarray
    acceptor_pos: np.ndarray
    angle_deg: float
    distance: float


def detect_hydrogen_bonds(frame: Frame, *, max_results=15000):
    """D-H...A geometric hints, including nearest periodic donor/acceptor images.

    Criteria: N/O/F donor/acceptor, D-H 0.55..1.25, H...A 1.4..2.7,
    D...A <= 3.5 Angstrom, D-H...A >= 120 degrees. Not chemical proof.
    """
    heavy = [i for i, s in enumerate(frame.symbols) if s in ('N', 'O', 'F')]
    hydrogens = [i for i, s in enumerate(frame.symbols) if s == 'H']
    if not heavy or not hydrogens:
        return []
    cell = periodic_basis(frame)
    base, _ = normalized_positions(frame)
    heavy_base = base[heavy]
    tiles = translations(frame)
    copied_positions = np.concatenate([
        heavy_base + (np.asarray(shift, float) @ cell if cell is not None else 0.)
        for shift in tiles], axis=0)
    copied_indices = np.tile(np.asarray(heavy, dtype=int), len(tiles))
    tree = cKDTree(copied_positions)
    results = []
    for h in hydrogens:
        h_position = base[h]
        # Search geometry in normalized coordinates, then offset the rendered
        # acceptor image so that H remains at its original input position.
        nearby = tree.query_ball_point(h_position, 2.7)
        shortest = {}
        for k in nearby:
            idx = int(copied_indices[k])
            vec = copied_positions[k] - h_position
            distance = float(np.linalg.norm(vec))
            if idx not in shortest or distance < shortest[idx][0]:
                shortest[idx] = (distance, vec)
        donors = [(d, shortest[d]) for d in heavy if d in shortest and
                  .55 <= shortest[d][0] <= 1.25]
        if not donors:
            continue
        donor, (d_h, dh_vec) = min(donors, key=lambda item: item[1][0])
        for acceptor, (h_a, ha_vec) in shortest.items():
            if acceptor == donor or not (1.4 <= h_a <= 2.7):
                continue
            if float(np.linalg.norm(ha_vec - dh_vec)) > 3.5:
                continue
            cosine = float(np.dot(dh_vec, ha_vec) / (d_h * h_a))
            angle = float(np.degrees(np.arccos(np.clip(cosine, -1., 1.))))
            if angle >= 120.:
                results.append(HydrogenBond(donor, h, acceptor,
                                            frame.positions[h].copy(),
                                            frame.positions[h] + ha_vec, angle, h_a))
                if len(results) >= max_results:
                    return results
    return results
