"""Real restart-writer syntax: continuations, state and expanded XC settings."""
import numpy as np
import pytest

from lele.cp2k_input import input_tree,logical_input_lines
from lele.formats import load_document
from lele.result_availability import has_curve_data


RESTART='''# Version information for this restart file
&GLOBAL
 PROJECT_NAME "sample!#name"
 RUN_TYPE MD
&END GLOBAL
&MOTION
 &MD
  ENSEMBLE NVT
  STEPS 3000
  TIMESTEP 9.9999999999999989E-001
  STEP_START_VAL 2300
  TIME_START_VAL 2.2999999999999254E+003
  TEMPERATURE 3.0000000000000000E+002
  ECONS_START_VAL -99.0
 &END MD
 &CONSTRAINT
  &FIXED_ATOMS
   LIST 1 4 7 10 \\
    13 16
  &END FIXED_ATOMS
 &END CONSTRAINT
&END MOTION
&FORCE_EVAL
 METHOD QS
 &DFT
  UKS T
  MULTIPLICITY 4
  &XC
   &XC_FUNCTIONAL NO_SHORTCUT
    &PBE T
    &END PBE
   &END XC_FUNCTIONAL
  &END XC
 &END DFT
 &SUBSYS
  &CELL
   A 5 0 0
   B -2.5 4.3 0
   C 0 0 14
   PERIODIC XYZ
  &END CELL
  &COORD
   Ni_dn .25 .5 .75
   Mn_up .1 .2 .3
   O .2 .4 .6
   SCALED T
  &END COORD
  &KIND "Ni_dn"
   ELEMENT "Ni"
   BASIS_SET "DZVP-MOLOPT-SR-GTH-q18"
  &END KIND
  &KIND "Mn_up"
   ELEMENT "Mn"
  &END KIND
 &END SUBSYS
&END FORCE_EVAL
'''


@pytest.mark.parametrize('name',['state.restart','state.restart.bak-1','renamed.data'])
def test_restart_with_wrapped_constraints_and_scaled_kind_aliases(tmp_path,name):
    path=tmp_path/name;path.write_text(RESTART)
    doc=load_document(path);frame=doc.frames[0];results=doc.calculation_results
    assert len(doc.frames)==1 and frame.symbols==['Ni','Mn','O']
    np.testing.assert_allclose(frame.positions,np.array([[.25,.5,.75],[.1,.2,.3],[.2,.4,.6]])@frame.cell)
    assert frame.pbc==(True,True,True)
    assert frame.info['source_line']==RESTART.splitlines().index('  &COORD')+1
    assert frame.info['cp2k_restart_step']==2300 and results.steps[0].cycle==2300
    assert frame.info['time_fs']==pytest.approx(2300.)
    assert frame.energy_ev is None and results.jobs[0].energy_ev is None and not has_curve_data(doc)
    assert results.jobs[0].method=='PBE'
    settings=results.metadata['jobs']['0']
    assert settings['Project']=='sample!#name'
    assert settings['MD requested steps']==3000
    assert settings['MD time step (fs)']==pytest.approx(1.)
    assert settings['MD target temperature (K)']==300
    assert settings['Restart step']==2300


def test_geometry_restart_state_is_not_an_energy_result(tmp_path):
    text=RESTART.replace('RUN_TYPE MD','RUN_TYPE GEO_OPT').replace('&MD','&GEO_OPT').replace('&END MD','&END GEO_OPT')
    text=text.replace('STEP_START_VAL 2300','STEP_START_VAL 14\n  OPTIMIZER BFGS\n  MAX_ITER 300')
    path=tmp_path/'geo.restart';path.write_text(text)
    doc=load_document(path);settings=doc.calculation_results.metadata['jobs']['0']
    assert settings['Optimizer']=='BFGS' and settings['Restart step']==14
    assert doc.frames[0].info['cp2k_restart_step']==14 and 'time_fs' not in doc.frames[0].info
    assert not has_curve_data(doc)


def test_continuations_preserve_comments_quotes_and_source_lines():
    lines=['&GLOBAL','# comment',' PROJECT "one#two!three"',
           ' VALUES 1 2 \\  # comment',' # intervening comment',' 3 \\',' 4','&END']
    records=list(logical_input_lines(lines))
    assert records[3]==(4,' VALUES 1 2   3   4')
    root,_=input_tree(lines);node=root.child('GLOBAL')
    assert node.get('PROJECT')==['one#two!three']
    assert node.get('VALUES')==['1','2','3','4']
    assert node.entries[-1][0]==4


def test_incomplete_continuation_fails_instead_of_silently_dropping_values():
    with pytest.raises(ValueError,match='Incomplete CP2K continuation at line 2'):
        input_tree(['&GLOBAL',' PROJECT example \\'])


def test_explicit_input_units_remain_attached_without_default_unit_relabel(tmp_path):
    path=tmp_path/'unit.restart';path.write_text(RESTART.replace('TIMESTEP 9.9999999999999989E-001','TIMESTEP [ps] .001'))
    settings=load_document(path).calculation_results.metadata['jobs']['0']
    assert settings['MD time step']=='[ps] .001' and 'MD time step (fs)' not in settings
