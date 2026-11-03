"""Target-value edits must preserve a terminal graph and reject constrained rings."""
from unittest.mock import patch
import numpy as np
import pytest
from lele.core import Frame, measure, visible_bonds, freeze_bonds
from lele.internal_coordinates import plan_internal_edit
from lele.periodic_geometry import periodic_bonds, normalized_positions
from test_periodic_fragment_ui_v171 import gui


def branched():
    return Frame(['C']*6,[[0,1.4,0],[0,0,0],[1.4,0,0],[1.4,1.4,1],[2.8,0,0],[9,9,9]],
                 energy_ev=-20.,bond_snapshot=frozenset({(0,1),(1,2),(2,3),(2,4)}))


@pytest.mark.parametrize('ids,target,moving',[
    ([1,2],2.1,[2,3,4]),([2,1],2.1,[0,1]),([0,5],3.,[5]),
    ([0,1,2],115.,[2,3,4]),([0,1,2],0.,[2,3,4]),([0,1,2],180.,[2,3,4]),
    ([0,1,2,3],-65.,[2,3,4]),([0,1,2,3],180.,[2,3,4]),([0,1,2,3],-180.,[2,3,4])])
def test_target_and_rigid_fragment_in_selection_order(ids,target,moving):
    frame=branched();original=frame.positions.copy()
    edit=plan_internal_edit(frame,ids,target)
    assert edit.moving==moving
    np.testing.assert_array_equal(frame.positions,original)
    fixed=sorted(set(range(6))-set(moving))
    np.testing.assert_array_equal(edit.positions[fixed],original[fixed])
    old=original[moving];new=edit.positions[moving]
    np.testing.assert_allclose(np.linalg.norm(old[:,None]-old,axis=2),np.linalg.norm(new[:,None]-new,axis=2),atol=1.e-12)
    result=frame.clone();result.positions=edit.positions
    kind,value=measure(result,ids)
    error=(value-target+180)%360-180 if kind=='dihedral' else value-target
    assert abs(error)<1.e-8
    if len(ids)==4:np.testing.assert_array_equal(edit.positions[2],original[2])


@pytest.mark.parametrize('ids,target',[([0,1],1.8),([0,1,2],105),([0,1,2,3],40)])
def test_ring_path_rejects_without_mutating(ids,target):
    frame=branched();frame.bond_snapshot|={(0,3)};original=frame.clone()
    with pytest.raises(ValueError,match='ring|bond path'):plan_internal_edit(frame,ids,target)
    np.testing.assert_array_equal(frame.positions,original.positions)
    assert frame.bond_snapshot==original.bond_snapshot


@pytest.mark.parametrize('left,target',[(1.,60.),(-1.,120.)])
def test_collinear_angle_has_a_deterministic_rotation(left,target):
    frame=Frame(['C']*3,[[left,0,0],[0,0,0],[1.4,0,0]],bond_snapshot=frozenset({(0,1),(1,2)}))
    edit=plan_internal_edit(frame,[0,1,2],target)
    frame.positions=edit.positions
    assert measure(frame,[0,1,2])[1]==pytest.approx(target)


@pytest.mark.parametrize('ids,target',[([0,1],0),([0,1],float('nan')),([0,1,2],181),([0,1,2,3],181)])
def test_invalid_target_is_not_applied(ids,target):
    with pytest.raises(ValueError):plan_internal_edit(branched(),ids,target)


def crossing():
    return Frame(['C','C','H','He'],[[.1,0,0],[9.5,0,0],[.4,.2,0],[5,5,5]],
                 np.eye(3)*10,(True,)*3,energy_ev=-12.,
                 bond_snapshot=frozenset({(0,1),(1,2)}),
                 periodic_bond_snapshot=((0,1,(-1,0,0)),(1,2,(1,0,0))),
                 hbond_added={(2,3):(1,0,0)})


def raw_edges(frame):
    _,floors=normalized_positions(frame)
    return [(i,j,np.asarray(s)+floors[i]-floors[j]) for i,j,s in periodic_bonds(frame)]


def test_periodic_finite_fragment_is_unwrapped_and_image_shifts_follow_it():
    frame=crossing();old_vector=frame.positions[2]+np.array([10,0,0])-frame.positions[1]
    edit=plan_internal_edit(frame,[0,1],1.5)
    assert edit.moving==[1,2]
    frame.positions=edit.positions;frame.periodic_bond_snapshot=edit.periodic_edges;frame.hbond_added=edit.hbond_added
    assert measure(frame,[0,1])[1]==pytest.approx(1.5)
    for i,j,s in raw_edges(frame):
        vector=frame.positions[j]+s@frame.cell-frame.positions[i]
        if (i,j)==(1,2):np.testing.assert_allclose(vector,old_vector,atol=1.e-12)
        else:assert np.linalg.norm(vector)==pytest.approx(1.5)
    assert frame.hbond_added[(2,3)]==(2,0,0)
    np.testing.assert_array_equal(frame.positions[[0,3]],[[.1,0,0],[5,5,5]])


@pytest.mark.parametrize('extra,message',[
    ((2,2,(1,0,0)),'infinite periodic'),((0,1,(0,0,0)),'multiple periodic images'),
    ((0,2,(0,0,0)),'ring|bond path')])
