"""Directional light state, selection readability, and default-only style edits."""
from pathlib import Path

import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.atom_appearance import AtomAppearance
from lele.core import Document, Frame
from lele.lighting import DEFAULT_LIGHT_POSITIONS, light_settings
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer, volume_surface_specs
from lele.style_presets import element_palette_color, BUILTIN_PRESETS


def test_default_style_changes_do_not_modify_custom_colors_or_geometry():
    opts = RenderOptions()
    assert (opts.atom_scale, opts.bond_scale) == (.45, .05)
    classic = BUILTIN_PRESETS['Classic ball and stick']
    assert (classic['atom_scale'], classic['bond_scale']) == (.45, .05)
    assert element_palette_color(opts, 'C') == '#ADADAD'
    # Repeated lookups never accumulate the extra white blend.
    assert element_palette_color(opts, 'C') == '#ADADAD'
    opts.element_colors['C'] = '#123456'
    assert element_palette_color(opts, 'C') == '#123456'
    frame = Frame(['C', 'O'], [[0., 0., 0.], [1.2, 0., 0.]])
    frame.atom_appearance[1] = AtomAppearance(color='#AABBCC')
    draw = MoleculeRenderer(vtkRenderer()); draw.options = opts
    before = frame.positions.copy()
    draw.set_scene(frame)
    assert draw.atom_color(frame, 1) == '#AABBCC'
    np.testing.assert_array_equal(frame.positions, before)
    specs = volume_surface_specs(opts)
    assert {s['color'] for s in specs} == {'#80E666', '#00C2FF'}
    assert all(s['opacity'] == .5 for s in specs)


def test_four_camera_lights_two_enabled_switch_without_geometry_rebuild():
    scene = vtkRenderer(); draw = MoleculeRenderer(scene)
    draw.set_scene(Frame(['C'], [[0., 0., 0.]]))
    actors = tuple(draw.dynamic)
    assert scene.GetLights().GetNumberOfItems() == 4
    assert [x.GetSwitch() for x in draw._lights] == [1, 1, 0, 0]
    assert all(x.LightTypeIsCameraLight() and not x.GetPositional() for x in draw._lights)
    assert tuple(x.GetPosition() for x in draw._lights) == DEFAULT_LIGHT_POSITIONS
    draw.options.light_enabled = (False, False, True, True)
    draw.apply_lighting()
    assert [x.GetSwitch() for x in draw._lights] == [0, 0, 1, 1]
    assert tuple(draw.dynamic) == actors
    draw.clear()
    assert scene.GetLights().GetNumberOfItems() == 4


def test_light_settings_survive_project_roundtrip(tmp_path):
    opts = RenderOptions(light_enabled=(False, True, True, False),
                         light_intensities=(.4, .6, .8, .5))
    document = Document(Path('atom.xyz'), 'XYZ', [Frame(['H'], [[0., 0., 0.]])])
    path = tmp_path / 'lights.lele'
    save_project(path, dict(documents=[dict(document=document, options=opts)], current_document=0))
    restored = load_project(path)['documents'][0]['options']
    assert light_settings(restored) == light_settings(opts)


def test_selection_outline_is_thick_solid_and_closed():
    draw = MoleculeRenderer(vtkRenderer()); draw.selected = [0]
    draw.set_scene(Frame(['C'], [[0., 0., 0.]]))
    actor = draw.atom_highlights[0]
    assert actor.GetProperty().GetLineWidth() >= 9
    geometry = actor.GetMapper().GetInput()
    assert geometry.GetNumberOfLines() == 1
    ring = geometry.GetCell(0).GetPointIds()
    assert ring.GetNumberOfIds() == geometry.GetNumberOfPoints() + 1
    assert ring.GetId(0) == ring.GetId(ring.GetNumberOfIds() - 1)
    assert len({ring.GetId(i) for i in range(ring.GetNumberOfIds() - 1)}) == geometry.GetNumberOfPoints()
    assert not actor.GetPickable()


@pytest.mark.parametrize('bad', [dict(light_enabled=(True,)),
    dict(light_intensities=(float('nan'), 1, 1, 1)),
    dict(light_positions=((0, 0, 0),)*4)])
def test_invalid_light_settings_rejected_before_mutating_scene(bad):
    draw = MoleculeRenderer(vtkRenderer())
    before = [(x.GetSwitch(), x.GetIntensity(), x.GetPosition()) for x in draw._lights]
    for name, value in bad.items(): setattr(draw.options, name, value)
    with pytest.raises(ValueError): draw.apply_lighting()
    assert before == [(x.GetSwitch(), x.GetIntensity(), x.GetPosition()) for x in draw._lights]
