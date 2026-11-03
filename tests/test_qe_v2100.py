"""QE PW input, vc-relax records, PH frequencies and explicit phonon binding."""
from pathlib import Path
from math import pi
from unittest.mock import patch
import os
import numpy as np
import pytest
from lele.core import Frame,Document
from lele.formats import load_document
from lele.qe_results import Ry,Bohr
from lele.qe_phonons import PhononMode,bind_qe_phonons
from lele.boundary import boundary_view
from lele.render_options import RenderOptions
from lele.project_file import save_project,load_project
from lele.trajectory_analysis import displacement_share
from test_periodic_fragment_ui_v171 import gui
from test_long_operations_v270 import qe_text


def write(tmp_path,name,text):
    p=tmp_path/name;p.write_text(text);return p


def input_text(unit='crystal',position='0.5 0 0'):
    return f'''&CONTROL
 calculation='vc-relax'
/
&SYSTEM
 ibrav=0, nat=1, ntyp=1, ecutwfc=50
/
&ELECTRONS
 conv_thr=1.0d-8
/
ATOMIC_SPECIES
H 1.008 H.UPF
CELL_PARAMETERS angstrom
4 0 0
0 4 0
0 0 4
ATOMIC_POSITIONS {unit}
H {position}
K_POINTS gamma
'''


def modes_text(q='0.5 0 0',vector='1 0 0 1 0 0'):
    return f'''diagonalizing the dynamical matrix ...
 q = {q}
 *************************************************************************
 freq ( 1) = -1.0 [THz] = -33.356410 [cm-1]
 ( {vector} )
 freq ( 2) = 2.0 [THz] = 66.712820 [cm-1]
 ( 0 0 0 0 1 0 )
 freq ( 3) = 3.0 [THz] = 100.069230 [cm-1]
 ( 0 0 1 0 0 0 )
 *************************************************************************
'''


@pytest.mark.parametrize('unit,xyz,expected',[
    ('crystal','0.5 0 0',2.),('angstrom','0.5 0 0',.5),('bohr','1 0 0',Bohr)])
def test_pw_input_units_species_cell_and_settings(tmp_path,unit,xyz,expected):
    d=load_document(write(tmp_path,'model.in',input_text(unit,xyz)))
    assert d.frames[0].positions[0,0]==pytest.approx(expected)
    np.testing.assert_array_equal(d.frames[0].cell,np.eye(3)*4)
    assert d.frames[0].symbols==['H'] and all(d.frames[0].pbc)
    assert d.calculation_results.settings['control']['calculation']=='vc-relax'
    assert d.frames[0].energy_ev is None


def test_pw_variable_cell_is_carried_across_separated_cards_and_raw_energies_preserved(tmp_path):
    text=''.join(qe_text(2,True)).replace('\n\nATOMIC_POSITIONS','\n\n\n\n\nATOMIC_POSITIONS')
    d=load_document(write(tmp_path,'job.pwo',text))
    assert len(d.frames)==2 and d.frames[-1].cell[0,0]==5.0001
    assert d.frames[-1].info['qe_total_energy_ry']==-2.001
    assert d.frames[-1].energy_ev==-2.001*Ry
    assert d.frames[-1].info['optimization_converged']


def test_pw_incomplete_tail_keeps_complete_records(tmp_path):
    text=''.join(qe_text(2))+'ATOMIC_POSITIONS (angstrom)\nH 0 0 0\n'
    d=load_document(write(tmp_path,'running.pwo',text))
    assert len(d.frames)==2 and 'Incomplete trailing' in d.note


def test_pw_multiple_evaluations_on_one_geometry_are_not_overwritten(tmp_path):
    d=load_document(write(tmp_path,'scf.pwo',''.join(qe_text(1))+'! total energy = -3.0 Ry\n'))
    assert len(d.frames)==2
    assert [f.info['qe_total_energy_ry'] for f in d.frames]==[-2.,-3.]


def test_input_and_pw_output_settings_survive_projects(tmp_path):
    docs=[load_document(write(tmp_path,'x.in',input_text())),load_document(write(tmp_path,'x.pwo',''.join(qe_text(3))))]
    state=dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0) for d in docs],current_document=0)
    save_project(tmp_path/'pw.lele',state)
    saved=load_project(tmp_path/'pw.lele')['documents']
    assert saved[0]['document'].calculation_results.settings['system']['ecutwfc']==50
    assert len(saved[1]['document'].frames)==3


def test_phonon_stdout_is_distinct_from_pw_and_does_not_invent_vectors(tmp_path):
    text=''.join(qe_text(1)).split('!')[0].replace('Program PWSCF','Program PHONON')
    text+='q = ( 0 0 0 )\nfreq ( 1) = -1.0 [THz] = -33.356410 [cm-1]\nJOB DONE.\n'
    d=load_document(write(tmp_path,'job.out03',text))
    assert d.format_name=='QE PHONON output' and len(d.frames)==1 and len(d.vibrations)==1
    assert d.vibrations[0].modes[0].displacements is None
    assert d.calculation_results.jobs[0].termination=='Completed (JOB DONE)'


