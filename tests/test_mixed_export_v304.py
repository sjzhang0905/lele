"""Normal structure → edited mixed site → synchronized UI and explicit export."""
from copy import deepcopy
from unittest.mock import patch

import numpy as np
import pytest

from lele.core import Frame
from lele.formats import load_document,export_frame
from lele.site_occupancy import (change_site_species,site_species,is_disordered,
                                maximum_occupancy_frame)
from test_periodic_fragment_ui_v171 import gui


def normal():
    return Frame(['Fe','Fe','O','H'],[[1,1,1],[3,1,1],[2,2,2],[2,2,3]],
                 np.eye(3)*8,(True,)*3,-12.,{'poscar_groups':[('Fe',2),('O',1),('H',1)],
                    'vasp_fixed_axes':[(True,False,True),(False,True,False),(False,False,False),(True,True,True)]})


@pytest.mark.parametrize('weights,representative',[({'Fe':.6,'Ni':.3},'Fe'),({'Fe':.3,'Ni':.6},'Ni')])
def test_manual_mixed_edit_updates_atoms_coordinates_palette_footer_and_legend(gui,weights,representative):
    from lele.atom_legend import legend_samples
    frame=normal();gui.attach(frame,second_frame=frame.clone());w=gui.window
    old_positions=frame.positions.copy();gui.select([0])
    assert w.apply_atom_species(0,weights)
    assert w.frame.symbols[0]==representative
    row=w.atom_panel._items[0]
    assert '[' not in row.text(0) and '/' not in row.text(0)
    assert w.atom_panel._component_items[0,'Fe'].text(3)==f'{weights["Fe"]*100:.10g}%'
    assert w.atom_panel._component_items[0,'Ni'].text(3)==f'{weights["Ni"]*100:.10g}%'
    assert 'vacancy 0.1' in row.toolTip(0)
    assert 'Ni' in w.atom_panel.target_label.text() and 'vacancy 0.1' in w.atom_panel.target_label.text()
    assert w.atom_panel._item_indices(row)==[0]
    assert w.atom_table.rowCount()==4 and w.atom_table.item(0,0).text()==f'1 {representative}*'
    assert 'Ni' in w.atom_table.item(0,0).toolTip() and 'vacancy 0.1' in w.atom_table.item(0,1).toolTip()
    np.testing.assert_allclose([[float(w.atom_table.item(i,c).text()) for c in (1,2,3)] for i in range(4)],old_positions)
    assert 'Ni' in [w.element_combo.itemText(i) for i in range(w.element_combo.count())]
    assert 'Ni' in {sample['symbol'] for sample in legend_samples(w.renderer)}
    assert 'Ni' in w.summary_label.text() and 'Atoms 4' in w.summary_label.text()
    assert 'unknown' in w.summary_label.text().lower()
    w.change_frame(1)
    assert w.atom_table.item(0,0).text()=='1 Fe' and 'Ni' not in w.atom_panel._items[0].text(0)
    w.change_frame(0)
    assert w.atom_table.item(0,0).text().endswith('*') and (0,'Ni') in w.atom_panel._component_items
    w.undo_edit()
    assert w.frame.energy_ev==-12 and w.atom_table.item(0,0).text()=='1 Fe'
    assert 'Ni' not in w.atom_panel._items[0].text(0) and 'Ni' not in w.atom_table.item(0,0).toolTip()


def test_same_frame_probability_refresh_does_not_keep_stale_atom_labels(gui):
    frame=normal();gui.attach(frame);w=gui.window
    change_site_species(frame,0,{'Fe':.6,'Ni':.3});w.refresh_scene();w._refresh_coordinates()
    assert w.atom_panel._component_items[0,'Ni'].text(3)=='30%'
    change_site_species(frame,0,{'Fe':.7,'Co':.2});w.refresh_scene();w._refresh_coordinates()
    assert w.atom_panel._component_items[0,'Co'].text(3)=='20%' and 'Ni' not in w.atom_panel._groups


def test_maximum_copy_keeps_order_positions_constraints_and_source_model():
    frame=normal()
    change_site_species(frame,0,{'Ni':.6,'Fe':.3})
    change_site_species(frame,1,{'Fe':0.})
    old_info=deepcopy(frame.info);old_positions=frame.positions.copy();old_symbols=list(frame.symbols)
    projected=maximum_occupancy_frame(frame)
    assert projected.symbols==['Ni','O','H'] and not is_disordered(projected)
    np.testing.assert_array_equal(projected.positions,frame.positions[[0,2,3]])
    assert projected.info['vasp_fixed_axes']==[old_info['vasp_fixed_axes'][i] for i in (0,2,3)]
    assert projected.info['poscar_groups']==[('Ni',1),('O',1),('H',1)]
    assert 'site_occupancies' not in projected.info and 'cif_row_order' not in projected.info
    assert frame.info==old_info and frame.symbols==old_symbols
    np.testing.assert_array_equal(frame.positions,old_positions)


