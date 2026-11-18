"""A drag updates coordinates live, then commits UI refresh and undo once."""
from unittest.mock import patch

import numpy as np

from lele.core import Frame
from test_periodic_fragment_ui_v171 import gui


def test_pan_reuses_scene_until_release_and_undo_restores_coordinates(gui):
    frame = Frame(['O', 'H', 'H', 'He'],
        [[0, 0, 0], [.96, 0, 0], [-.24, .92, 0], [10, 0, 0]])
    gui.attach(frame)
    gui.select([0])
    window = gui.window
    previous = frame.positions.copy()
    undo_count = len(window.undo_stack)
    with patch.object(window, 'refresh_scene', wraps=window.refresh_scene) as refresh:
        window._fragment_begin('pan', 20, 20)
        window._fragment_move('pan', 15, 0)
        preview = window._fragment_gesture['preview']
        assert preview is not None and not preview.closed
        window._fragment_move('pan', 15, 0)
        assert refresh.call_count == 0
        assert not np.array_equal(window.frame.positions[:3], previous[:3])
        np.testing.assert_array_equal(window.frame.positions[3], previous[3])
        assert len(window.undo_stack) == undo_count + 1
        window._fragment_end('pan')
        assert refresh.call_count == 1
        assert preview.closed
    window.undo_edit()
    np.testing.assert_allclose(window.frame.positions, previous)
