"""Selected atom size stays a display override through rendering and structure workflows."""
from dataclasses import replace
from pathlib import Path
import json
import zipfile

import numpy as np
import pytest

from lele.atom_appearance import AtomAppearance, appearance
from lele.core import Frame, Document, visible_bonds
from lele.project_file import save_project, load_project
from lele.render_options import RenderOptions
from test_periodic_fragment_ui_v171 import gui


def molecular():
    return Frame(['C','C','C'],[[0.,0.,0.],[1.4,0.,0.],[4.,2.,0.]],energy_ev=-12.)


def glyph_radii(renderer):
    """Inspect actual VTK per-instance scale arrays rather than the helper API."""
    values=[]
    for actor in renderer.dynamic:
        if not actor.IsA('vtkActor') or actor.GetMapper() is None:
            continue
        mapper=actor.GetMapper()
        if not mapper.IsA('vtkGlyph3DMapper'):
            continue
        data=mapper.GetInput();sizes=data.GetPointData().GetArray('atom_radius')
        if sizes is None:continue
        values.extend((np.array(data.GetPoint(i)),sizes.GetValue(i)) for i in range(data.GetNumberOfPoints()))
    return values


def radius_at(renderer,position):
    matches=[r for p,r in glyph_radii(renderer) if np.allclose(p,position,atol=1.e-6,rtol=0)]
    assert len(matches)==1
    return matches[0]


def vtk_objects(values):
    for obj in values:
        if isinstance(obj,(tuple,list)):
            yield from vtk_objects(obj)
        else:yield obj


@pytest.mark.parametrize('value',[0.,-.1,float('nan'),float('inf')])
def test_size_scale_rejects_nonpositive_or_nonfinite_values(value):
    assert AtomAppearance().size_scale==1.
    with pytest.raises(ValueError):AtomAppearance(size_scale=value)


def test_ui_size_changes_selected_atoms_only_across_matching_frames_and_undo(gui):
    frame=molecular();frame.atom_appearance[1]=AtomAppearance(size_scale=.6,color='#123456')
    gui.attach(frame,second_frame=frame.clone());w=gui.window
    before=frame.positions.copy();before_bonds=visible_bonds(frame);global_scale=w.render_options.atom_scale
    gui.select([0,2]);w.atom_panel.size_spin.setValue(1.7)
    assert [appearance(w.frame,i).size_scale for i in range(3)]==[1.7,.6,1.7]
    assert w.doc.frames[1].atom_appearance==w.frame.atom_appearance
    assert appearance(w.frame,1).color=='#123456'
    assert w.render_options.atom_scale==global_scale
    np.testing.assert_array_equal(w.frame.positions,before)
    assert visible_bonds(w.frame)==before_bonds and w.frame.energy_ev==-12.
    w.undo_edit()
    assert [appearance(w.frame,i).size_scale for i in range(3)]==[1.,.6,1.]
    assert w.doc.frames[1].atom_appearance==w.frame.atom_appearance


def test_mixed_size_selection_is_blank_and_does_not_modify_atoms(gui):
    frame=molecular();frame.atom_appearance={0:AtomAppearance(size_scale=.7),1:AtomAppearance(size_scale=1.2)}
    gui.attach(frame);w=gui.window;before=frame.atom_appearance.copy();undo=len(w.undo_stack)
    gui.select([0,1])
    assert w.atom_panel.size_spin.lineEdit().placeholderText()=='Mixed'
    assert w.atom_panel.size_spin.lineEdit().text()==''
    assert frame.atom_appearance==before and len(w.undo_stack)==undo
    w.atom_panel.size_spin.setValue(2.0)
    assert appearance(frame,0).size_scale==appearance(frame,1).size_scale==2.
    assert appearance(frame,2).size_scale==1.


def test_actual_glyphs_labels_and_selection_outline_follow_size_without_changing_bonds(gui):
    frame=molecular();gui.attach(frame);w=gui.window
    w.render_options.labels='Index (1..N)';gui.select([1]);w.refresh_scene()
    base=w.renderer._atom_radius('C','Ball and stick')
    old_tubes=sorted(obj.GetRadius() for obj in vtk_objects(w.renderer._keepalive)
                     if hasattr(obj,'IsA') and obj.IsA('vtkTubeFilter'))
    w.atom_panel.size_spin.setValue(2.)
    assert radius_at(w.renderer,frame.positions[0])==pytest.approx(base)
    assert radius_at(w.renderer,frame.positions[1])==pytest.approx(2*base)
    assert radius_at(w.renderer,frame.positions[2])==pytest.approx(base)
    np.testing.assert_allclose(w.renderer._label_radii,[base,2*base,base])
    assert len(w.renderer.atom_highlights)==1
    assert w.renderer.atom_highlights[0].GetScale()[0]==pytest.approx(2*base*1.15)
    tubes=sorted(obj.GetRadius() for obj in vtk_objects(w.renderer._keepalive)
                 if hasattr(obj,'IsA') and obj.IsA('vtkTubeFilter'))
    assert tubes==old_tubes


