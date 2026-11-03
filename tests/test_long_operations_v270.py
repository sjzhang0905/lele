"""Multistep values, observable progress, cancellation and display overlays."""
from pathlib import Path
from time import sleep
import threading
from unittest.mock import patch
import numpy as np
import pytest
from ase.units import Hartree
from lele.formats import load_document
from lele.core import Frame
from lele.output_text import output_read_session,load_progress,LoadCancelled,check_load_cancelled
from test_periodic_fragment_ui_v171 import gui


def qe_text(count,variable=False):
    yield '''Program PWSCF v.7.5 starts
 celldm(1)= 10.00000
 number of atoms/cell = 2
 number of atomic types = 1
 crystal axes: (cart. coord. in units of alat)
 a(1) = ( 1.0 0.0 0.0 )
 a(2) = ( 0.0 1.0 0.0 )
 a(3) = ( 0.0 0.0 1.0 )
 positions (alat units)
 1 H tau( 1) = ( 0.0 0.0 0.0 )
 2 H tau( 2) = ( 0.0 0.0 0.2 )
'''
    for i in range(count):
        if i:
            if variable:yield f'CELL_PARAMETERS (angstrom)\n{5+i*.0001:.8f} 0 0\n0 5 0\n0 0 5\n\n'
            yield f'ATOMIC_POSITIONS (angstrom)\nH 0 0 0\nH 0 0 {1+i*.00001:.8f}\n'
        yield f'!    total energy = {-2-i*.001:.9f} Ry\n'
    yield f'bfgs converged in {count} scf cycles and {count} bfgs steps\nEnd of BFGS Geometry Optimization\nJOB DONE.\n'


def nwchem_block(number,geometry=True):
    text=f'                                 NWChem DFT Module\n Total DFT energy = {-10-number*.0001:.8f}\n'
    if geometry:
        text+=(' DFT ENERGY GRADIENTS\n\n atom coordinates gradient\n x y z x y z\n'
               f' 1 H 0.0 0.0 0.0 0.0 0.0 0.001\n 2 H 0.0 0.0 {1+number*.00001:.8f} 0.0 0.0 -0.001\n\n')
    return text


def test_progress_does_not_repeat_read_ahead_eof():
    events=[]
    with output_read_session(progress=lambda *x:events.append(x)):
        report=load_progress('Reading',100)
        for _ in range(5000):report(100)
    assert len(events)==2 and events[-1]==('Reading',100,100)


@pytest.mark.parametrize('variable',[False,True])
def test_qe_matches_ase_structures_cells_energies_forces_and_keeps_all_frames(tmp_path,variable):
    from ase.io import read
    path=tmp_path/'relax.pwo';path.write_text(''.join(qe_text(1003,variable)))
    expected=read(path,format='espresso-out',index=':',results_required=False)
    events=[];doc=load_document(path,progress=lambda *args:events.append(args))
    assert len(doc.frames)==len(expected)==1003
    for actual,reference in zip(doc.frames,expected):
        assert actual.symbols==reference.get_chemical_symbols()
        np.testing.assert_array_equal(actual.positions,reference.positions)
        np.testing.assert_array_equal(actual.cell,reference.cell)
        assert actual.energy_ev==reference.get_potential_energy()
    assert not any(f.info.get('optimization_converged') for f in doc.frames[:-1])
    assert doc.frames[-1].info['optimization_converged']
    assert any('Quantum ESPRESSO' in e[0] for e in events)
    path.write_text(path.read_text().replace(f'bfgs converged in 1003 scf cycles and 1003 bfgs steps','The maximum number of steps has been reached.'))
    assert not any(f.info.get('optimization_converged') for f in load_document(path).frames)


def test_qe_job_boundaries_and_final_reprinted_structure(tmp_path):
    path=tmp_path/'jobs.pwo'
    text=''.join(qe_text(3))+'ATOMIC_POSITIONS (angstrom)\nH 0 0 0\nH 0 0 1.00002\n'
    path.write_text(text+''.join(qe_text(2)).replace('bfgs converged in 2 scf cycles and 2 bfgs steps','Stopped'))
    frames=load_document(path).frames
    assert len(frames)==6 and frames[3].info['optimization_converged']
    assert not frames[-1].info.get('optimization_converged')
    assert frames[-1].info['calculation_index']==1


def test_cp2k_many_spectra_have_only_their_next_printed_energy(tmp_path):
    from test_cp2k_v240 import HEADER,COORD,TD
    count=1003;path=tmp_path/'long.out'
    path.write_text(HEADER+''.join(f'OPTIMIZATION STEP: {i+1}\n'+COORD+TD+
        f' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-10-i*.0001:.8f}\n' for i in range(count)))
    doc=load_document(path)
    assert len(doc.frames)==len(doc.electronic_spectra)==count
    for i,s in enumerate(doc.electronic_spectra):
        assert s.reference.energy_ev/Hartree==pytest.approx(-10-i*.0001)
        assert len(s.transitions)==2


