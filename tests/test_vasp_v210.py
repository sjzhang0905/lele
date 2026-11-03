"""VASP ionic records remain independent of unavailable structures/energies."""
from pathlib import Path
from unittest.mock import patch
import csv
import numpy as np
import pytest

from lele.formats import load_document
from lele.legacy_converter import detect_format
from lele.result_availability import has_curve_data
from test_periodic_fragment_ui_v171 import gui

HEADER = '''vasp.6.3.0
 POTCAR: PAW_PBE N 08Apr2002
 POTCAR: PAW_PBE H 08Apr2002
 ions per type = 1 1
 NIONS = 2
 IBRION = 5
 POMASS = 14.0 1.0
 direct lattice vectors reciprocal lattice vectors
 8.0 0.0 0.0 0 0 0
 0.0 9.0 0.0 0 0 0
 0.0 0.0 10.0 0 0 0
'''
GEOMETRY = ''' POSITION TOTAL-FORCE (eV/Angst)
 ------------------
 0.0 0.0 0.0 0.1 0.0 -0.2
 0.0 0.0 1.0 0.0 0.3 0.0
 ------------------
'''
ENERGY = ''' FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)
 free energy TOTEN = -10.2 eV
 energy without entropy = -10.0 energy(sigma->0) = -10.1
'''
MODE = ''' Eigenvectors and eigenvalues of the dynamical matrix
 ----------------------------------
 1 f/i= 1.0 THz 6.0 2PiTHz 33.356 cm-1 4.0 meV
 X Y Z dx dy dz
 0.0 0.0 0.0 1.0 0.0 0.0
 0.0 0.0 1.0 -1.0 0.0 0.0
'''
XDAT = '''N H
2.0
1 0 0
0 2 0
0 0 3
N H
1 1
Direct configuration= 1
0 0 0
0.5 0.5 0.5
Direct configuration= 2
0.1 0 0
0.6 0.5 0.5
'''


def write(tmp_path, text, name='OUTCAR_test'):
    p = tmp_path / name
    p.write_text(text)
    return p


def attach(gui, path):
    w = gui.window
    doc = load_document(path)
    w.documents = [doc];w.current_doc = 0;w.frame_index = 0;w.selection = []
    w.files_tree.clear();w._add_document_tree(0, doc);w.change_frame(0)
    gui.addCleanup(lambda: [x.close() for x in list(w._analysis_windows)])
    return w, doc


def test_outcar_summary_energy_forces_cell_and_reference(tmp_path):
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + MODE))
    r = d.calculation_results
    assert len(d.frames) == len(r.steps) == 1
    assert d.frames[0].pbc == (True, True, True)
    assert np.linalg.det(d.frames[0].cell) == pytest.approx(720)
    assert d.frames[0].energy_ev == -10.1
    assert r.steps[0].info['vasp_free_energy_ev'] == -10.2
    assert r.steps[0].convergence['max_force'] == (.3, None)
    assert r.steps[0].convergence['rms_force'][0] == pytest.approx(np.sqrt(.14/6))
    assert d.vibrations[0].reference.energy_ev == -10.1
    assert d.vibrations[0].modes[0].frequency_cm1 == -33.356
    np.testing.assert_allclose(d.vibrations[0].modes[0].displacements[:, 0], [1/np.sqrt(14), -1])
    assert r.jobs[0].imaginary_modes == 1


def test_initial_electronic_toten_is_not_an_ionic_record(tmp_path):
    electronic = ''' ---- Iteration 1( 1) ----
 Free energy of the ion-electron system (eV)
 free energy TOTEN = -99 eV
 energy without entropy = -98 energy(sigma->0) = -97
'''
    d = load_document(write(tmp_path, HEADER + electronic + GEOMETRY + ENERGY))
    assert len(d.calculation_results.steps) == 1
    assert d.frames[0].energy_ev == -10.1


