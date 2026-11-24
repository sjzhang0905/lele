"""Batch exports use remembered source frames and restore the live view on every exit."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest
from ase.io import read

from lele.atom_appearance import AtomAppearance
from lele.core import Document, Frame
from lele.calculation_results import CalculationJob, CalculationResults
from lele.png_export import PngSettings
from lele.project_actions import camera_data
from test_periodic_fragment_ui_v171 import gui


def attach_documents(gui, tmp_path):
    w = gui.window
    base = Frame(['C', 'H', 'O', 'H'], [[1.,1.,1.], [2.,1.,1.], [1.,2.,1.], [1.,1.,2.]])
    moved = base.clone(); moved.positions += [.2,.3,.4]
    moved.atom_appearance[2] = AtomAppearance(visible=False)
    crystal = base.clone(); crystal.cell = np.eye(3) * 8; crystal.pbc = (True,)*3
    docs = [Document(tmp_path/'same.log', 'ORCA output', [base, moved]),
            Document(tmp_path/'same.out', 'VASP output', [crystal]),
            Document(tmp_path/'results.out', 'Results', [], calculation_results=CalculationResults('ORCA', jobs=[CalculationJob(0,1,energy_ev=-1.)]))]
    w.documents = docs; w.current_doc = -1; w.frame_index = 0
    w._view_document = w._scene_document = None; w._document_views.clear()
    w.selection = []; w.files_tree.clear()
    for index, doc in enumerate(docs): w._add_document_tree(index, doc)
    w.change_frame(1, switch_doc=0)
    w.render_options.labels = 'ORCA index (0..N-1)'
    w.scene.GetActiveCamera().SetPosition(10.,12.,13.)
    w.scene.GetActiveCamera().SetFocalPoint(1.,1.,1.)
    w.scene.GetActiveCamera().SetViewUp(.1,.9,.2)
    w.scene.GetActiveCamera().SetClippingRange(.2,100.)
    w.change_frame(0, switch_doc=1)
    w.render_options.labels = 'Element'
    w.scene.GetActiveCamera().SetPosition(20.,22.,23.)
    w.scene.GetActiveCamera().SetFocalPoint(2.,2.,2.)
    w.scene.GetActiveCamera().SetViewUp(.2,.8,.3)
    w.scene.GetActiveCamera().SetClippingRange(.3,200.)
    w.selection = [2,0,1]; w._sync_selection_to_table(); w.refresh_scene()
    w._remember_document_view()
    return w, docs


def assert_camera(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in actual.items():
        if isinstance(value, (tuple,list)):
            np.testing.assert_allclose(value, expected[key], rtol=0, atol=1e-12)
        else:
            assert value == pytest.approx(expected[key])


def test_unique_names_protect_existing_casefold_and_source_files(tmp_path):
    from lele.batch_export import allocate_paths
    source = tmp_path/'water.xyz'; source.write_text('source')
    (tmp_path/'WATER_2.XYZ').write_text('existing')
    docs = [SimpleNamespace(path=source), SimpleNamespace(path=tmp_path/'water.log')]
    paths = allocate_paths(docs, tmp_path, ['.xyz', '.xyz'])
    assert [p.name for p in paths] == ['water_3.xyz','water_4.xyz']
    assert source.read_text() == 'source'
    assert (tmp_path/'WATER_2.XYZ').read_text() == 'existing'


def test_conversion_uses_remembered_frame_all_atoms_and_periodic_cif(gui,tmp_path):
    w, docs = attach_documents(gui,tmp_path)
    folder = tmp_path/'converted';folder.mkdir()
    before = camera_data(w.scene.GetActiveCamera()); selection = list(w.selection)
    result = w._run_batch_convert(folder)
    assert len(result.exported) == 2 and len(result.skipped) == 1
    assert not result.failures and not result.cancelled
    assert {p.suffix for p in result.exported} == {'.xyz','.cif'}
    xyz = next(p for p in result.exported if p.suffix == '.xyz')
    cif = next(p for p in result.exported if p.suffix == '.cif')
    molecular = read(xyz);periodic = read(cif)
    assert len(molecular) == len(periodic) == 4
    np.testing.assert_allclose(molecular.positions,docs[0].frames[1].positions)
    np.testing.assert_allclose(periodic.positions,docs[1].frames[0].positions)
    assert w.current_doc == 1 and w.frame_index == 0 and w.selection == selection
    assert_camera(camera_data(w.scene.GetActiveCamera()),before)
    assert not w._batch_exporting


def test_conversion_failure_is_atomic_and_other_files_continue(gui,tmp_path):
    from lele.formats import export_frame as real_export
    w,_ = attach_documents(gui,tmp_path)
    folder=tmp_path/'failure';folder.mkdir()
    def fail_xyz(frame,path,target,*args,**kwargs):
        if target == 'xyz':
            Path(path).write_text('partial content')
            raise OSError('simulated writer failure')
        return real_export(frame,path,target,*args,**kwargs)
    with patch('lele.formats.export_frame',side_effect=fail_xyz):
        result=w._run_batch_convert(folder)
    assert len(result.failures)==1 and 'simulated writer failure' in result.failures[0]
    assert len(result.exported)==1 and result.exported[0].suffix=='.cif'
    assert list(folder.iterdir())==result.exported
    assert not w._batch_exporting


def test_png_uses_saved_per_document_view_and_restores_after_failure(gui,tmp_path):
    w,docs=attach_documents(gui,tmp_path)
    folder=tmp_path/'png';folder.mkdir()
    before=camera_data(w.scene.GetActiveCamera());selection=list(w.selection)
    expected0=camera_data(w._document_views[id(docs[0])].camera)
    saved_options=w.render_options
    captured=[]
    def capture(path,window,settings,**kwargs):
        captured.append((w.current_doc,w.frame_index,w.render_options.labels,
                         camera_data(w.scene.GetActiveCamera())))
        if w.current_doc==1:raise OSError('simulated PNG failure')
        Path(path).write_bytes(b'png')
    with patch('lele.png_export.export_png',side_effect=capture):
        result=w._run_batch_png(folder,PngSettings(400,300,1))
    assert [row[0] for row in captured]==[1,0]
    assert captured[1][1:3]==(1,'ORCA index (0..N-1)')
    assert_camera(captured[0][3],before);assert_camera(captured[1][3],expected0)
    assert len(result.exported)==1 and len(result.failures)==1 and len(result.skipped)==1
    assert set(folder.iterdir())==set(result.exported)
    assert w.current_doc==1 and w.frame_index==0 and w.selection==selection
    assert w.render_options is saved_options
    assert_camera(camera_data(w.scene.GetActiveCamera()),before)
    assert not w._batch_exporting


def test_png_cancel_between_files_restores_selected_frame_camera_and_plane(gui,tmp_path):
    w,_=attach_documents(gui,tmp_path)
    w._fit_selected_plane()
    saved_plane,saved_context=w._plane_fit,w._plane_context
    before=camera_data(w.scene.GetActiveCamera());selection=list(w.selection)
    folder=tmp_path/'cancel';folder.mkdir();captured=[]
    def capture(path,*args,**kwargs):
        captured.append(w.current_doc);Path(path).write_bytes(b'png')
    with patch('lele.png_export.export_png',side_effect=capture):
        result=w._run_batch_png(folder,PngSettings(400,300,1),cancelled=lambda:bool(captured))
    assert result.cancelled and len(result.exported)==1
    assert captured==[1] and w.current_doc==1 and w.selection==selection
    assert w._plane_fit is saved_plane and w._plane_context is saved_context
    assert_camera(camera_data(w.scene.GetActiveCamera()),before)
    assert not w._batch_exporting


def test_png_restores_active_vibration_reference_phase_and_selection(gui,tmp_path):
    w=gui.window;doc=gui.attach_vibrations()
    other=Document(tmp_path/'other.xyz','XYZ',[Frame(['He'],[[0.,0.,0.]])])
    w.documents.append(other);w._add_document_tree(1,other)
    w.select_vibration(0,0,0,autoplay=False)
    w._vibration_phase=1.234;w.selection=[0,1];w._sync_selection_to_table();w._render_vibration()
    before=camera_data(w.scene.GetActiveCamera());reference=w._vibration_reference
    folder=tmp_path/'vibration';folder.mkdir();captured=[]
    def capture(path,*args,**kwargs):
        captured.append((w.current_doc,w._active_vibration,w._vibration_phase))
        Path(path).write_bytes(b'png')
    with patch('lele.png_export.export_png',side_effect=capture):
        result=w._run_batch_png(folder,PngSettings(400,300,1))
    assert not result.failures and len(result.exported)==2
    assert captured[0]==(0,(0,0,0),1.234)
    assert w.current_doc==0 and w._active_vibration==(0,0,0)
    assert w._vibration_reference is reference and w._vibration_phase==pytest.approx(1.234)
    assert w.selection==[0,1]
    assert_camera(camera_data(w.scene.GetActiveCamera()),before)
    assert not w.vibration_timer.isActive()


def test_png_skips_results_only_active_page_and_restores_it(gui,tmp_path):
    w,_=attach_documents(gui,tmp_path)
    w.change_frame(0,switch_doc=2)
    folder=tmp_path/'results';folder.mkdir();captured=[]
    def capture(path,*args,**kwargs):
        captured.append(w.current_doc);Path(path).write_bytes(b'png')
    with patch('lele.png_export.export_png',side_effect=capture):
        result=w._run_batch_png(folder,PngSettings(400,300,1))
    assert len(result.exported)==2 and len(result.skipped)==1
    assert captured==[0,1]
    assert w.current_doc==2 and w.frame is None
    assert w.canvas_stack.currentWidget() is w.results_only_page
    assert not w._batch_exporting


def test_conversion_exports_active_vibration_reference_not_trajectory_or_displacement(gui,tmp_path):
    w=gui.window;doc=gui.attach_vibrations()
    w.select_vibration(0,0,0,autoplay=False)
    w._vibration_reference.positions[0]+=[.37,.21,.13]
    w._vibration_phase=1.0;w._render_vibration()
    expected=w.frame.positions.copy();reference=w._vibration_reference
    folder=tmp_path/'vibration_structure';folder.mkdir()
    result=w._run_batch_convert(folder)
    assert len(result.exported)==1 and not result.failures
    actual=read(result.exported[0])
    np.testing.assert_allclose(actual.positions,expected)
    assert w._active_vibration==(0,0,0) and w._vibration_reference is reference
    assert w._vibration_phase==pytest.approx(1.0)


@pytest.mark.parametrize('flag,value',[('_file_batch_active',object()),('_file_load_active',object()),('_file_load_queue',['pending.out']),('_batch_exporting',True),('_closing',True)])
def test_png_rejects_import_export_or_close_in_progress(gui,tmp_path,flag,value):
    w=gui.window
    before=camera_data(w.scene.GetActiveCamera())
    setattr(w,flag,value)
    try:
        with patch('lele.png_export.export_png') as capture:
            with pytest.raises(ValueError):w._run_batch_png(tmp_path,PngSettings(400,300,1))
        capture.assert_not_called()
        assert_camera(camera_data(w.scene.GetActiveCamera()),before)
    finally:
        setattr(w,flag,False if isinstance(value,bool) else [] if isinstance(value,list) else None)


def test_conversion_preserves_file_created_after_name_planning(gui,tmp_path):
    from lele.formats import export_frame as real_export
    w,_=attach_documents(gui,tmp_path)
    folder=tmp_path/'race';folder.mkdir()
    external=folder/'same.xyz'
    def write_then_race(frame,path,target,*args,**kwargs):
        notices=real_export(frame,path,target,*args,**kwargs)
        if target=='xyz':external.write_text('external writer content')
        return notices
    with patch('lele.formats.export_frame',side_effect=write_then_race):
        result=w._run_batch_convert(folder)
    assert external.read_text()=='external writer content'
    assert len(result.failures)==1 and len(result.exported)==1
    assert result.exported[0].suffix=='.cif'
    assert set(folder.iterdir())=={external,*result.exported}


def test_batch_png_pixels_match_each_saved_view_and_restored_current_view(gui,tmp_path):
    from PIL import Image
    from lele.png_export import export_png
    w,docs=attach_documents(gui,tmp_path)
    window=w.vtk.GetRenderWindow()
    del window.Render  # This fixture normally disables painting; exercise real VTK here.
    window.SetOffScreenRendering(True);window.SetMultiSamples(0);window.SetSize(400,300)
    gui.addCleanup(window.Finalize)
    settings=PngSettings(400,300,1)
    selection=list(w.selection)
    camera=camera_data(w.scene.GetActiveCamera())
    original_labels=w.render_options.labels
    expected0=tmp_path/'expected0.png';expected1=tmp_path/'expected1.png'
    w.change_frame(1,switch_doc=0)
    w.render_options.background = '#142635'
    w.refresh_scene()
    export_png(expected0,w.vtk.GetRenderWindow(),settings,mesh_items=w.renderer._keepalive)
    w.change_frame(0,switch_doc=1)
    w.render_options.background = '#CAD7DB'
    w.selection=list(selection);w._sync_selection_to_table();w.refresh_scene()
    export_png(expected1,w.vtk.GetRenderWindow(),settings,mesh_items=w.renderer._keepalive)
    folder=tmp_path/'actual_images';folder.mkdir()
    result=w._run_batch_png(folder,settings)
    assert not result.failures and len(result.exported)==2
    # Plans use document order for naming, then capture the active document first.
    for expected,actual in ((expected0,folder/'same.png'),(expected1,folder/'same_2.png')):
        with Image.open(expected) as a,Image.open(actual) as b:
            np.testing.assert_array_equal(np.asarray(a),np.asarray(b))
            assert b.getpixel((0, 0)) == (255,255,255)
    restored=tmp_path/'restored.png'
    export_png(restored,w.vtk.GetRenderWindow(),settings,mesh_items=w.renderer._keepalive)
    with Image.open(expected1) as a,Image.open(restored) as b:
        np.testing.assert_array_equal(np.asarray(a),np.asarray(b))
    assert_camera(camera_data(w.scene.GetActiveCamera()),camera)
    assert w.render_options.labels==original_labels and w.selection==selection
    assert w.render_options.background == '#CAD7DB'
    assert w.convert_all_action.isEnabled() and w.export_png_all_action.isEnabled()
