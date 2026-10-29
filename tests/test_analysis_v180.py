"""Numerical and integration checks for molecular output result analysis."""
from pathlib import Path
import json
import numpy as np
import pytest
from ase.units import Hartree
from lele.formats import load_document,export_frame
from lele.calculation_results import read_gaussian_results,OrbitalSet,Orbital
from lele.gaussian_properties import contribution_text
from lele.property_export import transition_rows

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'


@pytest.fixture
def gaussian():return load_document(EXAMPLES/'synthetic_analysis_v180.log')


def test_gaussian_geometry_segments_and_convergence_are_associated(gaussian):
    assert len(gaussian.frames)==4
    result=gaussian.calculation_results
    assert len(result.jobs)==2 and len(result.steps)==4
    assert [f.info['converter_charge'] for f in gaussian.frames]==[0,0,0,1]
    assert [f.info['converter_mult'] for f in gaussian.frames]==[1,1,1,2]
    assert [s.frame_index for s in result.steps]==[0,1,2,3]
    assert result.steps[1].convergence['max_force']==(.0002,.00045)
    assert result.steps[1].convergence['rms_force']==(.0001,.0003)
    assert result.steps[1].converged and result.steps[2].converged
    assert 'Scan' in result.jobs[0].tasks
    assert result.jobs[0].method=='b3lyp' and result.jobs[0].basis=='6-31g(d)'
    assert result.jobs[0].solvent=='water'
    assert all(job.termination=='Normal termination' for job in result.jobs)


def test_restricted_and_unrestricted_frontier_orbitals_use_real_occupations(gaussian):
    restricted,opened=gaussian.calculation_results.orbitals
    homo,lumo,gap=restricted.frontier('Restricted')
    assert (homo.number,lumo.number)==(5,6)
    assert np.isclose(homo.energy_ev,-.3*Hartree) and np.isclose(gap,.4*Hartree)
    assert restricted.frame_index==2
    assert set(opened.channels)=={'Alpha','Beta'}
    ha,la,ga=opened.frontier('Alpha');hb,lb,gb=opened.frontier('Beta')
    assert (ha.number,la.number,hb.number,lb.number)==(5,6,4,5)
    assert np.isclose(ga,.25*Hartree) and np.isclose(gb,.21*Hartree)
    assert opened.frame_index==3


def test_same_geometry_energy_different_link1_charge_is_not_merged(tmp_path):
    text=(EXAMPLES/'synthetic_properties.log').read_text()
    first,second=text.split(' --Link1--')
    second=second.replace('Charge = 0 Multiplicity = 1','Charge = 1 Multiplicity = 2')
    path=tmp_path/'charge.log';path.write_text(first+' --Link1--'+second)
    doc=load_document(path)
    assert len(doc.frames)==3
    assert [(f.info['converter_charge'],f.info['converter_mult']) for f in doc.frames]==[(0,1),(0,1),(1,2)]
    out=tmp_path/'charged.gjf';export_frame(doc.frames[-1],out,'gjf')
    assert '\n1 2\n' in out.read_text()


def test_truncated_output_and_missing_virtuals_do_not_invent_a_gap(tmp_path):
    path=tmp_path/'partial.log'
    path.write_text(' Entering Gaussian System\n Charge = 0 Multiplicity = 1\n SCF Done: E(RHF) = -1.0 A.U. after 4 cycles\n Alpha occ. eigenvalues -- -.5\n')
    result=read_gaussian_results(path)
    assert result.jobs[0].termination.startswith('Incomplete')
    homo,lumo,gap=result.orbitals[0].frontier('Restricted')
    assert homo.number==1 and lumo is None and gap is None


def test_degenerate_homo_uses_last_occupied_orbital_number():
    values=OrbitalSet(0,1,{'Restricted':[Orbital(1,2,-1),Orbital(2,2,-1),Orbital(3,0,-.5)]})
    assert values.frontier('Restricted')[0].number==2
    assert values.frontier('Restricted')[1].number==3 and values.frontier('Restricted')[2]==.5


def test_rohf_alpha_only_output_is_not_mislabeled_as_doubly_occupied(tmp_path):
    path=tmp_path/'rohf.log'
    path.write_text(' Charge = 0 Multiplicity = 2\n SCF Done: E(ROHF) = -1.0 A.U. after 4 cycles\n'
                    ' Alpha occ. eigenvalues -- -.5\n Alpha virt. eigenvalues -- .2\n')
    snapshot=read_gaussian_results(path).orbitals[0]
    assert set(snapshot.channels)=={'Alpha'} and snapshot.channels['Alpha'][0].occupation==1.


def test_signed_forward_and_backward_transition_coefficients_and_csv(gaussian):
    first=gaussian.electronic_spectra[0].transitions[0]
    assert len(first.contributions)==3
    assert [(c.from_orbital,c.to_orbital,c.direction,c.coefficient) for c in first.contributions]==[(5,6,'->',.68),(4,5,'->',-.2),(5,6,'<-',.08)]
    assert first.contributions[1].from_spin=='B'
    assert 'c=-0.200000' in contribution_text(first)
    row=transition_rows(gaussian)[0]
    data=json.loads(row['contributions_json'])
    assert data[2]['direction']=='<-' and data[1]['coefficient']==-.2


def test_orca_zero_based_numbers_ev_column_and_missing_strength_are_preserved():
    doc=load_document(EXAMPLES/'synthetic_orca_analysis_v180.out')
    assert len(doc.frames)==1 and doc.frames[0].info['converter_charge']==1
    assert doc.frames[0].info['converter_mult']==2
    result=doc.calculation_results
    assert result.jobs[0].method=='PBE0' and result.jobs[0].basis=='def2-SVP'
    snapshot=result.orbitals[0];h,l,gap=snapshot.frontier('Alpha')
    assert (h.number,l.number)==(1,2)
    assert np.isclose(gap,2.721139+5.442277)
    assert '0-based' in snapshot.numbering
    transition=doc.electronic_spectra[0].transitions[0]
    assert transition.oscillator_strength is None
    assert transition.contributions[0].coefficient==-.87185424
    assert transition.contributions[0].printed_weight==.760130


def test_original_example_frequency_summary_keeps_each_job():
    doc=load_document(EXAMPLES/'synthetic_properties.log')
    assert len(doc.frames)==2
    assert doc.calculation_results.jobs[1].frequency_count==3
    assert doc.calculation_results.jobs[1].imaginary_modes==1
