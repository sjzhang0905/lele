"""Source-coordinate coordination statistics, independent of display copies.

Baur D and the VESTA/Hoppe ECoN definition use the actual ligand distances.
Quadratic elongation and edge-angle variance are reported for recognized
tetrahedra and octahedra containing the central atom, not for arbitrary hulls.
"""
from itertools import combinations
import numpy as np
from scipy.spatial import ConvexHull
from .polyhedra import coordination_shells

METRIC_COLUMNS = (
    ('coordination', 'CN', ''), ('mean_length_A', 'Mean length', 'Å'),
    ('min_length_A', 'Min. length', 'Å'), ('max_length_A', 'Max. length', 'Å'),
    ('volume_A3', 'Volume', 'Å³'), ('distortion_index', 'Bond distortion D', ''),
    ('quadratic_elongation', 'Quadratic elongation', ''),
    ('angle_variance_deg2', 'Angle variance', 'deg²'),
    ('effective_coordination', 'ECoN', ''))


def measure_shell(shell):
    vectors = shell.vectors
    lengths = np.linalg.norm(vectors, axis=1)
    result = {key:None for key, _, _ in METRIC_COLUMNS}
    result.update(center=shell.center, coordination=len(lengths), shape='No polyhedron',
                  effective_coordination=0., distances=lengths)
    if not len(lengths):return result
    mean = float(lengths.mean())
    weights = np.exp(1.-(lengths/lengths.min())**6)
    weighted_length = float(np.dot(lengths, weights)/weights.sum())
    result.update(mean_length_A=mean, min_length_A=float(lengths.min()), max_length_A=float(lengths.max()),
        distortion_index=float(np.abs(lengths-mean).mean()/mean),
        effective_coordination=float(np.exp(1.-(lengths/weighted_length)**6).sum()))
    if not shell.faces:return result
    if shell.planar:result.update(shape='Planar', volume_A3=0.);return result
    hull = ConvexHull(vectors);volume = float(hull.volume)
    result.update(shape='General', volume_A3=volume)
    if np.any(hull.equations[:, 3] > 1.e-8):return result
    if len(lengths) == 4 and len(hull.vertices) == 4 and len(shell.edges) == 6:
        result['shape'] = 'Tetrahedron';regular_radius = (9.*np.sqrt(3.)*volume/8.)**(1./3.)
        ideal_angle = float(np.degrees(np.arccos(-1./3.)))
    elif len(lengths) == 6 and len(hull.vertices) == 6 and len(shell.edges) == 12 and all(
            sum(i in edge for edge in shell.edges) == 4 for i in range(6)):
        result['shape'] = 'Octahedron';regular_radius = (3.*volume/4.)**(1./3.);ideal_angle = 90.
    else:return result
    result['quadratic_elongation'] = float(np.mean((lengths/regular_radius)**2))
    directions = vectors/lengths[:, None]
    angles = [float(np.degrees(np.arccos(np.clip(np.dot(directions[i], directions[j]), -1., 1.))))
              for i, j in shell.edges]
    result['angle_variance_deg2'] = float(np.sum((np.asarray(angles)-ideal_angle)**2)/(len(angles)-1))
    return result


def analyze_polyhedra(frame, options, center_indices=None):
    return [(shell, {**measure_shell(shell), 'element':frame.symbols[shell.center]})
            for shell in coordination_shells(frame, options, center_indices)]


def polyhedron_series(document, options, center, indices=None, progress=None, reference_symbols=None, reference=None):
    from .output_text import progress_items
    from .atom_indices import atom_mapping
    indices = list(range(len(document.frames))) if indices is None else list(indices)
    if not indices:return []
    if reference is None:
        reference=(document.frames[indices[0]] if reference_symbols is None else
                   next((f for f in document.frames if f.symbols is reference_symbols),None))
        if reference is None:
            reference=next((f for f in document.frames if f.symbols==list(reference_symbols)),None)
    symbols = reference.symbols if reference is not None else list(reference_symbols)
    rows = []
    for i, index in enumerate(progress_items(indices,'Analyzing trajectory coordination')):
        if progress is not None and progress(i, len(indices)) is False:return None
        frame = document.frames[index]
        row = {key:None for key, _, _ in METRIC_COLUMNS}
        row.update(frame=index, center=center, element=symbols[center] if 0 <= center < len(symbols) else '', status='')
        mapping=atom_mapping(reference,frame,allow_partial=True) if reference is not None else None
        if mapping is None or not 0<=center<len(mapping) or mapping[center] is None:row['status'] = 'Atom sequence differs'
        else:
            found = analyze_polyhedra(frame, options, (mapping[center],))
            if found:row.update(found[0][1]);row['status'] = 'OK'
            else:row['status'] = 'Center excluded by element rules or atom visibility'
        rows.append(row)
    return rows


def summary_rows(records):
    columns = ['center', 'element', *[key for key, _, _ in METRIC_COLUMNS], 'shape']
    rows = [[data['center']+1, data['element'], *[data[key] for key, _, _ in METRIC_COLUMNS], data['shape']]
            for _, data in records]
    return columns, rows


def ligand_rows(frame, records):
    columns = ['center', 'center_element', 'ligand', 'ligand_element', 'image_a', 'image_b', 'image_c', 'distance_A']
    rows = []
    for shell, data in records:
        for index, shift, distance in zip(shell.ligand_indices, shell.image_shifts, data['distances']):
            rows.append([shell.center+1, frame.symbols[shell.center], int(index)+1, frame.symbols[index],
                         *[int(x) for x in shift], float(distance)])
    return columns, rows
