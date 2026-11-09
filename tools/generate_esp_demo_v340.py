"""Create reproducible analytical (NOT quantum-chemical ESP) example grids.

Run from the source root: python tools/generate_esp_demo_v340.py --render
"""
import argparse
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lele.core import Document,Frame,Volume
from lele.render_options import RenderOptions
from lele.field_export import export_active_cube
from lele.project_file import save_project


def make_demo(output,render=False):
    output.mkdir(parents=True,exist_ok=True)
    shape=(31,31,31)
    basis=np.array([[.2,0,0],[.04,.2,0],[.02,.03,.2]])
    origin=-np.sum(basis,axis=0)*15
    xyz=np.moveaxis(np.indices(shape),0,-1)@basis+origin
    density=np.exp(-np.sum(xyz*xyz,axis=-1))
    field=Volume(density,origin,basis,'Synthetic density','e/Bohr³')
    mb=np.array([[.3,0,0],[.03,.3,0],[.01,.02,.3]])
    mo=-np.sum(mb,axis=0)*15
    mx=np.moveaxis(np.indices(shape),0,-1)@mb+mo
    potential=mx@np.array([.2,-.1,.3])
    color=Volume(potential,mo,mb,'Synthetic potential','Hartree')
    frame=Frame(['H'],[[0.,0.,0.]])
    doc=Document(Path('synthetic_density.cube'),'Analytical demonstration',[frame],field,volumes=[field,color])
    export_active_cube(output/'synthetic_density.cube',doc,frame)
    export_active_cube(output/'synthetic_potential.cube',Document(Path('synthetic_potential.cube'),'Analytical demonstration',[frame],color),frame)
    mapped=RenderOptions(axes_position='Off',unit_cell=False,volume_surfaces=[
        dict(dataset=0,value=.2,color='#FFFFFF',opacity=1.,style='Surface',visible=True,
             map_dataset=1,map_palette='Red-white-blue',map_range=[-.5,.5],map_legend=True)])
    overlay=RenderOptions(axes_position='Off',unit_cell=False,volume_surfaces=[
        dict(dataset=0,value=.2,color='#A0A0A0',opacity=.45,style='Surface',visible=True),
        dict(dataset=1,value=-.2,color='#CC1420',opacity=.7,style='Surface',visible=True),
        dict(dataset=1,value=.2,color='#1438CC',opacity=.7,style='Surface',visible=True)])
    camera=dict(position=[0,-7,0],focal_point=[0,0,0],view_up=[0,0,1],parallel_scale=2.,
                parallel_projection=True,view_angle=30.,clipping_range=[.1,100.],window_center=[0.,0.])
    for name,opts in [('mapped',mapped),('overlay',overlay)]:
        state=dict(documents=[dict(document=doc,options=opts,frame_index=0,camera=camera)],current_document=0,selection=[])
        save_project(output/(name+'.lele'),state)
    if render:
        from vtkmodules.vtkRenderingCore import vtkRenderer,vtkRenderWindow
        from lele.renderer import MoleculeRenderer
        from lele.png_export import export_png,PngSettings
        scene=vtkRenderer();window=vtkRenderWindow();window.SetOffScreenRendering(1)
        window.SetMultiSamples(0);window.SetSize(800,600);window.AddRenderer(scene)
        draw=MoleculeRenderer(scene);draw.options=mapped;draw.set_scene(frame,field,volumes=doc.volumes)
        c=scene.GetActiveCamera();c.SetPosition(0,-7,0);c.SetFocalPoint(0,0,0);c.SetViewUp(0,0,1)
        scene.ResetCamera();window.Render()
        export_png(output/'mapped_preview.png',window,PngSettings(1200,900,2),mesh_items=draw._keepalive)
        window.Finalize()
    (output/'README_CN.txt').write_text('''人工解析示例，非真实分子 ESP 计算结果。

直接用 LELE v3.4.0 打开 mapped.lele：在 density=0.2 的表面上映射 potential。
打开 overlay.lele：同时显示不同数据场的三张等值面。
两个工程都嵌入网格，不依赖外部 CUBE；可继续编辑每层配置。

手动操作：打开 synthetic_density.cube → Import another field file… →
synthetic_potential.cube → Surface layers / ESP color mapping… → 保留正等值面
并设为0.2 → Source field 选 density → Color mapping 选 potential。

density = exp(-(x²+y²+z²))；potential = 0.2x - 0.1y + 0.3z。
两张网格具有不同间距与斜基矢；这里的单位只是解析示例约定。
实际 ESP 应使用电子结构程序提供的、同一构型和坐标系的密度及电势网格。
''',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'examples'/'esp_mapping_v340')
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args();make_demo(args.output,args.render)
