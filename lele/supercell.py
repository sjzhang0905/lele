"""Real diagonal supercells, preserving frame-local display edits."""
from copy import deepcopy
from itertools import product
from math import prod
from numbers import Integral
from uuid import uuid4

import numpy as np

from .core import Frame, canonical_pair
from .periodic_geometry import periodic_basis, normalized_positions, minimum_image, periodic_bonds

MAX_SUPERCELL_ATOMS = 50_000


def validate_repeats(frame, repeats, max_atoms=MAX_SUPERCELL_ATOMS):
    values = tuple(repeats)
    if len(values) != 3 or any(isinstance(n, bool) or not isinstance(n, Integral) or n < 1 for n in values):
        raise ValueError('Use three positive integer repeat factors for a, b and c.')
    values = tuple(int(n) for n in values)
    if periodic_basis(frame) is None:
        raise ValueError('A supercell needs a periodic structure with a valid unit cell.')
    if not frame.symbols:
        raise ValueError('The structure has no atoms to repeat.')
    if any(n != 1 and not periodic for n, periodic in zip(values, frame.pbc)):
        raise ValueError('Only periodic lattice directions can be repeated.')
    if len(frame.symbols) * prod(values) > max_atoms:
        raise ValueError(f'The supercell exceeds {max_atoms:,} atoms; reduce the repeat factors.')
    return values


def _repeat_bond_overrides(frame, repeats, tiles, floors, cutoff):
    """Map explicit links to their actual periodic images in the new cell."""
    if not (frame.bond_added or frame.bond_removed):
        return set(), set()
    base, source_floors = normalized_positions(frame)
    n = len(frame.symbols)
    tile_index = {tile: k for k, tile in enumerate(tiles)}
    paths = {}
    for pair in frame.bond_added | frame.bond_removed:
        a, b = pair
        # A moved manual bond still refers to its captured image. Recomputing
        # the nearest path here could add a different link during expansion.
        captured = {tuple(int(x) for x in np.asarray(s) - source_floors[a] + source_floors[b])
                    for i, j, s in (frame.periodic_bond_snapshot or ()) if (i, j) == pair}
        if captured:
            paths[pair] = captured
        else:
            _, shift = minimum_image(base[b] - base[a], frame)
            paths[pair] = {shift}
    if frame.bond_removed:
        probe = frame.clone()
        probe.bond_added.clear(); probe.bond_removed.clear()
        for a, b, shift in periodic_bonds(probe, cutoff):
            if (a, b) in frame.bond_removed:
                paths[a, b].add(shift)
    result = []
    for overrides in (frame.bond_added, frame.bond_removed):
        copied = set()
        for a, b in overrides:
            for shift in paths[a, b]:
                offset = np.asarray(shift) + floors[a] - floors[b]
                for k, tile in enumerate(tiles):
                    destination = np.asarray(tile) + offset
                    for axis, periodic in enumerate(frame.pbc):
                        if periodic:
                            destination[axis] %= repeats[axis]
                    other = tile_index.get(tuple(destination))
                    if other is not None:
                        copied.add(canonical_pair(k * n + a, other * n + b))
        result.append(copied)
    return tuple(result)


