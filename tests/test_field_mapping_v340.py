"""Independent analytical fields and complete UI/persistence/export workflows."""
from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer,vtkRenderWindow
from vtkmodules.util.numpy_support import vtk_to_numpy
from lele.core import Document,Frame,Volume
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.field_mapping import sample_field,attach_field_document,transformed_fields
from lele.field_export import export_active_cube
from test_periodic_fragment_ui_v171 import gui


def analytic_pair():
    # Different grid spacings and oblique voxel vectors, same Cartesian frame.
    basis=np.array([[.2,0,0],[.04,.2,0],[.02,.03,.2]])
    shape=(31,31,31);origin=-np.sum(basis,axis=0)*15
    xyz=np.moveaxis(np.indices(shape),0,-1)@basis+origin
    density=np.exp(-np.sum(xyz*xyz,axis=-1))
    base=Volume(density,origin,basis,'Analytic density','e/Bohr³')
    mb=np.array([[.3,0,0],[.03,.3,0],[.01,.02,.3]])
    mo=-np.sum(mb,axis=0)*15
    mx=np.moveaxis(np.indices(shape),0,-1)@mb+mo
    potential=mx@np.array([.2,-.1,.3])
    color=Volume(potential,mo,mb,'Analytic potential','Hartree')
    frame=Frame(['H'],[[0.,0.,0.]])
    return Document(Path('density.cube'),'Analytic',[frame],base,volumes=[base,color])


def options():
    return RenderOptions(axes_position='Off',unit_cell=False,volume_surfaces=[
        dict(dataset=0,value=.2,color='#ff0000',opacity=1.,style='Surface',visible=True,
             map_dataset=1,map_palette='Red-white-blue',map_range=[-.6,.6],map_legend=True)])


def draw_pair(doc=None,opts=None):
    doc=doc or analytic_pair();draw=MoleculeRenderer(vtkRenderer());draw.options=opts or options()
    draw.set_scene(doc.frames[0],doc.volume,volumes=doc.volumes)
    return draw,doc


def test_oblique_different_resolution_sampling_at_surface_vertices():
    draw,doc=draw_pair()
    assert len(draw.field_actors)==len(draw.field_scalar_bars)==1
    mapper=draw.field_actors[0].GetMapper();mapper.Update();poly=mapper.GetInput()
    points=vtk_to_numpy(poly.GetPoints().GetData());values=vtk_to_numpy(poly.GetPointData().GetScalars())
    np.testing.assert_allclose(values,points@[.2,-.1,.3],atol=8e-8)
    assert not draw.field_warnings
    assert 'Hartree' in draw.field_scalar_bars[0].GetTitle()
    lut=mapper.GetLookupTable()
    assert draw.field_actors[0].GetProperty().GetSpecularColor()==(1.,1.,1.)
    np.testing.assert_allclose(lut.GetColor(0),[1,1,1],atol=1e-12)
    assert lut.GetColor(-.5)[0]>lut.GetColor(-.5)[2]
    assert lut.GetColor(.5)[2]>lut.GetColor(.5)[0]


def test_mapping_and_layers_follow_source_rigid_transform():
    doc=analytic_pair();before=[v.data.copy() for v in doc.volumes]
    rotation=np.array([[0,1,0],[-1,0,0],[0,0,1.]])
    shift=np.array([2.,-1.,.7])
    doc.volume.origin=doc.volume.origin@rotation+shift
    doc.volume.voxel_vectors=doc.volume.voxel_vectors@rotation
    doc.frames[0].positions=doc.frames[0].positions@rotation+shift
    draw,_=draw_pair(doc)
    data=draw.field_actors[0].GetMapper().GetInput()
    points=vtk_to_numpy(data.GetPoints().GetData());scalars=vtk_to_numpy(data.GetPointData().GetScalars())
    np.testing.assert_allclose(scalars,((points-shift)@rotation.T)@[.2,-.1,.3],atol=2e-7)
    for a,b in zip(before,doc.volumes):np.testing.assert_array_equal(a,b.data)


