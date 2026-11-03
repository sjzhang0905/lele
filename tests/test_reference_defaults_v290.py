"""Reference tables affect geometry, rendering and saved views consistently."""
from pathlib import Path
import json
import zipfile
import numpy as np
import pytest

from lele.core import Frame, Document, colour, visible_bonds, freeze_bonds
from lele.display_reference import chemcraft_limit, vesta_radius
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.periodic_geometry import periodic_bonds, periodic_fragment
from lele.element_rules import install_rules, default_rule
from lele.project_file import save_project, load_project
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('pair,inside,outside', [
    (('C', 'C'), 1.89, 1.90), (('H', 'O'), 1.42, 1.44),
    (('Cu', 'Cu'), 3.26, 3.27), (('Fe', 'O'), 2.52, 2.53),
])
def test_ordinary_limits_and_pair_symmetry(pair, inside, outside):
    for symbols in (pair, pair[::-1]):
        frame = Frame(list(symbols), [[0, 0, 0], [inside, 0, 0]])
        assert visible_bonds(frame) == [(0, 1)]
        frame.positions[1, 0] = outside
        assert visible_bonds(frame) == []


def test_oh_hydrogen_record_does_not_make_an_ordinary_bond():
    frame = Frame(['O', 'H'], [[0, 0, 0], [2., 0, 0]])
    assert visible_bonds(frame) == []
    frame.bond_added.add((0, 1))
    assert visible_bonds(frame) == [(0, 1)]
    frame.bond_added.clear()
    install_rules(frame, [{**default_rule(), 'a1': 'H', 'a2': 'O', 'maximum': 2.1}])
    assert visible_bonds(frame, .1) == [(0, 1)]


def test_same_pair_limit_across_periodic_boundary_and_fragment():
    frame = Frame(['C', 'C'], [[.1, 0, 0], [2.25, 0, 0]], np.eye(3) * 4, (True, True, True))
    assert visible_bonds(frame) == []
    assert periodic_bonds(frame) == [(0, 1, (-1, 0, 0))]
    assert set(periodic_fragment(frame, [0]).indices) == {0, 1}
    frame.positions[1, 0] = 2.20
    assert periodic_bonds(frame) == []


def test_frozen_graph_and_explicit_removal_survive_reference_defaults():
    frame = Frame(['C', 'C'], [[0, 0, 0], [1.85, 0, 0]])
    freeze_bonds(frame)
    frame.positions[1, 0] = 4
    assert visible_bonds(frame) == [(0, 1)]
    frame.bond_removed.add((0, 1))
    assert visible_bonds(frame) == []
    assert chemcraft_limit('Og', 'C') is None  # Explicit fallback beyond the source table.


def test_vesta_space_filling_uses_unscaled_radii_and_preserves_small_ions():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    view = MoleculeRenderer(vtkRenderer())
    view.options = RenderOptions(style='Space filling', atom_scale=.6)
    assert view._atom_radius('C') == .77
    assert view._atom_radius('O') == .74
    view.options.space_filling_radii = 'van der Waals'
    assert view._atom_radius('C') == 1.70
    view.options.space_filling_radii = 'Ionic'
    view.options.space_filling_scale = .2
    assert view._atom_radius('C') == pytest.approx(.03)
    assert vesta_radius('Og') == .8  # VESTA's documented XX placeholder.


def test_compatibility_palette_and_independent_user_color_override():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    assert colour('C') == '#727272' and colour('O') == '#FF4040'
    assert colour('F') == '#80FFFF'
    view = MoleculeRenderer(vtkRenderer())
    view.options.atom_palette = 'GaussView style (Chemcraft)'
    frame = Frame(['O'], [[0, 0, 0]])
    view.options.element_colors['O'] = '#123456'
    assert view.atom_color(frame, 0) == '#123456'
    view.options.element_colors.clear()
    assert view.atom_color(frame, 0) == colour('O')