def test_outcar_energy_only_ignores_existing_companions(tmp_path):
    p = write(tmp_path, ENERGY + ENERGY.replace('-10.1', '-10.3'))
    write(tmp_path, XDAT, 'XDATCAR')
    write(tmp_path, 'not a valid structure', 'CONTCAR')
    d = load_document(p)
    assert not d.frames and has_curve_data(d)
    assert [s.energy_ev for s in d.calculation_results.steps] == [-10.1, -10.3]
    assert all(s.geometry is None and s.frame_index is None for s in d.calculation_results.steps)


@pytest.mark.parametrize('text,values', [
    ('free energy TOTEN = -10\nfree energy TOTEN = -11\n', [None, None]),
    ('energy without entropy = -10\nenergy without entropy = -11\n', [None, None]),
    ('energy(sigma->0) = -10\nenergy(sigma->0) = -11\n', [-10, -11])])
def test_only_e0_is_used_as_energy_when_other_quantities_load_alone(tmp_path, text, values):
    d = load_document(write(tmp_path, text))
    assert [s.energy_ev for s in d.calculation_results.steps] == values
    assert not d.frames


def test_outcar_structure_without_energy_retains_forces(tmp_path):
    d = load_document(write(tmp_path, HEADER + GEOMETRY))
    assert len(d.frames) == 1 and d.frames[0].energy_ev is None
    assert has_curve_data(d)  # real printed forces can still be plotted


def test_initial_orientation_cannot_borrow_an_unmatched_energy(tmp_path):
    initial = ' position of ions in cartesian coordinates (Angst):\n0 0 0\n0 0 1\n'
    d = load_document(write(tmp_path, HEADER + initial + ENERGY))
    assert d.frames[0].energy_ev is None
    assert d.calculation_results.steps[1].geometry is None


def test_truncated_last_structure_never_reuses_previous_positions(tmp_path):
    broken = 'POSITION TOTAL-FORCE\n----\n0 0 0 0 0 0\n'
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + broken + ENERGY))
    assert len(d.frames) == 1
    assert d.calculation_results.steps[-1].geometry is None
    assert d.calculation_results.steps[-1].frame_index is None
    assert 'Incomplete coordinates' in d.note


def test_concatenated_runs_keep_separate_jobs_and_missing_geometry(tmp_path):
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + 'vasp.6.4.0\n' + ENERGY))
    r = d.calculation_results
    assert len(r.jobs) == 2 and len(d.frames) == 1
    assert r.steps[1].job_index == 1 and r.steps[1].geometry is None


def test_fixed_width_adjacent_negative_lattice_values(tmp_path):
    text = HEADER.replace('8.0 0.0 0.0 0 0 0', '8.000000000-1.000000000-2.000000000 0 0 0')
    d = load_document(write(tmp_path, text + GEOMETRY))
    np.testing.assert_allclose(d.frames[0].cell[0], [8, -1, -2])


def test_raw_and_mass_divided_tables_are_not_duplicate_modes(tmp_path):
    divided = MODE.replace('Eigenvectors and eigenvalues of the dynamical matrix',
                           'Eigenvectors after division by SQRT(mass)').replace('1.0 0.0 0.0', '.25 0.0 0.0')
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + MODE + divided))
    assert len(d.vibrations) == len(d.vibrations[0].modes) == 1
    assert d.vibrations[0].modes[0].displacements[0, 0] == .25


def test_frequency_only_without_species_or_reference_is_readable(tmp_path):
    d = load_document(write(tmp_path, MODE.split(' X Y Z')[0]))
    assert d.frames == [] and d.vibrations == []
    assert not has_curve_data(d)
    assert d.calculation_results.jobs[0].frequency_count == 1


def test_mode_table_can_supply_its_own_reference_without_ionic_steps(tmp_path):
    d = load_document(write(tmp_path, HEADER + MODE))
    assert len(d.frames) == 1 and d.frames[0].energy_ev is None
    assert d.vibrations[0].modes[0].can_animate


