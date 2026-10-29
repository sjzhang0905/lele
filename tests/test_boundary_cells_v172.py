"""Boundary is a set of full original-sized cells, with individual edges."""
from itertools import product

import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.boundary import boundary_view
from lele.core import Frame


def test_two_by_two_repeats_every_atom_and_draws_each_original_cell_edge():
    source = Frame(['Si', 'O'], [[0, 0, 0], [1.1, 1.1, 1.1]], np.eye(3) * 3, (True,) * 3,
                   atom_appearance={1: AtomAppearance(opacity=.4)})
    view = boundary_view(source, ((0, 2), (0, 2), (0, 1)))
    assert len(view.source_indices) == 8
    assert view.tiles == tuple(product(range(2), range(2), range(1)))
    for k, tile in enumerate(view.tiles):
        np.testing.assert_allclose(view.frame.positions[2*k:2*k+2], source.positions + np.asarray(tile) @ source.cell)
        np.testing.assert_array_equal(view.source_indices[2*k:2*k+2], [0, 1])
        assert view.frame.atom_appearance[2*k+1].opacity == .4
    np.testing.assert_allclose(view.frame.cell, source.cell)
    assert all(np.isclose(np.linalg.norm(q-p), 3.) for p, q in view.cell_lines)
    assert len(view.cell_lines) == 33
    assert len(source.symbols) == 2


def test_negative_tiles_skew_lattice_and_partial_periodicity_keep_full_cell_contents():
    cell = np.array([[4., 0, 0], [1., 5., 0], [.5, .2, 8.]])
    positions = np.array([[.1, .2, 1.125], [.3, .2, 1.125]]) @ cell
    source = Frame(['C', 'H'], positions, cell, (True, True, False))
    view = boundary_view(source, ((-1, 1), (0, 1), (0, 2)))
    assert len(view.tiles) == 4 and len(view.source_indices) == 8
    for k, tile in enumerate(view.tiles):
        np.testing.assert_allclose(view.frame.positions[2*k:2*k+2], source.positions + np.asarray(tile) @ cell)
    lengths = np.linalg.norm(cell, axis=1)
    assert all(np.isclose(np.linalg.norm(q-p), lengths).any() for p, q in view.cell_lines)


@pytest.mark.parametrize('bounds', [((0, 0), (0, 1), (0, 1)),
                                   ((0, 1.5), (0, 1), (0, 1)), ((-10, 10),)*3])
def test_invalid_or_oversized_cell_ranges_are_rejected(bounds):
    source = Frame(['Si'], [[0, 0, 0]], np.eye(3) * 3, (True,) * 3)
    with pytest.raises(ValueError):
        boundary_view(source, bounds)
