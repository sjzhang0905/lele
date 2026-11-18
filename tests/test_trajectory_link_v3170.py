from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import csv
import shutil

import numpy as np
import pytest
from ase.units import Hartree
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from lele.formats import load_document
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.trajectory_link import association_role, link_trajectory
from test_periodic_fragment_ui_v171 import gui

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def xyz(path, rows):
    path.write_text(''.join(f'2\n{comment}\nO 0 0 0\nH 0 0 {z}\n' for comment, z in rows))
    return path


def cp2k(tmp_path, run='GEO_OPT', body=''):
    path = tmp_path / 'calc.out'
    path.write_text(f' CP2K| version string: CP2K version 2026.2\n GLOBAL| Run type {run}\n'
                    ' - Atoms: 2\n' + body)
    return path


def energy(value):
    return f' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {value}\n'


def opt(i, e, g):
    return (f' OPTIMIZATION STEP: {i}\n' + energy(e) + f' OPT| Step number {i}\n'
            f' OPT| Maximum gradient {g}\n OPT| RMS gradient {g / 2}\n')


def xtb_pair(tmp_path):
    log = tmp_path / 'run.out'
    shutil.copy(EXAMPLES / 'synthetic_xtb_v1110.out', log)
    path = tmp_path / 'elsewhere' / 'positions.log'
    path.parent.mkdir()
    shutil.copy(EXAMPLES / 'synthetic_xtb_v1110.xtbopt.log', path)
    return log, path


def test_cp2k_trials_initial_reevaluation_and_fixed_cell(tmp_path):
    body = (' CELL| Vector a [angstrom]: 2 0 0\n CELL| Vector b [angstrom]: 0 3 0\n'
            ' CELL| Vector c [angstrom]: 0 0 4\n CELL| Periodicity XY\n'
            ' OPTIMIZATION STEP: 1\n' + energy(-9) + energy(-7) + energy(-10) +
            ' OPT| Step number 1\n OPT| Maximum gradient .04\n' + opt(2, -11, .01) +
            ' Reevaluating energy at the minimum\n' + energy(-11.001))
    path = cp2k(tmp_path, body=body)
    tr = xyz(tmp_path / 'positions.xyz', [(f'i = {i}, E = {e}', 1+.01*i)
                                           for i, e in enumerate([-9, -10, -11, -11.001])])
    doc = link_trajectory(path, tr)
    steps = doc.calculation_results.steps
    assert [s.frame_index for s in steps] == [0, None, 1, 2, 3]
    assert [f.info['linked_step'] for f in doc.frames] == [0, 1, 2, 3]
    assert steps[2].convergence['max_force'][0] == .04
    np.testing.assert_equal(doc.frames[-1].cell, np.diag([2, 3, 4]))
    assert doc.frames[-1].pbc == (True, True, False)


def md(i):
    return (f' MD STEP: {i} / 30\n' + energy(-10-i*.01) + f' MD| Step number {i}\n'
            f' MD| Time [fs] {i*.5}\n MD| Temperature [K] {300+i} 299\n'
            f' MD| Kinetic energy [hartree] {i*.001} .1\n')


def test_sparse_aimd_preserves_unprinted_positions_and_trajectory_only_steps(tmp_path):
    path = cp2k(tmp_path, 'MD', ''.join(md(i) for i in [10, 11, 13, 14]))
    tr = xyz(tmp_path/'pos.xyz', [(f'i = {i}, time = {i*.5}, E = {-10-i*.01}', 1+.01*i)
                                   for i in [10, 12, 14]])
    doc = link_trajectory(path, tr)
    assert [s.cycle for s in doc.calculation_results.steps] == [10,11,12,13,14]
    assert [s.frame_index for s in doc.calculation_results.steps] == [0,None,1,None,2]
    assert [f.info['time_fs'] for f in doc.frames] == [5,6,7]
    assert doc.frames[0].info['cp2k_md_temperature_K'] == 310
    assert 'cp2k_md_temperature_K' not in doc.frames[1].info
    assert doc.trajectory_link['matched'] == 2 and doc.trajectory_link['trajectory_only'] == 1
    assert doc.frames[1].energy_ev/Hartree == pytest.approx(-10.12)