def test_gui_size_controls_have_independent_space_filling_scale(gui):
    gui.attach(Frame(['C', 'O'], [[0, 0, 0], [1.2, 0, 0]]))
    w = gui.window
    w.style_combo.setCurrentText('Space filling')
    assert w.atom_slider.value() == 100 and w.sf_radii_combo.isEnabled()
    w.atom_slider.setValue(140)
    w.sf_radii_combo.setCurrentText('van der Waals')
    assert w.render_options.space_filling_scale == 1.4
    w.style_combo.setCurrentText('Ball and stick')
    assert w.atom_slider.value() == 50 and not w.sf_radii_combo.isEnabled()
    w.style_combo.setCurrentText('Space filling')
    assert w.atom_slider.value() == 140


def test_gui_model_rebuilds_all_frames_and_keeps_manual_overrides(gui):
    frame = Frame(['C', 'C', 'H'], [[0, 0, 0], [1.85, 0, 0], [6, 0, 0]], bond_added={(0, 2)})
    freeze_bonds(frame)
    gui.attach(frame, second_frame=frame.clone())
    w = gui.window
    w.bond_model_combo.setCurrentText('Covalent radii')
    assert w.cutoff_spin.value() == 1.18
    assert all(visible_bonds(f, 1.18) == [(0, 2)] for f in w.doc.frames)
    assert all(f.bond_snapshot is None for f in w.doc.frames)
    w.bond_model_combo.setCurrentText('Chemcraft pair ranges')
    assert w.cutoff_spin.value() == 1.0
    assert all(visible_bonds(f) == [(0, 1), (0, 2)] for f in w.doc.frames)


def test_reference_controls_restore_independently_between_files(gui, tmp_path):
    gui.attach(Frame(['C'], [[0, 0, 0]]))
    w = gui.window
    w.style_combo.setCurrentText('Space filling')
    w.sf_radii_combo.setCurrentText('Ionic')
    w.atom_slider.setValue(120)
    path = tmp_path / 'other.xyz'
    path.write_text('1\nother\nO 0 0 0\n')
    w._open_path_now(path)
    w.bond_model_combo.setCurrentText('Covalent radii')
    w.sf_radii_combo.setCurrentText('van der Waals')
    w.atom_slider.setValue(150)
    w.change_frame(0, switch_doc=0)
    assert w.bond_model_combo.currentText() == 'Chemcraft pair ranges'
    assert w.cutoff_spin.value() == 1.0
    assert w.sf_radii_combo.currentText() == 'Ionic' and w.atom_slider.value() == 120
    w.change_frame(0, switch_doc=1)
    assert w.bond_model_combo.currentText() == 'Covalent radii'
    assert w.cutoff_spin.value() == 1.18
    assert w.sf_radii_combo.currentText() == 'van der Waals' and w.atom_slider.value() == 150


def test_reference_choices_roundtrip_and_old_project_keeps_legacy_bonds(tmp_path):
    frame = Frame(['C', 'C'], [[0, 0, 0], [1.85, 0, 0]])
    options = RenderOptions(space_filling_radii='Ionic', space_filling_scale=1.2)
    state = dict(documents=[dict(document=Document(Path('x.xyz'), 'XYZ', [frame]), options=options)], current_document=0)
    path = tmp_path / 'new.lele'
    save_project(path, state)
    restored = load_project(path)['documents'][0]
    assert restored['options'].space_filling_radii == 'Ionic'
    assert restored['options'].space_filling_scale == 1.2
    assert visible_bonds(restored['document'].frames[0]) == [(0, 1)]
    with zipfile.ZipFile(path) as source:
        files = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(files['manifest.json'])
    for node in manifest['nodes']:
        if node.get('type') == 'lele.render_options:RenderOptions':
            node['attributes'].pop('bond_model')
            node['attributes']['bond_cutoff'] = 1.18
    files['manifest.json'] = json.dumps(manifest).encode()
    old = tmp_path / 'old.lele'
    with zipfile.ZipFile(old, 'w') as target:
        for name, data in files.items():target.writestr(name, data)
    restored = load_project(old)['documents'][0]
    assert restored['options'].bond_model == 'Covalent radii'
    assert visible_bonds(restored['document'].frames[0], 1.18) == []
