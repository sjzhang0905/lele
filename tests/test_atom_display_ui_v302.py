"""Selected atom labels and independent Boundary settings in real Qt views."""
from pathlib import Path

import numpy as np
import pytest

from lele.atom_appearance import appearance
from lele.core import Document, Frame
from lele.render_options import RenderOptions
from lele.style_presets import ATOM_PALETTES, element_palette_color
from test_periodic_fragment_ui_v171 import gui


def test_selected_label_buttons_only_change_selected_atoms_and_support_undo(gui):
    frame = Frame(['O','H','H'], [[1,1,1],[1.9,1,1],[1,1.9,1]])
    gui.attach(frame, second_frame=frame.clone())
    w = gui.window
    w.render_options.labels = 'None'
    gui.select([0,2])
    panel = w.atom_panel
    for button, expected in [(panel.show_labels_button,['O','H']),
                             (panel.show_indices_button,['1','3']),
                             (panel.show_both_button,['O1','H3']),
                             (panel.hide_labels_button,[])]:
        button.click()
        assert [a.GetInput() for a in w.renderer._label_actors] == expected
        assert appearance(w.frame,1).label_mode == 'Global'
        assert w.render_options.labels == 'None'
        assert w.doc.frames[1].atom_appearance == w.frame.atom_appearance
    w.undo_edit()
    assert [a.GetInput() for a in w.renderer._label_actors] == ['O1','H3']
    w.change_frame(1)
    assert [a.GetInput() for a in w.renderer._label_actors] == ['O1','H3']


def test_boundary_face_picking_counts_and_selected_labels_use_original_ids(gui):
    frame = Frame(['Si'], [[0,1,1]], np.eye(3)*5, (True,)*3)
    gui.attach(frame)
    w = gui.window
    gui.select([0]); w.atom_panel.show_indices_button.click()
    assert len(w.renderer.displayed_atoms()) == 2
    assert [a.GetInput() for a in w.renderer._label_actors] == ['1','1']
    assert len(w.renderer.atom_highlights) == 2
    assert w.atom_table.rowCount() == 1 and 'Atoms 1' in w.summary_label.text()
    w.vtk.GetRenderWindow().SetSize(600,400)
    w.refresh_scene(reset_camera=True)
    for source, point in w.renderer.displayed_atoms():
        w.scene.SetWorldPoint(*point,1); w.scene.WorldToDisplay()
        x,y,_ = w.scene.GetDisplayPoint()
        assert source == w.renderer.pick_index(x,y) == 0


def test_new_file_starts_enabled_one_cell_and_existing_file_restores_own_range(gui, tmp_path):
    w = gui.window
    w.documents=[]; w.current_doc=-1; w.files_tree.clear()
    frame = Frame(['Si'], [[1,1,1]], np.eye(3)*5, (True,)*3)
    first=Document(tmp_path/'first.xyz','XYZ',[frame])
    second=Document(tmp_path/'second.xyz','XYZ',[frame.clone()])
    w._attach_loaded_document(first)
    ranges=((-1,2),(0,2),(0,1))
    w._apply_boundary(False,ranges)
    w._attach_loaded_document(second)
    assert w.render_options.boundary_enabled
    assert w.render_options.boundary_bounds == ((0.,1.),)*3
    w._activate_document(0); w.change_frame(0)
    assert not w.render_options.boundary_enabled and w.render_options.boundary_bounds == ranges
    project=tmp_path/'boundaries.lele'
    w.save_project_to(project); w._load_project_path(project)
    assert not w.render_options.boundary_enabled and w.render_options.boundary_bounds == ranges
    w._activate_document(1); w.change_frame(0)
    assert w.render_options.boundary_enabled and w.render_options.boundary_bounds == ((0.,1.),)*3


@pytest.mark.parametrize('symbol,color', [('H','#FFCCCC'),('D','#CCCCFF'),('C','#814929'),
    ('N','#B0BAE6'),('O','#FF0300'),('Si','#1B3BFA'),('Fe','#B57200'),('Og','#4C4C4C')])
def test_vesta_palette_uses_official_rgb_facts_and_element_bonds(symbol,color):
    options=RenderOptions(atom_palette='VESTA')
    assert 'VESTA' in ATOM_PALETTES
    assert element_palette_color(options,symbol) == color
    assert element_palette_color(options,symbol,for_bond=True) == color
    options.element_colors[symbol]='#123456'
    assert element_palette_color(options,symbol) == '#123456'


def test_siesta_curve_includes_moves_when_default_final_structure_has_no_energy(gui,tmp_path):
    from test_siesta_results_v302 import fire_output
    from lele.formats import load_document
    path=tmp_path/'fire.out'; path.write_text(fire_output())
    document=load_document(path)
    w=gui.window
    w.documents=[]; w.current_doc=-1; w.files_tree.clear()
    w._attach_loaded_document(document)
    assert w.frame_index == 3 and w.frame.energy_ev is None
    assert w.energy_curve_action.isEnabled()
    curve=w.show_energy_curve()
    assert [p['energy_ev'] for p in curve.points()] == [-10.1,-10.2]
    assert 'eV' in curve.energy_axes.get_ylabel()
    curve.close()


def test_siesta_energy_only_tree_uses_ev(gui,tmp_path):
    from lele.formats import load_document
    path=tmp_path/'energy.out'
    path.write_text('Welcome to SIESTA\nsiesta: E_KS(eV) = -10.5\n')
    w=gui.window
    w.documents=[]; w.current_doc=-1; w.files_tree.clear()
    w._attach_loaded_document(load_document(path))
    assert w.frame is None and w.energy_curve_action.isEnabled()
    item=w.files_tree.topLevelItem(0).child(0).child(0)
    assert '-10.50000000 eV' in item.text(0)