def make_supercell(frame: Frame, repeats, *, wrap=True, max_atoms=MAX_SUPERCELL_ATOMS,
                   bond_cutoff=1.0) -> Frame:
    """Return a new frame; atoms are ordered by tile, then original atom index.

    The new lattice rows are n_a*a, n_b*b, n_c*c. Periodicity and per-atom
    appearance are retained. Source energies and multiplicities do not describe
    the new system and are cleared, rather than multiplied or guessed.
    """
    repeats = validate_repeats(frame, repeats, max_atoms)
    factor = prod(repeats)
    if factor == 1:
        return frame.clone()
    base, original_floors = normalized_positions(frame)
    floors = np.zeros_like(original_floors) if wrap else original_floors
    if not wrap:
        base = frame.positions.copy()
    tiles = list(product(*(range(n) for n in repeats)))
    offsets = np.asarray(tiles, float) @ frame.cell
    positions = (base[None, :, :] + offsets[:, None, :]).reshape(-1, 3)
    n = len(frame.symbols)
    styles = {k * n + i: style for k in range(factor) for i, style in frame.atom_appearance.items()}
    added, removed = _repeat_bond_overrides(frame, repeats, tiles, floors, bond_cutoff)
    info = deepcopy(frame.info)
    for key in ('site_occupancies','vasp_fixed_axes'):
        if key in info:info[key]=info[key]*factor
    from .atom_indices import source_order
    info['atom_source_order']=list(source_order(frame))+['replica:'+uuid4().hex for _ in range(n*(factor-1))]
    if 'cif_row_order' in info:
        info['cif_row_order']=[(i+k*n,s) for k in range(factor) for i,s in frame.info['cif_row_order']]
    info.pop('optimization_converged',None)
    # POSCAR groups describe consecutive blocks, including intentionally
    # repeated species headers. Tile-major ordering repeats those same blocks.
    if 'poscar_groups' in info:
        info['poscar_groups'] = info['poscar_groups'] * factor
        info.pop('poscar_block_ids',None)
        from .poscar_labels import block_ids
        info['poscar_block_ids']=block_ids(info,frame.symbols*factor)
    from .chemical_analysis import known_net_charge
    charge = known_net_charge(frame)
    if charge is not None:
        for key in ('charge_override', 'converter_charge', 'net_charge', 'total_charge', 'charge'):
            if key in info:
                info[key] = charge * factor
        info['converter_charge'] = charge * factor
    for key in ('converter_mult', 'multiplicity', 'plane_alignment'):
        info.pop(key, None)
    info['supercell'] = {'repeats': list(repeats), 'source_atoms': n,
                         'source_cell': frame.cell.tolist(), 'wrapped': bool(wrap)}
    info['energy_note'] = 'Source energy cleared after building a supercell; no new calculation was performed.'
    result = Frame(frame.symbols * factor, positions,
                   np.asarray(repeats)[:, None] * frame.cell, frame.pbc, None, info,
                   added, removed, styles)
    # Replicate the source graph itself. No new proximity bonds are inferred
    # between copies or between atoms that were unconnected before expansion.
    paths = set()
    tile_index = {tile: k for k, tile in enumerate(tiles)}
    for a, b, shift in periodic_bonds(frame, bond_cutoff):
        offset = np.asarray(shift, dtype=int)
        if not wrap: offset = offset + original_floors[a] - original_floors[b]
        for k, tile in enumerate(tiles):
            destination = np.asarray(tile) + offset
            cell_shift = np.zeros(3, dtype=int)
            for axis, periodic in enumerate(frame.pbc):
                if periodic:
                    cell_shift[axis] = destination[axis] // repeats[axis]
                    destination[axis] %= repeats[axis]
            other = tile_index.get(tuple(destination))
            if other is None: continue
            i, j = k*n+a, other*n+b
            if i > j: i,j = j,i; cell_shift = -cell_shift
            if i == j and tuple(cell_shift) < tuple(-cell_shift): cell_shift = -cell_shift
            if i != j or np.any(cell_shift): paths.add((i,j,tuple(int(x) for x in cell_shift)))
    result.periodic_bond_snapshot = tuple(sorted(paths))
    result.bond_snapshot = frozenset((i,j) for i,j,s in paths if i != j and s == (0,0,0))
    from .hydrogen_bonds import repeat_hydrogen_bonds
    repeat_hydrogen_bonds(frame, result, tiles, repeats=repeats, wrap=wrap)
    return result


def make_fragment_supercell(frame: Frame, preview, *, bond_cutoff=1.0):
    """Build the cells needed by a finite fragment and map its image atom IDs.

    The fragment search uses shifts relative to the original lattice. A new
    supercell starts at zero, so subtract the preview's minimum tile from all
    selected image shifts. This also handles fragments crossing a negative face
    or more than one lattice direction without breaking their geometry.
    """
    repeats = preview.supercell_extent
    expanded = make_supercell(frame, repeats, bond_cutoff=bond_cutoff)
    minimum = np.asarray(preview.supercell_min, dtype=int)
    n = len(frame.symbols)
    selection = []
    for source in preview.indices:
        tile = tuple(np.asarray(preview.shifts[source], dtype=int) - minimum)
        selection.append(int(np.ravel_multi_index(tile, repeats)) * n + source)
    return expanded, selection
