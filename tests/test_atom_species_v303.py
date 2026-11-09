"""Single-site chemistry edits, vacancies, physical metadata and exports."""
from unittest.mock import patch

import numpy as np
import pytest

from lele.core import Frame,Volume
from lele.site_occupancy import (change_site_species,validate_site_species,site_species,
                                composition,is_disordered)
from lele.formats import export_frame,load_document
from test_periodic_fragment_ui_v171 import gui


def source():
    return Frame(['Fe','Fe','O'], [[1,1,1],[3,1,1],[2,2,2]],np.eye(3)*8,(True,)*3,-12.,
                 {'poscar_groups':[('Fe',2),('O',1)],'optimization_converged':True,
                  'energy_source':'original result','converter_mult':3,
                  'qe_forces_ev_ang':np.ones((3,3))})


def test_edit_single_site_retains_positions_ids_other_sites_and_clone_snapshot():
    frame=source();old=frame.clone();other=frame.clone()
    assert change_site_species(frame,0,[('co','0.6'),('Ni','0.3')])
    assert site_species(frame,0)=={'Co':.6,'Ni':.3}
    assert site_species(frame,1)=={'Fe':1.}
    assert frame.symbols==['Co','Fe','O']
    assert composition(frame)=='Co0.6FeNi0.3O'
    assert is_disordered(frame)
    np.testing.assert_array_equal(frame.positions,old.positions)
    assert frame.info['poscar_groups']==[('Co',1),('Fe',1),('O',1)]
    assert other.info==old.info and other.symbols==old.symbols
    assert frame.energy_ev is None
    for key in ('energy_source','optimization_converged','converter_mult','qe_forces_ev_ang'):
        assert key not in frame.info


def test_only_probability_changes_also_invalidate_calculated_values():
    frame=source()
    assert change_site_species(frame,0,{'Fe':.6,'Ni':.4})
    assert frame.symbols[0]=='Fe' and frame.energy_ev is None
    assert frame.info['composition_edited']


def test_representative_uses_highest_probability_with_stable_ties():
    frame=source()
    change_site_species(frame,0,{'Ni':.7,'Fe':.3})
    assert frame.symbols[0]=='Ni'
    change_site_species(frame,0,{'Fe':.5,'Ni':.5})
    assert frame.symbols[0]=='Ni'


@pytest.mark.parametrize('rows',[[('Fe',.6),('Ni',.5)], [('Fe',-1)], [('Fake',.5)],
    [('Fe','nan')],[('Fe','inf')],[('Fe','x')],[('Fe',1.1)],[('Fe',.5),('fe',.3)],
    [('Fe','')],[],[('',.5)],[('Fe','1e-99999999')],
    [('Fe','0.5000000000000001'),('Ni','0.5')]])
def test_invalid_species_are_rejected_before_any_mutation(rows):
    frame=source();old=frame.clone()
    with pytest.raises(ValueError):change_site_species(frame,0,rows)
    assert frame.symbols==old.symbols and frame.info==old.info and frame.energy_ev==old.energy_ev


def test_exact_decimal_total_and_zero_components():
    assert validate_site_species([('Fe','.1'),('Ni','.2'),('Co','.7')])=={'Fe':.1,'Ni':.2,'Co':.7}
    assert validate_site_species({'Fe':1.,'Ni':0.})=={'Fe':1.}
    assert validate_site_species({'Fe':0.})=={'Fe':0.}


def test_noop_preserves_original_energy_and_does_not_add_occupancy_metadata():
    frame=source()
    assert not change_site_species(frame,0,{'Fe':1.})
    assert frame.energy_ev==-12 and 'site_occupancies' not in frame.info


@pytest.mark.parametrize('weights',[(.6,.3),(1/3,2/3),(0.,0.)])
def test_edited_mixed_or_vacant_sites_roundtrip_cif(tmp_path,weights):
    frame=source()
    change_site_species(frame,0,dict(zip(('Co','Ni'),weights)))
    path=tmp_path/'edited.cif';export_frame(frame,path,'cif')
    restored=load_document(path).frames[0]
    assert restored.info['site_occupancies']==frame.info['site_occupancies']
    assert len(restored.symbols)==3
    np.testing.assert_allclose(restored.positions,frame.positions,atol=1.e-12)


@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian','xyz','gjf'])
def test_non_cif_export_keeps_existing_file_and_never_picks_the_majority(tmp_path,target):
    frame=source();change_site_species(frame,0,{'Ni':.7,'Fe':.3})
    path=tmp_path/'existing';path.write_text('original contents')
    with pytest.raises(ValueError,match='CIF'):export_frame(frame,path,target)
    assert path.read_text()=='original contents'


def test_ordered_replacement_exports_correct_poscar_groups_and_atom_order(tmp_path):
    frame=source();change_site_species(frame,1,{'Ni':1.})
    assert not is_disordered(frame)
    path=tmp_path/'POSCAR';export_frame(frame,path,'poscar-direct')
    assert path.read_text().splitlines()[5].split()==['Fe','Ni','O']
    restored=load_document(path).frames[0]
    assert restored.symbols==['Fe','Ni','O']
    np.testing.assert_allclose(restored.positions,frame.positions)