def test_xdatcar_geometry_only_cartesian_conversion_and_duplicate_species(tmp_path):
    d = load_document(write(tmp_path, XDAT, 'XDATCAR_trajectory'))
    assert len(d.frames) == 2 and not has_curve_data(d)
    np.testing.assert_allclose(d.frames[0].positions[1], [1, 2, 3])
    assert all(f.energy_ev is None for f in d.frames)
    text = XDAT.replace('N H\n1 1', 'H H\n1 1')
    repeated = load_document(write(tmp_path, text, 'renamed.data'))
    assert repeated.frames[0].info['poscar_groups'] == [('H', 1), ('H', 1)]


def test_legacy_structure_converter_can_still_read_xdatcar(tmp_path):
    from lele.legacy_converter import read_structure
    atoms, detection = read_structure(write(tmp_path, XDAT, 'XDATCAR'))
    assert len(atoms) == 2 and detection.kind == 'vasp_xdatcar'
    np.testing.assert_allclose(atoms.positions[0], [.2, 0, 0])


def test_xdatcar_cartesian_and_changing_cell_keep_distinct_frames(tmp_path):
    first = XDAT.split('Direct configuration= 2')[0].replace('Direct configuration', 'Cartesian configuration')
    second = first.replace('2.0\n', '3.0\n', 1)
    d = load_document(write(tmp_path, first + second, 'XDATCAR'))
    assert len(d.frames) == 2
    np.testing.assert_allclose(d.frames[0].positions[1], [1, 1, 1])
    np.testing.assert_allclose(d.frames[1].positions[1], [1.5, 1.5, 1.5])
    assert not np.allclose(d.frames[0].cell, d.frames[1].cell)


def test_xdatcar_negative_volume_scale_and_partial_tail(tmp_path):
    text = XDAT.replace('2.0\n', '-48.0\n', 1) + 'Direct configuration= 3\n0 0 0\n'
    d = load_document(write(tmp_path, text, 'XDATCAR'))
    assert len(d.frames) == 2 and abs(np.linalg.det(d.frames[0].cell)) == pytest.approx(48)
    assert 'Incomplete XDATCAR configuration' in d.note


def test_identical_timestep_geometries_are_not_collapsed(tmp_path):
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + GEOMETRY + ENERGY))
    assert len(d.frames) == 2
    assert [s.frame_index for s in d.calculation_results.steps] == [0, 1]


def test_frame_limit_rejects_without_silently_loading_last_frame(tmp_path):
    p = write(tmp_path, XDAT, 'XDATCAR')
    with pytest.raises(ValueError, match='exceeds 1 frames'):
        load_document(p, max_frames=1)


def test_blank_preamble_is_not_an_extra_calculation(tmp_path):
    d = load_document(write(tmp_path, '\n\n' + HEADER + GEOMETRY + ENERGY))
    assert len(d.calculation_results.jobs) == 1


def test_empty_coordinate_block_cannot_consume_a_later_table(tmp_path):
    text = HEADER + 'POSITION TOTAL-FORCE\n----\nFREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n'
    text += ENERGY + 'unrelated table\n0 0 0 0 0 0\n0 0 1 0 0 0\n'
    d = load_document(write(tmp_path, text))
    assert not d.frames and len(d.calculation_results.steps) == 1
    assert d.calculation_results.steps[0].energy_ev == -10.1


def test_partial_mass_divided_table_keeps_the_complete_raw_mode(tmp_path):
    divided = MODE.replace('Eigenvectors and eigenvalues of the dynamical matrix',
                           'Eigenvectors after division by SQRT(mass)')
    divided = divided.rsplit(' 0.0 0.0 1.0', 1)[0]
    d = load_document(write(tmp_path, HEADER + GEOMETRY + ENERGY + MODE + divided))
    assert len(d.vibrations[0].modes) == 1 and d.vibrations[0].modes[0].can_animate
    np.testing.assert_allclose(d.vibrations[0].modes[0].displacements[:, 0], [1/np.sqrt(14), -1])


