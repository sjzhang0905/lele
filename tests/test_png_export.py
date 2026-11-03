"""PNG dimensions, actual supersampled capture, and live-view restoration."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow

from lele.core import Frame, radius, visible_bonds
from lele.atom_legend import legend_samples
from lele.png_export import PngSettings, export_png, smooth_meshes, scaled_annotations
from lele.renderer import MoleculeRenderer
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('width,height', [(0,100),(100,0),(8193,100),(100,8193)])
def test_invalid_png_size_is_rejected(width,height):
    with pytest.raises(ValueError):PngSettings(width,height)


def test_capture_budget_is_checked_before_rendering():
    with pytest.raises(ValueError,match='smaller'):
        PngSettings(8192,8192).capture_scale((2000,2000))
    assert PngSettings(8192,8192,1).capture_scale((2000,2000))==5
    with pytest.raises(ValueError,match='canvas'):
        PngSettings(100,100).capture_scale((0,0))


@pytest.fixture
def drawing():
    scene=vtkRenderer();window=vtkRenderWindow();window.SetOffScreenRendering(True)
    window.SetMultiSamples(0);window.SetSize(160,120);window.AddRenderer(scene)
    draw=MoleculeRenderer(scene);draw.options.axes_position='Off'
    draw.set_scene(Frame(['O','H','H'],[[0,0,0],[.96,0,0],[-.24,.93,0]]),reset_camera=True)
    window.Render()
    try:yield draw,scene,window
    finally:window.Finalize()


def sources(draw):
    def flatten(items):
        for obj in items:
            if isinstance(obj,(tuple,list)):yield from flatten(obj)
            else:yield obj
    return [v for v in flatten(draw._keepalive) if hasattr(v,'IsA') and
            (v.IsA('vtkSphereSource') or v.IsA('vtkTubeFilter'))]


def mesh_state(draw):
    return [(obj.GetThetaResolution(),obj.GetPhiResolution()) if obj.IsA('vtkSphereSource')
            else obj.GetNumberOfSides() for obj in sources(draw)]


def test_default_h_radius_reaches_glyphs_labels_legend_without_changing_bonds(drawing):
    draw,_,_=drawing
    frame=draw.frame;before=frame.positions.copy();bonds=visible_bonds(frame)
    expected=radius('H')*.5*1.15
    assert draw.options.bond_scale==.07
    assert draw._atom_radius('H')==pytest.approx(expected)
    assert next(s for s in legend_samples(draw) if s['symbol']=='H')['radius']==pytest.approx(expected)
    glyphs=[a for a in draw.dynamic if a.IsA('vtkActor') and a.GetMapper().IsA('vtkGlyph3DMapper')]
    sizes=[a.GetMapper().GetInput().GetPointData().GetArray('atom_radius').GetTuple1(0) for a in glyphs]
    assert min(sizes)==pytest.approx(expected)
    draw.options.labels='Index (1..N)';draw.set_scene(frame)
    assert draw._label_radii[1]==pytest.approx(expected)
    draw.options.atom_palette='GaussView style (Chemcraft)'
    assert draw._atom_radius('H')==pytest.approx(radius('H')*.5)
    draw.options.atom_palette='Default';draw.options.style='Space filling'
    from lele.display_reference import vesta_radius
    assert draw._atom_radius('H')==vesta_radius('H','Atomic')
    np.testing.assert_array_equal(frame.positions,before)
    assert visible_bonds(frame)==bonds


def test_high_quality_meshes_restore_even_after_an_error(drawing):
    draw,_,_=drawing;original=mesh_state(draw)
    with pytest.raises(RuntimeError,match='forced'):
        with smooth_meshes(draw._keepalive,True):
            assert any(v==(64,48) for v in mesh_state(draw))
            assert 32 in mesh_state(draw)
            raise RuntimeError('forced')
    assert mesh_state(draw)==original


def test_labels_scale_with_capture_and_restore_after_failure(drawing):
    from vtkmodules.vtkRenderingCore import vtkTextActor
    draw,scene,window=drawing
    draw.options.labels='Index (1..N)';draw.set_scene(draw.frame)
    banner=vtkTextActor();banner.SetInput('converged');banner.GetTextProperty().SetFontSize(18)
    scene.AddViewProp(banner)
    props=[actor.GetTextProperty() for actor in draw._label_actors]
    old=[prop.GetFontSize() for prop in props]
    with pytest.raises(RuntimeError,match='forced'):
        with scaled_annotations(window,6):
            assert [prop.GetFontSize() for prop in props]==[size*6 for size in old]
            assert banner.GetTextProperty().GetFontSize()==18
            raise RuntimeError('forced')
    assert [prop.GetFontSize() for prop in props]==old
    assert banner.GetTextProperty().GetFontSize()==18


def test_exact_png_pixels_antialias_and_camera_window_restoration(drawing,tmp_path):
    draw,scene,window=drawing;camera=scene.GetActiveCamera()
    state=(camera.GetPosition(),camera.GetFocalPoint(),camera.GetViewUp(),camera.GetParallelScale(),
           window.GetSize(),window.GetTileScale(),window.GetTileViewport(),mesh_state(draw))
    standard=tmp_path/'standard.png';smooth=tmp_path/'smooth.png'
    export_png(standard,window,PngSettings(320,240,1),mesh_items=draw._keepalive)
    export_png(smooth,window,PngSettings(320,240,2),mesh_items=draw._keepalive)
    with Image.open(standard) as a,Image.open(smooth) as b:
        assert a.size==b.size==(320,240) and a.mode==b.mode=='RGB'
        assert np.asarray(b).std()>1
        assert b.info['dpi'][0]==pytest.approx(300,abs=.1)
        assert np.mean(abs(np.asarray(a).astype(float)-np.asarray(b).astype(float)))>.1
    assert state==(camera.GetPosition(),camera.GetFocalPoint(),camera.GetViewUp(),camera.GetParallelScale(),
                   window.GetSize(),window.GetTileScale(),window.GetTileViewport(),mesh_state(draw))


def test_encoder_failure_preserves_existing_file_and_live_state(drawing,tmp_path):
    draw,scene,window=drawing;path=tmp_path/'existing.png';path.write_bytes(b'keep existing output')
    original=mesh_state(draw);position=scene.GetActiveCamera().GetPosition()
    with patch('PIL.Image.Image.save',side_effect=OSError('forced encoding failure')):
        with pytest.raises(OSError,match='encoding'):
            export_png(path,window,PngSettings(240,180),mesh_items=draw._keepalive)
    assert path.read_bytes()==b'keep existing output'
    assert not list(tmp_path.glob('.lele-png-*')) and mesh_state(draw)==original
    assert window.GetSize()==(160,120) and scene.GetActiveCamera().GetPosition()==position


def test_png_dialog_resolution_custom_width_and_quality(gui):
    from PySide6.QtWidgets import QDialogButtonBox
    from lele.png_dialog import PngExportDialog
    dialog=PngExportDialog(view_size=(800,400));gui.addCleanup(dialog.deleteLater)
    assert dialog.settings()==PngSettings(3200,1600,2)
    dialog.scale_combo.setCurrentIndex(1)
    assert dialog.settings()==PngSettings(1600,800,2)
    dialog.scale_combo.setCurrentIndex(3)
    assert dialog.settings()==PngSettings(3200,1600,2)
    dialog.width_spin.setValue(1370)
    assert dialog.scale_combo.currentData() is None
    assert dialog.settings()==PngSettings(1370,685,2)
    dialog.smooth_check.setChecked(False)
    assert dialog.settings().supersample==1
    assert dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()


def test_save_png_uses_options_and_restores_playback_on_success_and_failure(gui,tmp_path):
    from PySide6.QtWidgets import QDialog
    from lele.png_dialog import PngExportDialog
    w=gui.window;path=tmp_path/'gui.png';settings=PngSettings(320,240,2)
    w.playback.start(1000)
    def accepted(_dialog):
        assert not w.playback.isActive() and w._png_exporting
        return QDialog.DialogCode.Accepted
    with patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(path),'')), \
            patch.object(PngExportDialog,'exec',accepted), \
            patch.object(PngExportDialog,'settings',return_value=settings), \
            patch('lele.png_export.export_png') as export:
        w.save_png();assert export.call_args.args[:3]==(str(path),w.vtk.GetRenderWindow(),settings)
        assert w.playback.isActive() and not w._png_exporting
        export.side_effect=OSError('full disk')
        with patch('lele.app.QMessageBox.warning') as warning:w.save_png()
        warning.assert_called_once()
        assert w.playback.isActive() and not w._png_exporting


def test_cancel_png_options_keeps_file_and_restores_timer(gui,tmp_path):
    from PySide6.QtWidgets import QDialog
    from lele.png_dialog import PngExportDialog
    w=gui.window;path=tmp_path/'unchanged.png';path.write_bytes(b'original')
    w.playback.start(1000)
    with patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(path),'')), \
            patch.object(PngExportDialog,'exec',return_value=QDialog.DialogCode.Rejected), \
            patch('lele.png_export.export_png') as export:
        w.save_png();export.assert_not_called()
    assert path.read_bytes()==b'original' and w.playback.isActive() and not w._png_exporting
