"""CP2K files expose independent printed structures and scientific results."""
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import csv
import json
import numpy as np
import pytest
from ase.units import Hartree,Bohr
from lele.formats import load_document
from lele.legacy_converter import detect_format
from lele.render_options import RenderOptions
from lele.result_availability import has_curve_data
from lele.project_file import save_project,load_project
from lele.property_export import export_transitions
from test_periodic_fragment_ui_v171 import gui

INPUT='''&GLOBAL
 PROJECT example
 RUN_TYPE GEO_OPT
&END
&FORCE_EVAL
 METHOD QS
 &DFT
  CHARGE 1
  MULTIPLICITY 2
  &XC
   &XC_FUNCTIONAL PBE
   &END
  &END
 &END
 &SUBSYS
  &CELL
   ABC [angstrom] 8 9 10
   PERIODIC XY
  &END
  &COORD
   O 0 0 0
   H 0 0 1
  &END
 &END
&END
'''
HEADER=''' CP2K| version string: CP2K version 2026.2
 GLOBAL| Run type GEO_OPT
 GLOBAL| Project name example
 DFT| Charge 0
 DFT| Multiplicity 1
 CELL| Vector a [angstrom]: 8 0 0 |a| = 8
 CELL| Vector b [angstrom]: 0 9 0 |b| = 9
 CELL| Vector c [angstrom]: 0 0 10 |c| = 10
 CELL| Periodicity XY
 - Atoms: 2
'''
COORD=''' MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM

 Atom Kind Element X Y Z Z(eff) Mass
 1 1 O 8 0 0 0 6.0 16.0
 2 2 H 1 0 0 1 1.0 1.0

'''
ENERGY=' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] -10.1\n'
METRICS=''' OPT| Step number 1
 OPT| Maximum gradient 0.0003
 OPT| Convergence limit for maximum gradient 0.0004
 OPT| RMS gradient 0.00005
 OPT| Convergence limit for RMS gradient 0.0001
 OPT| Maximum step size 0.001
 OPT| Convergence limit for maximum step size 0.003
 OPT| RMS step size 0.0005
 OPT| Convergence limit for RMS step size 0.0015
'''
TD=''' Only KERNEL NONE is active for k-point TDDFPT; transition dipole magnitudes are shown.
 State Excitation Transition dipole (a.u.) Oscillator
 number energy (eV) x y z strength (a.u.)
 --------
 TDDFPT| 1 2.0 1.0 2.0 3.0 0.5
 TDDFPT_KPOINT| 1 2 1 4 5 0.25
 TDDFPT| 2 3.0 0.1 0.2 0.3 0.04
'''
XYZ='''2
 i = 1, time = 0.5, E = -10.0
O 0 0 0
H 0 0 1
2
 i = 2, E = -10.2
O 0 0 0
H 0 0 1.1
'''


def write(tmp_path,text,name='cp2k.out'):
    path=tmp_path/name;path.write_text(text);return path


def attach(gui,path):
    w=gui.window;d=load_document(path)
    w.documents=[d];w.current_doc=0;w.frame_index=0;w.selection=[];w.files_tree.clear()
    w._add_document_tree(0,d);w.change_frame(0)
    gui.addCleanup(lambda:[dialog.close() for dialog in list(w._analysis_windows)])
    return w,d


@pytest.mark.parametrize('name',['cp2k.inp','project.restart','renamed.data'])
def test_input_and_restart_inline_structure_and_metadata(tmp_path,name):
    d=load_document(write(tmp_path,INPUT,name))
    assert len(d.frames)==1 and d.frames[0].energy_ev is None and not has_curve_data(d)
    assert d.frames[0].pbc==(True,True,False)
    np.testing.assert_array_equal(d.frames[0].cell,np.diag([8,9,10]))
    assert d.frames[0].info['converter_charge']==1 and d.frames[0].info['converter_mult']==2
    assert d.calculation_results.jobs[0].method=='PBE'