def test_phonon_frequencies_survive_without_a_printed_structure(tmp_path):
    text='Program PHONON v.7.3.1\nq = (0 0 0)\nfreq (1) = 1 [THz] = 33.356410 [cm-1]\n'
    d=load_document(write(tmp_path,'ph.out',text))
    assert not d.frames and d.calculation_results.jobs[0].frequency_count==1
    assert d.format_name=='QE PHONON output'


def test_partial_mode_vectors_keep_the_frequency(tmp_path):
    text=modes_text().replace('( 1 0 0 1 0 0 )','')
    d=load_document(write(tmp_path,'partial.modes',text))
    s=d.calculation_results.phonon_sets[0]
    assert len(s.modes)==3 and s.modes[0].displacements is None
    assert s.modes[0].frequency_cm1==-33.356410


def test_phonon_only_file_keeps_q_order_without_fabricating_atoms(tmp_path):
    path=write(tmp_path,'matdyn.modes',modes_text()+modes_text('0 0 0')+modes_text('0.5 0 0'))
    d=load_document(path)
    assert not d.frames and not d.vibrations
    assert len(d.calculation_results.phonon_sets)==3
    assert [s.qpoint for s in d.calculation_results.phonon_sets]==[(.5,0.,0.),(0.,0.,0.),(.5,0.,0.)]
    assert d.calculation_results.jobs[0].frequency_count==9
    assert d.calculation_results.phonon_sets[0].modes[0].imaginary


def test_explicit_binding_preserves_complex_vectors_and_unmatched_reference_fails(tmp_path):
    d=load_document(write(tmp_path,'matdyn.modes',modes_text()))
    ref=Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3)
    with pytest.raises(ValueError,match='alat'):bind_qe_phonons(d,ref,0.)
    with pytest.raises(ValueError,match='atom count'):bind_qe_phonons(d,Frame(['H','H'],np.zeros((2,3)),np.eye(3)),4.)
    bound=bind_qe_phonons(d,ref,4.)
    mode=bound.vibrations[0].modes[0]
    assert mode.can_animate and mode.q_fractional==(.5,0.,0.)
    np.testing.assert_array_equal(mode.imaginary_displacements,[[0,1,0]])
    assert mode.ir_intensity is None and mode.raman_activity is None
    assert not d.frames


def test_complex_motion_cycle_amplitude_and_participation():
    m=PhononMode(1,100.,np.array([[1,0,0],[0,0,0]]),
                 imaginary_displacements=np.array([[0,1,0],[0,0,2]]),q_fractional=(0.,0.,0.))
    r=Frame(['H','H'],np.zeros((2,3)))
    np.testing.assert_allclose(m.positions_at(r,0.,.4),[[0,-.2,0],[0,0,-.4]])
    np.testing.assert_allclose(m.positions_at(r,pi/2,.4),[[.2,0,0],[0,0,0]],atol=1.e-15)
    np.testing.assert_allclose(m.positions_at(r,2*pi,.4),m.positions_at(r,0,.4),atol=1.e-15)
    assert displacement_share(m,[1],2)==pytest.approx(4/6)


def test_non_gamma_boundary_bloch_phase_uses_equilibrium_cells():
    ref=Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3)
    mode=PhononMode(1,100.,np.array([[1.,0,0]]),qpoint=(.5,0,0),q_fractional=(.5,0,0))
    preview=mode.preview_frame(ref,pi/2,.3)
    shown=boundary_view(preview,((0,2),(0,1),(0,1)))
    np.testing.assert_allclose(shown.frame.positions,[[.3,0,0],[3.7,0,0]],atol=1.e-14)
    np.testing.assert_array_equal(ref.positions,[[0,0,0]])
    # A phase crossing the boundary must not swap the equilibrium tile IDs.
    preview=mode.preview_frame(ref,-pi/2,.3)
    shown=boundary_view(preview,((0,2),(0,1),(0,1)))
    np.testing.assert_allclose(shown.frame.positions,[[-.3,0,0],[4.3,0,0]],atol=1.e-14)


def test_complex_non_gamma_phase_matches_bloch_time_convention():
    ref=Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3)
    mode=PhononMode(1,100.,np.array([[1.,0,0]]),imaginary_displacements=np.array([[0,1.,0]]),
                    qpoint=(.25,0,0),q_fractional=(.25,0,0))
    shown=boundary_view(mode.preview_frame(ref,0.,.3),((0,2),(0,1),(0,1)))
    np.testing.assert_allclose(shown.frame.positions,[[0,-.3,0],[3.7,0,0]],atol=1.e-14)


