"""Real Qt selection, cross-frame appearance, result dialogs and graph picks."""
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from lele.core import Frame,Document
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/synthetic_analysis_v180.log'


def attach_result(gui):
    w=gui.window;doc=load_document(EXAMPLE)
    w.documents=[doc];w.current_doc=0;w.frame_index=0;w.selection=[]
    w.files_tree.clear();w._add_document_tree(0,doc);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w,doc


def rectangle_around(w,index):
    w.scene.SetWorldPoint(*w.frame.positions[index],1.)
    w.scene.WorldToDisplay();x,y,_=w.scene.GetDisplayPoint()
    width,height=w.vtk.GetRenderWindow().GetSize()
    qx=x*w.vtk.width()/width;qy=w.vtk.height()-y*w.vtk.height()/height
    w._rectangle_selected(qx-3,qy-3,qx+3,qy+3)


def test_two_plain_box_selections_accumulate_and_undo_individually(gui):
    gui.attach(Frame(['C']*3,[[-3,0,0],[0,0,0],[3,0,0]]))
    w=gui.window;w.vtk.GetRenderWindow().SetSize(600,400);w.refresh_scene(reset_camera=True)
    rectangle_around(w,0);assert w.selection==[0]
    rectangle_around(w,2);assert w.selection==[0,2]
    rectangle_around(w,2);assert len(w.undo_stack)==2
    w.undo_edit();assert w.selection==[0]
    w.undo_edit();assert w.selection==[]
    assert len(w.frame.symbols)==3 and not w.doc.modified


def test_selection_and_geometry_history_interleave_without_erasing_coordinates(gui):
    w=gui.window;w.selection=[];w.vtk.GetRenderWindow().SetSize(600,400);w.refresh_scene(reset_camera=True)
    rectangle_around(w,0)
    original=w.frame.positions.copy()
    w.delete_selected_atoms();assert len(w.frame.symbols)==3
    w.undo_edit();assert len(w.frame.symbols)==4 and w.selection==[0]
    w.undo_edit();assert w.selection==[]
    np.testing.assert_array_equal(w.frame.positions,original)


