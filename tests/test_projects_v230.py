"""Portable scientific snapshots and live multi-document view restoration."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import zipfile
import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance
from lele.core import Document, Frame, Volume, freeze_bonds, visible_bonds
from lele.formats import load_document
from lele.project_file import save_project, load_project, FORMAT, SCHEMA
from lele.render_options import RenderOptions
from lele.element_rules import default_rule, install_rules
from lele.crystal_planes import default_plane
from lele.trajectory_analysis import DisplayAlignment, GeometryParameter
from test_periodic_fragment_ui_v171 import gui
from test_crystal_v220 import octahedron

EXAMPLES = Path(__file__).resolve().parents[1]/'examples'


def state_for(document):
    return dict(documents=[dict(document=document, options=RenderOptions(), frame_index=0)],
                current_document=0, selection=[])


@pytest.mark.parametrize('name', [
    'water.xyz', 'synthetic_opt_freq.log', 'synthetic_properties.log',
    'synthetic_orca_full_v190.out', 'synthetic_neb_v1100.out',
    'synthetic_goat_v1100.out', 'synthetic_soc_v1100.out',
    'synthetic_xtb_energy_only_v1111.out', 'synthetic_gxtb_v1110.out',
    'synthetic_vasp_v210.OUTCAR', 'synthetic_vasp_energy_only_v210.OUTCAR',
    'synthetic_vasp_geometry_only_v210.XDATCAR'])
def test_all_builtin_scientific_results_roundtrip(tmp_path, name):
    source = load_document(EXAMPLES/name)
    path = tmp_path/'scientific.lele';save_project(path, state_for(source))
    restored = load_project(path)['documents'][0]['document']
    assert restored.format_name == source.format_name
    assert len(restored.frames) == len(source.frames)
    for a, b in zip(restored.frames, source.frames):
        assert a.symbols == b.symbols and a.energy_ev == b.energy_ev
        np.testing.assert_array_equal(a.positions, b.positions)
        np.testing.assert_array_equal(a.cell, b.cell)
    assert len(restored.vibrations) == len(source.vibrations)
    for a, b in zip(restored.vibrations, source.vibrations):
        np.testing.assert_array_equal(a.reference.positions, b.reference.positions)
        assert [m.frequency_cm1 for m in a.modes] == [m.frequency_cm1 for m in b.modes]
        for am, bm in zip(a.modes, b.modes):
            if bm.displacements is not None:np.testing.assert_array_equal(am.displacements, bm.displacements)
    assert len(restored.neb_runs) == len(source.neb_runs)
    assert len(restored.conformer_ensembles) == len(source.conformer_ensembles)
    assert len(restored.soc_results) == len(source.soc_results)
    if source.calculation_results is not None:
        a, b = restored.calculation_results, source.calculation_results
        assert type(a) is type(b) and len(a.steps) == len(b.steps)
        assert [s.energy_ev for s in a.steps] == [s.energy_ev for s in b.steps]
        assert len(a.hessians) == len(b.hessians)
        if hasattr(b, 'frequency_records'):assert a.frequency_records == b.frequency_records
    # A second save catches data-class fields or references lost on decoding.
    save_project(tmp_path/'second.lele', state_for(restored))


def test_volume_overrides_frozen_graph_and_shared_identity(tmp_path):
    f = octahedron();f.atom_appearance[1] = AtomAppearance(color='#123456', opacity=.4)
    f.bond_removed.add((0, 1));f.bond_added.add((1, 2));f.hbond_added[0, 3] = (0, 0, -1)
    freeze_bonds(f)
    f.info.update(complex_scalar=2+3j, array=np.arange(9).reshape(3, 3), missing=float('nan'))
    volume = Volume(np.arange(27).reshape(3, 3, 3), np.ones(3), np.eye(3)*.25)
    doc = Document(Path('missing.xyz'), 'XYZ', [f, f.clone()], volume, modified=True)
    state = state_for(doc);state['result_sequence'] = (doc, (1, 0), 'History')
    entry = state['documents'][0]
    entry['alignment'] = DisplayAlignment(f, (0, 1, 2), 0)
    entry['geometry_parameters'] = [GeometryParameter('Distance', (0, 1))]
    path = tmp_path/'graph.lele';save_project(path, state);new = load_project(path)
    restored = new['documents'][0]['document'];rf = restored.frames[0]
    assert new['result_sequence'][0] is restored
    assert new['documents'][0]['alignment'].reference is rf
    assert rf.bond_added == f.bond_added and rf.bond_removed == f.bond_removed
    assert rf.hbond_added == f.hbond_added and rf.bond_snapshot == f.bond_snapshot
    assert rf.periodic_bond_snapshot == f.periodic_bond_snapshot
    assert visible_bonds(rf) == visible_bonds(f)
    assert rf.atom_appearance == f.atom_appearance and restored.modified
    assert rf.info['complex_scalar'] == 2+3j and np.isnan(rf.info['missing'])
    np.testing.assert_array_equal(restored.volume.data, volume.data)
    np.testing.assert_array_equal(rf.info['array'], f.info['array'])
    assert new['documents'][0]['geometry_parameters'][0].value(rf) == 2
    with zipfile.ZipFile(path) as archive:
        assert 'manifest.json' in archive.namelist()
        assert all(n == 'manifest.json' or n.endswith('.npy') for n in archive.namelist())


def test_atomic_failure_keeps_previous_project(tmp_path):
    path = tmp_path/'existing.lele';state = state_for(Document(Path('a.xyz'), 'XYZ', [octahedron()]))
    save_project(path, state);before = path.read_bytes()
    with patch('lele.project_file.os.replace', side_effect=PermissionError('Destination busy')):
        with pytest.raises(PermissionError):save_project(path, state)
    assert path.read_bytes() == before and not list(tmp_path.glob('*.tmp'))
    state['unsupported'] = lambda:None
    with pytest.raises(ValueError, match='Unsupported project value'):save_project(path, state)
    assert path.read_bytes() == before


@pytest.mark.parametrize('invalid', ['schema', 'unknown_class', 'array_object', 'index', 'camera'])
def test_invalid_projects_are_rejected(tmp_path, invalid):
    path = tmp_path/'bad.lele'
    state = state_for(Document(Path('a.xyz'), 'XYZ', [octahedron()]))
    if invalid in ('index', 'camera'):
        if invalid == 'index':state['current_document'] = 10
        else:state['documents'][0]['camera'] = {'position':[float('nan'), 0, 0]}
        save_project(path, state)
    else:
        manifest = dict(format=FORMAT, schema=SCHEMA, root={'ref':0}, nodes=[])
        if invalid == 'schema':manifest['schema'] = 999
        elif invalid == 'unknown_class':manifest['nodes'] = [dict(kind='object', type='subprocess:Popen', attributes={})]
        else:manifest['nodes'] = [dict(kind='array', path='arrays/object.npy')]
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            if invalid == 'array_object':
                with archive.open('arrays/object.npy', 'w') as stream:np.save(stream, np.array([{}], dtype=object))
    with pytest.raises(ValueError):load_project(path)


def empty_window(gui):
    case = type(gui)('test_invert_complements_selection_and_updates_coordinate_table');case.setUp()
    gui.addCleanup(case.doCleanups)
    w = case.window;w.documents = [];w.current_doc = -1;w.files_tree.clear()
    w._view_document = w._scene_document = None;w._document_views.clear();w.selection = []
    return w


def set_camera(w, position):
    camera = w.scene.GetActiveCamera();camera.SetPosition(*position);camera.SetFocalPoint(1, 1, 1)
    camera.SetParallelProjection(True);camera.SetParallelScale(7.5);camera.SetClippingRange(.1, 100)
    return tuple(camera.GetPosition())


def test_project_restores_multiple_files_rules_views_and_no_source_dependency(gui, tmp_path):
    from lele.project_actions import camera_data
    source = tmp_path/'original.POSCAR';source.write_text((EXAMPLES/'SrTiO3_polyhedra.POSCAR').read_text())
    w = gui.window;w._open_path_now(source);first = w.doc;first_index = w.current_doc
    # Ignore the fixture's initial placeholder document in this session.
    w._apply_element_pair_rules([{**default_rule(), 'maximum':2.2}], True)
    w._set_option('style', 'Polyhedral');w.render_options.boundary_enabled = True
    w.render_options.boundary_bounds = ((0., 2.), (0., 1.), (0., 1.))
    w.render_options.lattice_planes = [{**default_plane(), 'hkl':(1, 1, 1), 'mode':'Show only'}]
    w.frame.atom_appearance[0] = AtomAppearance(color='#AA2233')
    w.refresh_scene();set_camera(w, (11, 13, 17));first_camera = camera_data(w.scene.GetActiveCamera())
    w._geometry_parameters[id(first)] = [GeometryParameter('Distance', (0, 1))]
    w._open_path_now(EXAMPLES/'water_trajectory.xyz');second = w.doc
    w.change_frame(1);w._set_option('style', 'Ball and stick');set_camera(w, (7, 8, 15))
    gui.select([1]);second_camera = camera_data(w.scene.GetActiveCamera());project = tmp_path/'session.lele'
    assert w.save_project_to(project)
    source.unlink()
    restored = empty_window(gui)
    with patch('lele.project_actions.QMessageBox.warning', side_effect=AssertionError('Unexpected warning')):
        assert restored._load_project_path(project)
    assert restored.current_doc == 2 and restored.frame_index == 1 and restored.selection == [1]
    assert camera_data(restored.scene.GetActiveCamera()) == second_camera
    assert restored._project_path == project and restored.save_project_action.isEnabled()
    restored.change_frame(0, switch_doc=first_index)
    assert restored.render_options.style == 'Polyhedral' and restored.render_options.pair_rules_only
    assert restored.render_options.boundary_enabled and restored.render_options.lattice_planes[0]['hkl'] == (1, 1, 1)
    assert restored.frame.atom_appearance[0].color == '#AA2233'
    assert camera_data(restored.scene.GetActiveCamera()) == first_camera
    assert restored.doc.source_preview and 'Sr' in restored.source_view.toPlainText()
    assert restored._geometry_parameters[id(restored.doc)][0].atoms == (0, 1)
    assert restored.render_options is not restored._document_views[id(restored.documents[2])].options


def test_project_restores_active_frequency_edited_reference_arrows_and_camera(gui, tmp_path):
    from lele.project_actions import camera_data
    gui.attach_vibrations();w = gui.window;w.select_vibration(0, 0, 1, autoplay=False)
    w._vibration_reference.positions[0] += [.1, .2, .3]
    w._vibration_reference.bond_added.add((0, 2))
    w.vibration_controls.amplitude.setValue(.75);w.vibration_controls.speed.setValue(2.)
    w.vibration_controls.arrows_check.setChecked(True);w.vibration_controls.selected_arrows_check.setChecked(True)
    w.vibration_controls.arrow_length.setValue(1.8);gui.select([0]);set_camera(w, (12, 15, 19))
    camera = camera_data(w.scene.GetActiveCamera());positions = w.frame.positions.copy()
    project = tmp_path/'frequency.lele';assert w.save_project_to(project)
    restored = empty_window(gui);assert restored._load_project_path(project)
    assert restored._active_vibration == (0, 0, 1) and not restored.vibration_timer.isActive()
    np.testing.assert_array_equal(restored.frame.positions, positions)
    assert restored.frame.bond_added == {(0, 2)} and restored.selection == [0]
    assert restored.vibration_controls.amplitude.value() == .75
    assert restored.vibration_controls.speed.value() == 2. and restored.vibration_controls.arrow_length.value() == 1.8
    assert restored.vibration_controls.arrows_check.isChecked() and restored.vibration_controls.selected_arrows_check.isChecked()
    assert camera_data(restored.scene.GetActiveCamera()) == camera


def test_energy_only_result_step_restore_and_append_preserve_existing_work(gui, tmp_path):
    w = gui.window;original = w.doc;w.frame.positions[0, 0] = 9.25
    w.files_tree.clear();w._add_document_tree(0, original)
    w._open_path_now(EXAMPLES/'synthetic_vasp_energy_only_v210.OUTCAR')
    group = w.files_tree.topLevelItem(w.current_doc).child(0);leaf = group.child(1)
    w.files_tree.setCurrentItem(leaf)
    assert w._energy_only_context is not None and w.frame is None
    project = tmp_path/'energies.lele';assert w.save_project_to(project)
    restored = empty_window(gui);assert restored._load_project_path(project)
    assert restored.frame is None and restored.canvas_stack.currentWidget() is restored.results_only_page
    assert restored._energy_only_context == (1, 1)
    assert 'E0 (σ→0):' in restored.results_only_info.toPlainText()
    before = list(w.documents);w._open_path_now(project)
    assert len(w.documents) == 4 and all(a is b for a, b in zip(w.documents, before))
    assert original.frames[0].positions[0, 0] == 9.25 and w._project_path is None


def test_malformed_project_does_not_change_open_documents(gui, tmp_path):
    w = gui.window;before = list(w.documents);source = w.frame;path = tmp_path/'bad.lele';path.write_text('invalid')
    with patch('lele.project_actions.QMessageBox.warning') as warning:
        assert not w._load_project_path(path)
    warning.assert_called_once()
    assert w.documents == before and w.frame is source
