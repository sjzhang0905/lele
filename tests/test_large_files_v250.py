"""Uncapped imports retain science, navigation and cancellation on long files."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import threading
import time

import numpy as np
import pytest
from ase.units import Hartree

from lele.core import Document, Frame
from lele.formats import load_document
from lele.output_text import LoadCancelled, output_read_session, read_output_lines
from lele.calculation_results import CalculationJob, CalculationResults, CalculationStage, CalculationStep
from test_periodic_fragment_ui_v171 import gui


def write(tmp_path, name, text):
    path=tmp_path/name;path.write_text(text);return path


def cp2k_xyz(count):
    return ''.join(f'2\n i = {i}, time = {i*.5}, E = {-10-i*.0001:.8f}\n'
                   f'O 0 0 0\nH 0 0 {1+i*.00001:.8f}\n' for i in range(count))


def attach(gui,doc):
    w=gui.window;w.documents=[doc];w.current_doc=0;w.frame_index=0;w.selection=[]
    w.files_tree.clear();w._add_document_tree(0,doc);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w


def wait_until(gui,predicate,timeout=8):
    # QTest.qWait holds the Python GIL on some PySide builds. A real event
    # loop matches the application and allows the parser thread to run.
    from PySide6.QtCore import QEventLoop,QTimer
    if predicate():return
    loop=QEventLoop();poll=QTimer();deadline=QTimer();deadline.setSingleShot(True)
    poll.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline.timeout.connect(loop.quit);poll.start(5);deadline.start(int(timeout*1000))
    loop.exec();poll.stop();deadline.stop()
    assert predicate(),'Background load did not complete'



def test_cp2k_xyz_over_750_keeps_every_coordinate_energy_time_and_source(tmp_path):
    doc=load_document(write(tmp_path,'long.xyz',cp2k_xyz(1803)))
    assert len(doc.frames)==len(doc.calculation_results.steps)==1803
    assert doc.calculation_results.steps[-1].frame_index==1802
    last=doc.frames[-1]
    assert last.energy_ev/Hartree==pytest.approx(-10.1802)
    assert last.info['time_fs']==901 and last.info['source_line']==1802*4+1
    assert not any(last.pbc) and not last.cell.any()
    np.testing.assert_allclose(last.positions[1],[0,0,1.01802])
    # Editing the displayed structure must still leave printed results intact.
    last.positions[1,2]=9
    assert doc.calculation_results.steps[-1].geometry.positions[1,2]==pytest.approx(1.01802)


def test_plain_xyz_over_750_and_extended_xyz_metadata_remain_distinct(tmp_path):
    plain=write(tmp_path,'plain.xyz',''.join(f'1\nframe {i}\nH 0 0 {i/1000}\n' for i in range(1003)))
    doc=load_document(plain)
    assert len(doc.frames)==1003 and doc.frames[-1].positions[0,2]==1.002
    assert all(f.energy_ev is None for f in doc.frames)
    ext=write(tmp_path,'extended.xyz',('1\nLattice="8 0 0 0 9 0 0 0 10" '
        'Properties=species:S:1:pos:R:3:forces:R:3 pbc="T T F" energy=-2.5\n'
        'H 0 0 1 .1 .2 .3\n')*1003)
    doc=load_document(ext)
    assert len(doc.frames)==1003
    np.testing.assert_array_equal(doc.frames[-1].cell,np.diag([8,9,10]))
    assert doc.frames[-1].pbc==(True,True,False) and doc.frames[-1].energy_ev==-2.5
    assert doc.frames[-1].info['cartesian_max_force_ev_ang']==.3


def test_streamed_xdatcar_over_750_keeps_variable_cells_and_missing_energies(tmp_path):
    header='H\n1\n{a} 0 0\n0 9 0\n0 0 10\nH\n1\n'
    chunks=[header.format(a=8)]
    for i in range(1003):
        if i==800:chunks.append(header.format(a=12))
        chunks.append(f'Direct configuration= {i+1}\n0.5 0.25 0.1\n')
    doc=load_document(write(tmp_path,'XDATCAR_long',''.join(chunks)))
    assert len(doc.frames)==1003
    assert doc.frames[799].positions[0,0]==4 and doc.frames[800].positions[0,0]==6
    assert doc.calculation_results.steps[-1].cycle==1003
    assert all(f.energy_ev is None for f in doc.frames)


def test_long_outcar_stays_e0_only(tmp_path):
    from test_vasp_v210 import HEADER,GEOMETRY
    text=HEADER.replace('IBRION = 5','IBRION = 2')
    text+=''.join(GEOMETRY+f' FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n'
        f' free energy TOTEN = {-20-i*.01}\n'
        f' energy without entropy = -5 energy(sigma->0) = {-10-i*.01}\n' for i in range(1003))
    doc=load_document(write(tmp_path,'OUTCAR_long',text))
    assert len(doc.frames)==1003 and doc.frames[-1].energy_ev==pytest.approx(-20.02)
    assert doc.frames[-1].energy_ev!=doc.calculation_results.steps[-1].info['vasp_free_energy_ev']


@pytest.mark.parametrize('program',['gaussian','orca'])
def test_molecular_optimization_outputs_over_750_keep_last_step(tmp_path,program):
    if program=='gaussian':
        text='Entering Gaussian System\n #p PBE/def2SVP opt\n\n Charge = 0 Multiplicity = 1\n'
        for i in range(803):
            text+=(' Standard orientation:\n --------\n Center Atomic Atomic Coordinates\n'
                ' Number Number Type X Y Z\n --------\n'
                f' 1 1 0 0.0 0.0 {i*.001:.6f}\n --------\n'
                f' SCF Done: E(RPBE) = {-10-i*.001:.8f} A.U. after 3 cycles\n')
        name='gaussian.log'
    else:
        text='O   R   C   A\n ! PBE def2-SVP Opt\n * xyz 0 1\n'
        for i in range(803):
            text+=(f' GEOMETRY OPTIMIZATION CYCLE {i+1}\n'
                ' CARTESIAN COORDINATES (ANGSTROEM)\n --------\n'
                f' H 0.0 0.0 {i*.001:.6f}\n\n FINAL SINGLE POINT ENERGY {-10-i*.001:.8f}\n')
        name='orca.out'
    doc=load_document(write(tmp_path,name,text))
    assert len(doc.frames)==803
    assert doc.frames[-1].positions[0,2]==pytest.approx(.802)
    assert doc.frames[-1].energy_ev/Hartree==pytest.approx(-10.802)


def test_siesta_and_xtb_trajectories_over_750(tmp_path):
    ani=write(tmp_path,'long.ANI',''.join(f'1\nstep {i}\nH 0 0 {i*.001}\n' for i in range(803)))
    doc=load_document(ani)
    assert len(doc.frames)==803 and doc.frames[-1].positions[0,2]==pytest.approx(.802)
    xtb=write(tmp_path,'xtbopt.log',''.join(f'1\n energy: {-10-i*.001:.8f} gnorm: .001 xtb: 6.7.0\nH 0 0 {i*.001}\n' for i in range(803)))
    doc=load_document(xtb)
    assert len(doc.frames)==803 and doc.frames[-1].energy_ev/Hartree==pytest.approx(-10.802)


def test_explicit_api_limits_still_raise_without_silent_last_frame_fallback(tmp_path):
    for name,text in [('cp2k.xyz',cp2k_xyz(4)),('plain.xyz','1\n\nH 0 0 0\n'*4),
                      ('extended.xyz','1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n'*4)]:
        with pytest.raises(ValueError,match='exceeds 2'):load_document(write(tmp_path,name,text),max_frames=2)


def test_source_lines_cache_is_one_load_only_and_uses_current_file_bytes(tmp_path):
    p=write(tmp_path,'text.out','first\nsecond\n')
    with output_read_session():
        first=read_output_lines(p)
        assert first is read_output_lines(p)
    p.write_text('changed\n')
    with output_read_session():assert read_output_lines(p)==['changed']


def test_orca_optional_analyses_share_one_decoded_source(tmp_path):
    import lele.output_text as source
    path=write(tmp_path,'orca.out','O   R   C   A\nCARTESIAN COORDINATES (ANGSTROEM)\nH 0 0 0\n\nFINAL SINGLE POINT ENERGY -1\n')
    with patch.object(source,'open_output_text',wraps=source.open_output_text) as opened:
        doc=load_document(path)
    assert len(doc.frames)==1 and opened.call_count==1


def test_streamed_cp2k_xyz_never_reads_all_bytes_and_retains_complete_tail(tmp_path):
    path=write(tmp_path,'cp2k.xyz',cp2k_xyz(803)+'2\n i = 804, E = -50\nH 0 0 0\n')
    with patch.object(Path,'read_bytes',side_effect=AssertionError('whole-file read')):
        doc=load_document(path)
    assert len(doc.frames)==803 and 'Incomplete trailing' in doc.note


def test_utf16_streamed_xyz_and_source_text(tmp_path):
    path=tmp_path/'cp2k.xyz';path.write_bytes(cp2k_xyz(803).encode('utf-16'))
    assert len(load_document(path).frames)==803
    path=tmp_path/'cp2k.out';path.write_bytes(('CP2K| version string: CP2K\n'
        'ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] -1\n').encode('utf-16-le'))
    assert load_document(path).calculation_results.steps[0].energy_ev/Hartree==-1


def test_long_lazy_tree_reaches_last_frame_and_keyboard_crosses_pages(gui,tmp_path):
    doc=load_document(write(tmp_path,'long.xyz',cp2k_xyz(2003)))
    w=attach(gui,doc)
    assert w.frame_spin.maximum()==2003
    w.frame_spin.setValue(2003)
    assert w.frame_index==2002 and w.files_tree.currentItem().text(0).startswith('Frame 2003')
    w.change_frame(255);w._step_next()
    assert w.frame_index==256 and w.frame_spin.value()==257
    w._step_previous();assert w.frame_index==255
    w.frame_spin.setValue(2003);w._step_next();assert w.frame_index==0


def test_multistage_lazy_tree_uses_each_stage_sequence_without_crossing(gui,tmp_path):
    frames=[Frame(['H'],[[0,0,i*.001]],info={'stage_index':i//1000}) for i in range(2000)]
    results=CalculationResults('CP2K',jobs=[CalculationJob(0,1)],stages=[
        CalculationStage(0,0,'First','optimization',1),CalculationStage(1,0,'Second','optimization',2)])
    doc=Document(tmp_path/'staged.out','CP2K output',frames,calculation_results=results)
    w=attach(gui,doc);head=w.files_tree.topLevelItem(0)
    second=head.child(1);second.setExpanded(True)
    last_page=second.child(second.childCount()-1);last_page.setExpanded(True)
    w.files_tree.setCurrentItem(last_page.child(last_page.childCount()-1))
    assert w.frame_index==1999 and w.frame_spin.maximum()==1000
    w._step_next();assert w.frame_index==1000
    w._step_previous();assert w.frame_index==1000
    path=tmp_path/'staged.lele'
    assert w.save_project_to(path) and w._load_project_path(path)
    assert w.frame_index==1000 and w.frame_spin.maximum()==1000
    w.frame_spin.setValue(1000);assert w.frame_index==1999


def test_energy_only_lazy_pages_keep_final_record_and_all_curve_points(gui,tmp_path):
    path=write(tmp_path,'cp2k.out','CP2K| version string: CP2K\n'+''.join(
        f'ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-10-i*.001:.8f}\n' for i in range(2003)))
    doc=load_document(path);w=attach(gui,doc)
    group=w.files_tree.topLevelItem(0).child(0);page=group.child(group.childCount()-1)
    page.setExpanded(True);w.files_tree.setCurrentItem(page.child(page.childCount()-1))
    assert w._energy_only_context==(0,2002) and w.frame is None
    assert len(w.show_energy_curve().points())==2003


def test_long_project_roundtrip_keeps_last_frame_and_edits(tmp_path):
    from lele.project_file import save_project,load_project
    from lele.render_options import RenderOptions
    doc=load_document(write(tmp_path,'long.xyz',cp2k_xyz(803)))
    doc.frames[-1].positions[1,2]=5
    path=tmp_path/'long.lele';save_project(path,{'documents':[{'document':doc,'options':RenderOptions()}]})
    restored=load_project(path)['documents'][0]['document']
    assert len(restored.frames)==803 and restored.frames[-1].positions[1,2]==5
    assert restored.calculation_results.steps[-1].geometry.positions[1,2]==pytest.approx(1.00802)


def test_cp2k_stdout_over_750_printed_structures_keeps_energy_pairing(tmp_path):
    from test_cp2k_v240 import HEADER,COORD
    text=HEADER+''.join(f' OPTIMIZATION STEP: {i}\n'+COORD+
        f' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {-10-i*.001:.8f}\n'
        for i in range(803))
    doc=load_document(write(tmp_path,'cp2k.out',text))
    assert len(doc.frames)==803 and doc.frames[-1].energy_ev/Hartree==pytest.approx(-10.802)
    assert doc.calculation_results.steps[-1].frame_index==802


def test_neb_reader_has_no_old_50000_frame_cap(tmp_path):
    from lele.orca_neb import read_xyz_records
    path=write(tmp_path,'long_MEP_ALL_trj.xyz','1\nE -1\nH 0 0 0\n'*50003)
    records=read_xyz_records(path)
    assert len(records)==50003 and records[-1].energy_ev/Hartree==-1


def test_packed_outcar_numeric_columns_still_use_original_semantics():
    from lele.vasp_results import _rows
    rows,end=_rows(['1.00000-2.00000 3.00000'],0,3,1)
    np.testing.assert_array_equal(rows,[[1,-2,3]])
    assert end==1


def test_background_import_keeps_gui_responsive_and_attaches_on_main_thread(gui,tmp_path):
    from PySide6.QtCore import QTimer
    path=write(tmp_path,'background.xyz',cp2k_xyz(803))
    w=gui.window;w._closing=False;w._backend_state='ready'
    entered=threading.Event();release=threading.Event();threads=[];attached=[];ticks=[]
    original=load_document
    def slow(path,*,cancelled=None,progress=None):
        threads.append(threading.get_ident());entered.set()
        while not release.wait(.005):
            if cancelled and cancelled():raise LoadCancelled()
        return original(path,cancelled=cancelled,progress=progress)
    def finish(doc):attached.append((threading.get_ident(),doc))
    timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(2)
    try:
        with patch('lele.file_loading.ASYNC_THRESHOLD',0),patch('lele.formats.load_document',side_effect=slow),patch.object(w,'_attach_loaded_document',side_effect=finish):
            w.open_path(path)
            wait_until(gui,lambda:entered.is_set() and len(ticks)>=4)
            assert w._file_load_active is not None and not attached
            release.set();wait_until(gui,lambda:w._file_load_active is None)
            wait_until(gui,lambda:not gui.app._lele_file_loaders)
    finally:release.set();timer.stop()
    assert threads[0]!=threading.get_ident() and attached[0][0]==threading.get_ident()
    assert len(attached[0][1].frames)==803


def test_cancelled_background_import_adds_no_partial_document_and_queue_continues(gui,tmp_path):
    first=write(tmp_path,'first.xyz',cp2k_xyz(803));second=write(tmp_path,'second.xyz',cp2k_xyz(804))
    w=gui.window;w._closing=False;w._backend_state='ready'
    entered=threading.Event();finished=[]
    original=load_document
    def slow(path,*,cancelled=None,progress=None):
        if Path(path)==first:
            entered.set()
            while not cancelled():time.sleep(.002)
            raise LoadCancelled()
        return original(path,cancelled=cancelled,progress=progress)
    with patch('lele.file_loading.ASYNC_THRESHOLD',0),patch('lele.formats.load_document',side_effect=slow),patch.object(w,'_attach_loaded_document',side_effect=lambda d:finished.append(d)):
        w.open_path(first);w.open_path(second)
        wait_until(gui,entered.is_set)
        w._file_load_progress.canceled.emit()
        wait_until(gui,lambda:len(finished)==1 and w._file_load_active is None)
        wait_until(gui,lambda:not gui.app._lele_file_loaders)
    assert finished[0].path==second.resolve() and len(finished[0].frames)==804


def test_cancellation_is_not_reported_as_parse_failure_or_partial_success(tmp_path):
    path=write(tmp_path,'large.xyz',cp2k_xyz(803))
    calls=[0]
    def cancelled():calls[0]+=1;return calls[0]>20
    with pytest.raises(LoadCancelled):load_document(path,cancelled=cancelled)