@pytest.mark.parametrize('unit,factor',[('bohr',Bohr),('angstrom',1.),('nm',10.)])
def test_input_coordinate_units_and_kind_alias(tmp_path,unit,factor):
    text=INPUT.replace('O 0 0 0','UNIT '+unit+'\n   oxygen 0 0 0').replace('H 0 0 1','hydrogen 0 0 1')
    text=text.replace(' &END\n&END\n','  &KIND oxygen\n   ELEMENT O\n  &END\n  &KIND hydrogen\n   ELEMENT H\n  &END\n &END\n&END\n')
    f=load_document(write(tmp_path,text,'in.inp')).frames[0]
    assert f.symbols==['O','H'] and f.positions[1,2]==pytest.approx(factor)


def test_input_scaled_coordinates_and_set_variables(tmp_path):
    text=('@SET L 8\n'+INPUT).replace('8 9 10','$L 9 10').replace('O 0 0 0','SCALED\n   O 0 0 0').replace('H 0 0 1','H .5 .5 .5')
    f=load_document(write(tmp_path,text,'in.inp')).frames[0]
    np.testing.assert_allclose(f.positions[1],[4,4.5,5])


def test_input_external_only_keeps_settings_without_opening_file(tmp_path):
    text=INPUT.replace('  &COORD\n   O 0 0 0\n   H 0 0 1\n  &END','  &TOPOLOGY\n   COORD_FILE_NAME absent.xyz\n  &END')
    d=load_document(write(tmp_path,text,'in.inp'))
    assert d.frames==[] and not has_curve_data(d) and d.calculation_results.jobs[0].charge==1
    assert 'referenced coordinate files are not opened' in d.note


def test_conditional_input_and_unsupported_expression_are_not_partial_structures(tmp_path):
    for text in ('@IF 1\n'+INPUT+'@ENDIF\n',INPUT.replace('H 0 0 1','H 0 0 sqrt(2)')):
        d=load_document(write(tmp_path,text,'in.inp'));assert d.frames==[]


def test_output_does_not_borrow_trajectory_coordinates(tmp_path):
    write(tmp_path,XYZ,'example-pos-1.xyz')
    d=load_document(write(tmp_path,HEADER+COORD+ENERGY+' OPTIMIZATION STEP: 1\n'+ENERGY.replace('-10.1','-10.2')+METRICS))
    assert len(d.frames)==1 and len(d.calculation_results.steps)==2
    assert d.frames[0].energy_ev==pytest.approx(-10.1*Hartree)
    last=d.calculation_results.steps[-1]
    assert last.frame_index is None and last.geometry is None
    assert last.energy_ev==pytest.approx(-10.2*Hartree) and last.convergence['max_force']==(.0003,.0004)
    assert d.calculation_results.force_unit.startswith('Hartree/bohr')


def test_output_energy_only_and_geometry_only(tmp_path):
    d=load_document(write(tmp_path,ENERGY,'renamed.txt'));assert d.frames==[] and has_curve_data(d)
    d=load_document(write(tmp_path,HEADER+COORD));assert len(d.frames)==1 and d.frames[0].energy_ev is None


def test_force_metrics_without_energy_are_not_lost_or_added_to_previous_step(tmp_path):
    d=load_document(write(tmp_path,HEADER+COORD+ENERGY+' OPTIMIZATION STEP: 1\n'+METRICS))
    assert len(d.calculation_results.steps)==2
    assert d.calculation_results.steps[0].convergence=={}
    assert d.calculation_results.steps[1].energy_ev is None
    assert d.calculation_results.steps[1].convergence['max_force']==(.0003,.0004)


def test_geometry_with_force_metrics_without_energy(tmp_path):
    d=load_document(write(tmp_path,HEADER+COORD+METRICS))
    assert len(d.frames)==1 and d.frames[0].energy_ev is None and has_curve_data(d)


def test_truncated_coordinates_cannot_reuse_previous_frame(tmp_path):
    broken=COORD.split(' 2 2 H')[0]
    d=load_document(write(tmp_path,HEADER+COORD+ENERGY+' OPTIMIZATION STEP: 1\n'+broken+ENERGY))
    assert len(d.frames)==1 and d.calculation_results.steps[-1].geometry is None


