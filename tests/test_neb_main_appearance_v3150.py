"""The NEB substrate follows the live scene; moving copies stay a path layer."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('VTK_DEFAULT_OPENGL_WINDOW', 'vtkEGLRenderWindow')
from types import SimpleNamespace

import numpy as np
import pytest

from test_vasp_neb_dialog_v370 import app, documents


def make_dialog():
    from PySide6.QtWidgets import QMainWindow
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.atom_appearance import AtomAppearance
    from lele.render_options import RenderOptions
    from lele.vasp_neb import build_neb_path, natural_path_key
    from lele.vasp_neb_dialog import VaspNebDialog
    docs = sorted(documents(), key=natural_path_key)
    path = build_neb_path(docs)
    window = QMainWindow()
    window.doc = docs[0]
    window.frame = docs[0].frames[0]
    window.frame.atom_appearance[1] = AtomAppearance(
        color='#123456', size_scale=1.7, representation='Sticks', opacity=.6)
    window.selection = [2]
    window.render_options = RenderOptions(
        style='Space filling', background='#26485A', atom_scale=.8,
        space_filling_scale=1.3, bond_scale=.18, element_colors={'Cu': '#ABCDEF'},
        labels='Element', axes_position='Corner', surface_finish='Matte',
        boundary_bounds=((0, 2), (0, 1), (0, 1)),
        light_enabled=(True, False, False, False),
        light_intensities=(.4, .2, .1, .1))
    window.scene = vtkRenderer()
    camera = window.scene.GetActiveCamera()
    camera.SetPosition(11, 13, 17)
    camera.SetFocalPoint(2, 0, 0)
    camera.SetViewUp(0, 1, .2)
    camera.SetParallelProjection(False)
    camera.SetViewAngle(27)
    camera.SetWindowCenter(.1, -.2)
    window.renderer = SimpleNamespace(alignment=None, fitted_plane=None)
    return window, VaspNebDialog(path, window)


def test_live_substrate_styles_camera_and_single_path_layer(app):
    window, dialog = make_dialog()
    try:
        assert dialog.options.style == 'Space filling'
        assert dialog.options.labels == 'Element'
        assert dialog.options.surface_finish == 'Matte'
        assert dialog.drawing._display_color('Cu') == '#ABCDEF'
        assert dialog.drawing.source_frame.atom_appearance[1] == window.frame.atom_appearance[1]
        assert not dialog.drawing.source_frame.atom_appearance[2].visible
        boundary = dialog.drawing.boundary_display
        assert len(boundary.tiles) == 2
        assert all(not boundary.frame.atom_appearance[i].visible
                   for i, source in enumerate(boundary.source_indices) if source == 2)
        from lele.atom_appearance import atom_is_drawn
        tracks = dialog.track_drawing.frame
        assert sum(atom_is_drawn(tracks, i) for i in range(len(tracks.symbols))) == 3
        assert dialog.track_drawing.options.style == 'Ball and stick'
        assert dialog.track_drawing.boundary_display is None
        camera = dialog.scene.GetActiveCamera()
        main_camera = window.scene.GetActiveCamera()
        np.testing.assert_allclose(camera.GetPosition(), main_camera.GetPosition())
        np.testing.assert_allclose(camera.GetFocalPoint(), main_camera.GetFocalPoint())
        np.testing.assert_allclose(camera.GetViewUp(), main_camera.GetViewUp())
        assert camera.GetViewAngle() == main_camera.GetViewAngle()
        assert camera.GetWindowCenter() == main_camera.GetWindowCenter()
        assert not camera.GetParallelProjection()
        assert dialog.scene.GetLights().GetNumberOfItems() == 4
        assert dialog.drawing._lights[0].GetIntensity() == pytest.approx(.4)
        assert dialog.axes_widget.GetEnabled()
        # Appearance is independent: neither the source nor the NEB snapshots
        # acquire the hidden moving sites used to compose the illustration.
        assert 2 not in window.frame.atom_appearance
        assert dialog.path.frames[0].atom_appearance == {}
        assert dialog.options is not window.render_options
    finally:
        dialog.close()
        window.close()


def test_apply_and_export_refresh_current_main_appearance(app, tmp_path):
    from PIL import Image
    from lele.png_export import PngSettings
    window, dialog = make_dialog()
    try:
        window.render_options.style = 'Wireframe'
        window.render_options.background = '#FFFFFF'
        window.render_options.element_colors['Cu'] = '#FEDCBA'
        window.render_options.boundary_enabled = False
        window.render_options.axes_position = 'Off'
        window.scene.GetActiveCamera().SetParallelProjection(True)
        window.scene.GetActiveCamera().SetParallelScale(5.5)
        dialog.use_main_view()
        assert dialog.options.style == 'Wireframe'
        assert dialog.drawing._display_color('Cu') == '#FEDCBA'
        assert dialog.drawing.boundary_display is None
        assert not dialog.axes_widget.GetEnabled()
        assert dialog.scene.GetActiveCamera().GetParallelProjection()
        assert dialog.scene.GetActiveCamera().GetParallelScale() == pytest.approx(5.5)
        window.render_options.style = 'Sticks'
        target = tmp_path / 'neb.png'
        dialog.write_caterpillar_png(target, PngSettings(width=480, height=320))
        assert dialog.options.style == 'Sticks'
        with Image.open(target) as image:
            assert image.size == (480, 320)
            pixels = np.array(image.convert('RGB'))
            assert np.count_nonzero(np.any(pixels < 240, axis=2)) > 100
    finally:
        dialog.close()
        window.close()
