"""Read ESP surface extrema supplied in X Y Z value order."""
from pathlib import Path

import numpy as np

from .annotations import EspExtremum
from .output_text import check_load_cancelled


def read_extrema_points(path):
    points = []
    with Path(path).open(encoding='utf-8-sig') as stream:
        for line_number, line in enumerate(stream, 1):
            check_load_cancelled()
            columns = line.partition('#')[0].replace(',', ' ').split()
            if not columns:
                continue
            if not points and len(columns) == 4 and [c.lower() for c in columns[:3]] == ['x', 'y', 'z']:
                continue
            try:
                if len(columns) != 4:
                    raise ValueError
                row = [float(c.replace('D', 'E').replace('d', 'e')) for c in columns]
                if not np.isfinite(row).all():
                    raise ValueError
            except ValueError:
                raise ValueError(f'Line {line_number}: expected four finite numbers (X Y Z value).') from None
            points.append(row)
    if not points:
        raise ValueError('The file contains no ESP extrema. Each row needs X Y Z value.')
    return np.asarray(points)


def make_extremum_labels(rows, unit, height, color, camera_rotation, display_rotation):
    """Lay out labels in the current camera plane, storing original-file coordinates."""
    from ase.units import Bohr
    scale = {'Å': 1., 'Bohr': Bohr}[unit]
    rotation = display_rotation @ camera_rotation
    # Clear the marker and its surface by placing the label above and right.
    offset = rotation @ [1.5 * height, 1.1 * height, .12]
    labels = []
    for x, y, z, value in rows:
        point = np.asarray([x, y, z]) * scale
        labels.append(EspExtremum('', point + offset, height=height, color=color,
                                  point=point, value=value))
    return labels
