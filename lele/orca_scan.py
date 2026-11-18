"""Printed ORCA relaxed-scan coordinates and final points, without interpolation."""
from dataclasses import dataclass, field
import re
from .calculation_results import NUMBER
from .gaussian_vibrations import _number

SCAN_STEP = re.compile(r'RELAXED\s+SURFACE\s+SCAN\s+STEP\s+(\d+)', re.I)
COORDINATE = re.compile(rf'(Bond|Angle|Dihedral)\s*\(\s*([\d,\s]+)\)\s*:\s*(.*)', re.I)
RANGE = re.compile(rf'range\s*=\s*({NUMBER})\s*\.\.\s*({NUMBER})\s+steps\s*=\s*(\d+)', re.I)


@dataclass
class ScanCoordinate:
    kind: str
    atoms: tuple
    start: float | None = None
    stop: float | None = None
    count: int | None = None

    @property
    def unit(self):
        return 'Å' if self.kind == 'Bond' else '°'

    @property
    def label(self):
        """Use normal displayed atom numbers; keep native indices in atoms."""
        return f'{self.kind} (' + ', '.join(str(atom + 1) for atom in self.atoms) + ')'


@dataclass
class ScanPoint:
    number: int
    source_line: int
    stage_index: int
    values: tuple = ()
    step_index: int | None = None
    frame_index: int | None = None
    energy_ev: float | None = None
    converged: bool = False
    convergence_line: int | None = None


@dataclass
class ScanRun:
    index: int
    job_index: int
    source_line: int
    coordinates: list = field(default_factory=list)
    points: list = field(default_factory=list)
    simultaneous: bool = False
    expected_points: int | None = None


def scan_point_label(coordinates, point):
    values = ', '.join(f'{coordinate.label}={value:.6g} {coordinate.unit}'
                       for coordinate, value in zip(coordinates, point.values) if value is not None)
    return f'Scan step {point.number}' + (f' · {values}' if values else '')


def refresh_scan_display_labels(results, frames=()):
    """Refresh derived captions in old projects without changing source data."""
    if results is None:
        return
    labels = {}
    stage_names = {}
    for run in getattr(results, 'scans', ()):
        labels[run.index] = [coordinate.label for coordinate in run.coordinates]
        for point in run.points:
            stage_names[point.stage_index] = scan_point_label(run.coordinates, point)
    if not labels:
        return
    for stage in results.stages:
        if stage.index in stage_names:
            stage.name = stage_names[stage.index]
    geometries = list(frames) + [step.geometry for step in results.steps if step.geometry is not None]
    for frame in geometries:
        run_labels = labels.get(frame.info.get('scan_run'))
        if run_labels is not None:
            frame.info['scan_coordinate_labels'] = list(run_labels)


def coordinate_from_line(line):
    match = COORDINATE.search(line)
    if match is None:
        return None
    kind = match[1].title()
    atoms = tuple(int(v) for v in match[2].split(','))
    if len(atoms) != {'Bond': 2, 'Angle': 3, 'Dihedral': 4}[kind]:
        return None
    ranged = RANGE.match(match[3])
    if ranged is not None:
        return ScanCoordinate(kind, atoms, _number(ranged[1]), _number(ranged[2]), int(ranged[3])), None
    value = re.match(NUMBER, match[3])
    return (ScanCoordinate(kind, atoms), _number(value[0])) if value is not None else None


def finish_scan_records(results):
    """Bind one evaluated endpoint to each printed scan step and tag its history.

    A truncated step remains explicitly incomplete; no planned coordinates or
    energies are synthesized, and no geometry is borrowed from a previous step.
    """
    grouped = {}
    for i, step in enumerate(results.steps):
        grouped.setdefault(step.stage_index, []).append((i, step))
    for run in results.scans:
        for point in run.points:
            records = grouped.get(point.stage_index, [])
            stage = results.stages[point.stage_index]
            optimization_converged = stage.status == 'Converged'
            evaluated = [(i, s) for i, s in records if s.geometry is not None and s.energy_ev is not None]
            point.converged = False
            if evaluated:
                point.step_index, endpoint = evaluated[-1]
                point.energy_ev = endpoint.energy_ev
                # ORCA prints a final optimized geometry and a final SP after
                # the convergence banner. A pre-banner evaluation is not the
                # optimized endpoint if the file stops before that final SP.
                point.converged = bool(optimization_converged and point.convergence_line is not None
                                       and endpoint.source_line > point.convergence_line)
                endpoint.converged = point.converged
            if optimization_converged and not point.converged:
                stage.status = 'Optimization converged; final endpoint energy not printed'
            elif not point.converged and stage.status == 'Not confirmed':
                stage.status = 'Incomplete / not converged'
            for _, step in records:
                if step.geometry is None:
                    continue
                step.geometry.info.update(scan_run=run.index, scan_step=point.number,
                    scan_values=list(point.values), scan_coordinate_labels=[c.label for c in run.coordinates],
                    scan_coordinate_units=[c.unit for c in run.coordinates],
                    scan_simultaneous=run.simultaneous)
            stage.name = scan_point_label(run.coordinates, point)


def link_scan_frames(results, frames):
    for run in results.scans:
        for point in run.points:
            if point.step_index is None:
                continue
            point.frame_index = results.steps[point.step_index].frame_index
            if point.frame_index is not None:
                frames[point.frame_index].info['scan_endpoint'] = True
                frames[point.frame_index].info['scan_converged'] = point.converged