def test_complete_trailing_structure_without_energy_is_retained(tmp_path):
    d=load_document(write(tmp_path,HEADER+COORD+ENERGY+' OPTIMIZATION STEP: 1\n'+COORD))
    assert len(d.frames)==2 and d.frames[-1].energy_ev is None


def test_concatenated_jobs_do_not_merge_structures_or_results(tmp_path):
    d=load_document(write(tmp_path,HEADER+COORD+ENERGY+HEADER+ENERGY))
    assert len(d.calculation_results.jobs)==2 and len(d.frames)==1
    assert d.calculation_results.steps[1].job_index==1 and d.calculation_results.steps[1].frame_index is None


def test_output_cell_norm_preserves_printed_high_precision_length(tmp_path):
    d=load_document(write(tmp_path,HEADER.replace('8 0 0 |a| = 8','8.123 0 0 |a| = 8.123456')+COORD))
    assert d.frames[0].cell[0,0]==pytest.approx(8.123456)


@pytest.mark.parametrize('text,energies',[(XYZ,[-10,-10.2]),(XYZ.replace(', E = -10.2',''),[-10,None])])
def test_xyz_step_energy_time_and_missing_cell(tmp_path,text,energies):
    path=write(tmp_path,text,'renamed.xyz');assert detect_format(path).kind=='cp2k_xyz'
    d=load_document(path);assert len(d.frames)==2
    assert [f.energy_ev for f in d.frames]==[None if e is None else e*Hartree for e in energies]
    assert not any(d.frames[0].pbc) and not d.frames[0].cell.any() and d.frames[0].info['time_fs']==.5


def test_xyz_partial_tail_and_frame_limit(tmp_path):
    path=write(tmp_path,XYZ+'2\n i = 3, E = -11\nO 0 0 0\n','traj.xyz')
    assert len(load_document(path).frames)==2
    with pytest.raises(ValueError,match='exceeds 1'):load_document(path,max_frames=1)


def test_mo_keeps_final_scf_tables_and_kpoint_spin_channels(tmp_path):
    def table(step,k,spin,energy):
        return f' MO| EIGENVALUES AND OCCUPATION NUMBERS AFTER SCF STEP {step} FOR K POINT {k} SPIN {spin}\n MO| Index Eigenvalue [a.u.] Eigenvalue [eV] Occupation\n MO| 4 -.2 {energy} 1\n MO| 5 .1 2.0 0\n\n'
    text=HEADER+COORD+table(0,1,1,-99)+table(2,1,1,-5)+table(2,2,1,-4)+table(2,1,2,-3)+ENERGY
    d=load_document(write(tmp_path,text));sets=d.calculation_results.orbitals
    assert len(sets)==1 and sets[0].frame_index==0 and len(sets[0].channels)==3
    assert sets[0].channels['k 1 / spin 1'][0].energy_ev==-5
    assert sets[0].frontier('k 2 / spin 1')[2]==6


@pytest.mark.parametrize('form',['length','velocity'])
def test_signed_tddfpt_transition_vectors_keep_form(tmp_path,form):
    text=TD.replace(' Only KERNEL NONE is active for k-point TDDFPT; transition dipole magnitudes are shown.',f' Transition dipoles calculated using {form} formulation')
    d=load_document(write(tmp_path,HEADER+COORD+text+ENERGY))
    t=d.electronic_spectra[0].transitions[0]
    vector=t.electric_dipole_au if form=='length' else t.velocity_dipole_au
    np.testing.assert_array_equal(vector,[1,2,3]);assert t.oscillator_strength==.5


def test_berry_form_is_not_relabelled_as_length_gauge(tmp_path):
    text=TD.replace(' Only KERNEL NONE is active for k-point TDDFPT; transition dipole magnitudes are shown.',
                    ' Transition dipoles calculated using BERRY formulation')
    t=load_document(write(tmp_path,text)).electronic_spectra[0].transitions[0]
    assert t.metadata['dipole_form']=='berry' and t.electric_dipole_au is None
    assert t.metadata['printed_components_au']==[1,2,3]


