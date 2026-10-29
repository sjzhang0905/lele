"""xTB source values, trajectory association and fractional/spin frontiers."""
from pathlib import Path
from shutil import copy2
import numpy as np
import pytest
from ase.units import Hartree,Bohr
from lele.formats import load_document
from lele.legacy_converter import detect_format,read_structure
from lele.xtb_results import read_xtb_results

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'
MAIN=EXAMPLES/'synthetic_xtb_v1110.out'
TRAJ=EXAMPLES/'synthetic_xtb_v1110.xtbopt.log'
GXTB=EXAMPLES/'synthetic_gxtb_v1110.out'


def copied(tmp_path,trajectory=True):
    p=tmp_path/MAIN.name;copy2(MAIN,p)
    if trajectory:copy2(TRAJ,tmp_path/TRAJ.name)
    return p


def test_detects_stdout_and_content_based_xtb_xyz_without_reclassifying_plain_xyz(tmp_path):
    assert detect_format(MAIN).kind=='xtb_out'
    assert detect_format(GXTB).kind=='xtb_out'
    for name in ('renamed.log','renamed.xyz'):
        p=tmp_path/name;copy2(TRAJ,p);assert detect_format(p).kind=='xtb_trj'
    p=tmp_path/'plain.xyz';p.write_text('1\nordinary XYZ\nH 0 0 0\n')
    assert detect_format(p).kind=='xyz'


def test_standalone_trajectory_uses_comment_hartrees_and_keeps_angstrom_positions():
    d=load_document(TRAJ);r=d.calculation_results
    assert len(d.frames)==3 and not r.orbitals
    np.testing.assert_allclose([f.energy_ev/Hartree for f in d.frames],[-10,-10.05,-10.1000000001])
    np.testing.assert_allclose(d.frames[-1].positions[1],[.96,0,0])
    assert r.stages[0].status!='Converged'
    assert all(not s.convergence for s in r.steps)


def test_matching_companion_restores_cycle_geometry_and_precise_final_single_point():
    d=load_document(MAIN);r=d.calculation_results
    assert len(d.frames)==3 and len(r.steps)==3
    assert [s.cycle for s in r.steps]==[1,2,3] and [s.frame_index for s in r.steps]==[0,1,2]
    assert r.stages[0].status=='Converged' and r.steps[-1].converged
    assert r.jobs[0].termination=='Normal termination' and r.jobs[0].method=='GFN2-xTB'
    assert np.isclose(d.frames[-1].energy_ev/Hartree,-10.100000000123,rtol=0,atol=1e-13)
    assert np.isclose(d.frames[-1].info['xtb_trajectory_energy_ev']/Hartree,-10.1000000001,rtol=0,atol=1e-13)
    assert '3 verified' in d.note


@pytest.mark.parametrize('change',[
    lambda t:t.replace('O 0.0 0.0 0.0','N 0.0 0.0 0.0'),
    lambda t:t.replace('-10.050000000000','-10.060000000000'),
    lambda t:t.replace('H 0.96 0.0 0.0','H 0.95 0.0 0.0'),
    lambda t:t.rsplit('H -0.20',1)[0],
])
def test_wrong_atom_order_energy_final_structure_or_truncated_companion_is_not_attached(tmp_path,change):
    p=copied(tmp_path);(tmp_path/TRAJ.name).write_text(change(TRAJ.read_text()))
    d=load_document(p)
    assert len(d.frames)==1 and len(d.calculation_results.steps)==3
    assert [s.frame_index for s in d.calculation_results.steps]==[None,None,0]
    assert 'not attached' in d.note


def test_fractional_lumo_and_higher_partially_occupied_levels_do_not_redefine_frontiers():
    r=load_document(MAIN).calculation_results;s=r.orbitals[-1];h,l,g=s.frontier('Restricted')
    assert h.number==2 and l.number==3 and l.occupation==.18
    assert any(row.number==4 and row.occupation>0 and row.energy_ev>l.energy_ev for row in s.channels['Restricted'])
    assert h.energy_ev==-8.1634 and l.energy_ev==-6.5307
    assert g==1.632683161 and s.reported_gap_ev==1.632683161


def test_initial_and_final_orbitals_stay_separate_while_duplicate_final_prints_merge():
    r=load_document(MAIN).calculation_results
    assert len(r.orbitals)==2
    assert [s.frame_index for s in r.orbitals]==[0,2]
    assert r.orbitals[0].frontier('Restricted')[0].energy_ev==-5.4423
    assert r.orbitals[-1].frontier('Restricted')[0].energy_ev==-8.1634
    assert len(r.orbitals[-1].channels['Restricted'])==5


def test_gxtb_alpha_beta_and_reported_overall_gap_are_independent():
    d=load_document(GXTB);r=d.calculation_results;s=r.orbitals[-1]
    assert r.jobs[0].method=='g-xTB' and r.jobs[0].charge==-2 and r.jobs[0].multiplicity==4
    assert list(s.channels)==['Alpha','Beta']
    assert [s.frontier(ch)[0].number for ch in s.channels]==[3,2]
    assert [s.frontier(ch)[1].number for ch in s.channels]==[4,3]
    assert [s.frontier(ch)[2] for ch in s.channels]==[8.1634,6.2586]
    assert s.reported_gap_ev==8.163415807
    assert r.orbitals[0].channels=={} and r.orbitals[0].frame_index is None
    assert s.frame_index==0 and len(d.frames)==1


