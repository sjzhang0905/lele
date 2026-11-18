"""Cropped scene exports omit axes and retain the visible figure content."""
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image, ImageDraw

from lele.png_export import (PngSettings, crop_background, export_png,
                             hidden_coordinate_axes)
from test_png_export import drawing
from test_periodic_fragment_ui_v171 import gui


def test_crop_keeps_distant_legend_and_labels():
    image = Image.new('RGB', (300, 200), '#FFFFFF')
    draw = ImageDraw.Draw(image)
    draw.rectangle((80, 65, 130, 120), fill='#D01020')
    # A detached color bar and title are figure content, not empty margins.
    draw.rectangle((250, 40, 259, 150), fill='#0033CC')
    draw.text((75, 30), 'ESP', fill='black')
    result = crop_background(image, (255, 255, 255), padding=2)
    assert result.width < image.width and result.height < image.height
    before = np.asarray(image)
    after = np.asarray(result)
    for color in ((208, 16, 32), (0, 51, 204), (0, 0, 0)):
        assert np.count_nonzero(np.all(before == color, axis=2)) == np.count_nonzero(np.all(after == color, axis=2))
    assert image.size == (300, 200)


def test_blank_crop_retains_valid_image():
    image = Image.new('RGB', (30, 20), '#123456')
    result = crop_background(image, (18, 52, 86))
    assert result is not image and result.size == image.size


def test_axis_visibility_restores_after_failure(drawing):
    from vtkmodules.vtkRenderingCore import vtkRenderer, vtkTextActor
    draw, scene, window = drawing
    draw.options.axes_position = 'Origin'
    draw.set_scene(draw.frame)
    overlay = vtkRenderer()
    overlay.SetLayer(1)
    window.SetNumberOfLayers(2)
    window.AddRenderer(overlay)
    marker = draw.make_corner_marker(draw.frame)
    overlay.AddViewProp(marker)
    for label in draw.corner_labels:
        overlay.AddViewProp(label)
    title = vtkTextActor()
    title.SetInput('ESP (a.u.)')
    scene.AddViewProp(title)
    axes = [actor for renderer in window.GetRenderers() for actor in renderer.GetViewProps()
            if actor.GetObjectName() == 'lele-coordinate-axis']
    assert len(axes) == 10  # 3 origin arrows, 3 labels, corner assembly + 3 labels
    axes[0].VisibilityOff()
    state = [actor.GetVisibility() for actor in axes]
    with pytest.raises(RuntimeError, match='forced'):
        with hidden_coordinate_axes(window, True):
            assert all(not actor.GetVisibility() for actor in axes)
            assert title.GetVisibility()
            raise RuntimeError('forced')
    assert [actor.GetVisibility() for actor in axes] == state
    window.RemoveRenderer(overlay)


def test_cropped_png_removes_axes_and_restores_live_camera(drawing, tmp_path):
    draw, scene, window = drawing
    draw.options.axes_position = 'Origin'
    draw.options.axes_length = 3
    draw.set_scene(draw.frame, reset_camera=True)
    camera = scene.GetActiveCamera()
    before = (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp())
    axes = [p for p in scene.GetViewProps() if p.GetObjectName() == 'lele-coordinate-axis']
    target = tmp_path / 'cropped.png'
    export_png(target, window, PngSettings(320, 240, 1, cropped=True), mesh_items=draw._keepalive)
    assert all(p.GetVisibility() for p in axes)
    assert (camera.GetPosition(), camera.GetFocalPoint(), camera.GetViewUp()) == before
    # Same fixed camera and scene, explicitly removing axes, gives identical pixels.
    for prop in axes:
        prop.VisibilityOff()
    reference = tmp_path / 'reference.png'
    export_png(reference, window, PngSettings(320, 240, 1), mesh_items=draw._keepalive)
    for prop in axes:
        prop.VisibilityOn()
    with Image.open(reference) as full, Image.open(target) as actual:
        expected = crop_background(full, (255, 255, 255))
        assert actual.width < full.width and actual.height < full.height
        np.testing.assert_array_equal(np.asarray(actual), np.asarray(expected))


def test_crop_preference_persists_only_after_save(gui, tmp_path):
    from PySide6.QtCore import QSettings
    from lele.png_dialog import PngExportDialog
    preferences = QSettings(str(tmp_path / 'preferences.ini'), QSettings.Format.IniFormat)
    with patch('lele.png_dialog.QSettings', return_value=preferences):
        first = PngExportDialog(view_size=(160, 120))
        assert not first.crop_check.isChecked()
        first.crop_check.setChecked(True)
        first.accept()
        second = PngExportDialog(view_size=(160, 120))
        assert second.settings().cropped
        assert 'before cropping' in second.size_label.text()
        second.crop_check.setChecked(False)
        second.reject()
        third = PngExportDialog(view_size=(160, 120))
        assert third.crop_check.isChecked()
        for dialog in (first, second, third):
            dialog.deleteLater()
