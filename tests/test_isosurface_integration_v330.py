"""Independent multi-surface persistence and image-export checks."""
from pathlib import Path
from copy import deepcopy
import numpy as np
from PIL import Image
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
from lele.core import Document, Frame, Volume
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.project_file import save_project, load_project
from lele.png_export import export_png, PngSettings
from lele.animation_export import export_animation_gif, GifSettings


def sample():
    x,y,z=np.meshgrid(*[np.linspace(-2,2,21)]*3,indexing='ij')
    volume=Volume(x*np.exp(-x*x-y*y-z*z),[-2,-2,-2],np.eye(3)*.2)
    frame=Frame([],np.empty((0,3)))
    doc=Document(Path('synthetic.cube'),'Synthetic',[frame,frame.clone()],volume)
    options=RenderOptions(axes_position='Off',unit_cell=False)
    options.volume_surfaces=[dict(value=-.15,color='#0000FF',opacity=1.,style='Surface',visible=True),
        dict(value=.15,color='#FF0000',opacity=1.,style='Surface',visible=True),
        dict(value=0,color='#00FF00',opacity=.2,style='Wireframe',visible=False)]
    return doc,options


def both_colors(pixels):
    p=np.asarray(pixels,dtype=int)
    assert np.count_nonzero((p[...,0]>p[...,1]+30)&(p[...,0]>p[...,2]+30))>50
    assert np.count_nonzero((p[...,2]>p[...,1]+30)&(p[...,2]>p[...,0]+30))>50


def test_custom_surface_project_roundtrip_and_detachment(tmp_path):
    doc,options=sample()
    doc.volume=None
    saved=deepcopy(options)
    path=tmp_path/'layers.lele'
    save_project(path,dict(documents=[dict(document=doc,options=options,frame_index=0)],current_document=0,selection=[]))
    item=load_project(path)['documents'][0]
    assert item['options']==saved
    assert item['document'].volume is None
    assert len(item['document'].volumes)==1
    draw=MoleculeRenderer(vtkRenderer());draw.options=item['options']
    draw.set_scene(item['document'].frames[0],item['document'].volume)
    assert not draw.dynamic


def test_custom_surface_png_and_gif_export(tmp_path):
    doc,options=sample();original=deepcopy(options)
    scene=vtkRenderer();window=vtkRenderWindow();window.SetOffScreenRendering(1)
    window.SetSize(240,180);window.AddRenderer(scene)
    draw=MoleculeRenderer(scene);draw.options=options
    draw.set_scene(doc.frames[0],doc.volume);scene.ResetCamera();window.Render()
    path=tmp_path/'layers.png'
    export_png(path,window,PngSettings(240,180,1),mesh_items=draw._keepalive)
    with Image.open(path) as image:both_colors(image.convert('RGB'))
    window.Finalize()
    path=tmp_path/'layers.gif'
    export_animation_gif(path,doc,GifSettings(width=240,height=180,last_frame=2,supersample=1),options)
    with Image.open(path) as gif:
        assert gif.n_frames==2
        for i in range(2):gif.seek(i);both_colors(gif.convert('RGB'))
    assert options==original