def test_unbound_and_bound_qe_results_roundtrip(tmp_path):
    raw=load_document(write(tmp_path,'matdyn.modes',modes_text()))
    ref=Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3)
    bound=bind_qe_phonons(raw,ref,4.)
    state=dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0) for d in (raw,bound)],current_document=1)
    save_project(tmp_path/'q.lele',state);restored=load_project(tmp_path/'q.lele')
    a,b=[x['document'] for x in restored['documents']]
    assert not a.frames and a.calculation_results.jobs[0].frequency_count==3
    assert b.vibrations[0].modes[0].can_animate
    np.testing.assert_array_equal(b.vibrations[0].modes[0].imaginary_displacements,[[0,1,0]])


def test_gui_results_only_binding_and_mode_controls(gui,tmp_path):
    raw=load_document(write(tmp_path,'matdyn.modes',modes_text()))
    gui.attach(Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3));w=gui.window
    ref=w.frame.clone();w._attach_loaded_document(raw)
    from lele.result_availability import results_text
    assert w.frame is None and 'q 1' in results_text(w.doc)
    from lele.qe_reference_dialog import QeReferenceDialog
    def accept(dialog):
        dialog.alat.setValue(4.);return dialog.DialogCode.Accepted
    with patch.object(QeReferenceDialog,'exec',accept):w.assign_qe_phonon_reference()
    assert len(w.doc.vibrations)==1
    w.select_vibration(w.current_doc,0,0,autoplay=False)
    assert w.vibration_controls.play_button.isEnabled()
    assert 'q 1' in w.vibration_controls.description.text()
    np.testing.assert_array_equal(w.frame.positions,ref.positions)


def test_frequency_action_routes_unbound_modes_to_reference_assignment(gui,tmp_path):
    raw=load_document(write(tmp_path,'matdyn.modes',modes_text()))
    gui.window._attach_loaded_document(raw)
    with patch.object(gui.window,'assign_qe_phonon_reference') as assign:
        gui.window.show_frequencies()
    assign.assert_called_once()
    assert raw.calculation_results.phonon_sets[0].modes[0].ir_intensity_unit==''


def test_gui_qe_edit_clears_source_energies_and_forces_and_undo_restores(gui,tmp_path):
    d=load_document(write(tmp_path,'x.pwo',''.join(qe_text(1))))
    f=d.frames[0];f.info['qe_forces_ev_ang']=np.ones((2,3));f.info['cartesian_max_force_ev_ang']=1.
    gui.attach(f);w=gui.window
    w.atom_table.item(1,3).setText('2.0000')
    assert w.frame.energy_ev is None
    assert 'qe_total_energy_ry' not in w.frame.info and 'qe_forces_ev_ang' not in w.frame.info
    w.undo_edit()
    assert w.frame.info['qe_total_energy_ry']==-2.


def test_qe_frequency_csv_keeps_q_coordinates(gui,tmp_path):
    raw=load_document(write(tmp_path,'matdyn.modes',modes_text()))
    bound=bind_qe_phonons(raw,Frame(['H'],[[0,0,0]],np.eye(3)*4,(True,)*3),4.)
    gui.window._attach_loaded_document(bound)
    from lele.vibration_analysis_dialog import VibrationAnalysisDialog
    dialog=VibrationAnalysisDialog(bound,gui.window);gui.addCleanup(dialog.deleteLater)
    path=tmp_path/'q.csv';dialog.write_csv(path)
    import csv
    with path.open(encoding='utf-8-sig',newline='') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==3 and rows[0]['q_x']=='0.5' and rows[0]['q_units']=='Cartesian 2pi/alat'


def test_real_supplied_qe_files():
    directory=os.environ.get('LELE_QE_EXAMPLE_DIR')
    if not directory:pytest.skip('Set LELE_QE_EXAMPLE_DIR; private QE examples are not redistributed')
    root=Path(directory)
    inp=load_document(root/'01_vc-relax.in');pw=load_document(root/'job.out')
    ph=load_document(root/'job.out03');raw=load_document(root/'matdyn.modes')
    assert inp.frames[0].symbols==['N','Cu','Cu','Cu']
    assert inp.frames[0].cell[0,0]==3.81470618
    assert len(pw.frames)==5
    assert [f.info['qe_total_energy_ry'] for f in pw.frames]==[-659.95586890,-659.95597679,-659.95599220,-659.95599220,-659.95599528]
    assert pw.frames[-1].info['optimization_converged']
    np.testing.assert_array_equal(pw.frames[-1].cell,np.eye(3)*3.826675649)
    assert len(ph.vibrations)==4 and sum(len(a.modes) for a in ph.vibrations)==48
    assert not any(m.can_animate for a in ph.vibrations for m in a.modes)
    reference=ph.frames[0];bound=bind_qe_phonons(raw,reference,reference.info['qe_alat_ang'],'PHONON reference')
    assert len(bound.vibrations)==5 and sum(m.can_animate for a in bound.vibrations for m in a.modes)==60
    assert bound.vibrations[0].modes[9].frequency_cm1==626.688678
    assert bound.vibrations[1].modes[0].frequency_cm1==-66.972589
