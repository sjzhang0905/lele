"""End-to-end selections, moved controls, NMR plots and portable projects."""
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from PySide6.QtCore import Qt
from lele.core import Frame,Document
from lele.atom_appearance import appearance,AtomAppearance
from test_periodic_fragment_ui_v171 import gui


def test_selected_display_modes_undo_global_fallback_and_project(gui,tmp_path):
    frame=Frame(['O','H','H'],[[0,0,0],[.96,0,0],[-.24,.93,0]])
    gui.attach(frame,second_frame=frame.clone());w=gui.window;gui.select([0,2])
    panel=w.atom_panel
    panel.representation_combo.setCurrentIndex(panel.representation_combo.findData('Space filling'))
    assert [appearance(w.frame,i).representation for i in range(3)]==['Space filling','Global','Space filling']
    assert w.render_options.style=='Ball and stick'
    assert w.doc.frames[1].atom_appearance==w.frame.atom_appearance
    # Exactly the H2 endpoint's half-bond remains; both other endpoints are space filling.
    with patch.object(w.renderer,'_tube_segments') as tubes:
        w.renderer._bonds(w.frame)
        segments=[s for call in tubes.call_args_list for s in call.args[0]]
    assert len(segments)==1
    np.testing.assert_allclose(segments[0][0],[.48,0,0])
    np.testing.assert_allclose(segments[0][1],[.96,0,0])
    assert w.renderer._atom_radius('O','Space filling')>w.renderer._atom_radius('O','Ball and stick')
    project=tmp_path/'styles.lele';w.save_project_to(project);w._load_project_path(project)
    assert appearance(w.frame,0).representation=='Space filling'
    gui.select([0]);w.atom_panel.representation_combo.setCurrentIndex(w.atom_panel.representation_combo.findData('Sticks'))
    assert w.renderer._atom_style(w.frame,0)=='Sticks'
    assert w.render_options.bond_scale <= w.renderer._atom_radius('O','Sticks') < w.renderer._atom_radius('O','Ball and stick')
    w.undo_edit();assert appearance(w.frame,0).representation=='Space filling'
    w.atom_panel.representation_combo.setCurrentIndex(0)
    assert appearance(w.frame,0).representation=='Global'
    assert appearance(w.frame,2).representation=='Space filling'


def test_atom_file_order_collapse_and_coordinate_double_click(gui):
    f=Frame(['N','O','H','C','O'],[[i*2,0,0] for i in range(5)])
    gui.attach(f);w=gui.window;p=w.atom_panel
    assert list(p._groups)==['N','O','H','C']
    assert not any(g.isExpanded() for g in p._groups.values())
    p.tree.setCurrentItem(p._groups['O'])
    assert not p._groups['O'].isExpanded()
    w.atom_table.itemDoubleClicked.emit(w.atom_table.item(4,0))
    assert p._groups['O'].isExpanded() and w.selection==[4]
    assert p.tree.currentItem() is p._items[4]
    assert p.selected_indices()==[4]
    assert w.sidebar_tabs.currentWidget() is p
    w.refresh_scene();assert p._groups['O'].isExpanded()
    gui.attach(f.clone());assert not any(g.isExpanded() for g in p._groups.values())


def test_mixed_cif_element_order_uses_original_component_rows(gui):
    f=Frame(['Sn','O'],[[0,0,0],[2,0,0]],info={
        'site_occupancies':[{'Sn':.6,'Mn':.4},{'O':1.}],
        'cif_row_order':[(0,'Mn'),(1,'O'),(0,'Sn')]})
    gui.attach(f)
    assert list(gui.window.atom_panel._groups)==['Mn','O','Sn']


def test_moved_panels_and_menu_windows_work(gui):
    w=gui.window
    assert [w.bottom_control_tabs.tabText(i) for i in range(w.bottom_control_tabs.count())]==['Axes','Labels','Field','Boundary']
    sidebar=[w.sidebar_tabs.tabText(i) for i in range(w.sidebar_tabs.count())]
    assert not set(sidebar)&{'Axes','Labels','Field','Boundary','Crystal','Dipole'}
    assert w.lower_splitter.widget(1) is w.tabs
    for action,dialog in ((w.crystal_action,w.crystal_window),(w.dipole_action,w.dipole_window)):
        action.trigger();assert dialog.isVisible()
        dialog.close();assert not dialog.isVisible()
        action.trigger();assert dialog.isVisible();dialog.close()


def test_nmr_plot_table_reference_exports_sorting_and_atom_link(gui,tmp_path):
    from lele.nmr_input import gaussian
    from test_nmr_v350 import GAUSSIAN
    gui.attach(Frame(['O','H','H'],[[0,0,0],[.96,0,0],[-.24,.93,0]]))
    w=gui.window;r=gaussian(GAUSSIAN.splitlines())[0]
    r.frame_index=0;r.reference=w.frame.clone();w.doc.nmr_results=[r];w.refresh_scene()
    assert w.nmr_action.isEnabled()
    dialog=w.show_nmr_results();gui.addCleanup(dialog.close)
    assert dialog.element.currentText()=='H' and dialog.table.rowCount()==2
    dialog.axis.setCurrentIndex(1)
    assert dialog._curve is None and not dialog.export_image.isEnabled()
    dialog.reference.setText('31');dialog.set_reference()
    np.testing.assert_array_equal(dialog._curve[2],[3,5])
    assert dialog.figure.axes[0].xaxis_inverted()
    dialog.table.sortItems(2,Qt.SortOrder.AscendingOrder)
    dialog.table.setCurrentCell(0,0)
    assert dialog.selected_nucleus().number==3
    dialog.request_atom(dialog.table.item(0,0))
    assert w.selection==[2] and w.atom_panel._groups['H'].isExpanded()
    dialog.element.setCurrentText('O');assert dialog.reference.text()==''
    dialog.axis.setCurrentIndex(0)
    assert dialog.table.rowCount()==1 and not dialog.figure.axes[0].xaxis_inverted()
    for suffix in ('.png','.svg'):
        path=tmp_path/('plot'+suffix)
        with patch('lele.nmr_dialog.QFileDialog.getSaveFileName',return_value=(str(path),'')):dialog.save_image()
        assert path.stat().st_size>1000
    table=tmp_path/'table.csv'
    with patch('lele.nmr_dialog.QFileDialog.getSaveFileName',return_value=(str(table),'')):dialog.save_table()
    assert len(table.read_text(encoding='utf-8-sig').splitlines())==4
    # Shift references are per element and survive a project round trip.
    project=tmp_path/'nmr.lele';w.save_project_to(project);w._load_project_path(project)
    assert w.doc.nmr_results[0].reference_shieldings=={'H':31}


def test_nmr_results_only_button_and_no_stale_geometry_link(gui,tmp_path):
    from lele.formats import load_document
    from test_nmr_v350 import CP2K
    path=tmp_path/'shift.data';path.write_text(CP2K)
    w=gui.window;w.documents=[];w.current_doc=-1;w.files_tree.clear()
    doc=load_document(path);w._attach_loaded_document(doc)
    assert w.frame is None and w.results_nmr_button.isEnabled()
    assert 'NMR:' in w.results_only_info.toPlainText()
    dialog=w.show_nmr_results();gui.addCleanup(dialog.close)
    dialog.table.setCurrentCell(0,0);dialog.request_atom(dialog.table.item(0,0))
    assert 'No matching source structure' in w.statusBar().currentMessage()
