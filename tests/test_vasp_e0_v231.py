"""E0 is the sole VASP energy across parsers, views, exports and projects."""
from pathlib import Path
from unittest.mock import patch
import csv
import numpy as np
import pytest

from lele.formats import load_document
from lele.project_file import save_project, load_project
from lele.render_options import RenderOptions
from lele.result_availability import has_curve_data
from lele.vasp_results import ENERGY_KEY
from test_vasp_v210 import HEADER, GEOMETRY, ENERGY, MODE, write, attach
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('text', [
    ' 1 F= -10.2 d E= -.1\n',
    ' 1 T= 300 E= -9 F= -10.2 EK= 1\n'])
def test_oszicar_without_e0_does_not_use_free_or_md_energy(tmp_path, text):
    d = load_document(write(tmp_path, text, 'OSZICAR'))
    assert d.frames == [] and not has_curve_data(d)
    assert d.calculation_results.steps[0].energy_ev is None
    assert d.calculation_results.jobs[0].energy_ev is None


def test_oszicar_e0_scientific_notation_and_missing_step(tmp_path):
    text = (' 1 F= -20 E0= -.101D+02 d E= -2\n'
            ' 2 F= -21 d E= -1\n'
            ' 3 T= 300 E= -9 F= -22 E0= -.103E+02 EK= 1\n')
    d = load_document(write(tmp_path, text, 'OSZICAR'))
    assert [s.energy_ev for s in d.calculation_results.steps] == [-10.1, None, -10.3]
    assert d.calculation_results.jobs[0].energy_ev == -10.3


def test_structure_and_curve_keep_missing_e0_as_gap_and_csv_blank(gui, tmp_path):
    no_e0 = ' FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n free energy TOTEN = -99 eV\n'
    text = HEADER+GEOMETRY+ENERGY+GEOMETRY+no_e0+GEOMETRY+ENERGY.replace('-10.1', '-10.3')
    w, d = attach(gui, write(tmp_path, text))
    assert [f.energy_ev for f in d.frames] == [-10.1, None, -10.3]
    w.change_frame(1)
    assert w.frame is d.frames[1] and 'E0 (σ→0):' not in w.info_view.toPlainText()
    curve = w.show_energy_curve()
    assert [r['energy_ev'] for r in curve.points()] == [-10.1, None, -10.3]
    y = curve.energy_axes.lines[0].get_ydata()
    assert len(y) == 3 and np.isnan(y[1])
    assert 'Relative E0' in curve.energy_axes.get_ylabel()
    destination = tmp_path/'e0.csv'
    with patch('lele.convergence_dialog.QFileDialog.getSaveFileName', return_value=(str(destination), 'CSV')):
        curve.export_data()
    with destination.open(encoding='utf-8-sig') as f:records = list(csv.DictReader(f))
    assert records[1]['energy_E0_eV'] == '' and float(records[2]['energy_E0_eV']) == -10.3
    assert set(records[0]) == {'ionic_record','geometry_frame','energy_E0_eV','max_force_eV_A','rms_force_eV_A','source_line'}


def test_free_energy_only_file_has_no_energy_curve_or_fake_structure(gui, tmp_path):
    w, d = attach(gui, write(tmp_path, 'free energy TOTEN = -10\nfree energy TOTEN = -11\n'))
    assert w.frame is None and not w.energy_curve_action.isEnabled()
    assert 'E0 (σ→0): not printed' in w.results_only_info.toPlainText()
    assert 'TOTEN' not in w.results_only_info.toPlainText()
    overview = w.show_calculation_overview()
    assert overview.table.horizontalHeaderItem(6).text() == 'E0 (eV)'
    assert overview.table.item(0, 6).text() == 'Not printed'


def test_geometry_edit_cannot_display_historical_e0_as_current_energy(gui, tmp_path):
    w, d = attach(gui, write(tmp_path, HEADER+GEOMETRY+ENERGY))
    assert 'E0 (σ→0): -10.100000000 eV' in w.info_view.toPlainText()
    w.atom_table.item(1, 3).setText('2.0')
    assert w.frame.energy_ev is None and w.frame.info[ENERGY_KEY] == -10.1
    assert 'E0 (σ→0): -10.100000000' not in w.info_view.toPlainText()
    # Source calculation results and the source text remain independently available.
    assert d.calculation_results.steps[0].energy_ev == -10.1
    assert 'free energy TOTEN' in w.source_view.toPlainText()


def test_project_migrates_old_fallbacks_and_keeps_edited_energies_cleared(tmp_path):
    d = load_document(write(tmp_path, HEADER+GEOMETRY+ENERGY+GEOMETRY+ENERGY))
    d.frames[0].energy_ev = d.calculation_results.steps[0].energy_ev = -99
    d.frames[0].info.pop(ENERGY_KEY);d.calculation_results.steps[0].info.pop(ENERGY_KEY)
    d.frames[0].info['energy_source'] = 'Free energy TOTEN'
    d.frames[1].energy_ev = None  # A prior coordinate edit invalidated this energy.
    d.calculation_results.jobs[0].energy_ev = -99
    d.note = d.calculation_results.note = 'Default energy: σ→0, then TOTEN, then energy without entropy, in eV.'
    cached = d.frames[0].clone()
    state = dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0,vibration_references={0:cached})],current_document=0)
    path = tmp_path/'legacy.lele';save_project(path,state);entry = load_project(path)['documents'][0]
    restored = entry['document']
    assert [f.energy_ev for f in restored.frames] == [None, None]
    assert [s.energy_ev for s in restored.calculation_results.steps] == [None, -10.1]
    assert restored.calculation_results.jobs[0].energy_ev == -10.1
    assert entry['vibration_references'][0].energy_ev is None
    assert 'energy_source' not in restored.frames[0].info and 'TOTEN' not in restored.note


def test_project_replaces_old_default_with_printed_e0_and_retains_mode_reference(tmp_path):
    d = load_document(write(tmp_path, HEADER+GEOMETRY+ENERGY+GEOMETRY+ENERGY.replace('-10.1','-12.3')+MODE))
    for f in [*d.frames, d.vibrations[0].reference]:f.energy_ev = -99
    for s in d.calculation_results.steps:s.energy_ev = -99
    d.calculation_results.jobs[0].energy_ev = -99
    path = tmp_path/'legacy_modes.lele'
    save_project(path,dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0)],current_document=0))
    new = load_project(path)['documents'][0]['document']
    assert [f.energy_ev for f in new.frames] == [-10.1, -12.3]
    assert new.vibrations[0].reference.energy_ev == -10.1
    assert new.calculation_results.jobs[0].energy_ev == -10.1


def test_project_with_only_legacy_free_energy_records_opens_without_fallback(gui, tmp_path):
    d = load_document(write(tmp_path, 'free energy TOTEN = -10\n'))
    d.calculation_results.steps[0].energy_ev = d.calculation_results.jobs[0].energy_ev = -10
    path = tmp_path/'legacy_results.lele'
    save_project(path,dict(documents=[dict(document=d,options=RenderOptions(),frame_index=0)],current_document=0))
    w = gui.window;assert w._load_project_path(path)
    assert w.frame is None and not w.energy_curve_action.isEnabled()
    assert w.doc.calculation_results.jobs[0].energy_ev is None
