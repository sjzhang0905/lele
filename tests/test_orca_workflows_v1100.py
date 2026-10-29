"""Multistage NEB/Hessian attribution, result sources and ensemble/SOC values."""
from pathlib import Path
from shutil import copy2
import numpy as np
from ase.units import Hartree
from lele.formats import load_document
from lele.orca_soc import read_soc
from lele.orca_goat import aligned_rmsd

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'
NEB=EXAMPLES/'synthetic_neb_v1100.out'
GOAT=EXAMPLES/'synthetic_goat_v1100.out'
SOC=EXAMPLES/'synthetic_soc_v1100.out'


def test_neb_stages_do_not_overwrite_endpoint_energy_or_convergence():
    d=load_document(NEB);r=d.calculation_results
    assert [s.kind for s in r.stages]==['reactant','product','neb','ts']
    assert [s.status for s in r.stages]==['Converged','Not converged (cycle limit)','Converged','Converged']
    product=next(s for s in r.steps if s.stage_index==1)
    assert np.isclose(product.energy_ev/Hartree,-9.99) and not product.converged
    ts=next(s for s in r.steps if s.stage_index==3)
    assert np.isclose(ts.energy_ev/Hartree,-9.9701)
    assert ts.geometry is not product.geometry and ts.source_line>product.source_line
    assert 'NEB-TS' in r.jobs[0].tasks


def test_neb_snapshots_and_fixed_image_histories_link_exact_energy_records():
    d=load_document(NEB);run,=d.neb_runs
    profiles=[p for p in run.profiles if p.source.endswith('.NEB.log')]
    assert run.nimages==4 and len(profiles)==2
    for p in profiles:
        assert len(p.frame_indices)==4
        for i,index in enumerate(p.frame_indices):
            f=d.frames[index]
            assert f.info['neb_image']==i and f.info['neb_iteration']==p.iteration
            assert np.isclose(f.energy_ev/Hartree,p.energies[i])
    assert run.ts_frame is not None
    assert d.frames[run.ts_frame].info['stage_index']==3
    assert run.convergence[-1]['max_ci']==.001


def test_inconsistent_interp_snapshot_does_not_borrow_xyz(tmp_path):
    for p in EXAMPLES.glob('synthetic_neb_v1100*'):copy2(p,tmp_path/p.name)
    p=tmp_path/'synthetic_neb_v1100.interp'
    p.write_text(p.read_text().replace('0.0300000','0.0310000'))
    d=load_document(tmp_path/NEB.name)
    p=next(p for p in d.neb_runs[0].profiles if p.source.endswith('.interp') and p.iteration==1)
    assert all(index is None for index in p.frame_indices)
    assert any('energy-only' in note for note in d.neb_runs[0].notes)


def test_direct_neb_log_retains_two_dimensional_links():
    d=load_document(EXAMPLES/'synthetic_neb_v1100.NEB.log')
    assert d.format_name=='ORCA NEB results' and len(d.frames)==8
    assert d.frames[0].info['neb_iteration']==0
    assert 'converter_charge' not in d.frames[0].info


def test_model_hessian_and_warning_banners_are_not_exact_calculations_or_input(tmp_path):
    text=NEB.read_text().replace(' PRODUCT OPTIMIZATION',' !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n ! SERIOUS PROBLEM WITH INTERNALS !\n !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n PRODUCT OPTIMIZATION')
    p=tmp_path/'warning.out';p.write_text(text)
    r=load_document(p).calculation_results
    assert 'SERIOUS PROBLEM' not in r.jobs[0].route
    assert not any('exact' in e.kind.lower() for e in r.hessians)


def test_initial_recalculated_and_final_hessians_keep_parent_cycles(tmp_path):
    block=(EXAMPLES/'synthetic_orca_full_v190.out').read_text().split(' VIBRATIONAL FREQUENCIES',1)[1].split(' DIPOLE MOMENT',1)[0]
    geometry=' CARTESIAN COORDINATES (ANGSTROEM)\n ---\n O 0 0 0\n H 1 0 0\n H 0 1 0\n\n'
    text=' ORCA VERSION 6.1\n ! HF def2-SVP OptTS Freq\n * xyz 1 2\n'
    for cycle in (1,2,3):
        text+=f' GEOMETRY OPTIMIZATION CYCLE {cycle}\n'+geometry+f' FINAL SINGLE POINT ENERGY {-75-cycle*.01}\n'
        if cycle in (1,3):text+=' SCF HESSIAN\n VIBRATIONAL FREQUENCIES'+block+f' Actual Hessian File stored as test.{cycle:03d}.hess\n'
    text+=' THE OPTIMIZATION HAS CONVERGED\n SCF HESSIAN\n VIBRATIONAL FREQUENCIES'+block+' ORCA TERMINATED NORMALLY\n'
    p=tmp_path/'hess.out';p.write_text(text);d=load_document(p)
    assert len(d.vibrations)==3
    assert [a.cycle for a in d.vibrations]==[1,3,None]
    assert all('Optimization Hessian' in a.purpose for a in d.vibrations[:2])
    assert d.vibrations[-1].purpose=='Final frequency verification'
    assert [e.cycle for e in d.calculation_results.hessians if 'exact' in e.kind.lower()]==[1,3,None]
    assert d.calculation_results.jobs[0].frequency_count==9