def test_md_summary_only_and_variable_cell_native_extxyz(tmp_path):
    path=cp2k(tmp_path, 'MD', ' MD_PAR| Ensemble type NPT_I\n' + ''.join(
        f' MD| Step number {i}\n MD| Time [fs] {i}.0\n MD| Potential energy [hartree] {-i}.0\n'
        for i in [6,7]))
    tr=xyz(tmp_path/'box.extxyz', [(f'Lattice="{i} 0 0 1 3 0 0 0 4" Step={i} Time={i} '
            f'Energy={-i} Properties=species:S:1:pos:R:3 pbc="T T F"', i*.1) for i in [6,7]])
    doc=link_trajectory(path,tr)
    assert [s.energy_ev / Hartree for s in doc.calculation_results.steps] == pytest.approx([-6,-7])
    for i, f in enumerate(doc.frames, 6):
        np.testing.assert_equal(f.cell, [[i,0,0],[1,3,0],[0,0,4]])
        assert f.pbc == (True,True,False)


@pytest.mark.parametrize('comment, reason', [('i = 1, E = -88', 'compatible'), ('i = 77, E = -10.01', 'matching'),
                                             ('i = 1, time = 9, E = -10.01', 'compatible')])
def test_wrong_metadata_rejected(tmp_path, comment, reason):
    path=cp2k(tmp_path,'MD',md(1))
    with pytest.raises(ValueError,match=reason):
        link_trajectory(path,xyz(tmp_path/'positions.xyz',[(comment, 1)]))


def test_repeated_restart_counters_require_unique_assignment(tmp_path):
    header=' CP2K| version string: CP2K version 2026.2\n GLOBAL| Run type MD\n'
    path=cp2k(tmp_path,'MD',md(1)+header+md(1))
    tr=xyz(tmp_path/'one.xyz',[('i = 1, E = -10.01',1)])
    with pytest.raises(ValueError,match='Several'):
        link_trajectory(path,tr)
    xyz(tr,[('i = 1, E = -10.01',1),('i = 1, E = -10.01',2)])
    assert [f.info['calculation_index'] for f in link_trajectory(path,tr).frames] == [0,1]


def test_xtb_renamed_partial_trajectory_preserves_final_energy_and_orbitals(tmp_path):
    path,tr=xtb_pair(tmp_path)
    lines=tr.read_text().splitlines(True)
    tr.write_text(''.join(lines[:5]+lines[10:]))
    doc=link_trajectory(path,tr)
    assert [s.frame_index for s in doc.calculation_results.steps] == [0,None,1]
    assert [s.frame_index for s in doc.calculation_results.orbitals] == [0,1]
    assert doc.frames[-1].info['xtb_trajectory_gnorm'] == .0001
    assert abs(doc.frames[-1].energy_ev/Hartree + 10.100000000123) < 1e-13
    assert doc.calculation_results.steps[1].optimizer_gradient_norm == .01
    tr.write_text(tr.read_text().replace('O 0.0','N 0.0'))
    with pytest.raises(ValueError,match='element order'):
        link_trajectory(path,tr)


def test_explicit_plain_xyz_and_output_only_xtb(tmp_path):
    p=tmp_path/'run.out';shutil.copy(EXAMPLES/'synthetic_xtb_energy_only_v1111.out',p)
    t=xyz(tmp_path/'user.xyz',[('plain',1),('plain',1.2),('plain',1.4)])
    doc=link_trajectory(p,t)
    assert [s.frame_index for s in doc.calculation_results.steps] == [0,1,2]
    assert doc.trajectory_link['by_order']
    xyz(t,[('plain',1),('plain',1.2)])
    with pytest.raises(ValueError):
        link_trajectory(p,t)


