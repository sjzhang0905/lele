"""Scientific edge cases for the three independent acceptance defects."""
import numpy as np
import pytest
from lele.formats import load_document
from lele.project_file import save_project,load_project
from lele.render_options import RenderOptions
from test_acceptance_v2101 import QE_HEADER,cp2k_input,write


SUCCESS='bfgs converged in 2 scf cycles and 1 bfgs steps\n'
END='End of BFGS Geometry Optimization\nJOB DONE.\n'
REPRINT='ATOMIC_POSITIONS (alat)\nH 0 0 0\nH 0 0 .2\n'


@pytest.mark.parametrize('ending,expected',[
    (END,False),
    ('bfgs failed after 2 scf cycles and 1 bfgs steps, convergence not achieved\n'+END,False),
    ('convergence NOT achieved after 100 iterations: stopping\n'+END,False),
    ('Maximum CPU time exceeded\n'+END,False),
    ('Error in routine electrons (1):\n'+END,False),
    (' BFGS CONVERGED in 2 scf cycles and 1 bfgs steps\n'+END,True),
])
def test_qe_only_explicit_optimization_success_confirms_geometry(tmp_path,ending,expected):
    d=load_document(write(tmp_path,'status.pwo',QE_HEADER+ending))
    assert bool(d.frames[-1].info.get('optimization_converged')) is expected
    assert d.calculation_results.steps[-1].converged is expected


@pytest.mark.parametrize('failure',[
    'The maximum number of steps has been reached.\n',
    'bfgs failed after 2 scf cycles and 1 bfgs steps, convergence not achieved\n',
    'Error in routine bfgs (1):\n',
])
@pytest.mark.parametrize('failure_first',[False,True])
def test_qe_failure_has_priority_over_success_and_reprints(tmp_path,failure,failure_first):
    tail=failure+SUCCESS+REPRINT if failure_first else SUCCESS+REPRINT+failure
    d=load_document(write(tmp_path,'failed.pwo',QE_HEADER+tail+END))
    assert not any(s.converged for s in d.calculation_results.steps)
    assert not any(f.info.get('optimization_converged') for f in d.frames)
    # A completed PWSCF process can still have an unconverged optimization.
    assert d.calculation_results.jobs[0].termination=='Completed (JOB DONE)'
    assert d.frames[0].info['qe_total_energy_ry']==-2.


def test_qe_failed_job_does_not_clear_other_jobs_success(tmp_path):
    failed=QE_HEADER+SUCCESS+REPRINT+'The maximum number of steps has been reached.\n'+END
    good=QE_HEADER+SUCCESS+END
    d=load_document(write(tmp_path,'jobs.pwo',good+failed+good))
    assert [s.converged for s in d.calculation_results.steps]==[True,False,False,True]
    assert [f.info['calculation_index'] for f in d.frames]==[0,1,1,2]


def test_qe_success_does_not_propagate_to_new_geometry_reprinted_twice(tmp_path):
    changed=REPRINT.replace('H 0 0 .2','H 0 0 .3')
    d=load_document(write(tmp_path,'changed.pwo',QE_HEADER+SUCCESS+changed+changed+END))
    assert [s.converged for s in d.calculation_results.steps]==[True,False]
    assert d.frames[0].info['optimization_converged']
    assert not d.frames[-1].info.get('optimization_converged')


OBLIQUE='''&FORCE_EVAL
 &SUBSYS
  &CELL
   A 4 0 0
   B -2 3 0
   C 0 0 6
   PERIODIC XY
   MULTIPLE_UNIT_CELL 2 3 1
  &END
  &COORD
   SCALED
   He .25 .5 .5
   H .75 .25 .125
  &END
  &TOPOLOGY
   MULTIPLE_UNIT_CELL 3 2 1
  &END
 &END
&END
'''


@pytest.mark.parametrize('scaled',[True,False])
def test_cp2k_unequal_repeats_oblique_cell_positions_species_and_order(tmp_path,scaled):
    text=OBLIQUE
    if not scaled:
        text=text.replace('SCALED','UNIT bohr').replace('He .25 .5 .5','He 0 2.834589188753655 5.66917837750731')
        text=text.replace('H .75 .25 .125','H 4.724315314589425 1.4172945943768276 1.4172945943768276')
    f=load_document(write(tmp_path,'oblique.inp',text)).frames[0]
    np.testing.assert_allclose(f.cell,[[8,0,0],[-6,9,0],[0,0,6]])
    assert f.pbc==(True,True,False) and f.symbols==['He','H']*6
    shifts=np.array([[0,0,0],[4,0,0],[8,0,0],[-2,3,0],[2,3,0],[6,3,0]])
    base=np.array([[0,1.5,3],[2.5,.75,.75]])
    np.testing.assert_allclose(f.positions,(base[None,:,:]+shifts[:,None,:]).reshape(-1,3),atol=1.e-8)


