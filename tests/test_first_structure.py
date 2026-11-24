"""First-file shortcuts keep the scientific reader and geometry semantics."""
import builtins
from unittest.mock import patch

import numpy as np
import pytest

from lele.bond_filter import prune_occluded
from lele.core import Frame, nearby_pairs, visible_bonds
from lele.periodic_geometry import short_contact_details
from lele.trajectory_io import read_plain_xyz


def test_small_xyz_opens_and_analyzes_without_optional_reader_imports(tmp_path):
    path = tmp_path / 'water.xyz'
    path.write_text('3\nWater molecule\nO 0 0 0\nH .96 0 0\nH -.24 .92 0\n')
    original = builtins.__import__

    def guard(name, *args, **kwargs):
        assert not (name.startswith('ase.io') or name.startswith('scipy')), name
        return original(name, *args, **kwargs)

    with patch('builtins.__import__', guard):
        frame, = read_plain_xyz(path)
        assert frame.info == {'Water': 'True', 'molecule': 'True'}
        assert visible_bonds(frame) == [(0, 1), (0, 2)]
        assert short_contact_details(frame) == []


@pytest.mark.parametrize('comment', ['Cu120 relax', '', 'uid', '"free text"', 'a\\ b',
                                      'frame-1', '两个原子', 'water water'])
def test_xyz_comments_match_ase(comment):
    from ase.io.extxyz import key_val_str_to_dict
    from lele.trajectory_io import _plain_xyz_info
    expected = {str(k): str(v)[:180] for k, v in key_val_str_to_dict(comment).items()
                if isinstance(v, (str, int, float, bool))}
    assert _plain_xyz_info(comment) == expected


@pytest.mark.parametrize('count', [1, 2, 32, 33])
def test_small_neighbor_search_matches_tree(count):
    from scipy.spatial import cKDTree
    positions = np.random.default_rng(count).random((count, 3))
    expected = cKDTree(positions).query_pairs(.6)
    assert set(map(tuple, nearby_pairs(positions, .6))) == expected
    frame = Frame(['H']*count, positions)
    assert {(row.first, row.second) for row in short_contact_details(frame)} == expected


def test_short_contact_strict_boundary():
    for x, expected in ((np.nextafter(.6, 0.), 1), (.6, 0), (np.nextafter(.6, 1.), 0)):
        frame = Frame(['H', 'H'], [[0, 0, 0], [x, 0, 0]])
        assert len(short_contact_details(frame)) == expected


def test_occlusion_uses_the_correct_periodic_image():
    # The central atom has both a collinear image and another image off the line.
    xyz = np.array([[1., 0, 0], [1., 0, 0], [0., 0, 0]])
    cell = np.array([[2., 0, 0], [1., 2., 0], [0., 0, 3.]])
    long = (0, 1, (1, 0, 0))
    left = (0, 2, (1, 0, 0))
    right = (1, 2, (0, 0, 0))
    other = (0, 2, (0, 1, 0))
    assert prune_occluded(xyz, [long, left, right, other], cell) == sorted([left, right, other])
    assert prune_occluded(xyz, [long, right, other], cell) == sorted([long, right, other])