def test_picking_tracks_enlarged_and_reduced_projected_sphere(gui):
    frame=Frame(['C'],[[0.,0.,0.]])
    gui.attach(frame);w=gui.window;gui.select([0])
    w.vtk.GetRenderWindow().SetSize(600,400)
    camera=w.scene.GetActiveCamera();camera.SetParallelProjection(True);camera.SetParallelScale(2.)
    camera.SetPosition(0.,0.,10.);camera.SetFocalPoint(0.,0.,0.);camera.SetViewUp(0.,1.,0.)
    base=w.renderer._atom_radius('C','Ball and stick')
    def pick(x):
        w.scene.SetWorldPoint(x,0.,0.,1.);w.scene.WorldToDisplay()
        sx,sy,_=w.scene.GetDisplayPoint()
        return w.renderer.pick_index(sx,sy)
    w.atom_panel.size_spin.setValue(2.)
    assert pick(base*1.5)==0
    w.atom_panel.size_spin.setValue(.5)
    assert pick(base*.75) is None
    assert pick(0.)==0


def test_size_survives_delete_undo_and_appearance_undo(gui):
    gui.attach(molecular());w=gui.window
    gui.select([2]);w.atom_panel.size_spin.setValue(2.4)
    gui.select([0]);w.delete_action.trigger()
    assert len(w.frame.symbols)==2 and appearance(w.frame,1).size_scale==2.4
    w.undo_edit()
    assert len(w.frame.symbols)==3 and appearance(w.frame,2).size_scale==2.4
    w.undo_edit()
    assert all(appearance(w.frame,i).size_scale==1. for i in range(3))


def test_size_project_roundtrip_and_old_project_default(tmp_path):
    frame=molecular();frame.atom_appearance[1]=AtomAppearance(size_scale=1.45,color='#123456')
    doc=Document(Path('molecule.xyz'),'XYZ',[frame])
    state={'documents':[{'document':doc,'options':RenderOptions(),'frame_index':0}],'current_document':0}
    saved=tmp_path/'size.lele';save_project(saved,state)
    restored=load_project(saved)['documents'][0]['document'].frames[0]
    assert appearance(restored,1).size_scale==1.45
    from project_archive_v1 import legacy_archive
    with legacy_archive(saved) as archive:members={name:archive.read(name) for name in archive.namelist()}
    manifest=json.loads(members['manifest.json'])
    for node in manifest['nodes']:
        if node.get('type')=='lele.atom_appearance:AtomAppearance':
            node['attributes'].pop('size_scale',None)
    members['manifest.json']=json.dumps(manifest).encode()
    old=tmp_path/'old.lele'
    with zipfile.ZipFile(old,'w') as archive:
        for name,data in members.items():archive.writestr(name,data)
    migrated=load_project(old)['documents'][0]['document'].frames[0]
    assert appearance(migrated,1).size_scale==1.
    assert appearance(migrated,1).color=='#123456'


def test_supercell_and_boundary_copy_original_size_to_every_displayed_atom(gui):
    from lele.supercell import make_supercell
    source=Frame(['C','O'],[[1.,1.,1.],[3.,3.,3.]],np.eye(3)*6,(True,)*3,
                 atom_appearance={1:AtomAppearance(size_scale=1.8)})
    expanded=make_supercell(source,(2,1,1))
    assert [appearance(expanded,i).size_scale for i in range(4)]==[1.,1.8,1.,1.8]
    gui.attach(source);w=gui.window;w._apply_boundary(((0,2),(0,1),(0,1)))
    displayed=w.renderer.displayed_atoms()
    assert len(displayed)==4
    for index,position in displayed:
        expected=w.renderer._atom_radius(source.symbols[index],'Ball and stick')*appearance(source,index).size_scale
        assert radius_at(w.renderer,position)==pytest.approx(expected)
    assert source.atom_appearance[1].size_scale==1.8


def test_periodic_fragment_images_and_mixed_occupancy_sectors_keep_size(gui):
    from lele.periodic_geometry import periodic_fragment
    frame=Frame(['O','H'],[[9.65,1.,1.],[.53,1.,1.]],np.eye(3)*10,(True,)*3,
                atom_appearance={1:AtomAppearance(size_scale=1.6)})
    gui.attach(frame);w=gui.window
    w.renderer.periodic_preview=periodic_fragment(frame,[0]);w.refresh_scene()
    for index,position in w.renderer.displayed_atoms():
        expected=w.renderer._atom_radius(frame.symbols[index],'Ball and stick')*appearance(frame,index).size_scale
        assert radius_at(w.renderer,position)==pytest.approx(expected)
    mixed=Frame(['C'],[[1.,2.,3.]],info={'site_occupancies':[{'C':.5,'N':.5}]},
                atom_appearance={0:AtomAppearance(size_scale=2.1)})
    gui.attach(mixed);w=gui.window
    sectors=[obj for obj in vtk_objects(w.renderer._keepalive) if hasattr(obj,'IsA') and obj.IsA('vtkSphereSource')]
    assert len(sectors)==2
    expected=w.renderer._atom_radius('C','Ball and stick')*2.1
    assert all(sphere.GetRadius()==pytest.approx(expected) for sphere in sectors)


