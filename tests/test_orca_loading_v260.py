"""Long ORCA imports: scientific values, progress, cancellation and Qt responsiveness."""
from pathlib import Path
from unittest.mock import patch
import threading
import time
import numpy as np
import pytest
from ase.units import Hartree
from lele.formats import load_document
from lele.output_text import LoadCancelled, output_read_session, read_output_lines
from test_periodic_fragment_ui_v171 import gui


def wait_until(gui,predicate,timeout=8):
    from PySide6.QtCore import QEventLoop,QTimer
    if predicate():return
    loop=QEventLoop();poll=QTimer();deadline=QTimer();deadline.setSingleShot(True)
    poll.timeout.connect(lambda:loop.quit() if predicate() else None)
    deadline.timeout.connect(loop.quit);poll.start(5);deadline.start(int(timeout*1000))
    loop.exec();poll.stop();deadline.stop()
    assert predicate(),'Background load did not complete'


def orca_text(count,noise=4):
    yield ' O   R   C   A\n | 1> ! B3LYP def2-SVP Opt\n | 2> * xyz 0 1\n'
    for i in range(count):
        yield (f'GEOMETRY OPTIMIZATION CYCLE {i+1}\n'
               f'CARTESIAN COORDINATES (ANGSTROEM)\n----------------\n'
               f'O 0.0 0.0 0.0\nH 0.0 0.0 {1+i*.00001:.8f}\n\n')
        yield '    12   -75.000001   0.0000001    0.0000002\n'*noise
        yield (f'FINAL SINGLE POINT ENERGY {-75-i*.0001:.10f}\n'
               f'MAX gradient {1/(i+1):.10f} 0.0003\n'
               f'Total Dipole Moment : 0.0 0.0 {i*.000001:.8f}\n')
    yield 'THE OPTIMIZATION HAS CONVERGED\nORCA TERMINATED NORMALLY\n'


def make_orca(path,count,noise=4):
    with path.open('w') as f:f.writelines(orca_text(count,noise))
    return path


def test_progress_is_observable_without_changing_values_and_bisect_keeps_references(tmp_path):
    path=make_orca(tmp_path/'many.out',1803)
    progress=[];doc=load_document(path,progress=lambda *args:progress.append(args))
    assert len(doc.frames)==len(doc.calculation_results.steps)==len(doc.dipoles)==1803
    for i in (0,900,1802):
        assert doc.frames[i].energy_ev/Hartree==pytest.approx(-75-i*.0001)
        assert doc.calculation_results.steps[i].cycle==i+1
        assert doc.calculation_results.steps[i].convergence['max_force'][0]==pytest.approx(1/(i+1),abs=1.e-10)
        np.testing.assert_array_equal(doc.dipoles[i].reference.positions,doc.frames[i].positions)
        assert doc.dipoles[i].reference.energy_ev==doc.frames[i].energy_ev
    labels={label for label,_,_ in progress}
    assert any(label.startswith('Reading ') for label in labels)
    assert 'ORCA: identifying calculation jobs' in labels
    assert 'ORCA: geometry, energies and orbitals' in labels
    assert 'Collecting structure frames' in labels and 'ORCA: dipoles and excited states' in labels
    assert all(0<=value<=total for _,value,total in progress if total)
    for label in labels:
        values=[(value,total) for phase,value,total in progress if phase==label]
        assert values[-1][0]==values[-1][1]
    assert len(progress)<100  # signal traffic is throttled, not one event per source line


@pytest.mark.parametrize('encoding',['utf-8','utf-16','utf-16-le','utf-16-be'])
def test_byte_progress_handles_windows_encodings(tmp_path,encoding):
    path=tmp_path/'encoded.out';path.write_text(''.join(orca_text(2)),encoding=encoding)
    events=[];doc=load_document(path,progress=lambda *args:events.append(args))
    assert len(doc.frames)==2
    reading=[(value,total) for label,value,total in events if label.startswith('Reading ')]
    assert reading[-1]==(path.stat().st_size,path.stat().st_size)
    assert all(value<=total for value,total in reading)


def test_cancellation_during_property_pass_never_returns_partial_results(tmp_path):
    path=make_orca(tmp_path/'cancel.out',1200);stage=['']
    def progress(label,*_):stage[0]=label
    with pytest.raises(LoadCancelled):
        load_document(path,progress=progress,cancelled=lambda:stage[0]=='ORCA: dipoles and excited states')


