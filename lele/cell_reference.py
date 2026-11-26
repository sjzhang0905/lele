"""Associate a fixed simulation cell with Cartesian trajectory data."""
from itertools import chain
from pathlib import Path
import re

import numpy as np

from .output_text import read_output_lines
from .periodic_geometry import full_cell, valid_periodic_cell


def accepts_cell_reference(document):
    from .trajectory_link import association_role
    role = association_role(document)
    return (role == 'output' and document.format_name == 'CP2K output'
            or role == 'trajectory' and document.format_name != 'xTB optimization trajectory')


def _compatible_cell(left, right):
    # CP2K outputs may round lattice vectors to six decimal places.
    return np.allclose(left, right, rtol=1.e-6, atol=1.e-5)


def _variable_cell(run, ensemble):
    if run.upper() == 'CELL_OPT':
        return True
    ensemble = ensemble.upper()
    return run.upper() == 'MD' and (ensemble.startswith(('NPT', 'NPE', 'NPH', 'MSST'))
                                    or ensemble == 'HYDROSTATICSHOCK')


def read_cell_reference(path):
    """Read only lattice metadata. No coordinate file or atom matching is needed."""
    path = Path(path).expanduser().resolve()
    candidates = []
    variable = False
    if path.suffix.lower() == '.cif':
        from ase.io.cif import parse_cif
        for block in parse_cif(str(path)):
            cellpar = block.get_cellpar()
            if cellpar is None:
                continue
            try:
                parameters = np.asarray(cellpar, dtype=float)
                if (parameters.shape != (6,) or not np.isfinite(parameters).all()
                        or (parameters[:3] <= 0).any() or (parameters[3:] <= 0).any()
                        or (parameters[3:] >= 180).any()):
                    raise ValueError('Invalid CIF cell parameters')
                cell = np.asarray(block.get_cell())
            except (AssertionError, TypeError, ValueError) as error:
                raise ValueError('Invalid CIF cell lengths or angles.') from error
            if not np.isfinite(cell).all() or not full_cell(cell):
                raise ValueError('The CIF cell must contain three independent lattice vectors.')
            candidates.append((cell, (True, True, True)))
    else:
        from .cp2k_input import input_cell, input_tree
        lines = read_output_lines(path)
        if any(re.match(r'\s*@(?:IF|ELIF|ELSE)\b', line, re.I) for line in lines):
            raise ValueError('Select a resolved CP2K input, restart or CIF for a conditional input.')
        root, _ = input_tree(lines)
        run = ' '.join(root.child('GLOBAL').get('RUN_TYPE'))
        ensemble = ' '.join(root.child('MOTION').child('MD').get('ENSEMBLE'))
        variable = _variable_cell(run, ensemble)
        for force in root.all('FORCE_EVAL'):
            for node in force.child('SUBSYS').all('CELL'):
                if node.get('CELL_FILE_NAME'):
                    raise ValueError('The input refers to an external cell. Select the CIF or a restart with explicit vectors.')
                _, cell, pbc, _ = input_cell(node)
                if not cell.any():
                    continue
                if any(pbc) and not valid_periodic_cell(cell, pbc):
                    raise ValueError('The periodic cell vectors in the CP2K input are linearly dependent.')
                candidates.append((cell, pbc))
    if not candidates:
        raise ValueError('No explicit unit cell found. Select a CIF with cell lengths and angles or a CP2K input with &SUBSYS / &CELL.')
    cell, pbc = candidates[0]
    if any(flags != pbc or not _compatible_cell(cell, other) for other, flags in candidates[1:]):
        raise ValueError('The reference contains different unit cells. Select a single matching cell.')
    return dict(path=str(path), cell=cell.tolist(), pbc=list(pbc), variable_cell=variable)


def apply_cell_reference(document, reference):
    """Validate all frames, then attach missing lattice data without copying positions."""
    cell = np.asarray(reference['cell'], dtype=float)
    flags = tuple(reference['pbc'])
    results = document.calculation_results
    steps = getattr(results, 'steps', ())
    geometries = (s.geometry for s in steps if s.geometry is not None)
    frames = {id(f): f for f in chain(document.frames, geometries)}.values()
    variable = reference['variable_cell']
    settings = getattr(results, 'metadata', {}).get('jobs', {})
    if results is not None:
        for job in results.jobs:
            ensemble = settings.get(str(job.index), {}).get('MD ensemble', '')
            variable |= any(_variable_cell(task, ensemble) for task in job.tasks)

    updates = []
    native_cells = []
    for frame in frames:
        info = frame.info
        needs_cell = info.get('cell_from_reference', False) or not frame.cell.any()
        if needs_cell and variable:
            raise ValueError('This variable-cell run requires a cell for each frame. Link a trajectory containing the per-frame lattice vectors.')
        if not needs_cell:
            native_cells.append(frame.cell)
        if 'trajectory_pbc' in info:
            pbc = frame.pbc
        elif 'cp2k_periodicity' in info:
            pbc = tuple(info['cp2k_periodicity'])
        elif not needs_cell and not info.get('source_kind', '').startswith('cp2k'):
            pbc = frame.pbc
        else:
            pbc = flags
        effective_cell = cell if needs_cell else frame.cell
        if any(pbc) and not valid_periodic_cell(effective_cell, pbc):
            raise ValueError('The associated cell is incompatible with the periodic directions of this trajectory.')
        updates.append((frame, needs_cell, pbc))

    # A partially recorded changing cell cannot be reconstructed from one reference.
    if native_cells and not variable and any(not _compatible_cell(c, cell) for c in native_cells):
        complete = len(native_cells) == len(updates)
        if not complete or all(_compatible_cell(native_cells[0], c) for c in native_cells):
            raise ValueError('The reference differs from the cell recorded in the trajectory or output.')
    if not updates and variable:
        raise ValueError('Link a trajectory with per-frame lattice vectors before associating this variable-cell run.')
    for frame, needs_cell, pbc in updates:
        if needs_cell:
            frame.cell = cell.copy()
            frame.info['cell_from_reference'] = True
        frame.pbc = pbc
    document.cell_reference = dict(reference)