def test_ctrl_a_selects_atoms_and_keeps_native_text_selection(gui):
    from PySide6.QtWidgets import QLineEdit
    w=gui.window;w.show();w.vtk.setFocusPolicy(Qt.FocusPolicy.StrongFocus);w.vtk.setFocus();gui.app.processEvents()
    QTest.keyClick(w.vtk,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    assert w.selection==list(range(len(w.frame.symbols)))
    w.undo_edit();assert w.selection==[]
    editor=QLineEdit('some text',w);editor.show();editor.setFocus();gui.app.processEvents()
    QTest.keyClick(editor,Qt.Key.Key_A,Qt.KeyboardModifier.ControlModifier)
    assert editor.selectedText()=='some text' and w.selection==[]


def test_appearance_propagates_in_file_and_undo_survives_frame_replacement(gui):
    first=Frame(['O','H','H'],[[0,0,0],[1,0,0],[0,1,0]],bond_added={(1,2)})
    second=first.clone();second.positions+=2;second.bond_added=set()
    gui.attach(first,second_frame=second);w=gui.window
    other=Document(Path('other.xyz'),'XYZ',[first.clone()]);w.documents.append(other)
    positions=[f.positions.copy() for f in w.doc.frames];bonds=[f.bond_added.copy() for f in w.doc.frames]
    w._change_atom_appearance([1],{'color':'#123456','opacity':.3})
    assert all(f.atom_appearance[1].color=='#123456' for f in w.doc.frames)
    assert other.frames[0].atom_appearance=={}
    for f,p,b in zip(w.doc.frames,positions,bonds):
        np.testing.assert_array_equal(f.positions,p);assert f.bond_added==b
    w.change_frame(1);gui.select([0]);w.delete_selected_atoms()
    w.undo_edit();assert w.frame.atom_appearance[1].opacity==.3
    w.undo_edit();assert all(f.atom_appearance=={} for f in w.documents[0].frames)


def test_reset_appearance_applies_to_all_compatible_frames(gui):
    w=gui.window;w.doc.frames.append(w.frame.clone())
    w._change_atom_appearance([0],{'color':'#abcdef','opacity':.2})
    w._reset_atom_appearance([0]);assert all(f.atom_appearance=={} for f in w.doc.frames)
    w.undo_edit();assert all(f.atom_appearance[0].opacity==.2 for f in w.doc.frames)


def test_homo_popup_opens_on_button_click_with_ev_and_two_spin_channels(gui):
    from lele.orbital_dialog import OrbitalDialog
    w=gui.window
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    w._open_path_now(EXAMPLE)
    assert not any(isinstance(d,OrbitalDialog) for d in w._analysis_windows)
    assert w.orbital_btn.isEnabled()
    w.orbital_btn.click()
    dialog=next(d for d in w._analysis_windows if isinstance(d,OrbitalDialog))
    assert dialog.unit.currentText()=='eV' and dialog.summary.rowCount()==2
    assert dialog.summary.item(0,1).text()=='5' and dialog.summary.item(0,3).text()=='6'
    assert np.isclose(float(dialog.summary.item(0,5).text()),.25*27.211386024367243,atol=1.e-5)


def test_calculation_overview_separates_charges_methods_and_termination(gui):
    w,doc=attach_result(gui);dialog=w.show_calculation_overview()
    assert dialog.table.rowCount()==2
    assert [dialog.table.item(i,4).text() for i in range(2)]==['0','1']
    assert [dialog.table.item(i,5).text() for i in range(2)]==['1','2']
    assert dialog.table.item(0,7).text()=='Normal termination'
    dialog.table.setCurrentCell(0,0);dialog.show_details()
    assert 'water' in dialog.details.toPlainText() and 'max_force' in dialog.details.toPlainText()


def test_click_energy_or_rms_point_changes_to_its_geometry_frame(gui):
    from matplotlib.backend_bases import MouseEvent
    w,doc=attach_result(gui);dialog=w.show_energy_curve();gui.app.processEvents();dialog.canvas.draw()
    assert dialog.grab().width()>500  # Exercise Qt's native paint-device virtual methods.
    assert len(dialog.energy_axes.lines)>=1 and len(dialog.metric_axes.lines)>=2
    for line in [dialog.energy_axes.lines[0],dialog.metric_axes.lines[0]]:
        w.change_frame(0)
        frame=dialog.line_frames[line][-1]
        x,y=line.get_xdata()[-1],line.get_ydata()[-1]
        px,py=line.axes.transData.transform((x,y))
        event=MouseEvent('button_press_event',dialog.canvas,px,py,button=1)
        dialog.canvas.callbacks.process('button_press_event',event)
        assert w.frame_index==frame
        np.testing.assert_array_equal(w.frame.positions,doc.frames[frame].positions)


def test_scan_filter_and_transition_composition_table(gui):
    w,doc=attach_result(gui);curve=w.show_energy_curve()
    assert curve.scan_only.isChecked()
    assert [r['frame'] for r in curve.points()]==[1,2]
    curve.scan_only.setChecked(False)
    assert [r['frame'] for r in curve.points()]==[0,1,2]
    dialog=w.show_transition_results();dialog.table.setCurrentCell(0,0);dialog.show_details()
    assert dialog.table.rowCount()==2 and dialog.details.rowCount()==3
    assert '5A -> 6A' in dialog.table.item(0,4).text()
    assert any(dialog.details.item(i,5).text()=='-0.2' for i in range(3))


def test_unmatched_job_does_not_borrow_other_segments_curve_data(gui):
    from lele.calculation_results import CalculationJob
    w,doc=attach_result(gui)
    doc.calculation_results.jobs.append(CalculationJob(2,999,route='# freq',charge=2,multiplicity=1))
    dialog=w.show_energy_curve();dialog.job.setCurrentIndex(2)
    assert dialog.points()==[] and not dialog.line_frames
