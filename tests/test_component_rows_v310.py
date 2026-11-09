"""Element rows and occupancy percentages are aliases of one physical site."""
from unittest.mock import patch

import numpy as np
import pytest

from lele.atom_appearance import appearance
from lele.atom_panel import COMPONENT_ROLE
from lele.core import Frame
from lele.formats import export_frame,load_document
from lele.site_occupancy import change_site_species,site_species
from test_periodic_fragment_ui_v171 import gui


def normal(existing_sn=False):
    return Frame(['Mn','Mn','Sn' if existing_sn else 'O'],[[1.1,1,1],[3,2,1],[3,4,1]],
                 np.eye(3)*8,(True,)*3)


def mixed(gui,weights=None,existing_sn=False):
    gui.attach(normal(existing_sn));w=gui.window
    assert w.apply_atom_species(0,weights or {'Mn':.5,'Sn':.5})
    return w,w.atom_panel


def test_normal_rows_have_a_separate_full_occupancy_column(gui):
    gui.attach(normal());p=gui.window.atom_panel
    assert p.tree.columnCount()==4 and p.tree.headerItem().text(3)=='Occupancy %'
    assert len(p._component_items)==3
    assert all(item.text(3)=='100%' for item in p._component_items.values())
    assert all(item.text(3)=='' for item in p._groups.values())


def test_new_sn_group_lists_same_site_as_mn_with_50_percent_each(gui):
    w,p=mixed(gui)
    mn=p._component_items[0,'Mn'];sn=p._component_items[0,'Sn']
    assert set(p._groups)=={'Mn','O','Sn'}
    assert p._groups['Mn'].childCount()==2 and p._groups['Sn'].childCount()==1
    assert mn.text(0)=='Mn1  ·  #1' and sn.text(0)=='Sn1  ·  #1'
    assert mn.text(3)==sn.text(3)=='50%'
    assert p._component_items[1,'Mn'].text(3)==p._component_items[2,'O'].text(3)=='100%'
    assert not any('[' in item.text(0) or '/' in item.text(0) for item in p._component_items.values())
    assert p._item_indices(mn)==p._item_indices(sn)==[0]
    assert mn.toolTip(0).split('Cartesian / Å: ')[1].split('\n')[0]==sn.toolTip(0).split('Cartesian / Å: ')[1].split('\n')[0]
    assert '1.10000000, 1.00000000, 1.00000000' in sn.toolTip(0)
    assert len(w.frame.symbols)==3 and len(p._component_items)==4
    assert w.atom_table.rowCount()==3 and 'Atoms 3' in w.summary_label.text()
    np.testing.assert_array_equal(w.frame.positions,normal().positions)


def test_component_rows_also_appear_for_an_already_mixed_frame(gui):
    f=normal();f.info['site_occupancies']=[{'Mn':.5,'Sn':.5},{'Mn':1.},{'O':1.}]
    assert 'Sn' not in f.symbols
    gui.attach(f)
    assert gui.window.atom_panel._component_items[0,'Sn'].text(3)=='50%'


def test_new_component_joins_an_existing_sn_group_without_duplicate_rows(gui):
    w,p=mixed(gui,existing_sn=True)
    assert p._groups['Sn'].childCount()==2
    assert p._component_items[0,'Sn'].text(3)=='50%'
    assert p._component_items[2,'Sn'].text(3)=='100%'
    assert p._component_items[2,'Sn'].text(0)=='Sn2  ·  #3'
    assert len(p._component_items)==4 and len(w.frame.symbols)==3


def test_fraction_only_refresh_updates_percentages_without_rebuilding_rows(gui):
    w,p=mixed(gui);old=p._component_items[0,'Sn']
    change_site_species(w.frame,0,{'Mn':.75,'Sn':.25});w.refresh_scene()
    assert p._component_items[0,'Sn'] is old
    assert old.text(3)=='25%' and p._component_items[0,'Mn'].text(3)=='75%'


def test_component_removal_and_undo_refresh_groups_and_percentages(gui):
    w,p=mixed(gui)
    assert w.apply_atom_species(0,{'Mn':1.})
    assert 'Sn' not in p._groups and p._component_items[0,'Mn'].text(3)=='100%'
    w.undo_edit()
    assert p._component_items[0,'Sn'].text(3)==p._component_items[0,'Mn'].text(3)=='50%'


@pytest.mark.parametrize('fraction,text',[(.125,'12.5%'),(.005,'0.5%'),(1/3,'33.33333333%'),(0.,'0%')])
def test_percentage_formatting_uses_fraction_times_100(gui,fraction,text):
    w,p=mixed(gui,{'Mn':fraction})
    assert p._component_items[0,'Mn'].text(3)==text
    assert site_species(w.frame,0)=={'Mn':fraction}


def test_selecting_sn_selects_one_shared_coordinate_and_keeps_sn_focus(gui):
    from PySide6.QtCore import Qt
    w,p=mixed(gui)
    p._groups['Sn'].setExpanded(True)
    p.tree.setCurrentItem(p._component_items[0,'Sn'])
    assert w.selection==p.selected_indices()==[0]
    assert p.tree.currentItem().data(0,COMPONENT_ROLE)=='Sn'
    assert p._component_items[0,'Sn'].isSelected() and p._component_items[0,'Mn'].isSelected()
    assert '· Sn' in p.target_label.text()
    assert {index.row() for index in w.atom_table.selectionModel().selectedRows()}=={0}
    assert len(w.renderer.atom_highlights)==1


