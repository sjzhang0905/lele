"""ORCA printed units, job boundaries, spin manifolds and incomplete output."""
from pathlib import Path
from math import pi
import numpy as np
import pytest
from ase.units import Hartree
from lele.formats import load_document
from lele.gaussian_properties import AU_TO_DEBYE, selected_dipole
from lele.property_export import transition_rows, export_dipoles
from lele.spectra import simulated_spectrum

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/synthetic_orca_full_v190.out'


@pytest.fixture
def doc():
    return load_document(EXAMPLE)


def test_orca_jobs_keep_geometry_charge_energy_and_convergence_together(doc):
    result = doc.calculation_results
    assert len(result.jobs) == 2 and len(doc.frames) == 3
    assert [f.info['converter_charge'] for f in doc.frames] == [0, 0, 1]
    assert [f.info['converter_mult'] for f in doc.frames] == [1, 1, 2]
    np.testing.assert_allclose([f.energy_ev/Hartree for f in doc.frames], [-75, -75.01, -74.8])
    assert result.force_unit == 'Hartree/Bohr' and result.displacement_unit == 'Bohr'
    assert result.steps[1].convergence['max_force'] == (.00004, .0003)
    assert result.steps[1].converged and 'Scan' in result.jobs[0].tasks
    assert result.jobs[0].solvent == 'water'
    assert [j.scf_cycles for j in result.jobs] == [4, 6]
    assert result.jobs[0].frequency_count == 9 and result.jobs[0].imaginary_modes == 1
    assert result.jobs[1].spin_squared == .752


def test_orca_frontier_numbers_occupations_and_spin_channels_are_printed_values(doc):
    restricted, opened = doc.calculation_results.orbitals
    assert restricted.frame_index == 0 and opened.frame_index == 2
    h, l, gap = restricted.frontier('Restricted')
    assert (h.number, l.number, h.occupation, l.occupation) == (4, 5, 2, 0)
    assert np.isclose(gap, 9.523985)
    assert set(opened.channels) == {'Alpha', 'Beta'}
    assert opened.frontier('Alpha')[0].number == 1
    assert opened.frontier('Beta')[0].number == 0


def test_orca_modes_use_frequency_geometry_and_printed_vectors_without_mass_reweighting(doc):
    analysis, = doc.vibrations
    np.testing.assert_array_equal(analysis.reference.positions, doc.frames[1].positions)
    assert [m.number for m in analysis.modes] == [6, 7, 8]
    assert [m.frequency_cm1 for m in analysis.modes] == [-250, 1500, 3600]
    assert all(m.can_animate for m in analysis.modes)
    mode = analysis.modes[0]
    np.testing.assert_array_equal(mode.displacements[1], [.15, .4, 0])
    moved = mode.positions_at(analysis.reference, pi/2, .35)
    assert np.isclose(np.linalg.norm(moved-analysis.reference.positions, axis=1).max(), .35)
    assert analysis.reference.info['converter_charge'] == 0


def test_ir_uses_integrated_int_column_instead_of_eps_or_dipole_strength(doc):
    modes = doc.vibrations[0].modes
    assert modes[1].ir_intensity == 10.13 and modes[1].ir_intensity_unit == 'km/mol'
    assert modes[2].ir_intensity == 198.71 and modes[2].raman_activity == 24.527417
    for kind in ('IR', 'Raman', 'UV-Vis'):
        x, y, _ = simulated_spectrum(doc, kind)
        assert len(x) == 5000 and np.isfinite(y).all() and np.isclose(y.max(), 1)


def test_orca_moments_keep_units_geometry_and_signed_contributions(doc, tmp_path):
    assert len(doc.dipoles) == 3 and doc.dipoles[-1].kind == 'excited permanent'
    assert doc.dipoles[-1].state_number == 1 and doc.dipoles[-1].density == 'ORCA unrelaxed'
    np.testing.assert_allclose(doc.dipoles[0].vector, [1*AU_TO_DEBYE, -2*AU_TO_DEBYE, .5*AU_TO_DEBYE])
    np.testing.assert_array_equal(doc.dipoles[0].reference.positions, doc.frames[1].positions)
    spectrum, = doc.electronic_spectra
    np.testing.assert_array_equal(spectrum.reference.positions, doc.frames[2].positions)
    first = spectrum.transitions[0]
    np.testing.assert_allclose(first.electric_dipole_au, [.1, -.2, 1.002247])
    np.testing.assert_allclose(first.velocity_dipole_au, [.01, -.02, .03])
    np.testing.assert_allclose(first.magnetic_dipole_au, [.001, -.002, .003])
    assert first.oscillator_strength == .1 and first.oscillator_strength_velocity == .09
    assert first.contributions[0].coefficient == -.87185424
    assert first.contributions[0].printed_weight == .760130
    assert first.source_label == '0-2A -> 1-2A'
    assert selected_dipole(doc, doc.frames[0], 'transition:0:1') is None
    np.testing.assert_allclose(selected_dipole(doc, doc.frames[2], 'transition:0:1'), first.electric_dipole_au*AU_TO_DEBYE)
    row = transition_rows(doc)[0]
    assert 'source_label' in row and '-0.87185424' in row['contributions_json']
    assert export_dipoles(tmp_path/'moments.csv', doc) == 5


@pytest.mark.parametrize('encoding', ['utf-16', 'utf-16-be', 'utf-8-sig'])
def test_windows_output_encoding_is_detected_and_read(tmp_path, encoding):
    path = tmp_path/'encoded.out'
    path.write_bytes(EXAMPLE.read_text().encode(encoding))
    result = load_document(path)
    assert result.format_name == 'ORCA output' and len(result.frames) == 3
    assert result.electronic_spectra[0].transitions[0].oscillator_strength == .1