def test_xtb_orbitals_keep_cycle_associations(tmp_path):
    count=2003;path=tmp_path/'long.out'
    path.write_text(' * xtb version 6.7.0\n'+''.join(
        f' ... CYCLE {i+1} ...\n * total energy : {-10-i*.0001:.8f} Eh\n'
        ' # Occupation Energy/Eh Energy/eV\n 1 2.0 -0.5 -13.6057\n 2 0.0 0.1 2.7211\n\n'
        for i in range(count))+' *** GEOMETRY OPTIMIZATION CONVERGED AFTER 2003 ITERATIONS ***\n')
    doc=load_document(path);r=doc.calculation_results
    assert len(r.steps)==len(r.orbitals)==count
    assert [s.step_index for s in r.orbitals]==list(range(count))
    assert r.steps[-1].converged and not doc.frames


@pytest.mark.parametrize('continuations',[False,True])
def test_nwchem_matches_ase_for_geometries_and_long_geometry_free_continuations(tmp_path,continuations):
    from ase.io import read
    path=tmp_path/'nwchem.nwo'
    text=' Northwest Computational Chemistry Package\n'+nwchem_block(0)+''.join(nwchem_block(i,not continuations) for i in range(1,1003))
    text+=nwchem_block(1003)+' Optimization converged\n'
    path.write_text(text)
    old=read(path,format='nwchem-out',index=':')
    doc=load_document(path)
    assert len(doc.frames)==len(old)==(2 if continuations else 1004)
    for a,b in zip(doc.frames,old):
        np.testing.assert_array_equal(a.positions,b.positions)
        np.testing.assert_array_equal(a.cell,b.cell)
        assert a.energy_ev==b.get_potential_energy()
        forces=b.get_forces()
        assert a.info['cartesian_max_force_ev_ang']==float(np.abs(forces).max())
    assert doc.frames[-1].info['optimization_converged']
    assert not any(f.info.get('optimization_converged') for f in doc.frames[:-1])


def test_success_marks_only_matching_geometry_and_edits_remove_status(gui,tmp_path):
    from test_orca_loading_v260 import make_orca
    doc=load_document(make_orca(tmp_path/'opt.out',4))
    assert [bool(f.info.get('optimization_converged')) for f in doc.frames]==[False,False,False,True]
    w=gui.window;w.documents=[doc];w.current_doc=0;w.frame_index=3
    w.files_tree.clear();w._add_document_tree(0,doc);w.change_frame(3)
    assert 'converged' in w._frame_tree_items[0,3].text(0)
    w.selection=[0,1];w._refresh_measurement();w.measurement_value.setValue(1.4);w._apply_measurement_value()
    assert not w.frame.info.get('optimization_converged')
    w.undo_edit();assert w.frame.info['optimization_converged']


def test_cp2k_and_vasp_convergence_has_a_geometry_not_a_normal_exit(tmp_path):
    from test_cp2k_v240 import HEADER,COORD,ENERGY,METRICS
    p=tmp_path/'cp2k.out';p.write_text(HEADER+COORD+ENERGY+METRICS+' GEOMETRY OPTIMIZATION COMPLETED\n')
    assert load_document(p).frames[-1].info['optimization_converged']
    p.write_text(HEADER+COORD+ENERGY+'PROGRAM ENDED AT today\n')
    assert not load_document(p).frames[-1].info.get('optimization_converged')
    from test_vasp_v210 import HEADER as VH,GEOMETRY as VG,ENERGY as VE
    v=tmp_path/'OUTCAR';v.write_text(VH.replace('IBRION = 5','IBRION = 2')+VG+VE+
        ' reached required accuracy - stopping structural energy minimisation\n')
    assert load_document(v).frames[-1].info['optimization_converged']