def test_cross_dataset_overlay_stays_bound_on_dataset_switch():
    doc=analytic_pair();opts=options();opts.volume_surfaces[0]['map_dataset']=-1
    opts.volume_surfaces.append(dict(dataset=1,value=.1,color='#0000ff',opacity=.5,style='Wireframe'))
    draw,_=draw_pair(doc,opts);old=[a.GetBounds() for a in draw.field_actors]
    from lele.field_actions import select_field
    select_field(doc,1);draw.set_scene(doc.frames[0],doc.volume,volumes=doc.volumes)
    assert len(draw.field_actors)==2
    for a,b in zip(old,draw.field_actors):np.testing.assert_allclose(a,b.GetBounds())


def test_outside_color_grid_is_nan_and_partial_surface_warns_gray():
    doc=analytic_pair();color=doc.volumes[1]
    color.origin=np.zeros(3);color.reference_origin=np.zeros(3)
    vals=sample_field(color,[[-1.,0,0],[.2,.3,.4]])
    assert np.isnan(vals[0]) and np.isfinite(vals[1])
    draw,_=draw_pair(doc)
    assert draw.field_actors and any('gray' in message for message in draw.field_warnings)
    samples=vtk_to_numpy(draw.field_actors[0].GetMapper().GetInput().GetPointData().GetScalars())
    assert np.isnan(samples).any() and np.isfinite(samples).any()
    color.origin+=100;color.reference_origin=color.origin.copy()
    draw.set_scene(doc.frames[0],doc.volume,volumes=doc.volumes)
    assert not draw.field_actors and any('omitted' in message for message in draw.field_warnings)


def test_periodic_sampling_wraps_skew_lattice_and_origin():
    shape=(4,5,6);basis=np.array([[.3,.1,0],[0,.4,.1],[.1,0,.5]])
    v=Volume(np.arange(np.prod(shape)).reshape(shape),[1.,2.,3.],basis,periodic=True)
    p=np.array([[.2,1.4,2.8],[3.8,4.7,5.9]])@basis+v.origin
    expected=sample_field(v,p)
    cell=np.asarray(shape)[:,None]*basis
    np.testing.assert_allclose(sample_field(v,p+[2,-3,4]@cell),expected,atol=1e-11)


@pytest.mark.parametrize('periodic',[False,True])
def test_boundary_repeats_cell_sized_source_without_changing_periodicity(periodic):
    n=8;basis=np.array([[1.,0,0],[.3,1.,0],[.2,.1,1.]])
    data=np.broadcast_to(np.cos(2*np.pi*np.arange(n)[:,None,None]/n),(n,n,n))
    field=Volume(data,[0,0,0],basis/n,'density','test',periodic)
    mapfield=Volume(data,[0,0,0],basis/n,'potential','test',True)
    frame=Frame(['H'],[[.5,.5,.5]@basis],basis,(True,)*3)
    doc=Document(Path('a.cube'),'test',[frame],field,volumes=[field,mapfield])
    opts=options();opts.boundary_bounds=((-1,1),(0,1),(0,1));opts.volume_surfaces[0]['value']=0.
    draw,_=draw_pair(doc,opts)
    assert len(draw.field_actors)==2
    assert field.periodic is periodic
    allpoints=np.concatenate([vtk_to_numpy(a.GetMapper().GetInput().GetPoints().GetData()) for a in draw.field_actors])@np.linalg.inv(basis)
    np.testing.assert_allclose([allpoints[:,0].min(),allpoints[:,0].max()],[-.75,.75],atol=1e-6)


