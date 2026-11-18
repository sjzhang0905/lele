"""Printed CP2K settings and MD records remain independent of companions."""
from pathlib import Path
from ase.units import Hartree
import pytest
from lele.cp2k_results import read_cp2k_output, summary_lines
from lele.formats import load_document
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.result_availability import results_text


HEADER = ''' CP2K| version string: CP2K version 2026.2
 GLOBAL| Project name example
 GLOBAL| Run type GEO_OPT
 GLOBAL| Basis set file name BASIS_MOLOPT
 GLOBAL| Potential file name GTH_POTENTIALS
 DFT| Spin unrestricted (spin-polarized) Kohn-Sham calculation UKS
 DFT| Multiplicity 4
 DFT| Charge 0
 DFT+U| Method MULLIKEN
 FUNCTIONAL| PBE:
 QS| Method: GPW
 QS| Number of grid levels: 5
 QS| Density cutoff [a.u.]: 300.0
 QS| Relative density cutoff [a.u.]: 30.0
 1. Atomic kind: Ni_dn Number of atoms: 3
 Orbital Basis Set DZVP-MOLOPT-SR-GTH-q18
 GTH Potential information for GTH-PBE-q18
 A DFT+U correction is applied to atoms of this atomic kind:
 Angular quantum momentum number L: 2
 U(eff) = (U - J) value in [eV]: 6.000
 2. Atomic kind: O Number of atoms: 6
 Orbital Basis Set DZVP-MOLOPT-SR-GTH-q6
 GTH Potential information for GTH-PBE-q6
 - Atoms: 9
 SCF PARAMETERS Density guess: ATOMIC
 max_scf: 200
 eps_scf: 1.00E-06
 Outer loop SCF in use
 eps_scf 1.00E-06
 max_scf 10
 SCF WAVEFUNCTION OPTIMIZATION
 SCF run converged in 8 steps
 outer SCF loop converged in 2 iterations or 27 steps
 ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] -10.0
 OPT| Optimization method BFGS
 PROGRAM ENDED AT example
'''


def read(tmp_path, text, name='cp2k.out'):
    path=tmp_path/name
    path.write_text(text)
    return read_cp2k_output(path)


def test_printed_basis_potential_u_and_scf_settings(tmp_path):
    r=read(tmp_path,HEADER);job=r.jobs[0];m=r.metadata['jobs']['0']
    assert job.method=='PBE + U (MULLIKEN)'
    assert job.basis=='Ni_dn: DZVP-MOLOPT-SR-GTH-q18; O: DZVP-MOLOPT-SR-GTH-q6'
    assert (job.charge,job.multiplicity)==(0,4)
    assert m['Atomic kinds'][0]['Potential']=='GTH-PBE-q18'
    assert m['Atomic kinds'][0]['Ueff (eV)']=='6.000'
    assert 'Ueff (eV)' not in m['Atomic kinds'][1]
    assert m['Atoms']==9
    assert m['SCF max_scf']=='200' and m['Outer SCF max_scf']=='10'
    assert m['Requested SCF density guess']=='ATOMIC'
    assert m['Last outer SCF iterations']==2 and m['Last outer SCF total steps']==27
    assert job.scf_cycles==8
    assert m['SCF eps_scf']=='1.00E-06' and m['Optimizer']=='BFGS'
    assert m['Density cutoff (Hartree)']=='300.0'


MD_HEADER=''' CP2K| version string: CP2K version 2026.2
 GLOBAL| Run type MD
 GLOBAL| Project name PBE_does_not_prove_the_method
 GLOBAL| Global print level LOW
 - Atoms: 216
 MD_PAR| Ensemble type NVT
 MD_PAR| Number of time steps 2
 MD_PAR| Time step [fs] 1.000000
 MD_PAR| Temperature [K] 300.000000
 THERMOSTAT| Type of thermostat Canonical Sampling/Velocity Rescaling
 THERMOSTAT| CSVR time constant [fs] 100.000000
 Spin 1
 Number of electrons: 694
 Spin 2
 Number of electrons: 622
'''


def md_energy(value):
    return (' SCF WAVEFUNCTION OPTIMIZATION\n SCF run converged in 14 steps\n'
            f' ENERGY| Total FORCE_EVAL ( QS ) energy [hartree] {value}\n')


def md_record(step):
    return (f' MD| Step number {step}\n MD| Time [fs] {step}.000000\n'
            f' MD| Temperature [K] {300+step}.0 299.0\n'
            ' MD| Kinetic energy [hartree] .2 .1\n'
            ' MD| Conserved quantity [hartree] -9.8\n')