def test_magnitudes_are_not_vectors_or_amplitudes_and_survive_csv(tmp_path):
    d=load_document(write(tmp_path,TD,'spectrum.data'));assert d.frames==[] and not has_curve_data(d)
    t=d.electronic_spectra[0].transitions[0]
    assert t.electric_dipole_au is None and t.velocity_dipole_au is None and t.contributions==[]
    assert t.metadata['component_magnitudes_au']==[1,2,3] and t.metadata['kpoint_source_fields']==['2','1','4','5','0.25']
    path=tmp_path/'transitions.csv';export_transitions(path,d)
    with path.open(encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
    assert float(rows[0]['component_magnitude_x_au'])==1 and rows[0]['electric_x_au']==''
    assert json.loads(rows[0]['source_metadata_json'])['dipole_form']=='component magnitudes'


def test_initial_guess_is_not_a_final_transition_table(tmp_path):
    text=' CP2K| version string: CP2K 2026\n TDDFPT Initial Guess\n 1 4 5 3.0\n TDDFPT| Number of states calculated 200\n'
    assert load_document(write(tmp_path,text)).electronic_spectra==[]


def test_output_curve_keeps_energy_only_steps_and_csv_source_units(gui,tmp_path):
    w,d=attach(gui,write(tmp_path,HEADER+COORD+ENERGY+' OPTIMIZATION STEP: 1\n'+ENERGY+METRICS))
    curve=w.show_energy_curve();assert len(curve.points())==2
    assert [r['frame'] for r in curve.points()]==[0,None]
    with patch.object(w,'_jump_to_result_frame') as jump:
        curve.pick_point(SimpleNamespace(artist=curve.energy_axes.lines[0],ind=[1]));jump.assert_not_called()
    path=tmp_path/'curve.csv'
    with patch('lele.convergence_dialog.QFileDialog.getSaveFileName',return_value=(str(path),'CSV')):curve.export_data()
    with path.open(encoding='utf-8-sig') as stream:rows=list(csv.DictReader(stream))
    assert len(rows)==2 and rows[1]['geometry_frame']=='' and float(rows[1]['energy_Eh'])==pytest.approx(-10.1)
    assert rows[1]['force_unit'].startswith('Hartree/bohr')


def test_spectrum_without_structure_has_results_controls_and_paints(gui,tmp_path):
    from lele.spectrum_dialog import SpectrumDialog
    w,d=attach(gui,write(tmp_path,TD,'spectra.out'))
    assert w.frame is None and w.results_spectrum_button.isEnabled() and w.results_transition_button.isEnabled()
    assert not w.energy_curve_action.isEnabled()
    dialog=SpectrumDialog(d,'UV-Vis',w);gui.addCleanup(dialog.close);dialog.show();gui.app.processEvents()
    assert dialog.table.rowCount()==2 and not dialog.grab().isNull()
    assert dialog.table.item(0,7).text()=='component magnitudes'


@pytest.mark.parametrize('text,name',[(INPUT,'input.restart'),(HEADER+COORD+TD+ENERGY,'cp2k.out'),(XYZ,'pos.xyz'),(TD,'spectrum.out')])
def test_cp2k_project_roundtrip(tmp_path,text,name):
    d=load_document(write(tmp_path,text,name));path=tmp_path/'project.lele'
    save_project(path,dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0)],current_document=0))
    new=load_project(path)['documents'][0]['document']
    assert type(new.calculation_results) is type(d.calculation_results)
    assert len(new.frames)==len(d.frames)
    for a,b in zip(new.frames,d.frames):np.testing.assert_array_equal(a.positions,b.positions);assert a.energy_ev==b.energy_ev
    if d.electronic_spectra:
        assert new.electronic_spectra[0].transitions[0].metadata==d.electronic_spectra[0].transitions[0].metadata