def test_periodic_network_cannot_be_broken_by_a_numeric_edit(extra,message):
    frame=crossing();frame.periodic_bond_snapshot+=(extra,)
    with pytest.raises(ValueError,match=message):plan_internal_edit(frame,[0,1],1.5)


def test_dashed_annotations_do_not_drag_an_unbonded_atom():
    frame=branched();frame.hbond_added={(3,5):(0,0,0)}
    assert plan_internal_edit(frame,[1,2],1.8).moving==[2,3,4]


def test_gui_edit_clears_stale_energy_freezes_bonds_and_undo_restores(gui):
    frame=branched();other=frame.clone();gui.attach(frame,second_frame=other);w=gui.window
    gui.select([0,1,2]);original=frame.clone();w.measurement_value.setValue(112.5);w.measurement_set.click()
    assert measure(w.frame,[0,1,2])[1]==pytest.approx(112.5)
    assert w.doc.modified and w.frame.energy_ev is None and len(w.undo_stack)==1
    assert w.frame.bond_snapshot==original.bond_snapshot
    np.testing.assert_array_equal(other.positions,original.positions)
    assert w.measurement_value.value()==112.5
    w.undo_edit();np.testing.assert_array_equal(w.frame.positions,original.positions)
    assert w.frame.energy_ev==-20. and w.selection==[0,1,2]


def test_gui_ring_warning_restores_field_without_undo_or_mutation(gui):
    frame=branched();frame.bond_snapshot|={(0,3)};gui.attach(frame);w=gui.window
    gui.select([0,1,2]);original=frame.positions.copy()
    with patch('lele.app.QMessageBox.warning') as warning:
        w.measurement_value.setValue(120.);w.measurement_set.click()
    warning.assert_called_once();assert 'ring' in warning.call_args.args[-1]
    assert not w.undo_stack and not w.doc.modified
    np.testing.assert_array_equal(frame.positions,original)
    assert w.measurement_value.value()==90.


def test_enter_applies_once_and_pauses_trajectory_playback(gui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    gui.attach(branched());w=gui.window;gui.select([1,2]);w.show();gui.app.processEvents()
    w.playback.start(1000);w.play_btn.setText('Pause');w.measurement_value.setFocus();gui.app.processEvents()
    assert not w.playback.isActive()
    field=w.measurement_value.lineEdit();field.selectAll();QTest.keyClicks(field,'2.2000')
    QTest.keyClick(field,Qt.Key.Key_Return)
    assert measure(w.frame,[1,2])[1]==pytest.approx(2.2) and len(w.undo_stack)==1
    QTest.keyClick(field,Qt.Key.Key_Return);assert len(w.undo_stack)==1


def test_cutoff_rebuilds_frozen_automatic_bonds_and_retains_manual_links(gui):
    frame=Frame(['C','C','H','H'],[[0,0,0],[2,0,0],[0,8,0],[0,9,0]],
                bond_added={(0,2)},bond_removed={(2,3)})
    freeze_bonds(frame);other=frame.clone();gui.attach(frame,second_frame=other);w=gui.window
    assert visible_bonds(frame)==[(0,2)]
    w.cutoff_spin.setValue(1.5)
    assert w.cutoff_slider.value()==150 and w.render_options.bond_cutoff==1.5
    assert frame.bond_snapshot is None and other.bond_snapshot is None
    assert visible_bonds(frame,1.5)==[(0,1),(0,2)]
    assert frame.bond_added=={(0,2)} and frame.bond_removed=={(2,3)}
    w.cutoff_slider.setValue(10)
    assert w.cutoff_spin.value()==.10 and visible_bonds(frame,.10)==[(0,2)]
    assert w.cutoff_slider.maximum()==500 and w.cutoff_spin.maximum()==5.


def test_cutoff_keeps_explicit_pair_rule_distances(gui):
    from lele.element_rules import validate_rules
    frame=Frame(['Ti','O'],[[0,0,0],[2,0,0]])
    gui.attach(frame);w=gui.window
    w._apply_element_pair_rules(validate_rules([dict(a1='Ti',a2='O',maximum=2.5)]),False)
    w.cutoff_spin.setValue(.1)
    assert visible_bonds(frame,.1)==[(0,1)]
    assert 'pair rules' in w.statusBar().currentMessage()


def test_summary_and_edit_controls_use_the_window_bottom_strip(gui):
    from PySide6.QtCore import QPoint
    gui.attach(branched());w=gui.window;gui.select([0,1,2,3]);w.resize(1380,850);w.show();gui.app.processEvents()
    bottom=w.summary_label.mapTo(w,QPoint(0,w.summary_label.height())).y()
    assert w.height()-bottom<=8
    assert w.measurement_value.isVisible() and w.measurement_set.isVisible()
    assert w.measurement_set.mapTo(w,QPoint(w.measurement_set.width(),0)).x()<=w.width()
    assert w.vtk.height()>480


def test_frequency_and_aligned_views_keep_measurement_read_only(gui):
    gui.attach_vibrations();w=gui.window;w.select_vibration(0,0,0,autoplay=False);gui.select([0,1])
    assert not w.measurement_value.isEnabled() and not w.measurement_set.isVisible()