def test_ties_use_current_representative_and_vacancy_is_not_an_element():
    frame=normal();change_site_species(frame,0,{'Ni':.7,'Fe':.3})
    change_site_species(frame,0,{'Fe':.5,'Ni':.5})
    change_site_species(frame,1,{'Co':.2})
    projected=maximum_occupancy_frame(frame)
    assert projected.symbols[:2]==['Ni','Co']


@pytest.mark.parametrize('target,filename',[('xyz','out.xyz'),('gjf','out.gjf'),
    ('poscar-direct','POSCAR_direct'),('poscar-cartesian','POSCAR_cartesian')])
def test_confirmed_maximum_exports_roundtrip_and_do_not_rewrite_source(tmp_path,target,filename):
    frame=normal();change_site_species(frame,0,{'Ni':.6,'Fe':.3})
    change_site_species(frame,1,{'Co':.2})
    old_info=deepcopy(frame.info);old_symbols=list(frame.symbols)
    path=tmp_path/filename
    notices=export_frame(frame,path,target,occupancy_policy='maximum')
    restored=load_document(path).frames[0]
    assert restored.symbols==['Ni','Co','O','H'] and not is_disordered(restored)
    np.testing.assert_allclose(restored.positions,frame.positions,atol=1.e-8)
    assert 'highest-occupancy' in ' '.join(notices)
    assert frame.info==old_info and frame.symbols==old_symbols and is_disordered(frame)


def test_confirmed_poscar_omits_full_vacancy_and_retains_selective_dynamics(tmp_path):
    frame=normal();change_site_species(frame,0,{'Ni':.6,'Fe':.3});change_site_species(frame,1,{'Fe':0.})
    path=tmp_path/'POSCAR'
    export_frame(frame,path,'poscar-direct',occupancy_policy='maximum')
    restored=load_document(path).frames[0]
    assert restored.symbols==['Ni','O','H']
    np.testing.assert_array_equal(restored.info['vasp_fixed_axes'],[frame.info['vasp_fixed_axes'][i] for i in (0,2,3)])
    assert len(frame.symbols)==4 and site_species(frame,1)=={'Fe':0.}


def test_cif_keeps_fractions_even_if_caller_supplies_the_maximum_policy(tmp_path):
    frame=normal();change_site_species(frame,0,{'Ni':.6,'Fe':.3})
    path=tmp_path/'out.cif';export_frame(frame,path,'cif',occupancy_policy='maximum')
    restored=load_document(path).frames[0]
    assert restored.info['site_occupancies']==frame.info['site_occupancies']


def test_all_vacant_export_leaves_existing_file_intact(tmp_path):
    frame=normal()
    for i,symbol in enumerate(frame.symbols):change_site_species(frame,i,{symbol:0.})
    path=tmp_path/'POSCAR';path.write_text('previous contents')
    with pytest.raises(ValueError,match='completely vacant'):
        export_frame(frame,path,'poscar-direct',occupancy_policy='maximum')
    assert path.read_text()=='previous contents'


@pytest.mark.parametrize('choice,filename',[('XYZ (.xyz)','out.xyz'),('Gaussian GJF (.gjf)','out.gjf'),
    ('POSCAR Direct (POSCAR)','POSCAR_direct'),('POSCAR Cartesian (POSCAR)','POSCAR_cartesian')])
def test_gui_confirmation_exports_maximum_elements_only_in_copy(gui,tmp_path,choice,filename):
    gui.attach(normal());w=gui.window
    assert w.apply_atom_species(0,{'Ni':.6,'Fe':.3})
    source=w.frame;before=deepcopy(source.info);undo_count=len(w.undo_stack)
    path=tmp_path/filename
    with patch('lele.app.QInputDialog.getItem',return_value=(choice,True)), \
         patch('lele.structure_edit_dialogs.confirm_maximum_occupancy_export',return_value=True) as confirm, \
         patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(path),'')), \
         patch('lele.app.QMessageBox.warning') as warning:
        w.export_dialog()
    confirm.assert_called_once_with(w);warning.assert_not_called()
    assert load_document(path).frames[0].symbols==['Ni','Fe','O','H']
    assert w.frame is source and w.frame.info==before and len(w.undo_stack)==undo_count
    assert is_disordered(w.frame) and w.atom_table.item(0,0).text()=='1 Ni*'


