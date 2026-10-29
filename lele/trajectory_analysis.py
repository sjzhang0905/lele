"""Selection-driven analysis and reversible display alignment.

All values are computed from the source geometry. Missing/undefined values
remain NaN. Alignment applies proper rotations only and never edits a Frame.
"""
from dataclasses import dataclass
import numpy as np

from .core import Frame, measure, rotation_between_vectors
from .periodic_geometry import minimum_image


def displacement_share(mode, selected, atom_count):
    """Fraction of squared Cartesian displacement on the selected atoms.

    This is a geometric displacement share, not a mass-weighted energy share.
    Missing and zero displacement tables have no defined share.
    """
    indices = tuple(dict.fromkeys(int(i) for i in selected))
    if not indices or any(i < 0 or i >= atom_count for i in indices):
        return None
    data = mode.displacements
    if data is None or data.shape != (atom_count, 3):
        return None
    weights = np.einsum('ij,ij->i', data, data)
    total = float(weights.sum())
    if not np.isfinite(total) or total <= 1.e-30:
        return None
    return float(weights[list(indices)].sum() / total)


PARAMETER_KINDS = (
    'Distance', 'Angle', 'Dihedral', 'Plane angle', 'Vector angle',
    'Point–plane distance', 'Point–line distance', 'Vector–plane angle',
)


@dataclass(frozen=True)
class GeometryParameter:
    kind: str
    atoms: tuple[int, ...]
    other: tuple[int, ...] = ()
    nearest_images: bool = False

    @property
    def unit(self):
        return 'Å' if self.kind in ('Distance', 'Point–plane distance', 'Point–line distance') else '°'

    @property
    def label(self):
        first = '–'.join(str(i + 1) for i in self.atoms)
        second = ' / ' + '–'.join(str(i + 1) for i in self.other) if self.other else ''
        return f'{self.kind} {first}{second}'

    def validate(self, atom_count):
        if self.kind not in PARAMETER_KINDS:
            raise ValueError('Unknown geometry parameter')
        sizes = {'Distance': (2, 0), 'Angle': (3, 0), 'Dihedral': (4, 0),
                 'Vector angle': (2, 2), 'Point–line distance': (1, 2)}
        if self.kind in sizes:
            if (len(self.atoms), len(self.other)) != sizes[self.kind]:
                raise ValueError('Incorrect number of atoms for ' + self.kind)
        elif self.kind == 'Plane angle':
            if min(len(self.atoms), len(self.other)) < 3:
                raise ValueError('Each plane needs at least three atoms')
        elif self.kind == 'Point–plane distance':
            if len(self.atoms) != 1 or len(self.other) < 3:
                raise ValueError('Specify one point and at least three plane atoms')
        elif self.kind == 'Vector–plane angle':
            if len(self.atoms) != 2 or len(self.other) < 3:
                raise ValueError('Specify two vector atoms and at least three plane atoms')
        if any(i < 0 or i >= atom_count for i in self.atoms + self.other):
            raise ValueError('Atom number outside this structure')
        if len(set(self.atoms)) != len(self.atoms) or len(set(self.other)) != len(self.other):
            raise ValueError('Do not repeat an atom within one group')

    def value(self, frame):
        self.validate(len(frame.symbols))
        if self.kind in ('Distance', 'Angle', 'Dihedral'):
            probe = frame
            atoms = self.atoms
            if self.nearest_images and any(frame.pbc):
                positions = [frame.positions[atoms[0]].copy()]
                for previous, current in zip(atoms, atoms[1:]):
                    delta = minimum_image(frame.positions[current] - frame.positions[previous], frame)[0]
                    positions.append(positions[-1] + delta)
                probe = Frame([frame.symbols[i] for i in atoms], positions)
                atoms = tuple(range(len(atoms)))
            return measure(probe, atoms)[1]

        def points(indices):
            p = frame.positions[list(indices)].copy()
            if self.nearest_images and any(frame.pbc):
                p = np.array([p[0] + minimum_image(q - p[0], frame)[0] for q in p])
            return p

        def plane(indices):
            p = points(indices); center = p.mean(axis=0)
            _, s, axes = np.linalg.svd(p - center, full_matrices=False)
            if s[1] < max(1.e-12, s[0] * 1.e-10):
                raise ValueError('Plane atoms are collinear')
            return center, axes[-1]

        def vector(indices):
            p = points(indices); v = p[1] - p[0]; size = np.linalg.norm(v)
            if size < 1.e-12:
                raise ValueError('Vector atoms coincide')
            return p[0], v / size

        def angle(a, b, unsigned=False):
            cosine = float(np.dot(a, b))
            return float(np.degrees(np.arccos(np.clip(abs(cosine) if unsigned else cosine, -1, 1))))

        if self.kind == 'Plane angle':
            return angle(plane(self.atoms)[1], plane(self.other)[1], unsigned=True)
        if self.kind == 'Vector angle':
            return angle(vector(self.atoms)[1], vector(self.other)[1])
        if self.kind == 'Vector–plane angle':
            return 90. - angle(vector(self.atoms)[1], plane(self.other)[1], unsigned=True)
        origin, direction = plane(self.other) if self.kind == 'Point–plane distance' else vector(self.other)
        delta = frame.positions[self.atoms[0]] - origin
        if self.nearest_images:
            delta = minimum_image(delta, frame)[0]
        if self.kind == 'Point–plane distance':
            return float(abs(np.dot(delta, direction)))
        return float(np.linalg.norm(np.cross(delta, direction)))


def parameter_values(document, sequence, parameter, symbols, *, unwrap=False):
    values = []
    for index in sequence:
        frame = document.frames[index]
        try:
            value = parameter.value(frame) if tuple(frame.symbols) == tuple(symbols) else np.nan
        except (ValueError, IndexError, FloatingPointError, np.linalg.LinAlgError):
            value = np.nan
        values.append(value)
    result = np.array(values, dtype=float)
    if unwrap and parameter.kind == 'Dihedral':
        # Never unwrap across a missing/undefined geometry.
        finite = np.flatnonzero(np.isfinite(result))
        for block in np.split(finite, np.where(np.diff(finite) > 1)[0] + 1):
            result[block] = np.degrees(np.unwrap(np.radians(result[block])))
    return result


@dataclass
class DisplayAlignment:
    reference: Frame
    indices: tuple[int, ...]
    reference_index: int = 0

    def transform(self, frame):
        if frame.symbols != self.reference.symbols:
            raise ValueError('Atom count/order differs from the alignment reference')
        if not self.indices or any(i < 0 or i >= len(frame.symbols) for i in self.indices):
            raise ValueError('Invalid alignment atoms')
        source = frame.positions[list(self.indices)]
        target = self.reference.positions[list(self.indices)]
        a, b = source.mean(axis=0), target.mean(axis=0)
        x, y = source - a, target - b
        u, singular, vt = np.linalg.svd(x.T @ y)
        if singular[0] < 1.e-20:
            rotation = np.eye(3)
        elif singular[1] < singular[0] * 1.e-10:
            # Linear molecules have no observable rotation about their axis.
            k = int(np.linalg.norm(x, axis=1).argmax())
            rotation = rotation_between_vectors(x[k], y[k]).T
        else:
            correction = np.eye(3)
            correction[-1, -1] = 1. if np.linalg.det(u @ vt) > 0 else -1.
            rotation = u @ correction @ vt
        return rotation, b - a @ rotation

    def apply(self, frame):
        rotation, translation = self.transform(frame)
        display = frame.clone()
        display.positions = frame.positions @ rotation + translation
        display.cell = frame.cell @ rotation
        return display, rotation, translation