def test_typing_first_atoms_size_into_mixed_selection_still_applies_to_all(gui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    frame=molecular();frame.atom_appearance={0:AtomAppearance(size_scale=.7),1:AtomAppearance(size_scale=1.2)}
    gui.attach(frame);w=gui.window;gui.select([0,1])
    spin=w.atom_panel.size_spin
    assert spin.value()==.7 and spin.lineEdit().text()==''
    spin.lineEdit().setFocus();QTest.keyClicks(spin.lineEdit(),'0.70');QTest.keyClick(spin.lineEdit(),Qt.Key.Key_Return)
    assert appearance(frame,0).size_scale==appearance(frame,1).size_scale==.7
    assert appearance(frame,2).size_scale==1.
    assert len(w.undo_stack)==1


def test_gif_render_pipeline_retains_selected_sizes_without_mutating_sources(tmp_path,monkeypatch):
    from PIL import Image
    from lele.animation_export import _OffscreenScene,GifSettings,export_animation_gif
    first=molecular();first.atom_appearance[0]=AtomAppearance(size_scale=2.)
    second=first.clone();second.positions+=np.array([.2,.1,0.])
    doc=Document(tmp_path/'sizes.xyz','XYZ',[first,second])
    positions=[f.positions.copy() for f in doc.frames]
    styles=[f.atom_appearance.copy() for f in doc.frames]
    captured=[]
    def capture(scene):
        captured.append(sorted(radius for _,radius in glyph_radii(scene.draw)))
        return Image.new('RGB',(80,60),'white')
    monkeypatch.setattr(_OffscreenScene,'_capture_image',capture)
    options=RenderOptions();settings=GifSettings(width=80,height=60,supersample=1,first_frame=1,last_frame=2)
    output=tmp_path/'sizes.gif'
    assert export_animation_gif(output,doc,settings,options)==2
    assert output.exists() and captured
    for radii in captured:
        assert len(radii)==3
        assert radii[0]==pytest.approx(radii[1])
        assert radii[2]==pytest.approx(radii[0]*2)
    for frame,original,appearance_snapshot in zip(doc.frames,positions,styles):
        np.testing.assert_array_equal(frame.positions,original)
        assert frame.atom_appearance==appearance_snapshot


def test_actual_png_preserves_selected_atom_radius_and_restores_live_glyphs(tmp_path):
    from PIL import Image
    from vtkmodules.vtkRenderingCore import vtkRenderer,vtkRenderWindow
    from lele.renderer import MoleculeRenderer
    from lele.png_export import PngSettings,export_png
    frame=Frame(['C','C'],[[-3.,0.,0.],[3.,0.,0.]],
                atom_appearance={1:AtomAppearance(size_scale=2.)})
    source_positions=frame.positions.copy();source_styles=frame.atom_appearance.copy()
    scene=vtkRenderer();window=vtkRenderWindow()
    window.SetOffScreenRendering(True);window.SetMultiSamples(0)
    window.SetSize(480,240);window.AddRenderer(scene)
    draw=MoleculeRenderer(scene)
    draw.options=RenderOptions(style='Space filling',background='#ffffff',surface_finish='Matte',
                               axes_position='Off',unit_cell=False,labels='None')
    try:
        draw.set_scene(frame)
        camera=scene.GetActiveCamera();camera.SetParallelProjection(True);camera.SetParallelScale(3.)
        camera.SetPosition(0.,0.,20.);camera.SetFocalPoint(0.,0.,0.);camera.SetViewUp(0.,1.,0.)
        scene.ResetCameraClippingRange();window.Render()
        before=sorted(r for _,r in glyph_radii(draw))
        path=tmp_path/'selected_size.png'
        export_png(path,window,PngSettings(480,240,2),mesh_items=draw._keepalive)
        with Image.open(path) as image:
            assert image.size==(480,240)
            pixels=np.array(image.convert('RGB'))
        mask=np.any(pixels<245,axis=2)
        left,right=mask[:,:240],mask[:,240:]
        left_y,left_x=np.nonzero(left);right_y,right_x=np.nonzero(right)
        assert left_x.size>100 and right_x.size>100
        # Orthographic projection: doubling the radius doubles its diameter
        # and quadruples its silhouette area, within antialiasing tolerance.
        assert 1.85<(np.ptp(right_x)+1)/(np.ptp(left_x)+1)<2.15
        assert 1.85<(np.ptp(right_y)+1)/(np.ptp(left_y)+1)<2.15
        assert 3.6<right.sum()/left.sum()<4.4
        np.testing.assert_allclose(sorted(r for _,r in glyph_radii(draw)),before,rtol=0,atol=0)
        assert frame.atom_appearance==source_styles
        np.testing.assert_array_equal(frame.positions,source_positions)
    finally:
        window.Finalize()