def test_gui_cancel_never_opens_file_picker_or_touches_an_existing_destination(gui,tmp_path):
    gui.attach(normal());w=gui.window;w.apply_atom_species(0,{'Fe':.6,'Ni':.3})
    path=tmp_path/'POSCAR';path.write_text('previous contents')
    source=w.frame
    with patch('lele.app.QInputDialog.getItem',return_value=('POSCAR Direct (POSCAR)',True)), \
         patch('lele.structure_edit_dialogs.confirm_maximum_occupancy_export',return_value=False), \
         patch('lele.app.QFileDialog.getSaveFileName') as picker:
        w.export_dialog()
    picker.assert_not_called()
    assert path.read_text()=='previous contents' and w.frame is source


@pytest.mark.parametrize('mixed,cif',[(True,True),(False,False)])
def test_cif_and_ordered_exports_do_not_ask_for_occupancy_conversion(gui,tmp_path,mixed,cif):
    gui.attach(normal());w=gui.window
    if mixed:w.apply_atom_species(0,{'Fe':.6,'Ni':.3})
    path=tmp_path/('out.cif' if cif else 'out.xyz')
    choice='CIF (.cif)' if cif else 'XYZ (.xyz)'
    with patch('lele.app.QInputDialog.getItem',return_value=(choice,True)), \
         patch('lele.structure_edit_dialogs.confirm_maximum_occupancy_export') as confirm, \
         patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):
        w.export_dialog()
    confirm.assert_not_called();assert path.exists()


@pytest.mark.parametrize('choice',['Use highest-occupancy element','Cancel','close'])
def test_actual_prompt_buttons_cancel_default_and_close_behavior(gui,choice):
    from PySide6.QtWidgets import QMessageBox
    from lele.structure_edit_dialogs import confirm_maximum_occupancy_export
    def choose(message):
        assert {button.text() for button in message.buttons()}=={'Use highest-occupancy element','Cancel'}
        assert message.defaultButton().text()=='Cancel' and message.escapeButton().text()=='Cancel'
        assert 'Completely vacant' in message.text() and 'remain unchanged' in message.text()
        if choice=='close':message.close()
        else:next(button for button in message.buttons() if button.text()==choice).click()
    with patch.object(QMessageBox,'exec',choose):
        assert confirm_maximum_occupancy_export(gui.window) is (choice=='Use highest-occupancy element')


def test_normal_poscar_right_click_edit_cif_export_and_project_restore(gui,tmp_path):
    from PySide6.QtWidgets import QDialogButtonBox
    from lele.structure_edit_dialogs import AtomIndexDialog
    path=tmp_path/'POSCAR';export_frame(normal(),path,'poscar-direct')
    w=gui.window;w.documents=[];w.current_doc=-1;w.files_tree.clear()
    w._attach_loaded_document(load_document(path));original=w.frame.positions.copy()
    def accept(dialog):
        table=dialog.species.table
        table.item(0,1).setText('.3');table.item(1,0).setText('Ni');table.item(1,1).setText('.6')
        dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        return dialog.result()
    w.vtk.resize(600,400);w.vtk.GetRenderWindow().SetSize(600,400)
    with patch.object(w.renderer,'pick_index',return_value=0),patch.object(AtomIndexDialog,'exec',accept):
        w._atom_context_from_canvas(40,40)
    assert w.atom_table.item(0,0).text()=='1 Ni*'
    assert site_species(w.frame,0)=={'Fe':.3,'Ni':.6}
    out=tmp_path/'edited.cif'
    with patch('lele.app.QInputDialog.getItem',return_value=('CIF (.cif)',True)), \
         patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(out),'')):
        w.export_dialog()
    reread=load_document(out).frames[0]
    assert reread.info['site_occupancies']==w.frame.info['site_occupancies']
    np.testing.assert_allclose(reread.positions,original,atol=1.e-12)
    project=tmp_path/'mixed.lele';w.save_project_to(project);w._load_project_path(project)
    assert w.atom_table.item(0,0).text()=='1 Ni*'
    assert w.atom_panel._component_items[0,'Fe'].text(3)=='30%'
    assert w.atom_panel._component_items[0,'Ni'].text(3)=='60%'
    assert 'Ni' in w.summary_label.text()
    np.testing.assert_array_equal(w.frame.positions,original)