def test_oszicar_only_ionic_summaries_no_electronic_iterations(tmp_path):
    text = ''' N E dE d eps ncg rms rms(c)
DAV: 1 -99.0 -1.0 0 10 1 1
 1 F= -10.2 E0= -10.1 d E= -.1
DAV: 1 -98.0 -1.0 0 10 1 1
 2 T= 300. E= -9.0 F= -10.4 E0= -10.3 EK= 1.0
'''
    d = load_document(write(tmp_path, text, 'OSZICAR'))
    assert d.frames == []
    assert [s.energy_ev for s in d.calculation_results.steps] == [-10.1, -10.3]


def test_renamed_vasp_energy_only_output_detected_from_contents(tmp_path):
    p = write(tmp_path, 'vasp.6.3.0\n' + ENERGY, 'energy.out')
    assert detect_format(p).kind == 'vasp_out'
    assert not load_document(p).frames


def test_energy_only_ui_curve_csv_and_overview(gui, tmp_path):
    w, d = attach(gui, write(tmp_path, ENERGY + ENERGY.replace('-10.1', '-10.3')))
    assert w.frame is None and w.canvas_stack.currentWidget() is w.results_only_page
    assert not w.play_btn.isEnabled() and not w.gif_action.isEnabled()
    assert w.energy_curve_action.isEnabled()
    assert 'eV' in w.files_tree.topLevelItem(0).child(0).child(0).text(0)
    curve = w.show_energy_curve()
    assert [x['energy_ev'] for x in curve.points()] == [-10.1, -10.3]
    assert all(x['frame'] is None for x in curve.points())
    assert not hasattr(curve, 'energy_kind')
    out = tmp_path/'energies.csv'
    with patch('PySide6.QtWidgets.QFileDialog.getSaveFileName', return_value=(str(out), 'CSV')):
        curve.export_data()
    records = list(csv.DictReader(out.open(encoding='utf-8-sig')))
    assert len(records) == 2 and records[0]['geometry_frame'] == ''
    assert float(records[1]['energy_E0_eV']) == -10.3
    assert not any('free_energy' in key or 'without_entropy' in key or 'selected_energy' in key for key in records[0])
    overview = w.show_calculation_overview()
    assert 'No structure' in overview.header.text()
    assert 'E0 (σ→0): -10.300000000 eV' in w.results_only_info.toPlainText()
    item = w.files_tree.topLevelItem(0).child(0).child(0)
    w.files_tree.setCurrentItem(item)
    assert 'E0 (σ→0): -10.100000000 eV' in w.results_only_info.toPlainText()
    assert 'TOTEN' not in w.results_only_info.toPlainText()


def test_vasp_frequency_ui_uses_reference_and_source_cell(gui, tmp_path):
    w, d = attach(gui, write(tmp_path, HEADER + GEOMETRY + ENERGY + MODE))
    assert w.frame is d.frames[0]
    assert 'Frequency calculation structures' in w.files_tree.topLevelItem(0).child(0).text(0)
    w.select_vibration(0, 0, 0, autoplay=False)
    assert w.frame is not None and w.frame.pbc == (True, True, True)
    np.testing.assert_allclose(w.frame.cell, d.frames[0].cell)
    assert '33.356' in w.info_view.toPlainText()
    overview = w.show_calculation_overview()
    assert 'threshold not printed' in overview.details.toPlainText()
    assert 'E0 (σ→0): -10.100000000 eV' in w.info_view.toPlainText()
    assert 'TOTEN' not in w.info_view.toPlainText()


def test_xdatcar_ui_navigation_and_results_only_switch(gui, tmp_path):
    w, d = attach(gui, write(tmp_path, XDAT, 'XDATCAR'))
    assert not w.energy_curve_action.isEnabled() and w.play_btn.isEnabled()
    w._step_next();assert w.frame_index == 1
    w._open_path_now(write(tmp_path, ENERGY, 'OUTCAR_energy'))
    assert w.frame is None and w.canvas_stack.currentWidget() is w.results_only_page
    w.change_frame(1, switch_doc=0)
    assert w.frame is d.frames[1] and w.canvas_stack.currentWidget() is w.structure_page
    assert not w.energy_curve_action.isEnabled()
