"""Check the actual glyph, surface and PNG pixels in addition to material fields."""
import json
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import label
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkWindowToImageFilter

from lele.atom_appearance import AtomAppearance
from lele.core import Document, Frame, Volume, radius
from lele.lighting import light_settings
from lele.png_export import PngSettings, export_png
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.style_presets import BUILTIN_PRESETS, validate_preset


def interiors(image):
    """Interior discs exclude background, antialiased edges and the two-atom bond."""
    height, width = image.shape[:2]
    pixels_per_angstrom = height / 1.74
    yy, xx = np.ogrid[:height, :width]
    for x in (-1.4, 0., 1.4):
        cx = width/2 + x*pixels_per_angstrom - .5
        cy = height/2 - .5
        r = .78 * .62 * radius('C') * pixels_per_angstrom
        yield (xx-cx)**2 + (yy-cy)**2 < r*r


def canvas_image(window):
    window.Render()
    grab = vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.ReadFrontBufferOff()
    grab.SetInputBufferTypeToRGB()
    grab.Update()
    w, h = window.GetSize()
    return vtk_to_numpy(grab.GetOutput().GetPointData().GetScalars()).reshape(h, w, 3)[::-1].copy()


def test_glossy_peak_shape_body_color_and_translucent_surface_in_canvas_and_png(tmp_path):
    renderer = vtkRenderer()
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetMultiSamples(0)
    window.SetSize(560, 200)
    window.AddRenderer(renderer)
    draw = MoleculeRenderer(renderer)
    # The original VMD comparison exercises this explicit three-light material.
    draw.options.light_enabled = (True, True, False, True)
    draw.options.highlight_size = draw.options.highlight_brightness = 50.
    draw.options.atom_scale = .62
    draw.options.axes_position = 'Off'
    draw.options.volume_surfaces = [dict(value=0., color='#00C2FF', opacity=.8)]
    frame = Frame(['C', 'C'], [[-1.4,0,0], [0,0,0]],
                  atom_appearance={1:AtomAppearance(color='#A05A34')})
    draw.fixed_bonds = [(0, 1)]
    coords = np.linspace(-.7, .7, 49)
    x, y, z = np.meshgrid(coords, coords, coords, indexing='ij')
    volume = Volume((.47**2-x*x-y*y-z*z).astype(np.float32), [.7,-.7,-.7], np.eye(3)*(coords[1]-coords[0]))
    try:
        draw.set_scene(frame, volume)
        camera = renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        camera.SetPosition(0, 0, 10)
        camera.SetFocalPoint(0, 0, 0)
        camera.SetViewUp(0, 1, 0)
        camera.SetParallelScale(.87)
        renderer.ResetCameraClippingRange()
        live = canvas_image(window)
        path = tmp_path/'glossy.png'
        export_png(path, window, PngSettings(560, 200, 2), mesh_items=draw._keepalive)
        with Image.open(path) as png:
            high_res = np.array(png.convert('RGB'))
        grey, copper, cyan = interiors(live)
        for image in (live, high_res):
            whiteness = image.min(axis=2)
            hot = grey & (whiteness >= 240)
            components, _ = label(hot)
            sizes = np.bincount(components.ravel())[1:]
            assert np.count_nonzero(sizes > .005*grey.sum()) == 3
            assert .065 < hot.sum()/grey.sum() < .16
            assert whiteness[copper].max() >= 250
            body = np.median(image[copper], axis=0)
            assert body[0] > body[2] + 65 and body[2] < 80
            assert whiteness[cyan].max() > 100
        draw.options.highlight_brightness = 0
        draw.refresh_surface_finish()
        no_reflection = canvas_image(window)
        assert no_reflection[copper].min(axis=1).max() < 100
        assert live[cyan].min(axis=1).max() > no_reflection[cyan].min(axis=1).max() + 65
        assert draw.field_actors[0].GetProperty().GetOpacity() == .8
    finally:
        window.Finalize()


@pytest.mark.parametrize('custom', ['none', 'switch', 'intensity', 'position'])
def test_restore_pre411_lights_only_upgrades_the_complete_old_default(tmp_path, custom):
    path = tmp_path/'scene.lele'
    old = RenderOptions(light_enabled=(True,True,False,False), light_intensities=(.85,.45,.45,.35))
    if custom == 'switch':
        old.light_enabled = (True,False,False,False)
    elif custom == 'intensity':
        old.light_intensities = (.9,.45,.45,.35)
    elif custom == 'position':
        old.light_positions = ((0.,0.,1.), *old.light_positions[1:])
    doc = Document(tmp_path/'model.xyz','XYZ',[Frame(['C'], [[0.,0.,0.]])])
    save_project(path, dict(documents=[dict(document=doc, options=old)], current_document=0))
    # A current project may deliberately store the exact previous light values.
    assert light_settings(load_project(path)['documents'][0]['options']) == light_settings(old)
    legacy = tmp_path/'old.lele'
    from project_archive_v1 import legacy_archive
    with legacy_archive(path) as saved, ZipFile(legacy, 'w') as output:
        for name in saved.namelist():
            data = saved.read(name)
            if name == 'manifest.json':
                manifest = json.loads(data)
                for node in manifest['nodes']:
                    if node.get('type') == 'lele.render_options:RenderOptions':
                        del node['attributes']['highlight_brightness']
                data = json.dumps(manifest)
            output.writestr(name, data)
    restored = load_project(legacy)['documents'][0]['options']
    expected = RenderOptions() if custom == 'none' else old
    assert light_settings(restored) == light_settings(expected)
    assert restored.highlight_brightness == 47.


def test_invalid_brightness_in_settings_and_presets():
    for value in (float('nan'), -1, 101):
        with pytest.raises(ValueError):
            RenderOptions(highlight_brightness=value)
        with pytest.raises(ValueError):
            validate_preset({**BUILTIN_PRESETS['Glossy molecule'], 'highlight_brightness': value})
