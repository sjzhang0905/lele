"""Pan redraws reuse molecular actors and retain expensive field geometry."""
from unittest.mock import patch

import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import Frame, Volume
from lele.fragment_preview import start_fragment_pan_preview
from lele.renderer import MoleculeRenderer


def molecule():
    return Frame(['O', 'H', 'H', 'O', 'H', 'H'],
        [[0, 0, 0], [.96, 0, 0], [-.24, .92, 0],
         [10, 0, 0], [10.96, 0, 0], [9.76, .92, 0]])


def test_pan_moves_only_cached_fragment_actors_and_retains_fields():
    frame = molecule()
    original_coordinates = frame.positions.copy()
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.labels = 'Index (1..N)'
    renderer.selected = [0, 1, 2]
    volume = Volume(np.indices((5, 5, 5))[0].astype(float) / 4, np.zeros(3), np.eye(3))
    renderer.options.volume_iso = .5
    renderer.set_scene(frame, volume)
    fields = list(renderer.field_actors)
    originals = list(renderer.fragment_geometry_actors)
    assert fields and originals
    with patch('lele.surface_rendering.draw_fields', side_effect=AssertionError('field rebuilt')):
        preview = start_fragment_pan_preview(renderer, frame, [0, 1, 2])
        assert all(not actor.GetVisibility() for actor in originals)
        assert all(actor.GetVisibility() for actor in fields)
        moving = {id(actor) for actor, _ in preview.moving_actors}
        static_positions = [(actor, actor.GetPosition()) for actor in preview.actors if id(actor) not in moving]
        with patch.object(MoleculeRenderer, 'set_scene', side_effect=AssertionError('scene rebuilt')):
            for _ in range(20):
                preview.translate([.1, -.05, .02])
        for actor, origin in preview.moving_actors:
            np.testing.assert_allclose(actor.GetPosition(), origin + [2, -1, .4], atol=1e-12)
        for actor, position in static_positions:
            np.testing.assert_allclose(actor.GetPosition(), position)
        np.testing.assert_array_equal(frame.positions, original_coordinates)
        assert renderer.field_actors == fields
        preview.close()
        preview.close()
        assert all(actor.GetVisibility() for actor in originals)
        assert all(actor.GetVisibility() for actor in fields)


def test_periodic_preview_translates_replicas_without_rotating_cell():
    frame = Frame(['C', 'He'], [[0, 0, 0], [2, 2, 2]], np.eye(3) * 5, (True,) * 3)
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.labels = 'Index (1..N)'
    renderer.selected = [0]
    renderer.set_scene(frame)
    assert len(renderer.boundary_display.source_indices) > 2
    cell = frame.cell.copy()
    preview = start_fragment_pan_preview(renderer, frame, [0])
    moving = preview.builders[1]
    assert set(actor.GetInput() for actor in moving._label_actors) == {'1'}
    assert len(moving.atom_highlights) > 1
    preview.translate([.5, .25, 0])
    for actor, origin in preview.moving_actors:
        np.testing.assert_allclose(actor.GetPosition(), origin + [.5, .25, 0])
    np.testing.assert_array_equal(frame.cell, cell)
    preview.close()


def test_polyhedral_mode_retains_full_geometry_update_path():
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.options.style = 'Polyhedral'
    assert start_fragment_pan_preview(renderer, molecule(), [0]) is None


def test_an_intervening_full_redraw_closes_preview_without_leaked_actors():
    frame = molecule()
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.set_scene(frame)
    preview = start_fragment_pan_preview(renderer, frame, [0, 1, 2])
    preview_actors = list(preview.actors)
    assert not preview.closed
    renderer.set_scene(frame)
    assert preview.closed
    assert renderer._fragment_pan_preview is None
    for actor in preview_actors:
        assert not renderer.renderer.HasViewProp(actor)


def test_cross_fragment_hydrogen_link_keeps_full_update_to_stretch_link():
    frame = molecule()
    frame.hbond_added[(1, 3)] = (0, 0, 0)
    renderer = MoleculeRenderer(vtkRenderer())
    renderer.set_scene(frame)
    assert start_fragment_pan_preview(renderer, frame, [0, 1, 2]) is None