def test_atom_legend_is_distinct_visible_elements_with_no_structure_mutation():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.renderer import MoleculeRenderer,rgb
    from lele.atom_legend import AtomLegend,legend_samples
    from lele.atom_appearance import AtomAppearance
    frame=Frame(['O','H','H','C'],[[0,0,0],[0,0,1],[1,0,0],[5,0,0]],
        atom_appearance={0:AtomAppearance(color='#123456'),3:AtomAppearance(visible=False)})
    draw=MoleculeRenderer(vtkRenderer());before=frame.clone();draw.set_scene(frame)
    samples=legend_samples(draw);legend=AtomLegend(vtkRenderer());legend.set_samples(samples,draw.options)
    assert [(s['symbol'],s['source_index']) for s in samples]==[('O',0),('H',1)]
    assert [label.GetInput() for label in legend.labels]==['O','H']
    assert legend.actors[0].GetPosition()[0]<legend.actors[1].GetPosition()[0]
    np.testing.assert_allclose(legend.actors[0].GetProperty().GetColor(),rgb('#123456'))
    assert all(not a.GetPickable() for a in legend.actors)
    assert legend.renderer.GetActors().GetNumberOfItems()==2
    draw.renderer.GetActiveCamera().Azimuth(70);legend.layout()
    assert legend.renderer.GetActiveCamera().GetPosition()==(0.,0.,10.)
    np.testing.assert_array_equal(before.positions,frame.positions)
    assert frame.bond_added==before.bond_added and frame.symbols==before.symbols
    legend.set_samples([],draw.options);assert not legend.samples


def test_legacy_legend_flag_does_not_add_a_main_canvas_overlay(tmp_path):
    from vtkmodules.vtkRenderingCore import vtkRenderer,vtkRenderWindow,vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from lele.renderer import MoleculeRenderer
    window=vtkRenderWindow();window.SetOffScreenRendering(True);window.SetSize(640,480)
    scene=vtkRenderer();window.AddRenderer(scene);draw=MoleculeRenderer(scene)
    frame=Frame(['O','H','H'],[[0,0,0],[0,0,1],[1,0,0]],info={'optimization_converged':True})
    def capture():
        window.Render();image=vtkWindowToImageFilter();image.SetInput(window)
        image.ReadFrontBufferOff();image.Update()
        return vtk_to_numpy(image.GetOutput().GetPointData().GetScalars()).copy()
    try:
        draw.set_scene(frame,reset_camera=True);before=capture();cam=scene.GetActiveCamera();position=cam.GetPosition()
        draw.options.atom_legend=True;draw.set_scene(frame)
        assert cam.GetPosition()==position
        np.testing.assert_array_equal(before,capture())
        assert window.GetRenderers().GetNumberOfItems()==1
    finally:window.Finalize()



def test_data_task_dialog_is_delayed_enabled_and_qt_timer_runs(gui):
    from PySide6.QtCore import QTimer
    from lele.operations import OperationProgress,run_data_task
    w=gui.window;main=threading.get_ident();observed=[];threads=[];ticks=[]
    timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(10)
    def observe():
        observed.extend((p.isVisible(),p.isEnabled(),p.labelText()) for p in gui.app.topLevelWidgets()
                        if isinstance(p,OperationProgress))
    QTimer.singleShot(500,observe)
    def calculate():
        threads.append(threading.get_ident());report=load_progress('Processing frames',20)
        for i in range(20):report(i);sleep(.035)
        report(20);return 42
    try:assert run_data_task(w,'Calculating data',calculate)==42
    finally:timer.stop()
    assert threads==[threads[0]] and threads[0]!=main and len(ticks)>10
    assert any(visible and enabled and 'Elapsed' in label for visible,enabled,label in observed)
    with patch.object(OperationProgress,'show') as show:
        assert run_data_task(w,'Quick',lambda:7)==7
        show.assert_not_called()


def test_cancellable_data_task_stops_cooperatively_and_propagates_errors(gui):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QPushButton
    from lele.operations import OperationProgress,run_data_task
    clicked=[]
    def cancel():
        for p in gui.app.topLevelWidgets():
            if isinstance(p,OperationProgress) and p.cancellable:
                p.findChild(QPushButton).click();clicked.append(True)
    QTimer.singleShot(500,cancel)
    def calculate():
        for _ in range(200):check_load_cancelled();sleep(.01)
        return 'should not finish'
    with pytest.raises(LoadCancelled):run_data_task(gui.window,'Cancellable',calculate,cancellable=True)
    assert clicked
    with pytest.raises(ValueError,match='source error'):
        run_data_task(gui.window,'Error',lambda:(_ for _ in ()).throw(ValueError('source error')))


def test_second_email_and_legacy_legend_project_remain_loadable(gui,tmp_path):
    from lele import APP_CONTACT_EMAIL_SECONDARY
    from test_large_files_v250 import attach
    from lele.core import Document
    w=attach(gui,Document(tmp_path/'a.xyz','XYZ',[Frame(['H'],[[0,0,0]])]))
    w.render_options.atom_legend=True  # Legacy project field remains readable; no main overlay.
    path=tmp_path/'legend.lele';assert w.save_project_to(path)
    from lele.project_file import load_project
    state=load_project(path);assert state['documents'][0]['options'].atom_legend
    assert APP_CONTACT_EMAIL_SECONDARY in w.welcome_page.contact_label.text()
