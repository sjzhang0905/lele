"""Output backgrounds, scoped ESP actions and explicitly saved appearance."""
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest
from PIL import Image
from matplotlib import rc_context
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow

from lele.animation_export import GifSettings, export_animation_gif
from lele.atom_legend import AtomLegend
from lele.core import Document, Frame, Volume
from lele.figure_export import export_figure
from lele.png_export import PngSettings, export_png
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from test_periodic_fragment_ui_v171 import gui


def check_white_margins(image):
    pixels = np.asarray(image.convert('RGBA'))
    for y in (slice(0,4), slice(-4,None)):
        for x in (slice(0,4), slice(-4,None)):
            assert np.all(pixels[y,x] == 255)
    assert np.any(pixels[:,:,:3] < 150)


def test_png_on_dark_gradient_restores_live_scene_and_automatic_labels(tmp_path):
    scene = vtkRenderer()
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(240,160)
    window.SetMultiSamples(0)
    window.AddRenderer(scene)
    legend = AtomLegend(scene)
    options = RenderOptions(background='#18243A')
    legend.set_samples([dict(symbol='Fe',radius=.3,color='#BE4937',opacity=.7)],options)
    scene.SetBackground2(.1,.15,.2)
    scene.SetBackgroundAlpha(.3)
    scene.GradientBackgroundOn()
    old = (scene.GetBackground(),scene.GetBackground2(),scene.GetBackgroundAlpha())
    title = legend.labels[0].GetTextProperty()
    original_text = title.GetColor()
    def inspect(label,*_):
        if label == 'Rendering high-resolution PNG':
            assert scene.GetBackground() == (1.,1.,1.)
            assert title.GetColor() == pytest.approx((.10,.13,.18))
    try:
        path = tmp_path/'legend.png'
        export_png(path,window,PngSettings(480,320),progress=inspect)
        with Image.open(path) as image:
            check_white_margins(image)
        def fail_before_write(label,*args):
            if label == 'Writing PNG':
                raise RuntimeError('cancel export')
        with pytest.raises(RuntimeError,match='cancel export'):
            export_png(path,window,PngSettings(480,320),progress=fail_before_write)
        assert (scene.GetBackground(),scene.GetBackground2(),scene.GetBackgroundAlpha()) == old
        assert scene.GetGradientBackground() and title.GetColor() == original_text
        export_png(path,window,PngSettings(240,160,white_background=False))
        with Image.open(path) as image:
            assert max(image.convert('RGB').getpixel((0,0))) < 150
    finally:
        window.Finalize()


@pytest.mark.parametrize('dither', [False,True])
def test_gif_has_exact_white_on_every_frame_even_with_dark_view(tmp_path,dither):
    frames = [Frame(['O','H'],[[x,0,0],[x+.8,.1,0]]) for x in (0,.15,.30)]
    doc = Document(tmp_path/'example.xyz','XYZ',frames)
    options = RenderOptions(background='#172335',axes_position='Off')
    path = tmp_path/'trajectory.gif'
    export_animation_gif(path,doc,GifSettings(width=240,height=160,last_frame=3,dither=dither),options)
    with Image.open(path) as image:
        assert image.n_frames == 3
        for i in range(image.n_frames):
            image.seek(i)
            check_white_margins(image)
    assert options.background == '#172335'


@pytest.mark.parametrize('extension',['png','tiff','jpeg','svg','pdf'])
def test_plots_export_an_opaque_white_page_and_plot_area(tmp_path,extension):
    figure = Figure(figsize=(4,3), facecolor='#26415D')
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    axes.set_facecolor('#E5CEB7')
    axes.plot([0,1],[.2,.2],color='#18324F')
    axes.set_ylim(0,1)
    colors = (figure.get_facecolor(),axes.get_facecolor())
    path = tmp_path/f'curve.{extension}'
    with rc_context({'savefig.transparent':True,'savefig.facecolor':'#111111'}):
        export_figure(path,figure,None if extension in ('svg','pdf') else PngSettings(400,300))
    if extension == 'svg':
        root = ElementTree.parse(path).getroot()
        for name in ('figure_1','axes_1'):
            patch = root.find(f".//*[@id='{name}']/*[1]/*[1]")
            assert '#ffffff' in patch.get('style','').lower()
    elif extension == 'pdf':
        assert path.read_bytes().startswith(b'%PDF-')
    else:
        with Image.open(path) as image:
            check_white_margins(image)
            assert image.convert('RGBA').getpixel((200,105)) == (255,255,255,255)
    assert colors == (figure.get_facecolor(),axes.get_facecolor())


def test_extrema_menu_uses_the_clicked_files_actual_mapping(gui,tmp_path):
    w = gui.window
    frame = Frame(['H'],[[0.,0.,0.]])
    values = np.arange(27.).reshape(3,3,3)
    grids = [Volume(values,[0,0,0],np.eye(3),label) for label in ('density','ESP','orbital')]
    doc = Document(tmp_path/'esp.cube','Gaussian CUBE',[frame],grids[0],volumes=grids)
    w._attach_loaded_document(doc)
    options = w.render_options
    def has_action(target):
        menu = w._loaded_file_menu(target)
        result = any(action.text() == 'Add ESP extrema…' for action in menu.actions())
        menu.deleteLater()
        return result
    assert not has_action(doc)
    options.volume_surfaces = [dict(dataset=1,map_dataset=1,value=.5)]
    assert not has_action(doc)
    options.volume_surfaces = [dict(dataset=0,map_dataset=2,value=.5)]
    assert not has_action(doc)
    options.volume_surfaces[0]['map_dataset'] = 1
    other = Document(tmp_path/'ESP.xyz','XYZ',[frame.clone()])
    w._attach_loaded_document(other)
    assert not has_action(other) and has_action(doc)
    assert not w._add_esp_extrema(other)
    options.volume_surfaces.clear()
    assert not has_action(doc)


def test_default_scene_and_previously_saved_style_are_distinct(tmp_path):
    from lele.project_file import load_project,save_project
    from lele.style_presets import BUILTIN_PRESETS
    drawing = MoleculeRenderer(vtkRenderer())
    assert drawing.renderer.GetBackground() == (1.,1.,1.)
    assert all(style['background'] == '#FFFFFF' for name,style in BUILTIN_PRESETS.items()
               if name != 'Dark presentation')
    previous = RenderOptions(light_enabled=(True,True,False,True),highlight_size=50.,
                             highlight_brightness=50.,volume_opacity=.90,
                             volume_negative_opacity=.72,background='#151A25')
    doc = Document(Path('saved.xyz'),'XYZ',[Frame(['H'],[[0,0,0]])])
    path = tmp_path/'appearance.lele'
    save_project(path,dict(documents=[dict(document=doc,options=previous)],current_document=0))
    assert load_project(path)['documents'][0]['options'] == previous