def test_project_retains_link_without_original_files(tmp_path):
    p,t=xtb_pair(tmp_path);d=link_trajectory(p,t)
    project=tmp_path/'linked.lele'
    save_project(project,dict(documents=[dict(document=d,options=RenderOptions(),frame_index=2)],current_document=0))
    p.unlink();t.unlink()
    restored=load_project(project)['documents'][0]['document']
    assert restored.trajectory_link==d.trajectory_link
    assert [s.frame_index for s in restored.calculation_results.steps]==[0,1,2]
    np.testing.assert_equal(restored.frames[1].positions,d.frames[1].positions)
    assert restored.calculation_results.steps[1].optimizer_gradient_norm==.01


@pytest.mark.parametrize('reverse',[False,True])
def test_tree_menu_both_directions_merges_open_documents_and_curve_pick(gui,tmp_path,reverse):
    w=gui.window;p,t=xtb_pair(tmp_path);w._open_path_now(p);output=w.doc;w._open_path_now(t);trajectory=w.doc
    target,other=(trajectory,p) if reverse else (output,t)
    before=len(w.documents);menu=w._loaded_file_menu(target)
    action=next(a for a in menu.actions() if a.text()=='Associate file…')
    with patch('lele.loaded_documents.QFileDialog.getOpenFileName',return_value=(str(other),'')):
        action.trigger()
    assert len(w.documents)==before-1 and w.doc.path==p
    assert w.files_tree.topLevelItemCount() == len(w.documents)
    curve=w.show_energy_curve()
    assert curve.metric_combo.currentData()=='gnorm'
    np.testing.assert_allclose(curve.metric_axes.lines[0].get_ydata(),[.1,.01,.0001])
    curve.metric_combo.setCurrentIndex(curve.metric_combo.findData('optimizer_norm'))
    curve.pick_point(SimpleNamespace(artist=curve.metric_axes.lines[0],ind=[1]))
    assert w.frame_index==1 and w.frame.info['linked_step']==2
    assert 'Position trajectory:' in w.info_view.toPlainText()
    assert w._associate_loaded_file(w.doc,t)
    assert len(w.documents)==before-1 and len(w.doc.frames)==3


def test_failed_link_keeps_both_documents_and_modified_copy(gui,tmp_path):
    w=gui.window;p,t=xtb_pair(tmp_path);w._open_path_now(p);old=w.doc
    old.modified=True
    with patch('lele.loaded_documents.QMessageBox.warning') as warning:
        assert not w._associate_loaded_file(old,p)
        assert warning.called and w.doc is old
    assert w._associate_loaded_file(old,t)
    assert old in w.documents and w.doc is not old and old.modified


