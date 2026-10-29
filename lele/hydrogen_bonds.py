"""Manual dashed links, separate from the covalent fragment graph."""
from dataclasses import dataclass
import numpy as np
from .core import canonical_pair
from .chemical_analysis import detect_hydrogen_bonds
from .periodic_geometry import minimum_image, normalized_positions


@dataclass(frozen=True)
class HydrogenBondLink:
    first: int
    second: int
    start: np.ndarray
    end: np.ndarray
    atoms: tuple
    manual: bool = False


def hydrogen_bond_links(frame, automatic=True):
    links = []
    if automatic:
        for hb in detect_hydrogen_bonds(frame):
            pair = canonical_pair(hb.hydrogen, hb.acceptor)
            if pair in frame.hbond_added or pair in frame.hbond_removed:
                continue
            links.append(HydrogenBondLink(hb.hydrogen, hb.acceptor, hb.hydrogen_pos,
                hb.acceptor_pos, (hb.donor, hb.hydrogen, hb.acceptor)))
    for (i, j), shift in sorted(frame.hbond_added.items()):
        links.append(HydrogenBondLink(i, j, frame.positions[i],
            frame.positions[j] + np.asarray(shift) @ frame.cell, (i, j), True))
    return links


def toggle_hydrogen_bond(frame, selection, automatic=False):
    indices = list(dict.fromkeys(int(i) for i in selection))
    if len(indices) != 2:
        raise ValueError('Select exactly two atoms for Ctrl+H (usually H and its acceptor).')
    if any(i < 0 or i >= len(frame.symbols) for i in indices):
        raise ValueError('Selected atom out of range')
    pair = canonical_pair(*indices)
    visible = pair in frame.hbond_added
    if automatic and not visible and pair not in frame.hbond_removed:
        visible = any(canonical_pair(hb.hydrogen, hb.acceptor) == pair
                      for hb in detect_hydrogen_bonds(frame))
    if visible:
        frame.hbond_added.pop(pair, None)
        frame.hbond_removed.add(pair)
        return 'removed'
    i, j = pair
    _, shift = minimum_image(frame.positions[j] - frame.positions[i], frame)
    frame.hbond_removed.discard(pair)
    frame.hbond_added[pair] = shift
    return 'added'


def repeat_hydrogen_bonds(frame, result, tiles, *, repeats=None, wrap=True):
    """Map explicit image links onto Boundary copies or a real supercell."""
    if not (frame.hbond_added or frame.hbond_removed):
        return
    _, floors = normalized_positions(frame)
    tile_index = {tuple(tile): k for k, tile in enumerate(tiles)}
    n = len(frame.symbols)
    for pair in frame.hbond_added.keys() | frame.hbond_removed:
        a, b = pair
        shift = frame.hbond_added.get(pair)
        if shift is None:
            _, shift = minimum_image(frame.positions[b] - frame.positions[a], frame)
        offset = np.asarray(shift, dtype=int)
        if wrap:
            offset = offset - floors[a] + floors[b]
        for k, tile in enumerate(tiles):
            destination = np.asarray(tile) + offset
            outer = np.zeros(3, dtype=int)
            if repeats is not None:
                for axis, periodic in enumerate(frame.pbc):
                    if periodic:
                        outer[axis] = destination[axis] // repeats[axis]
                        destination[axis] %= repeats[axis]
            other = tile_index.get(tuple(destination))
            if other is None:
                continue
            i, j = k*n + a, other*n + b
            target = canonical_pair(i, j)
            if pair in frame.hbond_added:
                if i > j: outer = -outer
                result.hbond_added[target] = tuple(int(x) for x in outer)
            else:
                result.hbond_removed.add(target)