def test_low_print_md_summary_and_post_energy_step_association(tmp_path):
    r=read(tmp_path,MD_HEADER+md_energy(-10)+md_energy(-11)+md_record(1)+md_energy(-12)+md_record(2)+' PROGRAM ENDED AT end\n')
    assert len(r.steps)==3 and not r.frames()
    assert [s.cycle for s in r.steps]==[0,1,2]
    assert r.steps[1].energy_ev/Hartree==pytest.approx(-11)
    assert r.steps[-1].info['time_fs']==2
    assert r.steps[-1].info['cp2k_md_temperature_K']==302
    assert r.steps[-1].info['cp2k_md_kinetic_hartree']==.2
    assert r.jobs[0].method==r.jobs[0].basis==''
    assert r.jobs[0].charge is None and r.jobs[0].multiplicity is None
    assert r.metadata['jobs']['0']['Spin electrons']=={'1':694.,'2':622.}
    assert r.stages[0].status=='Completed (printed MD steps and normal termination)'
    text='\n'.join(summary_lines(r,0))
    assert 'MD ensemble: NVT' in text and 'Last printed MD step: 2' in text
    assert 'Last MD temperature (K): 302' in text


def test_final_energy_without_md_summary_does_not_reuse_previous_step(tmp_path):
    r=read(tmp_path,MD_HEADER+md_energy(-10)+md_energy(-11)+md_record(1)+md_energy(-12)+' PROGRAM ENDED AT end\n')
    assert r.steps[-1].cycle is None
    assert 'cp2k_md_step' not in r.steps[-1].info
    assert 'final MD step not confirmed' in r.stages[0].status
    assert 'Last printed MD step: 1' in '\n'.join(summary_lines(r,0))


def test_final_step_banner_has_energy_but_does_not_borrow_old_statistics(tmp_path):
    r=read(tmp_path,MD_HEADER+md_energy(-10)+' MD STEP: 1 / 2\n'+md_energy(-11)+md_record(1)
           +' MD STEP: 2 / 2\n'+md_energy(-12)+' PROGRAM ENDED AT end\n')
    assert [s.cycle for s in r.steps]==[0,1,2]
    assert r.steps[-1].info['cp2k_md_step']==2
    assert 'time_fs' not in r.steps[-1].info and 'cp2k_md_temperature_K' not in r.steps[-1].info
    assert r.stages[0].status.startswith('Completed')
    text='\n'.join(summary_lines(r,0))
    assert 'Last printed MD step: 2' in text
    assert 'statistics are from step 1' in text
    assert 'Last printed MD time (fs): 1' in text


def test_pre_energy_md_statistics_do_not_overwrite_previous_step(tmp_path):
    r=read(tmp_path,MD_HEADER+md_record(1)+md_energy(-10)+md_record(2)+md_energy(-11))
    assert [s.cycle for s in r.steps]==[1,2]
    assert [s.info['time_fs'] for s in r.steps]==[1,2]
    assert [s.info['cp2k_md_temperature_K'] for s in r.steps]==[301,302]
    assert [s.energy_ev/Hartree for s in r.steps]==pytest.approx([-10,-11])


def test_concatenated_runs_do_not_inherit_settings(tmp_path):
    r=read(tmp_path,HEADER+MD_HEADER+md_energy(-10))
    assert len(r.jobs)==2
    assert r.jobs[1].method==r.jobs[1].basis==''
    assert 'Atomic kinds' not in r.metadata['jobs']['1']
    assert r.metadata['jobs']['1']['MD ensemble']=='NVT'


def test_summary_metadata_survives_project_and_results_text(tmp_path):
    path=tmp_path/'cp2k.out';path.write_text(HEADER)
    d=load_document(path);project=tmp_path/'session.lele'
    save_project(project,dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0)],current_document=0))
    new=load_project(project)['documents'][0]['document']
    assert new.calculation_results.metadata==d.calculation_results.metadata
    text=results_text(new)
    assert 'Ni_dn' in text and 'Ueff (eV): 6.000' in text and 'Optimizer: BFGS' in text


def test_quoted_spin_values_are_retained_without_guessing_multiplicity(tmp_path):
    r=read(tmp_path,MD_HEADER+' Integrated spin density: 72.00000001\n'
           ' Ideal and single determinant S**2 : 1332.000000 1332.210718\n')
    assert r.jobs[0].spin_squared==1332.210718
    assert r.jobs[0].multiplicity is None
    assert r.metadata['jobs']['0']['Last integrated spin density']==72.00000001