def test_aimd_curve_csv_and_gaps(gui,tmp_path):
    w=gui.window;p=cp2k(tmp_path,'MD',''.join(md(i) for i in [10,11,12]))
    t=xyz(tmp_path/'sparse.xyz',[(f'i = {i}, time = {i*.5}, E = {-10-i*.01}', 1+.01*i) for i in [10,12]])
    w._open_path_now(p)
    assert not w.doc.frames and w._associate_loaded_file(w.doc,t)
    d=w.doc;curve=w.show_energy_curve()
    assert curve.metric_combo.currentText()=='Temperature (K)'
    np.testing.assert_allclose(curve.metric_axes.lines[0].get_ydata(),[310,311,312])
    curve.pick_point(SimpleNamespace(artist=curve.energy_axes.lines[0],ind=[0]))
    assert w.frame_index==0
    curve.pick_point(SimpleNamespace(artist=curve.metric_axes.lines[0],ind=[1]))
    assert w.frame_index==0 and 'No matched geometry' in curve.note.text()
    curve.pick_point(SimpleNamespace(artist=curve.metric_axes.lines[0],ind=[2]))
    assert w.frame is d.frames[1]
    out=tmp_path/'md.csv';curve._write_csv(out)
    with out.open(encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
    assert [r['geometry_frame'] for r in rows]==['1','','2']
    assert float(rows[2]['time_fs'])==6 and float(rows[2]['cp2k_md_temperature_K'])==312


def test_info_copy_selection_and_whole_text_on_both_pages(gui,tmp_path):
    w=gui.window
    assert not any('Global index starts' in label.text() for label in w.findChildren(QLabel))
    assert all(w.tabs.tabText(i)!='Input / output text' for i in range(w.tabs.count()))
    assert not hasattr(w,'source_view') and not hasattr(w,'results_only_source')
    w.tabs.setCurrentWidget(w.info_view)
    def test_copy(widget):
        w.activateWindow();widget.setFocus();QApplication.processEvents()
        clip=QApplication.clipboard();clip.setText('before')
        QTest.keyClick(widget,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        assert clip.text()==widget.toPlainText() and widget.toPlainText()
        cursor=widget.textCursor();cursor.setPosition(0);cursor.setPosition(4,cursor.MoveMode.KeepAnchor)
        widget.setTextCursor(cursor)
        QTest.keyClick(widget,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        assert clip.text()==widget.toPlainText()[:4]
    test_copy(w.info_view)
    w._open_path_now(cp2k(tmp_path,'MD',md(1)))
    assert w.frame is None
    test_copy(w.results_only_info)


@pytest.mark.parametrize('modern',[False,True])
def test_md_force_norms_use_complete_tables_and_native_units(tmp_path,modern):
    from ase.units import Bohr
    forces = (' FORCES| Atomic forces [EV/ANGSTROM]\n FORCES| Atom x y z |f|\n'
              ' FORCES| 1 3 4 0 5\n FORCES| 2 0 0 1 1\n FORCES| Sum 3 4 1\n' if modern else
              ' ATOMIC FORCES in [a.u.]\n # Atom Kind Element X Y Z\n'
              ' 1 1 O 3 4 0\n 2 2 H 0 0 1\n SUM OF ATOMIC FORCES 3 4 1\n')
    path=cp2k(tmp_path,'MD',md(1)+forces+md(2))
    d=link_trajectory(path,xyz(tmp_path/'pair.xyz',[('i = 1, E = -10.01',1),('i = 2, E = -10.02',1.5)]))
    factor=Bohr/Hartree if modern else 1.
    first,second=d.calculation_results.steps
    assert first.convergence['max_force'][0]==pytest.approx(5*factor)
    assert first.convergence['rms_force'][0]==pytest.approx(np.sqrt(13)*factor)
    assert not second.convergence


def test_legacy_optimization_summary_and_sparse_steps(tmp_path):
    path=cp2k(tmp_path,body=(' OPTIMIZATION STEP: 3\n ENERGY| Total FORCE_EVAL ( QS ) energy (a.u.): -8.5\n'
          ' -------- Informations at step = 3 ------------\n Total Energy = -8.5000000\n'
          ' Max. gradient = .112\n Conv. limit for gradients = .001\n'
          ' RMS gradient = .021\n Conv. limit for RMS grad. = .0005\n'))
    d=link_trajectory(path,xyz(tmp_path/'pair.xyz',[('i = 3, E = -8.5',1)]))
    assert d.calculation_results.steps[0].convergence=={'max_force':(.112,.001),'rms_force':(.021,.0005)}


def test_wrong_file_types_and_different_atom_count(tmp_path):
    p=cp2k(tmp_path,body=opt(1,-10,.1))
    t=xyz(tmp_path/'run-frc-1.xyz',[('i = 1, E = -10',1)])
    with pytest.raises(ValueError,match='position trajectory'):
        link_trajectory(p,t)
    t=tmp_path/'run-pos-1.xyz';t.write_text('1\ni = 1, E = -10\nO 0 0 0\n')
    with pytest.raises(ValueError,match='atom count'):
        link_trajectory(p,t)
    p=cp2k(tmp_path,run='ENERGY',body=energy(-10))
    assert association_role(load_document(p)) is None


def test_legacy_md_atom_kind_alias_and_reftraj_initial_structure(tmp_path):
    body=(' 1. Atomic kind: Al Number of atoms: 1\n 2. Atomic kind: H Number of atoms: 1\n'
          ' MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM\n'
          ' 1 1 O 8 9.0 0.0 0.0\n 2 2 H 1 9.0 0.0 1.0\n\n'
          ' MD| Ensemble Type REFTRAJ\n'+energy(-10)+
          ' INITIAL POTENTIAL ENERGY[hartree] = -10.0\n'+energy(-10.2)+
          ' STEP NUMBER = 2\n TIME [fs] = 1.00\n POTENTIAL ENERGY[hartree] = -10.2 -10.1\n')
    p=cp2k(tmp_path,'MD',body); t=xyz(tmp_path/'positions.xyz',[('i = 1, time = 0, E = -10',1),
                                                               ('i = 2, time = 1, E = -10.2',1.1)])
    d=link_trajectory(p,t)
    assert [f.info['cp2k_md_step'] for f in d.frames]==[1,2]
    assert [s.info.get('time_fs') for s in d.calculation_results.steps]==[0,1]
    assert d.frames[0].positions[0,0]==0


def test_cp2k_curve_uses_accepted_optimization_steps_and_force_pick(gui,tmp_path):
    w=gui.window
    p=cp2k(tmp_path,body=(' OPTIMIZATION STEP: 1\n'+energy(-6)+energy(-8)+' OPT| Step number 1\n'
                          ' OPT| Maximum gradient .040\n'+opt(2,-9,.025)))
    t=xyz(tmp_path/'POS.xyz',[('i = 1, E = -8',1),('i = 2, E = -9',1.1)])
    w._open_path_now(t); assert w._associate_loaded_file(w.doc,p)
    curve=w.show_energy_curve()
    assert [(r['x'],r['frame']) for r in curve.points()]==[(1,0),(2,1)]
    np.testing.assert_allclose(curve.metric_axes.lines[0].get_ydata(),[.04,.025])
    curve.pick_point(SimpleNamespace(artist=curve.metric_axes.lines[0],ind=[0]))
    assert w.frame.info['linked_step']==1


def test_summary_without_force_eval_and_energy_only_without_step_numbers(tmp_path):
    t=xyz(tmp_path/'pos.xyz',[('i = 1, E = -10',1),('i = 2, E = -11',2)])
    p=cp2k(tmp_path,body=''.join(f' OPT| Step number {i}\n OPT| Total energy [hartree] {v}\n'
                                  ' OPT| Maximum gradient .01\n' for i,v in [(1,-10),(2,-11)]))
    assert [s.cycle for s in link_trajectory(p,t).calculation_results.steps]==[1,2]
    p=cp2k(tmp_path,body=energy(-10)+energy(-11))
    d=link_trajectory(p,t)
    assert [s.frame_index for s in d.calculation_results.steps]==[0,1]
    assert [f.info['linked_step'] for f in d.frames]==[1,2]


def test_incomplete_tail_is_distinct_from_malformed_interior(tmp_path):
    p=cp2k(tmp_path,body=opt(1,-10,.01)+opt(2,-11,.01))
    t=xyz(tmp_path/'pos.xyz',[('i = 1, E = -10',1)])
    first=t.read_text()
    t.write_text(first+'2\ni = 2, E = -11\nO 0 0 0\n')
    assert 'Incomplete trailing' in link_trajectory(p,t).note
    t.write_text(first+'2\ni = 2, E = -11\nO 0 0 0\nUnknown 0 0 1\n')
    with pytest.raises(ValueError,match='Unknown'):
        link_trajectory(p,t)
