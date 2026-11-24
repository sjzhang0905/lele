"""Reproduce the periodic-geometry reference data using exact arithmetic."""

import argparse
from collections import deque
from fractions import Fraction
from itertools import product
import json
from math import ceil, floor, isqrt
from pathlib import Path
import shlex

ROOT = Path(__file__).resolve().parent
ZERO = (0, 0, 0)


def read_fixture(path):
    """Read the intentionally small subset used by these XSF and XYZ fixtures."""
    lines = path.read_text(encoding='ascii').splitlines()
    if path.suffix == '.xsf':
        if lines[0] != 'SLAB' or lines[1] != 'PRIMVEC' or lines[5] != 'PRIMCOORD':
            raise ValueError(f'Unexpected XSF fixture header in {path.name}')
        cell = [list(map(Fraction, row.split())) for row in lines[2:5]]
        count = int(lines[6].split()[0])
        rows = lines[7:]
        mask = (True, True, False)
    else:
        count = int(lines[0])
        fields = dict(token.split('=', 1) for token in shlex.split(lines[1]))
        entries = list(map(Fraction, fields['Lattice'].split()))
        cell = [entries[i:i+3] for i in (0, 3, 6)]
        mask = tuple(x == 'T' for x in fields['pbc'].split())
        rows = lines[2:]
    if len(rows) != count:
        raise ValueError(f'Atom count differs in {path.name}')
    symbols = [row.split()[0] for row in rows]
    positions = [tuple(map(Fraction, row.split()[1:])) for row in rows]
    return symbols, positions, cell, mask


def dot(first, second):
    return sum(x*y for x, y in zip(first, second))


def inverse(matrix):
    """Return a rational inverse using elementary row operations."""
    n = len(matrix)
    rows = [list(row) + [Fraction(i == j) for j in range(n)] for i, row in enumerate(matrix)]
    for j in range(n):
        pivot = next((k for k in range(j, n) if rows[k][j]), None)
        if pivot is None:
            raise ValueError('Dependent periodic lattice rows')
        rows[j], rows[pivot] = rows[pivot], rows[j]
        divisor = rows[j][j]
        rows[j] = [v / divisor for v in rows[j]]
        for k, row in enumerate(rows):
            if k != j:
                factor = row[j]
                rows[k] = [v - factor*u for v, u in zip(row, rows[j])]
    return [row[n:] for row in rows]


class Lattice:
    def __init__(self, cell, mask):
        self.cell = cell
        self.axes = [i for i, active in enumerate(mask) if active]
        rows = [cell[i] for i in self.axes]
        self.valid = bool(rows)
        try:
            gram_inverse = inverse([[dot(row, other) for other in rows] for row in rows])
        except ValueError:
            # LELE handles a dependent declared lattice as nonperiodic geometry.
            self.valid = False
            self.axes = []
            self.dual = []
        else:
            self.dual = [[sum(coefficient * row[j] for coefficient, row in zip(coefficients, rows))
                          for j in range(3)] for coefficients in gram_inverse]

    def distance_squared(self, delta, shift):
        vector = [delta[j] + sum(shift[i]*row[j] for i, row in enumerate(self.cell)) for j in range(3)]
        return dot(vector, vector)

    def images_within(self, delta, radius_squared):
        # An image inside radius R satisfies |s_i + delta.dual_i| <= R*|dual_i|.
        # Rounding each bound outward preserves every possible integer image.
        ranges = [(0,)] * 3
        for i, dual in zip(self.axes, self.dual):
            center = -dot(delta, dual)
            bound_squared = radius_squared * dot(dual, dual)
            bound = isqrt(bound_squared.numerator // bound_squared.denominator)
            if bound * bound < bound_squared:
                bound += 1
            ranges[i] = range(ceil(center-bound), floor(center+bound)+1)
        for shift in product(*ranges):
            distance = self.distance_squared(delta, shift)
            if distance <= radius_squared:
                yield shift, distance

    def minimum_images(self, delta):
        trial = [0, 0, 0]
        for i, dual in zip(self.axes, self.dual):
            trial[i] = round(-dot(delta, dual))
        upper_bound = self.distance_squared(delta, trial)
        images = list(self.images_within(delta, upper_bound))
        smallest = min(distance for _, distance in images)
        return smallest, [list(shift) for shift, distance in images if distance == smallest]


def difference(first, second):
    return tuple(b-a for a, b in zip(first, second))


def neighbor_records(positions, lattice, cutoff_squared):
    for i, first in enumerate(positions):
        for j, second in enumerate(positions):
            for shift, distance in lattice.images_within(difference(first, second), cutoff_squared):
                if distance < cutoff_squared and (i != j or shift != ZERO):
                    yield i, j, shift, distance


def fragment(bonds, root):
    graph = {}
    for i, j, shift in bonds:
        graph.setdefault(i, []).append((j, shift))
        graph.setdefault(j, []).append((i, tuple(-x for x in shift)))
    assigned = {root: ZERO}
    queue = deque([root])
    while queue:
        i = queue.popleft()
        for j, shift in graph.get(i, ()):
            image = tuple(x+y for x, y in zip(assigned[i], shift))
            if j not in assigned:
                assigned[j] = image
                queue.append(j)
            elif assigned[j] != image:
                return {'infinite': True}
    return {'infinite': False, 'images': [[i, list(assigned[i])] for i in sorted(assigned)]}


def evaluate(case):
    _, positions, cell, mask = read_fixture(ROOT / case['source'])
    lattice = Lattice(cell, mask)
    cutoff_squared = Fraction(case['cutoff_angstrom'])**2
    mic = []
    contacts = []
    for i, first in enumerate(positions):
        for j in range(i+1, len(positions)):
            delta = difference(first, positions[j])
            distance, shifts = lattice.minimum_images(delta)
            row = {'pair': [i, j], 'distance_squared': str(distance), 'shifts': shifts}
            mic.append(row)
            if distance < cutoff_squared:
                contacts.append(row)
    neighbors = [[i, j, list(shift), str(d2)]
                 for i, j, shift, d2 in neighbor_records(positions, lattice, cutoff_squared)]
    minimum, maximum = map(Fraction, case['bond_window_angstrom'])
    bonds = [(i, j, shift) for i, j, shift, d2 in neighbor_records(positions, lattice, maximum**2)
             if minimum**2 < d2 and (i < j or (i == j and shift > ZERO))]
    return {
        'valid_periodic_lattice': lattice.valid,
        'minimum_images': mic,
        'neighbors': neighbors,
        'short_contacts': contacts,
        'bonds': [[i, j, list(shift)] for i, j, shift in bonds],
        'fragment': fragment(bonds, case['fragment_root']),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--regenerate', action='store_true', help='Recompute expected.json from the fixtures.')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))
    calculated = {case['id']: evaluate(case) for case in manifest['cases']}
    expected = ROOT / 'expected.json'
    if args.regenerate:
        expected.write_text(json.dumps(calculated, indent=2) + '\n', encoding='utf-8')
    else:
        known = json.loads(expected.read_text(encoding='utf-8'))
        if calculated != known:
            different = {k for k in calculated.keys() | known.keys() if calculated.get(k) != known.get(k)}
            raise SystemExit('Reference data differ for ' + ', '.join(sorted(different)))
    print(f'{len(calculated)} periodic-geometry reference cases verified.')


if __name__ == '__main__':
    main()