def test_dialog_two_columns_rows_validation_and_independent_index_tab(gui):
    from PySide6.QtWidgets import QDialogButtonBox
    from lele.structure_edit_dialogs import AtomIndexDialog
    dialog=AtomIndexDialog(source(),0,[0,1],parent=gui.window)
    panel=dialog.species;table=panel.table
    assert table.columnCount()==2 and table.rowCount()==2
    table.item(0,1).setText('0.6')
    table.item(1,0).setText('Ni');table.item(1,1).setText('0.3')
    assert panel.valid and 'Vacancy 0.1' in panel.total.text()
    table.item(1,1).setText('0.5')
    ok=dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert not panel.valid and not ok.isEnabled()
    dialog.tabs.setCurrentWidget(dialog.index_page)
    assert ok.isEnabled() and ok.text()=='Set index'
    dialog.tabs.setCurrentWidget(panel)
    assert not ok.isEnabled()
    table.selectRow(1);panel.remove_button.click()
    assert panel.valid and table.rowCount()==1
    panel.add_button.click();assert table.rowCount()==2 and panel.valid
    dialog.close()


def test_right_click_changes_clicked_site_only_and_undo_restores_frame_volume_and_energy(gui):
    from PySide6.QtWidgets import QDialog,QDialogButtonBox
    from lele.structure_edit_dialogs import AtomIndexDialog
    frame=source();other=frame.clone()
    volume=Volume(np.zeros((2,2,2)),np.zeros(3),np.eye(3))
    gui.attach(frame,volume=volume,second_frame=other)
    gui.select([0,1]);w=gui.window
    def accept(dialog):
        table=dialog.species.table
        table.item(0,1).setText('.6');table.item(1,0).setText('Ni');table.item(1,1).setText('.3')
        dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
        assert dialog.result()==QDialog.DialogCode.Accepted
        return dialog.result()
    with patch.object(w.renderer,'pick_index',return_value=0),patch.object(AtomIndexDialog,'exec',accept):
        w.vtk.resize(600,400);w.vtk.GetRenderWindow().SetSize(600,400)
        w._atom_context_from_canvas(40,40)
    assert site_species(w.frame,0)=={'Fe':.6,'Ni':.3}
    assert site_species(w.frame,1)=={'Fe':1.}
    assert w.doc.frames[1] is other and 'site_occupancies' not in other.info
    assert w.doc.volume is None and w.frame.energy_ev is None
    assert w.frame.bond_snapshot is not None
    assert w.atom_table.rowCount()==3 and w.selection==[0,1]
    w.undo_edit()
    assert w.frame.energy_ev==-12 and w.doc.volume is volume and 'site_occupancies' not in w.frame.info
    assert w.frame.info['optimization_converged']


def test_noop_and_cancel_have_no_undo_or_energy_side_effect(gui):
    from PySide6.QtWidgets import QDialog
    from lele.structure_edit_dialogs import AtomIndexDialog
    gui.attach(source());w=gui.window
    assert not w.apply_atom_species(0,{'Fe':1.}) and not w.undo_stack
    with patch.object(w.renderer,'pick_index',return_value=0),patch.object(AtomIndexDialog,'exec',return_value=QDialog.DialogCode.Rejected):
        w.vtk.resize(600,400);w.vtk.GetRenderWindow().SetSize(600,400)
        w._atom_context_from_canvas(40,40)
    assert not w.undo_stack and w.frame.energy_ev==-12


def test_project_and_boundary_keep_the_complete_site_after_gui_edit(gui,tmp_path):
    from lele.project_file import load_project
    gui.attach(source());w=gui.window
    assert w.apply_atom_species(0,{'Ni':.6,'Fe':.3})
    for source_index,values in zip(w.renderer.boundary_display.source_indices,w.renderer.boundary_display.frame.info['site_occupancies']):
        assert values==site_species(w.frame,source_index)
    path=tmp_path/'edited.lele';w.save_project_to(path)
    restored=load_project(path)['documents'][0]['document'].frames[0]
    assert site_species(restored,0)=={'Ni':.6,'Fe':.3}


def test_read_only_dialog_keeps_species_and_index_disabled(gui):
    from PySide6.QtWidgets import QDialogButtonBox
    from lele.structure_edit_dialogs import AtomIndexDialog
    dialog=AtomIndexDialog(source(),0,editable=False,parent=gui.window)
    assert not dialog.species.add_button.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.tabs.setCurrentWidget(dialog.index_page)
    assert not dialog.index.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    dialog.close()


def test_opening_precise_source_values_without_changes_keeps_them_exact(gui):
    from lele.site_species_editor import SiteSpeciesEditor
    frame=source();weights={'Fe':.10000000000000005,'Ni':.9}
    frame.symbols[0]='Ni'
    frame.info['site_occupancies']=[weights,{'Fe':1.},{'O':1.}]
    panel=SiteSpeciesEditor(frame,0)
    assert panel.valid and panel.requested_species()==weights
    assert not change_site_species(frame,0,panel.requested_rows())
    assert frame.energy_ev==-12


@pytest.mark.parametrize('index',[-1,3,True])
def test_invalid_site_index_cannot_mutate_a_different_atom(index):
    frame=source()
    with pytest.raises(ValueError):change_site_species(frame,index,{'Ni':1.})
    assert frame.symbols==['Fe','Fe','O'] and frame.energy_ev==-12


def test_zero_weight_without_an_element_is_an_incomplete_row(gui):
    from lele.site_species_editor import SiteSpeciesEditor
    frame=source();frame.info['site_occupancies']=[{'Fe':0.},{'Fe':1.},{'O':1.}]
    panel=SiteSpeciesEditor(frame,0)
    panel.table.item(0,0).setText('')
    assert not panel.valid
