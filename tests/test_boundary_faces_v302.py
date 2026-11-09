"""Inclusive outer cell faces are display images, never additional atoms."""
from itertools import product

import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.boundary import boundary_view
from lele.core import Frame


@pytest.mark.parametrize('fractional,count', [([.2,.3,.4],1), ([0,.3,.4],2),
    ([1,.3,.4],2), ([0,0,.4],4), ([0,0,0],8), ([1,1,1],8),
    ([1.e-9,.3,.4],2), ([1.e-6,.3,.4],1)])
def test_faces_edges_corners_have_shared_source_id(fractional, count):
    lattice = np.array([[5,0,0],[1,6,0],[.3,.2,7]])
    source = Frame(['Si'], np.asarray([fractional])@lattice, lattice, (True,)*3,
                   atom_appearance={0:AtomAppearance(label_mode='Index (1..N)')})
    original = source.positions.copy()
    view = boundary_view(source, ((0,1),)*3)
    assert len(view.frame.symbols) == count
    assert set(view.source_indices) == {0}
    assert all(style.label_mode == 'Index (1..N)' for style in view.frame.atom_appearance.values())
    assert len(source.symbols) == 1
    np.testing.assert_array_equal(source.positions, original)
    assert len({tuple(p) for p in np.round(view.frame.positions, 8)}) == count


def test_negative_range_all_endpoint_images_and_partial_periodicity():
    source = Frame(['Si'], [[0,0,0]], np.eye(3)*5, (True,True,False))
    view = boundary_view(source, ((-1,1),(0,2),(0,1)))
    assert len(view.frame.symbols) == 9
    assert set(map(tuple, view.shifts)) == set(product(range(-1,2), range(3), [0]))
    assert len(view.tiles) == 4


def test_bonds_and_manual_hydrogen_links_follow_extra_face_images():
    source = Frame(['C','H'], [[0,1,1],[4,1,1]], np.eye(3)*5, (True,)*3)
    source.hbond_added[(0,1)] = (-1,0,0)
    view = boundary_view(source, ((0,1),)*3)
    assert len(view.frame.symbols) == 3 and view.source_indices.tolist() == [0,1,0]
    assert view.bonds == [(1,2)]
    assert view.frame.hbond_added == {(1,2):(0,0,0)}
    assert source.hbond_added == {(0,1):(-1,0,0)}


def test_memory_limit_counts_face_images(monkeypatch):
    import lele.boundary as module
    monkeypatch.setattr(module, 'MAX_DISPLAY_ATOMS', 7)
    source = Frame(['Si'], [[0,0,0]], np.eye(3)*5, (True,)*3)
    with pytest.raises(ValueError, match='face images'):
        boundary_view(source, ((0,1),)*3)