def test_selecting_sn_group_deduplicates_sites_and_does_not_auto_expand(gui):
    w,p=mixed(gui,existing_sn=True)
    parent=p._groups['Sn'];assert not parent.isExpanded()
    p.tree.setCurrentItem(parent)
    assert w.selection==[0,2] and p.selected_indices()==[0,2]
    assert not parent.isExpanded()


def test_shared_site_visibility_and_transparency_keep_component_rows_in_sync(gui):
    from PySide6.QtCore import Qt
    w,p=mixed(gui)
    p._component_items[0,'Sn'].setCheckState(0,Qt.CheckState.Unchecked)
    assert not appearance(w.frame,0).visible
    assert p._component_items[0,'Mn'].checkState(0)==p._component_items[0,'Sn'].checkState(0)==Qt.CheckState.Unchecked
    assert p._component_items[1,'Mn'].checkState(0)==Qt.CheckState.Checked
    w.undo_edit()
    gui.select([0]);p.transparency_spin.setValue(40)
    for symbol in ('Mn','Sn'):
        assert p._component_items[0,symbol].text(2)=='40'
        assert p._component_items[0,symbol].text(3)=='50%'


def test_components_use_their_own_palette_colour_and_source_overrides(gui):
    w,p=mixed(gui)
    w._set_option('atom_palette','VESTA')
    assert p._component_items[0,'Mn'].text(1)==w.renderer._display_color('Mn').lower()
    assert p._component_items[0,'Sn'].text(1)==w.renderer._display_color('Sn').lower()
    assert p._component_items[0,'Sn'].text(1)!=p._component_items[0,'Mn'].text(1)
    w._change_atom_appearance([0],{'color':'#123456'})
    assert p._component_items[0,'Mn'].text(1)==p._component_items[0,'Sn'].text(1)=='#123456'
    w._reset_atom_appearance([0])
    assert p._component_items[0,'Sn'].text(1)==w.renderer._display_color('Sn').lower()


def test_sn_colour_dialog_starts_from_sn_palette_colour(gui):
    from PySide6.QtGui import QColor
    w,p=mixed(gui)
    p._groups['Sn'].setExpanded(True);p.tree.setCurrentItem(p._component_items[0,'Sn'])
    with patch('lele.atom_panel.QColorDialog.getColor',return_value=QColor()) as dialog:
        p.choose_color()
    assert dialog.call_args.args[0].name()==w.renderer._display_color('Sn').lower()
    assert appearance(w.frame,0).color is None


def test_partial_vacancy_stays_implicit_without_a_fake_element_group(gui):
    w,p=mixed(gui,{'Mn':.5,'Sn':.3})
    gui.select([0])
    assert p._component_items[0,'Mn'].text(3)=='50%'
    assert p._component_items[0,'Sn'].text(3)=='30%'
    assert set(p._groups)=={'Mn','O','Sn'}
    assert 'vacancy 0.2' in p.target_label.text()


def test_cif_and_project_reopen_restore_component_rows_and_shared_coordinates(gui,tmp_path):
    w,p=mixed(gui);original=w.frame.positions.copy()
    path=tmp_path/'mixed.cif';export_frame(w.frame,path,'cif')
    restored=load_document(path).frames[0]
    assert site_species(restored,0)=={'Mn':.5,'Sn':.5}
    gui.attach(restored);w=gui.window
    assert w.atom_panel._component_items[0,'Sn'].text(3)=='50%'
    project=tmp_path/'mixed.lele';w.save_project_to(project);w._load_project_path(project)
    assert w.atom_panel._component_items[0,'Sn'].text(3)==w.atom_panel._component_items[0,'Mn'].text(3)=='50%'
    np.testing.assert_allclose(w.frame.positions,original,atol=1.e-12)


def test_maximum_occupancy_export_does_not_remove_the_sn_component_from_the_ui(gui,tmp_path):
    w,p=mixed(gui)
    path=tmp_path/'POSCAR';export_frame(w.frame,path,'poscar-direct',occupancy_policy='maximum')
    assert load_document(path).frames[0].symbols==['Mn','Mn','O']
    assert p._component_items[0,'Sn'].text(3)=='50%' and site_species(w.frame,0)=={'Mn':.5,'Sn':.5}


def test_sn_selection_delete_and_undo_operate_on_the_shared_site_once(gui):
    w,p=mixed(gui)
    p._groups['Sn'].setExpanded(True);p.tree.setCurrentItem(p._component_items[0,'Sn'])
    w.delete_selected_atoms()
    assert len(w.frame.symbols)==2 and 'Sn' not in p._groups
    w.undo_edit()
    assert len(w.frame.symbols)==3 and p._component_items[0,'Sn'].text(3)=='50%'
    np.testing.assert_array_equal(w.frame.positions,normal().positions)


def test_empty_frame_clears_every_component_and_group(gui):
    w,p=mixed(gui);p.set_frame(None)
    assert not p._component_items and not p._groups and not p._items
    assert not p.editor.isEnabled() and p.tree.columnCount()==4