def test_goat_printed_weights_degeneracy_and_conformer_coordinates():
    d=load_document(GOAT);e,=d.conformer_ensembles
    assert len(e.conformers)==4 and e.temperature==298.15
    assert [c.number for c in e.conformers]==[0,1,2,3]
    assert e.conformers[1].degeneracy==2
    assert all(c.frame_index is not None for c in e.conformers)
    weights=e.populations(298.15)
    assert np.isclose(weights.sum(),100)
    np.testing.assert_allclose(weights,[c.printed_percent for c in e.conformers],atol=.03)
    assert e.populations(900)[-1]>weights[-1]
    assert aligned_rmsd(e.conformers[0].reference,e.conformers[1].reference)>0


def test_numerical_hessian_displacements_do_not_overwrite_parent_geometry_energy_or_moments(tmp_path):
    coord=' CARTESIAN COORDINATES (ANGSTROEM)\n ---\n O 0 0 0\n H 1 0 0\n H 0 1 0\n\n'
    text=' ORCA VERSION 6.1\n ! HF def2-SVP OptTS\n * xyz 0 1\n GEOMETRY OPTIMIZATION CYCLE 1\n'+coord+' FINAL SINGLE POINT ENERGY -10\n NUMERICAL HESSIAN\n'+coord.replace('O 0 0 0','O 0.01 0 0')+' FINAL SINGLE POINT ENERGY -9.5\n Total Dipole Moment : 7 8 9\n Actual Hessian File stored as numerical.hess\n GEOMETRY OPTIMIZATION CYCLE 2\n'+coord+' FINAL SINGLE POINT ENERGY -10.1\n'
    path=tmp_path/'numerical.out';path.write_text(text)
    d=load_document(path)
    np.testing.assert_allclose([f.energy_ev/Hartree for f in d.frames],[-10,-10.1])
    assert all(f.positions[0,0]==0 for f in d.frames) and not d.dipoles


def test_goat_missing_companion_preserves_energy_only_rows(tmp_path):
    p=tmp_path/GOAT.name;copy2(GOAT,p)
    e,=load_document(p).conformer_ensembles
    assert len(e.conformers)==4 and all(c.frame_index is None for c in e.conformers)


def test_direct_goat_xyz_does_not_duplicate_or_invent_printed_weights():
    d=load_document(EXAMPLES/'synthetic_goat_v1100.finalensemble.xyz');e,=d.conformer_ensembles
    assert len(d.frames)==4 and [c.frame_index for c in e.conformers]==[0,1,2,3]
    assert all(c.printed_percent is None for c in e.conformers)


def test_goat_log_without_printed_geometry_links_ensemble_once(tmp_path):
    text=GOAT.read_text();start=text.index(' CARTESIAN COORDINATES');end=text.index(' Ensemble temperature',start)
    path=tmp_path/GOAT.name;path.write_text(text[:start]+text[end:])
    xyz=EXAMPLES/'synthetic_goat_v1100.finalensemble.xyz';copy2(xyz,tmp_path/xyz.name)
    d=load_document(path)
    assert len(d.frames)==4 and [c.frame_index for c in d.conformer_ensembles[0].conformers]==[0,1,2,3]


def test_goat_energy_only_log_still_exposes_printed_analysis(tmp_path):
    text=GOAT.read_text();start=text.index(' CARTESIAN COORDINATES');end=text.index(' Ensemble temperature',start)
    path=tmp_path/GOAT.name;path.write_text(text[:start]+text[end:])
    d=load_document(path)
    assert len(d.conformer_ensembles[0].conformers)==4
    assert d.frames[0].info['missing_geometry'] and 'Analysis-only' in d.note


def test_complex_soc_components_states_and_corrected_spectra_stay_separate():
    d=load_document(SOC);a,=d.soc_results
    assert len(a.elements)==3 and len(a.states)==2 and len(a.transitions)==1
    assert a.elements[0].components=={'Z':1+2j,'X':3+4j,'Y':5+6j}
    assert np.isclose(a.elements[0].norm,np.sqrt(91))
    assert a.states[0].composition[1]['imag']==.4
    assert a.transitions[0]['complex_dipole']['X']==[.1,-.2]
    assert len(d.electronic_spectra)==1 and len(d.electronic_spectra[0].transitions)==1
    assert d.electronic_spectra[0].transitions[0].oscillator_strength is None


def test_sparse_soc_preserves_ms_and_complex_scalar(tmp_path):
    p=tmp_path/'scalar.out';p.write_text('NONZERO SOC MATRIX ELEMENTS (cm**-1)\n0 1 1 0 0 2 1 -1 -3.0 4.0\n')
    a,=read_soc(p);e,=a.elements
    assert e.bra=='B0/R1/S1/Ms0' and e.ket=='B0/R2/S1/Ms-1'
    assert e.components['H']==-3+4j and e.norm==5
