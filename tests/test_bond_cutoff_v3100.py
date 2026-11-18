"""A smaller display default changes inferred bonds, never saved user choices."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from lele.core import Document, Frame, find_bonds
from lele.display_reference import bond_limits, chemcraft_limit
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from test_periodic_fragment_ui_v171 import gui


def carbon_pair(distance=1.85):
    return Frame(['C', 'C'], [[0., 0., 0.], [distance, 0., 0.]])


def test_default_cutoff_removes_long_cc_contact_and_is_applied_once():
    options = RenderOptions()
    assert options.bond_cutoff == .88
    assert options.bond_scale == .05  # Thickness is independent of connectivity.
    limit = chemcraft_limit('C', 'C')
    assert limit == pytest.approx(1.89226636602779)
    assert bond_limits(['C'], options.bond_cutoff)[('C', 'C')] == pytest.approx(limit * .88)
    assert find_bonds(carbon_pair(), 1.0) == [(0, 1)]
    assert find_bonds(carbon_pair(), options.bond_cutoff) == []
    # 1.60 Å remains below the single-scaled limit (1.665 Å), but would be
    # incorrectly removed if .88 were multiplied a second time (1.465 Å).
    assert find_bonds(carbon_pair(1.60), options.bond_cutoff) == [(0, 1)]


def bond_segments(renderer, frame):
    with patch.object(renderer, '_tube_segments') as tubes:
        renderer._bonds(frame)
    return [segment for call in tubes.call_args_list for segment in call.args[0]]


def test_gui_controls_use_default_and_really_change_drawn_bonds(gui):
    frame = carbon_pair()
    gui.attach(frame)
    w = gui.window
    before = frame.positions.copy()
    assert w.cutoff_spin.value() == .88 and w.cutoff_slider.value() == 88
    assert w.renderer.options.bond_cutoff == .88
    assert bond_segments(w.renderer, frame) == []
    thickness = w.render_options.bond_scale
    w.cutoff_spin.setValue(1.0)
    assert w.cutoff_slider.value() == 100 and w.renderer.options.bond_cutoff == 1.0
    assert len(bond_segments(w.renderer, frame)) == 2
    w.cutoff_slider.setValue(88)
    assert w.cutoff_spin.value() == .88 and bond_segments(w.renderer, frame) == []
    assert w.render_options.bond_scale == thickness
    np.testing.assert_array_equal(frame.positions, before)
    frame.bond_added.add((0, 1))
    w.refresh_scene()
    assert len(bond_segments(w.renderer, frame)) == 2  # Explicit bonds remain explicit.


def test_model_switch_back_to_chemcraft_uses_new_default(gui):
    gui.attach(carbon_pair())
    w = gui.window
    w.bond_model_combo.setCurrentText('Covalent radii')
    assert w.cutoff_spin.value() == 1.18
    w.bond_model_combo.setCurrentText('Chemcraft pair ranges')
    assert w.render_options.bond_cutoff == .88
    assert w.cutoff_spin.value() == .88 and w.cutoff_slider.value() == 88


@pytest.mark.parametrize('cutoff', [1.0, 1.37, .88])
def test_project_keeps_explicit_cutoff_values(tmp_path, cutoff):
    path = tmp_path / 'saved.lele'
    state = dict(documents=[dict(document=Document(Path('pair.xyz'), 'XYZ', [carbon_pair()]),
        options=RenderOptions(bond_cutoff=cutoff))], current_document=0)
    save_project(path, state)
    result = load_project(path)['documents'][0]
    assert result['options'].bond_cutoff == cutoff
    assert result['options'].bond_scale == .05
    assert find_bonds(result['document'].frames[0], result['options'].bond_cutoff) == ([] if cutoff == .88 else [(0, 1)])


@pytest.mark.parametrize('cutoff', [1.0, 1.37])
def test_gui_project_load_does_not_replace_explicit_cutoff_with_default(gui, tmp_path, cutoff):
    gui.attach(carbon_pair())
    w = gui.window
    w.cutoff_spin.setValue(cutoff)
    path = tmp_path / 'custom.lele'
    assert w.save_project_to(path)
    w.cutoff_spin.setValue(.88)
    w._load_project_path(path)
    assert w.render_options.bond_cutoff == cutoff
    assert w.cutoff_spin.value() == cutoff and w.cutoff_slider.value() == round(cutoff * 100)
    assert len(bond_segments(w.renderer, w.frame)) == 2


def test_document_switch_restores_each_explicit_cutoff(gui, tmp_path):
    gui.attach(carbon_pair())
    w = gui.window
    w.cutoff_spin.setValue(1.31)
    other = tmp_path / 'other.xyz'
    other.write_text('2\nCC\nC 0 0 0\nC 1.85 0 0\n')
    w._open_path_now(other)
    # Newly opened documents continue to inherit the current user setting.
    assert w.render_options.bond_cutoff == 1.31
    w.cutoff_spin.setValue(.97)
    w.change_frame(0, switch_doc=0)
    assert w.render_options.bond_cutoff == 1.31 and w.cutoff_slider.value() == 131
    w.change_frame(0, switch_doc=1)
    assert w.render_options.bond_cutoff == .97 and w.cutoff_spin.value() == .97
