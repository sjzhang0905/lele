"""Annotation gestures and atom edits have independent, undoable state."""
import numpy as np
from lele.annotations import TextAnnotation
from lele.core import Frame,Document
from test_periodic_fragment_ui_v171 import gui


def test_text_move_rotate_delete_undo_leave_atoms_unchanged(gui):
    gui.attach(Frame(['C','O'],[[0,0,0],[1.3,0,0]]))
    w=gui.window
    original=w.frame.positions.copy()
    w._append_annotation(TextAnnotation('Test',[0,1,0]))
    assert w._selected_annotation==0 and w.doc.annotations[0].text=='Test'
    assert w.edit_text_action.isEnabled()
    assert w._begin_annotation_gesture('pan',10,10)
    assert w._move_annotation_gesture('pan',30,20)
    assert w._end_annotation_gesture('pan')
    moved=np.array(w.doc.annotations[0].position)
    assert not np.allclose(moved,[0,1,0])
    np.testing.assert_array_equal(w.frame.positions,original)
    w.undo_edit()
    np.testing.assert_allclose(w.doc.annotations[0].position,[0,1,0])
    assert w._begin_annotation_gesture('orbit',10,10)
    w._move_annotation_gesture('orbit',20,5);w._end_annotation_gesture('orbit')
    assert not np.allclose(w.doc.annotations[0].rotation,np.eye(3))
    np.testing.assert_array_equal(w.frame.positions,original)
    assert w.delete_canvas_text()
    assert not w.doc.annotations
    w.undo_edit();assert len(w.doc.annotations)==1
    assert not np.allclose(w.doc.annotations[0].rotation,np.eye(3))
    w.undo_edit();np.testing.assert_allclose(w.doc.annotations[0].rotation,np.eye(3))
    w.undo_edit();assert not w.doc.annotations


def test_atom_selection_deselects_text_and_document_switch_isolates_text(gui):
    gui.attach(Frame(['C'],[[0,0,0]]))
    w=gui.window
    w._append_annotation(TextAnnotation('first'))
    first=w.doc
    gui.select([0])
    assert w._selected_annotation is None
    assert not w.edit_text_action.isEnabled()
    other=Document(first.path.with_name('other.xyz'),'XYZ',[Frame(['H'],[[0,0,0]])])
    w.documents.append(other);w._add_document_tree(1,other)
    w.change_frame(0,switch_doc=1)
    assert not w._annotation_manager.actors
    w._append_annotation(TextAnnotation('second'))
    w.change_frame(0,switch_doc=0)
    assert w.doc is first
    assert [a.text for a in w.doc.annotations]==['first']
    assert w._selected_annotation is None
    assert w._annotation_manager.actors[0].GetInput()=='first'


def test_pending_text_click_places_and_escape_cancels_without_atom_edit(gui):
    gui.attach(Frame(['C'],[[0,0,0]]))
    w=gui.window
    w.vtk.GetRenderWindow().SetSize(640,310)
    w._pending_annotation=TextAnnotation('Placed')
    assert w._pick_annotation_from_canvas(w.vtk.width()/2,w.vtk.height()/2)
    assert w._pending_annotation is None and len(w.doc.annotations)==1
    np.testing.assert_allclose(w.frame.positions,[[0,0,0]])
    w._pending_annotation=TextAnnotation('Cancelled')
    w.cancel_pointer_action()
    assert w._pending_annotation is None
    assert len(w.doc.annotations)==1


def test_coordinate_template_refresh_retains_document_text(gui,tmp_path):
    from test_coordinate_update_ui_v360 import setup_documents
    from lele.coordinate_update import prepare_coordinate_update
    w,path,target,source=setup_documents(gui,tmp_path)
    text=TextAnnotation('Keep caption',[2,3,4])
    target.annotations.append(text)
    plan=prepare_coordinate_update(path,source.frames[0])
    assert w.apply_coordinate_update(plan,target)
    assert target.annotations==[text]
    w.change_frame(0,switch_doc=0)
    assert w._annotation_manager.actors[0].GetInput()=='Keep caption'