def test_small_output_uses_worker_and_displays_stage_and_elapsed_without_threshold_patch(gui,tmp_path):
    path=make_orca(tmp_path/'small.out',2)
    assert path.stat().st_size<4*1024*1024
    w=gui.window;w._closing=False;w._backend_state='ready'
    w.show();gui.app.processEvents()
    entered=threading.Event();release=threading.Event();threads=[];attached=[]
    original=load_document
    def gated(path,*,cancelled=None,progress=None):
        threads.append(threading.get_ident());progress('ORCA: test phase',30,100);entered.set()
        while not release.wait(.005):
            if cancelled():raise LoadCancelled()
        return original(path,cancelled=cancelled,progress=progress)
    try:
        with patch('lele.formats.load_document',side_effect=gated),patch.object(w,'_attach_loaded_document',side_effect=lambda d:attached.append(threading.get_ident())):
            w.open_path(path)
            wait_until(gui,lambda:entered.is_set() and 'test phase' in w._file_load_progress.labelText())
            dialog=w._file_load_progress
            assert '30%' in dialog.labelText() and 'Elapsed' in dialog.labelText()
            assert dialog.maximum()==1000 and dialog.value()==300
            wait_until(gui,dialog.isVisible)
            release.set();wait_until(gui,lambda:w._file_load_active is None)
            wait_until(gui,lambda:not gui.app._lele_file_loaders)
    finally:release.set()
    assert threads[0]!=threading.get_ident() and attached==[threading.get_ident()]


def test_long_orca_load_uses_real_qt_event_loop_and_keeps_timer_alive(gui,tmp_path):
    from PySide6.QtCore import QEventLoop,QTimer
    path=make_orca(tmp_path/'responsive.out',2403,noise=50)
    w=gui.window;w._closing=False;w._backend_state='ready'
    w.show();gui.app.processEvents()
    ticks=[];loop=QEventLoop();original=w._attach_loaded_document;attached=[];start=time.monotonic();stages=[]
    def attach(doc):
        attached.append((threading.get_ident(),len(ticks),time.monotonic()-start));original(doc)
        QTimer.singleShot(0,loop.quit)
    timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()))
    deadline=QTimer();deadline.setSingleShot(True);deadline.timeout.connect(loop.quit)
    with patch.object(w,'_attach_loaded_document',side_effect=attach):
        timer.start();deadline.start(15000);w.open_path(path)
        w._file_load_active.progress.connect(lambda label,value,total:stages.append((time.monotonic()-start,label,value,total)))
        loop.exec();timer.stop();deadline.stop()
    wait_until(gui,lambda:not gui.app._lele_file_loaders)
    assert attached and attached[0][0]==threading.get_ident() and attached[0][1]>=3, (attached,[t-start for t in ticks],stages)
    assert len(w.doc.frames)==2403 and len(w.doc.dipoles)==2403
    assert w._file_load_active is None
    w.frame_spin.setValue(2403)
    assert w.frame_index==2402 and w.frame.positions[1,2]==pytest.approx(1.02402)


def test_close_during_import_cancels_without_attaching_or_dangling_thread(gui,tmp_path):
    path=make_orca(tmp_path/'closing.out',2);w=gui.window;w._closing=False;w._backend_state='ready'
    entered=threading.Event();attached=[]
    def gated(path,*,cancelled=None,progress=None):
        entered.set()
        while not cancelled():time.sleep(.002)
        raise LoadCancelled()
    with patch('lele.formats.load_document',side_effect=gated),patch.object(w,'_attach_loaded_document',side_effect=attached.append):
        w.open_path(path);wait_until(gui,entered.is_set)
        w._closing=True;w._cancel_file_imports()
        wait_until(gui,lambda:w._file_load_active is None and not gui.app._lele_file_loaders)
    assert not attached and w._file_load_progress is None


def test_indexed_references_do_not_cross_a_compound_job_without_coordinates(tmp_path):
    path=tmp_path/'compound.out'
    path.write_text(''.join(orca_text(2))+'\nJOB NUMBER 2\nTotal Dipole Moment : 1 2 3\nORCA TERMINATED NORMALLY\n')
    doc=load_document(path)
    assert len(doc.calculation_results.jobs)==2 and len(doc.dipoles)==3
    assert doc.dipoles[-1].reference is None


def test_background_output_then_multiple_small_structures_drain_the_whole_queue(gui,tmp_path):
    first=make_orca(tmp_path/'first.out',2)
    second=tmp_path/'second.xyz';second.write_text('1\nsecond\nH 0 0 1\n')
    third=tmp_path/'third.xyz';third.write_text('1\nthird\nH 0 0 2\n')
    w=gui.window;w._closing=False;w._backend_state='ready';attached=[]
    with patch.object(w,'_attach_loaded_document',side_effect=lambda d:attached.append(d.path)):
        w.open_path(first);w.open_path(second);w.open_path(third)
        wait_until(gui,lambda:len(attached)==3 and w._file_load_active is None)
        wait_until(gui,lambda:not gui.app._lele_file_loaders)
    assert attached==[first.resolve(),second.resolve(),third.resolve()] and not w._file_load_queue