def test_no_companion_retains_every_cycle_energy_without_assigning_final_geometry_to_earlier_cycles(tmp_path):
    d=load_document(copied(tmp_path,False));r=d.calculation_results
    assert len(d.frames)==1 and [s.frame_index for s in r.steps]==[None,None,0]
    assert r.orbitals[0].frame_index is None and r.orbitals[-1].frame_index==0
    np.testing.assert_allclose([s.energy_ev/Hartree for s in r.steps],[-10,-10.05,-10.100000000123])


def test_incomplete_stdout_uses_latest_optimizer_energy_without_claiming_convergence(tmp_path):
    p=tmp_path/'partial.out';p.write_text(MAIN.read_text().split(' *** GEOMETRY OPTIMIZATION')[0])
    r=load_document(p).calculation_results
    assert len(r.steps)==3 and np.isclose(r.jobs[0].energy_ev/Hartree,-10.1)
    assert r.stages[0].status!='Converged' and not any(s.converged for s in r.steps)


def test_normal_program_termination_does_not_imply_optimization_convergence(tmp_path):
    text=MAIN.read_text().replace('GEOMETRY OPTIMIZATION CONVERGED AFTER 3 ITERATIONS','GEOMETRY OPTIMIZATION FAILED AFTER 3 ITERATIONS')
    p=tmp_path/'failed.out';p.write_text(text)
    r=load_document(p).calculation_results
    assert r.jobs[0].termination=='Normal termination'
    assert r.stages[0].status=='Not converged' and not r.steps[-1].converged


def test_finished_stdout_without_stderr_normal_termination_keeps_its_printed_status(tmp_path):
    p=tmp_path/'stdout.out';p.write_text(MAIN.read_text().replace(' normal termination of xtb',''))
    r=load_document(p).calculation_results
    assert r.jobs[0].termination=='Finished run' and r.stages[0].status=='Converged'


def test_complete_records_survive_truncated_standalone_trajectory(tmp_path):
    p=tmp_path/'partial.log';p.write_text(TRAJ.read_text()+'3\nenergy: -11 xtb: 6.7\nO 0 0 0\n')
    d=load_document(p)
    assert len(d.frames)==3 and 'Incomplete or invalid' in d.note


def test_scf_done_xtbopt_xyz_energy_and_turbomole_final_coordinate_units(tmp_path):
    p=tmp_path/'xtbopt.xyz';p.write_text('1\n SCF done -5.0 0.001\nH 1 0 0\n')
    d=load_document(p);assert np.isclose(d.frames[0].energy_ev/Hartree,-5)
    p=tmp_path/'coord.out';p.write_text(' * xtb version 6.7.0\n final structure:\n$coord\n1.0 0 0 h\n$end\n | TOTAL ENERGY -5.0 Eh |\n normal termination of xtb\n')
    d=load_document(p)
    assert np.isclose(d.frames[0].positions[0,0],Bohr) and np.isclose(d.frames[0].energy_ev/Hartree,-5)


def test_utf16_stdout_and_trajectory_keep_identical_values(tmp_path):
    p=tmp_path/MAIN.name;p.write_text(MAIN.read_text(),encoding='utf-16')
    (tmp_path/TRAJ.name).write_text(TRAJ.read_text(),encoding='utf-16')
    d=load_document(p)
    assert len(d.frames)==3 and d.calculation_results.orbitals[-1].frontier('Restricted')[0].number==2


def test_concatenated_jobs_keep_their_own_energy_charge_and_frontiers(tmp_path):
    p=tmp_path/'both.out';p.write_text(MAIN.read_text()+GXTB.read_text())
    r=load_document(p).calculation_results
    assert len(r.jobs)==2 and [j.charge for j in r.jobs]==[0,-2]
    assert [j.method for j in r.jobs]==['GFN2-xTB','g-xTB']
    assert [len([s for s in r.steps if s.job_index==j.index]) for j in r.jobs]==[3,2]
    assert r.orbitals[-1].job_index==1 and list(r.orbitals[-1].channels)==['Alpha','Beta']


def test_legacy_structure_conversion_and_frame_limit(tmp_path):
    atoms,detection=read_structure(MAIN)
    assert detection.kind=='xtb_out' and len(atoms)==3 and atoms.info['converter_charge']==0
    np.testing.assert_allclose(atoms.positions[1],[.96,0,0])
    with pytest.raises(ValueError,match='exceeds'):load_document(TRAJ,max_frames=2)


def test_orbital_table_without_lumo_does_not_invent_virtual_level(tmp_path):
    text=GXTB.read_text().replace(' 4         0.1000000 2.7211 (LUMO)','').replace(' 3         0.0500000 1.3606 (LUMO)','')
    p=tmp_path/'missing.out';p.write_text(text)
    s=read_xtb_results(p).orbitals[-1]
    assert s.frontier('Alpha')[1] is None and s.frontier('Beta')[1] is None