def test_attachment_matches_transformed_geometry_and_is_atomic():
    doc=analytic_pair();incoming=Document(Path('esp.cube'),'CUBE',[doc.frames[0].clone()],doc.volumes[1])
    doc.volumes=doc.volumes[:1]
    rotation=np.array([[0,1,0],[-1,0,0],[0,0,1.]])
    shift=np.array([2,3,4.])
    doc.volume.origin=doc.volume.origin@rotation+shift;doc.volume.voxel_vectors=doc.volume.voxel_vectors@rotation
    doc.frames[0].positions=doc.frames[0].positions@rotation+shift
    assert attach_field_document(doc,doc.frames[0],incoming)==1
    np.testing.assert_allclose(doc.volumes[1].origin,incoming.volume.origin@rotation+shift)
    assert not np.shares_memory(doc.volumes[1].data,incoming.volume.data)
    before=list(doc.volumes);incoming.frames[0].positions+=1
    with pytest.raises(ValueError,match='coordinates'):attach_field_document(doc,doc.frames[0],incoming)
    assert all(a is b for a,b in zip(before,doc.volumes)) and len(doc.volumes)==2
    doc.modified=True;doc.volume=None
    with pytest.raises(ValueError,match='detached'):attach_field_document(doc,doc.frames[0],incoming)


def test_import_button_and_project_have_no_external_dependency(gui,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from lele.project_file import save_project,load_project
    doc=analytic_pair();color_doc=Document(Path('esp.cube'),'CUBE',[doc.frames[0].clone()],doc.volumes.pop())
    path=tmp_path/'esp.cube';export_active_cube(path,color_doc,color_doc.frames[0])
    w=gui.window;w._attach_loaded_document(doc)
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *a:(str(path),''))
    w.field_import_button.click();assert len(doc.volumes)==2
    w._set_surface_option('volume_surfaces',options().volume_surfaces)
    assert len(w.renderer.field_scalar_bars)==1
    project=tmp_path/'mapped.lele'
    save_project(project,dict(documents=[dict(document=doc,options=w.render_options,frame_index=0)],current_document=0,selection=[]))
    path.unlink();entry=load_project(project)['documents'][0]
    restored=entry['document'];assert len(restored.volumes)==2
    draw,_=draw_pair(restored,entry['options']);assert draw.field_scalar_bars and not draw.field_warnings
    restored.volume=None;draw.set_scene(restored.frames[0],None,volumes=restored.volumes)
    assert not draw.field_actors and not draw.field_scalar_bars


def test_mapping_dialog_preserves_scale_and_cancel(monkeypatch):
    from PySide6.QtWidgets import QApplication,QMessageBox
    from lele.field_mapping_dialog import FieldMappingDialog
    from lele.isosurface_dialog import IsosurfaceLayersDialog
    app=QApplication.instance() or QApplication([]);doc=analytic_pair();opts=options();before=deepcopy(opts)
    dialog=IsosurfaceLayersDialog(opts,fields=doc.volumes,active_index=0)
    dialog.commit();assert dialog.layers==opts.volume_surfaces
    mapping=FieldMappingDialog(doc.volumes,opts.volume_surfaces[0]);mapping.source.setCurrentIndex(0)
    mapping.reject();assert opts==before
    mapping=FieldMappingDialog(doc.volumes,opts.volume_surfaces[0]);errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a))
    mapping.minimum.setText('0.1');mapping.commit();assert mapping.settings is None and errors
    mapping.minimum.setText('-.2');mapping.maximum.setText('.4');mapping.commit()
    assert mapping.settings['map_range']==[-.2,.4]