def test_truncated_normal_mode_chunk_does_not_create_motion_from_missing_rows(tmp_path):
    text = EXAMPLE.read_text()
    start = text.index('\n 6 7 8\n')
    truncated = text[:text.index('\n 8 ', start+10)]
    path = tmp_path/'partial.out';path.write_text(truncated)
    doc = load_document(path)
    assert len(doc.vibrations[0].modes) == 3
    assert all(m.displacements is None for m in doc.vibrations[0].modes)
    assert 'incomplete displacement' in doc.vibrations[0].note


def test_later_job_without_coordinates_never_borrows_an_old_reference(tmp_path):
    text = EXAMPLE.read_text().split(' JOB NUMBER 2')[0]
    text += '\n JOB NUMBER 2\n VIBRATIONAL FREQUENCIES\n 6: 123.0 cm**-1\n\n Total Dipole Moment : 1.0 2.0 3.0\n'
    path = tmp_path/'missing_reference.out';path.write_text(text)
    doc = load_document(path)
    assert len(doc.vibrations) == 1 and doc.dipoles[-1].reference is None
    assert 'no reference geometry' in doc.note


def test_classic_combined_spin_table_maps_triplets_with_restarted_state_numbers(tmp_path):
    text = EXAMPLE.read_text().split(' VIBRATIONAL FREQUENCIES')[0]
    text += '''
 TD-DFT/TDA EXCITED STATES (SINGLETS)
 STATE 1: E= 0.1 au 2.721 eV
 4a -> 5a : 0.81 (c= -0.9)
 TD-DFT/TDA EXCITED STATES (TRIPLETS)
 STATE 1: E= 0.05 au 1.360 eV
 4a -> 5a : 0.64 (c= 0.8)
 ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
 State Energy Wavelength fosc T2 TX TY TZ
       (cm-1) (nm) (au**2) (au) (au) (au)
 1 21947.46 455.6 0.1 1.5 1.0 -0.5 0.5
 2 10973.73 911.3 spin forbidden (mult=3)
'''
    path = tmp_path/'spin.out';path.write_text(text)
    doc = load_document(path);singlet, triplet = doc.electronic_spectra
    assert len(singlet.transitions) == len(triplet.transitions) == 1
    assert triplet.transitions[0].number == 1 and triplet.transitions[0].source_label == '2'
    assert triplet.transitions[0].oscillator_strength == 0
    assert triplet.transitions[0].electric_dipole_au is None
    assert singlet.transitions[0].contributions[0].coefficient == -.9


def test_orca6_table_spin_local_number_maps_global_state_number_without_duplicate(tmp_path):
    text = EXAMPLE.read_text().split(' VIBRATIONAL FREQUENCIES')[0]
    text += '''
 TD-DFT/TDA EXCITED STATES (SINGLETS)
 STATE 1: E= 0.1 au 2.721 eV Mult 1
 TD-DFT/TDA EXCITED STATES (TRIPLETS)
 STATE 2: E= 0.05 au 1.360 eV Mult 3
 4a -> 5a : 0.64 (c= -0.8)
 ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
 Transition Energy Energy Wavelength fosc(D2) D2 DX DY DZ
 (eV) (cm-1) (nm) (au**2) (au) (au) (au)
 0-1Ag -> 1-3Bu 1.360 10973.73 911.3 0.0 0.0 0.0 0.0 0.0
 0-1Ag -> 1-1Bu 2.721 21947.46 455.6 0.1 1.5 1.0 -0.5 0.5
'''
    path = tmp_path/'spin_local.out';path.write_text(text)
    doc = load_document(path);singlet, triplet = doc.electronic_spectra
    assert len(triplet.transitions) == 1 and triplet.transitions[0].number == 2
    assert triplet.transitions[0].source_label == '0-1Ag -> 1-3Bu'
    assert triplet.transitions[0].contributions[0].coefficient == -.8
    assert singlet.transitions[0].oscillator_strength == .1


def test_legacy_ir_t_squared_is_retained_without_claiming_integrated_units(tmp_path):
    text = EXAMPLE.read_text().replace('Mode freq eps Int T**2 TX TY TZ', 'Mode freq (cm**-1) T**2 TX TY TZ')
    text = text.replace('7: 1500.00 0.002004 10.13 0.000511', '7: 1500.00 10.13')
    text = text.replace('8: 3600.00 0.039321 198.71 0.004363', '8: 3600.00 198.71')
    path = tmp_path/'legacy_ir.out';path.write_text(text)
    doc = load_document(path)
    assert doc.vibrations[0].modes[1].ir_intensity == 10.13
    assert doc.vibrations[0].modes[1].ir_intensity_unit == 'printed T²'


def test_spectrum_only_output_retains_zero_based_state_numbers(tmp_path):
    text = EXAMPLE.read_text().split(' VIBRATIONAL FREQUENCIES')[0]
    text += '''
 ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS
 State Energy Wavelength fosc T2 TX TY TZ
       (cm-1) (nm) (au**2) (au) (au) (au)
 0 21947.46 455.6 0.1 1.5 1.0 -0.5 0.5
 1 32921.19 303.7 0.2 2.0 -1.0 0.5 -0.5
'''
    path = tmp_path/'spectrum_only.out';path.write_text(text)
    transitions = load_document(path).electronic_spectra[0].transitions
    assert [t.number for t in transitions] == [0, 1]
    assert transitions[1].oscillator_strength == .2
