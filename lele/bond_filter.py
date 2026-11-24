"""Reject nearly collinear long automatic edges shielded by two shorter bonds."""
import numpy as np


def prune_occluded(positions, edges, cell=None):
    positions = np.asarray(positions, dtype=float)
    zero = (0, 0, 0)
    lattice = np.zeros((3, 3)) if cell is None else np.asarray(cell)
    images = {}

    def image(site, shift):
        if shift == zero:
            return positions[site]
        key = (site, shift)
        if key not in images:
            images[key] = positions[site] + np.asarray(shift) @ lattice
        return images[key]

    # Adjacent triangles share edges. Store directed lengths once, retaining
    # the original Cartesian image for strict comparisons at the thresholds.
    neighbors = {}
    directed = {}
    candidates = []
    for a, b, shift in edges:
        shift = tuple(shift)
        reverse = tuple(-v for v in shift)
        q = image(b, shift)
        back = image(a, reverse)
        length = float(np.linalg.norm(q - positions[a]))
        reverse_length = length if shift == zero else float(np.linalg.norm(back - positions[b]))
        neighbors.setdefault(a, []).append((b, shift, q, length))
        neighbors.setdefault(b, []).append((a, reverse, back, reverse_length))
        directed[a, b, shift] = length
        directed[b, a, reverse] = reverse_length
        candidates.append((a, b, shift, q, length))

    result = []
    for a, b, shift, q, length in candidates:
        limit = .85 * length
        sx, sy, sz = shift
        for k, tile, middle, left in neighbors[a]:
            if not .2 < left < limit:
                continue
            remaining = (sx-tile[0], sy-tile[1], sz-tile[2])
            right = directed.get((k, b, remaining))
            if right is None:
                continue
            if tile != zero:
                # Subtract the actual images to keep the historical rounding
                # in skew cells and for coordinates far from the origin.
                right = float(np.linalg.norm(q - middle))
            if .2 < right < limit and left + right < 1.08 * length:
                break
        else:
            result.append((a, b, shift))
    return sorted(result)
