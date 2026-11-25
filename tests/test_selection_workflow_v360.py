"""Live third-column selection, named fragments and scientific atom identity."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from lele.core import Document,Frame
from lele.saved_fragments import fragments
from test_periodic_fragment_ui_v171 import gui


def frame():
    return Frame(['C','O','H','N','H','C'],
        [[0.,0.,0.],[1.,2.,3.],[2.,1.,0.],[3.,2.,1.],[4.,0.,2.],[5.,1.,2.]],
        [[8.,0.,0.],[1.,10.,0.],[0.,2.,12.]],(True,True,True),-10.,
        {'fixed_axes':[[True,False,False],[False]*3,[None]*3,[True]*3,[False]*3,[False]*3],
         'fixed_axes_basis':'cartesian'})


def cell(model,row,header):
    return model.data(model.index(row,model.headers.index(header)))


def assert_coordinates(window):
    assert window.atom_table.rowCount()==len(window.frame.symbols)
    for row,(symbol,point) in enumerate(zip(window.frame.symbols,window.frame.positions)):
        assert window.atom_table.item(row,0).text().startswith(f'{row+1} {symbol}')
        np.testing.assert_allclose([float(window.atom_table.item(row,c).text()) for c in (1,2,3)],point,atol=1e-6)


def test_three_bottom_regions_and_compact_fragment_buttons(gui):
    w=gui.window;w.resize(1600,900);w.show();gui.app.processEvents()
    assert w.lower_splitter.count()==3
    assert [w.lower_splitter.widget(i) for i in range(3)]==[
        w.bottom_control_tabs,w.tabs,w.selection_tabs]
    assert [w.selection_tabs.tabText(i) for i in range(3)]==['Current selection','Fragment','Atoms selection']
    w.selection_tabs.setCurrentWidget(w.fragment_panel);gui.app.processEvents()
    for button in (w.fragment_panel.save_button,w.fragment_panel.delete_button,
                   w.fragment_panel.front_button,w.fragment_panel.back_button):
        assert button.width()<=button.sizeHint().width()
        assert button.width()<w.fragment_panel.width()
    w.hide()


def test_selection_reacts_to_coordinates_occupancy_fixed_flags_and_undo(gui):
    gui.attach(frame());w=gui.window;gui.select([3,1,0])
    model=w.selection_panel.model
    assert w.selection_panel.summary_label.text()=='Atoms 1, 2, 4'
    assert [cell(model,row,'Index') for row in range(3)]==['1','2','4']
    assert [cell(model,0,'Free '+axis) for axis in 'XYZ']==['F','T','T']
    assert model.headerData(model.headers.index('Free X'),Qt.Orientation.Horizontal,
                            Qt.ItemDataRole.ToolTipRole).endswith('cartesian.')
    w.atom_table.item(1,1).setText('6.25')
    assert cell(model,1,'Cartesian X')=='6.25000000'
    expected=w.frame.positions[1]@np.linalg.inv(w.frame.cell)
    np.testing.assert_allclose([float(cell(model,1,'Direct '+axis)) for axis in 'XYZ'],expected,atol=1e-8)
    assert w.apply_atom_species(1,[('O',.6),('N',.4)])
    assert model.rowCount()==4
    assert [cell(model,row,'Element') for row in range(4)]==['C','O','N','N']
    assert [cell(model,row,'Occ. %') for row in (1,2)]==['60','40']
    w.undo_edit()
    assert model.rowCount()==3 and cell(model,1,'Cartesian X')=='6.25000000'
    w.undo_edit()
    assert cell(model,1,'Cartesian X')=='1.00000000'
    gui.select([2])
    assert [cell(model,0,'Free '+axis) for axis in 'XYZ']==['—']*3
    w.clear_selection();assert model.rowCount()==0
    assert w.selection_panel.summary_label.text()=='No atoms selected'


def test_fragment_buttons_save_click_move_both_ways_and_two_undos(gui):
    gui.attach(frame());w=gui.window;original=w.frame.clone();gui.select([4,1,3])
    panel=w.fragment_panel
    panel.save_button.click()
    assert fragments(w.frame)==[{'name':'fragment1','indices':[1,3,4]}]
    assert panel.current_name()=='fragment1'
    # Exercise the actual list click rather than its private callback.
    w.show();w.selection_tabs.setCurrentWidget(panel);gui.app.processEvents()
    gui.select([0]);item=panel.list_widget.item(0)
    QTest.mouseClick(panel.list_widget.viewport(),Qt.MouseButton.LeftButton,
                    pos=panel.list_widget.visualItemRect(item).center())
    assert w.selection==[1,3,4]
    baseline_undo=len(w.undo_stack)
    panel.front_button.click()
    first=[1,3,4,0,2,5]
    np.testing.assert_array_equal(w.frame.positions,original.positions[first])
    assert w.selection==[0,1,2]
    assert fragments(w.frame)[0]['indices']==[0,1,2]
    assert w.selection_panel.summary_label.text()=='Atoms 1-3'
    assert_coordinates(w)
    panel.back_button.click()
    last=[0,2,5,1,3,4]
    np.testing.assert_array_equal(w.frame.positions,original.positions[last])
    assert w.selection==[3,4,5]
    assert w.selection_panel.summary_label.text()=='Atoms 4-6'
    assert w.frame.energy_ev==-10.
    assert_coordinates(w)
    assert len(w.undo_stack)==baseline_undo+2
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions,original.positions[first])
    assert w.selection==[0,1,2]
    assert fragments(w.frame)[0]['indices']==[0,1,2]
    w.undo_edit()
    np.testing.assert_array_equal(w.frame.positions,original.positions)
    assert w.selection==[1,3,4]
    assert fragments(w.frame)[0]['indices']==[1,3,4]
    assert_coordinates(w)
    w.hide()


def test_delete_fragment_preserves_atoms_and_stale_name_is_harmless(gui):
    gui.attach(frame());w=gui.window;gui.select([0,2]);w.save_named_fragment()
    original=w.frame.clone();before=len(w.undo_stack)
    w.fragment_panel.delete_button.click()
    assert fragments(w.frame)==[] and len(w.undo_stack)==before+1
    np.testing.assert_array_equal(w.frame.positions,original.positions)
    assert w.selection==[0,2]
    w.delete_named_fragment('fragment1')
    assert len(w.undo_stack)==before+1
    w.undo_edit()
    assert fragments(w.frame)==[{'name':'fragment1','indices':[0,2]}]
    assert w.fragment_panel.list_widget.count()==1


def test_fragment_and_selection_are_isolated_when_switching_documents_and_frames(gui):
    first=frame();gui.attach(first,second_frame=first.clone());w=gui.window
    gui.select([1,3]);w.save_named_fragment()
    w.change_frame(1)
    assert fragments(w.frame)==[] and w.fragment_panel.list_widget.count()==0
    gui.select([4]);w.save_named_fragment()
    assert fragments(w.frame)==[{'name':'fragment1','indices':[4]}]
    second=Document(Path('other.xyz'),'XYZ',[Frame(['He'],[[0.,0.,0.]])])
    w._attach_loaded_document(second)
    assert w.current_doc==1 and w.selection==[]
    assert w.fragment_panel.list_widget.count()==0 and w.selection_panel.model.rowCount()==0
    assert 'Direct X' not in w.selection_panel.model.headers
    assert 'Free X' not in w.selection_panel.model.headers
    w.change_frame(0,switch_doc=0)
    assert fragments(w.frame)==[{'name':'fragment1','indices':[1,3]}]
    assert w.fragment_panel.list_widget.count()==1 and w.selection==[]
    w.select_named_fragment([1,3])
    assert w.selection_panel.summary_label.text()=='Atoms 2, 4'
    w.change_frame(1)
    assert fragments(w.frame)==[{'name':'fragment1','indices':[4]}]


def test_fragment_project_roundtrip_restores_order_selection_and_fixed_state(gui,tmp_path):
    gui.attach(frame());w=gui.window;gui.select([1,3,4]);w.save_named_fragment()
    w.move_named_fragment('fragment1','front');expected=w.frame.clone()
    path=tmp_path/'selection.lele'
    assert w.save_project_to(path)
    with patch('lele.project_actions.QMessageBox.warning',side_effect=AssertionError('Unexpected project failure')):
        assert w._load_project_path(path)
    np.testing.assert_array_equal(w.frame.positions,expected.positions)
    assert fragments(w.frame)==fragments(expected)
    assert w.selection==[0,1,2]
    assert w.selection_panel.summary_label.text()=='Atoms 1-3'
    assert w.fragment_panel.list_widget.count()==1
    assert [cell(w.selection_panel.model,0,'Free '+axis) for axis in 'XYZ']==['T']*3
    assert_coordinates(w)


def test_nmr_atom_navigation_follows_reordered_identity_but_rejects_edited_geometry(gui):
    from lele.nmr import NMRNucleus,NMRResult
    gui.attach(frame());w=gui.window;reference=w.frame.clone()
    result=NMRResult('Gaussian','synthetic',1,[NMRNucleus(2,'O',20.)],
                     frame_index=0,reference=reference)
    w.doc.nmr_results=[result];gui.select([1,3]);w.save_named_fragment()
    w.move_named_fragment('fragment1','back')
    w._locate_nmr_atom(w.doc,0,2)
    assert w.selection==[4]
    assert w.selection_panel.summary_label.text()=='Atoms 5'
    assert w.atom_panel._items[4].isSelected()
    assert result.reference is reference and result.nuclei[0].number==2
    w.atom_table.item(4,1).setText('99')
    w.clear_selection();w._locate_nmr_atom(w.doc,0,2)
    assert w.selection==[]
    assert 'edited' in w.statusBar().currentMessage()


def test_results_only_document_clears_selection_and_disables_fragment_mutations(gui):
    from lele.nmr import NMRNucleus,NMRResult
    gui.attach(frame());w=gui.window;gui.select([0,1]);w.save_named_fragment()
    result=NMRResult('CP2K','SHIFT',1,[NMRNucleus(1,'C',50.)])
    w._attach_loaded_document(Document(Path('results.out'),'Results only',[],nmr_results=[result]))
    assert w.frame is None and w.selection_panel.model.rowCount()==0
    assert w.fragment_panel.list_widget.count()==0
    assert not w.fragment_panel.save_button.isEnabled()
    assert not w.apply_coordinates_action.isEnabled()
    w.change_frame(0,switch_doc=0)
    assert w.fragment_panel.list_widget.count()==1


def test_saved_fragment_mutations_are_disabled_for_frequency_reference(gui):
    gui.attach_vibrations();w=gui.window;w.select_vibration(0,0,0,autoplay=False)
    gui.select([0])
    assert not w.fragment_panel.save_button.isEnabled()
    assert not w.apply_coordinates_action.isEnabled()
    old=len(w.undo_stack);w.save_named_fragment()
    assert len(w.undo_stack)==old and fragments(w.frame)==[]