def test_cp2k_cell_only_does_not_rescale_fractional_coordinates(tmp_path):
    text=OBLIQUE.replace('MULTIPLE_UNIT_CELL 3 2 1','MULTIPLE_UNIT_CELL 1 1 1')
    f=load_document(write(tmp_path,'cell_only.inp',text)).frames[0]
    assert f.symbols==['He','H']
    np.testing.assert_allclose(f.positions,[[0,1.5,3],[2.5,.75,.75]])
    np.testing.assert_allclose(f.cell,[[8,0,0],[-6,9,0],[0,0,6]])


@pytest.mark.parametrize('keyword',['ALPHA_BETA_GAMMA','ANGLES'])
@pytest.mark.parametrize('value',['[deg] 90 90 120','[rad] 1.5707963267948966 1.5707963267948966 2.0943951023931953'])
def test_cp2k_angles_support_explicit_degree_and_radian_units(tmp_path,keyword,value):
    f=load_document(write(tmp_path,'angles.inp',cp2k_input(angles=f'{keyword} {value}'))).frames[0]
    np.testing.assert_allclose(f.cell,[[4,0,0],[-2,2*np.sqrt(3),0],[0,0,4]],atol=1.e-12)
    assert abs(np.linalg.det(f.cell))==pytest.approx(32*np.sqrt(3))


@pytest.mark.parametrize('value',['90 90','90 90 90 90','0 90 90','90 90 180','10 10 170','60 60 120','[grad] 90 90 120'])
def test_cp2k_invalid_angles_do_not_silently_invent_orthogonal_cell(tmp_path,value):
    d=load_document(write(tmp_path,'bad_angles.inp',cp2k_input(angles='ANGLES '+value)))
    assert not d.frames and ('angle' in d.note.lower() or 'cell' in d.note.lower())


@pytest.mark.parametrize('section',['cell','topology'])
@pytest.mark.parametrize('value',['2 1','0 1 1','-1 1 1','1.5 1 1'])
def test_cp2k_invalid_repeat_factors_withhold_geometry_and_report_section(tmp_path,section,value):
    values={section+'_repeat':'MULTIPLE_UNIT_CELL '+value}
    d=load_document(write(tmp_path,'bad_repeat.inp',cp2k_input(**values)))
    assert not d.frames and section.upper()+'/MULTIPLE_UNIT_CELL' in d.note


def test_cp2k_topology_atom_guard_uses_nonoverflowing_integer_product(tmp_path):
    text=cp2k_input(topology_repeat='MULTIPLE_UNIT_CELL 4294967296 4294967296 1')
    d=load_document(write(tmp_path,'excessive.inp',text))
    assert not d.frames and 'Excessive CP2K TOPOLOGY/MULTIPLE_UNIT_CELL' in d.note


def test_cp2k_missing_cell_does_not_make_coincident_replicas(tmp_path):
    text=cp2k_input(topology_repeat='MULTIPLE_UNIT_CELL 2 1 1').replace('ABC 4 4 4','PERIODIC NONE')
    d=load_document(write(tmp_path,'no_cell.inp',text))
    assert not d.frames and 'coordinate repetition requires an inline cell' in d.note


def test_unequal_topology_repeats_include_cp2k_calculation_compatibility_note(tmp_path):
    d=load_document(write(tmp_path,'repeat.inp',OBLIQUE))
    assert len(d.frames[0].symbols)==12 and 'requires matching CELL/TOPOLOGY' in d.note


def test_fixed_geometry_and_qe_status_survive_project_roundtrip(tmp_path):
    docs=[load_document(write(tmp_path,'oblique.inp',OBLIQUE)),
          load_document(write(tmp_path,'good.pwo',QE_HEADER+SUCCESS+REPRINT+END)),
          load_document(write(tmp_path,'failed.pwo',QE_HEADER+'The maximum number of steps has been reached.\n'+END))]
    state=dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0) for d in docs],current_document=0)
    path=tmp_path/'fixed.lele';save_project(path,state)
    restored=[entry['document'] for entry in load_project(path)['documents']]
    for actual,expected in zip(restored,docs):
        assert actual.frames[0].symbols==expected.frames[0].symbols
        np.testing.assert_array_equal(actual.frames[0].positions,expected.frames[0].positions)
        np.testing.assert_array_equal(actual.frames[0].cell,expected.frames[0].cell)
        assert actual.frames[0].energy_ev==expected.frames[0].energy_ev
    assert restored[1].frames[-1].info['optimization_converged']
    assert not restored[2].frames[-1].info.get('optimization_converged')