def test_mapped_surface_png_gif_and_colorbar(tmp_path):
    from PIL import Image
    from lele.png_export import export_png,PngSettings
    from lele.animation_export import export_animation_gif,GifSettings
    draw,doc=draw_pair();scene=draw.renderer
    window=vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(400,300);window.AddRenderer(scene)
    camera=scene.GetActiveCamera();camera.SetPosition(0,-6,0);camera.SetFocalPoint(0,0,0);camera.SetViewUp(0,0,1)
    scene.ResetCamera();window.Render()
    target=tmp_path/'esp.png';export_png(target,window,PngSettings(800,600,1),mesh_items=draw._keepalive)
    def check_image(im):
        p=np.asarray(im.convert('RGB'),dtype=int)
        # Exclude the legend: colors must occur on the actual surface.
        p=p[int(.15*len(p)):int(.8*len(p))]
        assert np.count_nonzero((p[...,0]>p[...,2]+40)&(p[...,0]>p[...,1]+20))>100
        assert np.count_nonzero((p[...,2]>p[...,0]+40)&(p[...,2]>p[...,1]+20))>100
    with Image.open(target) as im:check_image(im);assert im.size==(800,600)
    window.Finalize();doc.frames.append(doc.frames[0].clone())
    export_animation_gif(tmp_path/'esp.gif',doc,GifSettings(width=400,height=300,last_frame=2,supersample=1),draw.options)
    with Image.open(tmp_path/'esp.gif') as im:
        assert im.n_frames==2;check_image(im)


def test_pre_v330_missing_stages_does_not_crash_info(gui,tmp_path):
    from test_wavefunction_inputs import fchk_text
    path=tmp_path/'a.fchk';path.write_text(fchk_text())
    from lele.formats import load_document
    doc=load_document(path);assert len(doc.calculation_results.stages)==1
    assert doc.calculation_results.stages[0].status=='Convergence not recorded'
    doc.calculation_results.stages=[]
    gui.window._attach_loaded_document(doc)
    assert gui.window.mo_generate.isEnabled()


def test_new_document_cannot_inherit_other_documents_dataset_references(gui):
    w=gui.window;first=analytic_pair();w._attach_loaded_document(first)
    w._set_surface_option('volume_surfaces',options().volume_surfaces)
    second=analytic_pair();second.path=Path('second.cube');second.volumes=second.volumes[:1]
    w._attach_loaded_document(second)
    assert w.render_options.volume_surfaces==[]
    w._activate_document(w.documents.index(first));w.change_frame(0)
    assert w.render_options.volume_surfaces==options().volume_surfaces
    assert len(w.renderer.field_scalar_bars)==1


def test_periodic_seams_negative_roundoff_and_translated_grid_clipping():
    doc=analytic_pair();basis=np.array([[1.,0,0],[.3,1.,0],[.2,.1,1.]])
    n=8;data=np.broadcast_to(np.cos(2*np.pi*np.arange(n)[:,None,None]/n),(n,n,n))
    field=Volume(data,np.array([.2,.3,0])@basis,basis/n,'periodic','test',True)
    # Tiny negative coordinates used to produce an out-of-bounds index n.
    points=np.array([[.3,-1e-18,0],[0,0,0],[8,8,8]])@field.voxel_vectors+field.origin
    assert np.isfinite(sample_field(field,points)).all()
    frame=Frame(['H'],[[.5,.5,.5]@basis],basis,(True,)*3)
    doc=Document(Path('shift.cube'),'test',[frame],field)
    opts=RenderOptions(volume_signs='Positive',volume_iso=.1,boundary_bounds=((1,2),(0,1),(0,1)),axes_position='Off')
    draw,_=draw_pair(doc,opts)
    assert len(draw.field_actors)==4
    for actor in draw.field_actors:
        mapper=actor.GetMapper();assert mapper.GetNumberOfClippingPlanes()==6
        for plane in mapper.GetClippingPlanes():
            assert plane.EvaluateFunction(np.array([1.5,.5,.5])@basis)>0


def test_reject_occupancies_and_mismatched_periodic_cell():
    doc=analytic_pair();incoming=deepcopy(doc)
    doc.frames[0].info['site_occupancies']=[{'H':.5}]
    with pytest.raises(ValueError,match='occupancies'):attach_field_document(doc,doc.frames[0],incoming)
    doc.frames[0].info.clear();incoming.volumes[0].periodic=True
    incoming.frames[0].cell=np.eye(3)*10
    with pytest.raises(ValueError,match='lattice'):attach_field_document(doc,doc.frames[0],incoming)
