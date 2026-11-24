"""Display cell origin, independent of stored atom coordinates and lattice."""
import numpy as np
from .periodic_geometry import lattice_coordinates


def cell_origin(frame):
    return np.asarray(frame.info.get('cell_origin_fractional',(0.,0.,0.)),dtype=float) @ frame.cell


def set_cell_origin(frame, origin):
    frame.info['cell_origin_fractional'] = lattice_coordinates(origin, frame.cell, frame.pbc).tolist()


def translate_cell_origin(frame, translation):
    """After rotating the cell, apply a full-structure translation to its box."""
    if 'cell_origin_fractional' in frame.info:
        set_cell_origin(frame,cell_origin(frame)+translation)
