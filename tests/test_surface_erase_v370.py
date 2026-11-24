"""Exact through-depth mask geometry, field preservation and real UI routing."""
from pathlib import Path
import numpy as np
import pytest
from vtkmodules.vtkCommonCore import vtkPoints
from vtkmodules.vtkCommonDataModel import vtkCellArray, vtkPolyData
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy

from lele.core import Frame, Volume, Document
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer, volume_surface_specs
from lele.surface_erase import (validate_hidden_regions, rectangle_hidden_region,
                               display_region_planes, hide_polydata)
from test_periodic_fragment_ui_v171 import gui


def region(xlo, xhi, ylo, yhi):
    return {'planes': [[1, 0, 0, -xlo], [-1, 0, 0, xhi],
                       [0, 1, 0, -ylo], [0, -1, 0, yhi]]}


def mesh(vertices, triangles):
    points=vtkPoints();points.SetData(numpy_to_vtk(np.asarray(vertices,dtype=float),deep=True))
    faces=vtkCellArray()
    for triangle in triangles:
        faces.InsertNextCell(len(triangle))
        for i in triangle:faces.InsertCellPoint(i)
    data=vtkPolyData();data.SetPoints(points);data.SetPolys(faces)
    values=np.asarray(vertices)@np.array([1.,2.,3.])
    scalars=numpy_to_vtk(values,deep=True);scalars.SetName('analytic')
    data.GetPointData().SetScalars(scalars)
    return data


def area(poly):
    total=0.
    for index in range(poly.GetNumberOfCells()):
        cell=poly.GetCell(index);points=np.array([poly.GetPoint(cell.GetPointId(i)) for i in range(cell.GetNumberOfPoints())])
        for i in range(1,len(points)-1):
            total+=np.linalg.norm(np.cross(points[i]-points[0],points[i+1]-points[0]))/2
    return total


def assert_no_interior_centers(poly, masks):
    for index in range(poly.GetNumberOfCells()):
        cell=poly.GetCell(index)
        center=np.mean([poly.GetPoint(cell.GetPointId(i)) for i in range(cell.GetNumberOfPoints())],axis=0)
        for item in masks:
            planes=np.asarray(item['planes'])
            assert not np.all(planes[:,:3]@center+planes[:,3]>1e-6)


def test_rectangle_inside_large_triangles_is_cut_with_exact_area_and_scalars():
    # No original vertex lies in the rectangle: point/cell filtering is wrong.
    original=mesh([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],[(0,1,2),(0,2,3)])
    masks=[region(-.5,.5,-.5,.5)]
    clipped,keep=hide_polydata(original,masks)
    assert keep and area(clipped)==pytest.approx(3.,abs=1e-7)
    assert area(original)==4.
    assert_no_interior_centers(clipped,masks)
    coords=vtk_to_numpy(clipped.GetPoints().GetData())
    values=vtk_to_numpy(clipped.GetPointData().GetScalars())
    np.testing.assert_allclose(values,coords@np.array([1.,2.,3.]),atol=1e-7)


def test_repeated_overlapping_masks_remove_union_and_both_depths():
    layers=[]
    for z in (-100.,100.):
        layers.append(mesh([[-1,-1,z],[1,-1,z],[1,1,z],[-1,1,z]],[(0,1,2),(0,2,3)]))
    masks=[region(-.5,.5,-.5,.5),region(0.,1.,-.5,.5)]
    for original in layers:
        result,_=hide_polydata(original,masks)
        assert area(result)==pytest.approx(2.5,abs=1e-6)
        assert_no_interior_centers(result,masks)
    result,_=hide_polydata(layers[0],[region(-2,2,-2,2)])
    assert result.GetNumberOfCells()==0


@pytest.mark.parametrize('parallel',[True,False])
def test_camera_rectangle_follows_projection_and_survives_camera_changes(parallel):
    scene=vtkRenderer();window=vtkRenderWindow();window.SetOffScreenRendering(1)
    window.SetSize(400,300);window.AddRenderer(scene)
    camera=scene.GetActiveCamera();camera.SetPosition(0,0,10);camera.SetFocalPoint(0,0,0)
    camera.SetViewUp(0,1,0);camera.SetParallelProjection(parallel);camera.SetParallelScale(3)
    camera.SetClippingRange(.1,20)
    mask=rectangle_hidden_region(scene,(160,110,240,190))
    coefficients=np.asarray(mask['planes'])
    for depth in (-30.,0.,8.):
        for x,y in ((0,0),(.1,.2),(2,0),(-2,2)):
            point=np.array([x,y,depth]);scene.SetWorldPoint(*point,1);scene.WorldToDisplay()
            px,py,_=scene.GetDisplayPoint()
            inside=bool(np.all(coefficients[:,:3]@point+coefficients[:,3]>=-1e-7))
            assert inside==(160<=px<=240 and 110<=py<=190)
    before=coefficients.copy();camera.Azimuth(77);camera.Elevation(31)
    np.testing.assert_array_equal(mask['planes'],before)
    window.Finalize()


def test_masks_follow_display_alignment_without_changing_model_region():
    theta=.7;rotation=np.array([[np.cos(theta),np.sin(theta),0],[-np.sin(theta),np.cos(theta),0],[0,0,1]])
    translation=np.array([3.,-2.,4.]);mask=region(-.5,.5,-.5,.5)
    planes=display_region_planes(mask,rotation,translation)
    original=np.array([[0,0,0],[1,0,10],[0,1,-10]])
    displayed=original@rotation+translation
    expected=np.all(original@np.asarray(mask['planes'])[:,:3].T+np.asarray(mask['planes'])[:,3]>=0,axis=1)
    np.testing.assert_array_equal(np.all(displayed@planes[:,:3].T+planes[:,3]>=0,axis=1),expected)
    source=mesh([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],[(0,1,2),(0,2,3)])
    coords=vtk_to_numpy(source.GetPoints().GetData()).copy()
    moved=mesh(coords@rotation+translation,[(0,1,2),(0,2,3)])
    result,_=hide_polydata(moved,[mask],rotation=rotation,translation=translation)
    assert area(result)==pytest.approx(3.,abs=1e-6)


def sample_document():
    data=np.indices((3,3,3))[2].astype(float)
    volume=Volume(data,np.zeros(3),np.eye(3),'density','test')
    frame=Frame(['H'],[[.2,.2,.2]],np.eye(3)*3,(True,)*3)
    return Document(Path('mask.cube'),'test',[frame],volume)


def test_masks_cut_boundary_copies_and_preserve_source_data():
    doc=sample_document();before=doc.volume.data.copy();positions=doc.frames[0].positions.copy()
    draw=MoleculeRenderer(vtkRenderer())
    draw.options=RenderOptions(axes_position='Off',volume_signs='Positive',volume_iso=1.,
        boundary_bounds=((0,2),(0,2),(0,1)),volume_hidden_regions=[region(.5,1.5,.5,1.5)])
    draw.set_scene(doc.frames[0],doc.volume)
    assert len(draw.field_actors)==4
    surfaces=[actor.GetMapper().GetInput() for actor in draw.field_actors]
    assert sorted(area(poly) for poly in surfaces)==pytest.approx([3.,4.,4.,4.])
    np.testing.assert_array_equal(doc.volume.data,before)
    np.testing.assert_array_equal(doc.frames[0].positions,positions)


def test_none_suppresses_explicit_layers_without_discarding_any_field():
    doc=sample_document();layers=[dict(value=1.,color='#112233',opacity=1.,style='Surface')]
    draw=MoleculeRenderer(vtkRenderer());draw.options=RenderOptions(volume_signs='None',volume_surfaces=layers)
    assert volume_surface_specs(draw.options)==[]
    draw.set_scene(doc.frames[0],doc.volume)
    assert draw.field_actors==[] and draw.options.volume_surfaces==layers
    assert doc.volume is doc.volumes[0]
    draw.options.volume_signs='Both';draw.set_scene(doc.frames[0],doc.volume)
    assert len(draw.field_actors)==1


@pytest.mark.parametrize('bad',[None,{},[{}],[{'planes':[[0,0,0,0]]*4}],
    [{'planes':[[1,0,0,float('nan')]]*4}],[{'planes':[[1,0,0,0]]*3}]])
def test_invalid_saved_masks_are_rejected(bad):
    with pytest.raises(ValueError):validate_hidden_regions(bad)


def test_masks_and_none_roundtrip_project(tmp_path):
    from lele.project_file import save_project,load_project
    doc=sample_document();options=RenderOptions(volume_signs='None',volume_hidden_regions=[region(.5,1.5,.5,1.5)])
    state=dict(documents=[dict(document=doc,options=options,frame_index=0)],current_document=0,selection=[])
    file=tmp_path/'masked.lele';save_project(file,state)
    loaded=load_project(file)['documents'][0]
    assert loaded['options']==options
    np.testing.assert_array_equal(loaded['document'].volume.data,doc.volume.data)


def test_mapped_colors_interpolate_at_new_cut_vertices():
    doc=sample_document();color_data=np.indices((3,3,3))[0]+2.*np.indices((3,3,3))[1]
    color=Volume(color_data,np.zeros(3),np.eye(3),'color','test')
    doc.volumes.append(color)
    draw=MoleculeRenderer(vtkRenderer());draw.options=RenderOptions(axes_position='Off',
        volume_hidden_regions=[region(.5,1.5,.5,1.5)],volume_surfaces=[dict(value=1.,
        color='#ffffff',opacity=.7,style='Surface',dataset=0,map_dataset=1,map_palette='Viridis',
        map_range=[0.,6.],map_legend=False)])
    draw.set_scene(doc.frames[0],doc.volume,volumes=doc.volumes)
    assert len(draw.field_actors)==1
    mapper=draw.field_actors[0].GetMapper();data=mapper.GetInput()
    points=vtk_to_numpy(data.GetPoints().GetData());scalars=vtk_to_numpy(data.GetPointData().GetScalars())
    np.testing.assert_allclose(scalars,points[:,0]+2*points[:,1],atol=1e-6)
    assert mapper.GetScalarVisibility() and draw.field_actors[0].GetProperty().GetOpacity()==.7
    assert area(data)==pytest.approx(3.)


def test_field_ui_rectangle_undo_restore_and_document_isolation(gui):
    w=gui.window;doc=sample_document();w._attach_loaded_document(doc)
    w._set_option('volume_iso',1.);w.field_signs.setCurrentText('Positive')
    w.vtk.GetRenderWindow().SetSize(600,400)
    camera=w.scene.GetActiveCamera();camera.SetPosition(1,1,10);camera.SetFocalPoint(1,1,1)
    camera.SetViewUp(0,1,0);camera.SetParallelProjection(True);camera.SetParallelScale(2.)
    w.scene.ResetCameraClippingRange()
    box_states=[];w.vtk.set_box_selection=box_states.append
    assert w.surface_hide_check.isEnabled()
    w.box_select_action.setChecked(True);w.surface_hide_check.setChecked(True)
    assert not w.box_select_action.isChecked() and box_states[-1]
    selection=list(w.selection);positions=w.frame.positions.copy();grids=doc.volume.data.copy()
    def qt_point(x,y):
        w.scene.SetWorldPoint(x,y,1,1);w.scene.WorldToDisplay();px,py,_=w.scene.GetDisplayPoint()
        vw,vh=w.vtk.GetRenderWindow().GetSize()
        return px*w.vtk.width()/vw,w.vtk.height()-py*w.vtk.height()/vh
    a=qt_point(.5,.5);b=qt_point(1.5,1.5)
    w._rectangle_selected(*a,*b)
    assert len(w.render_options.volume_hidden_regions)==1
    assert area(w.renderer.field_actors[0].GetMapper().GetInput())==pytest.approx(3.,abs=1e-5)
    assert w.selection==selection and not doc.modified
    np.testing.assert_array_equal(w.frame.positions,positions);np.testing.assert_array_equal(doc.volume.data,grids)
    w.undo_edit();assert w.render_options.volume_hidden_regions==[]
    assert area(w.renderer.field_actors[0].GetMapper().GetInput())==pytest.approx(4.)
    w._rectangle_selected(*a,*b);w.surface_hide_restore.click()
    assert not w.render_options.volume_hidden_regions
    w._rectangle_selected(*a,*b)
    w.field_signs.setCurrentText('None')
    assert w.renderer.field_actors==[] and w.slice_button.isEnabled()
    assert not w.surface_hide_check.isChecked() and not box_states[-1]
    other=sample_document();other.path=Path('other-mask.cube');w._attach_loaded_document(other)
    assert w.render_options.volume_hidden_regions==[]
    w._activate_document(w.documents.index(doc))
    assert len(w.render_options.volume_hidden_regions)==1 and w.render_options.volume_signs=='None'


def test_png_export_keeps_hole_at_higher_resolution(tmp_path):
    from PIL import Image
    from lele.png_export import export_png,PngSettings
    scene=vtkRenderer();scene.SetBackground(1.,1.,1.)
    draw=MoleculeRenderer(scene);draw.options=RenderOptions(volume_signs='Positive',volume_iso=1.,
        volume_positive_color='#0000ff',volume_opacity=1.,volume_hidden_regions=[region(-.5,.5,-.5,.5)])
    volume=Volume(np.indices((3,3,3))[2].astype(float),[-1,-1,0],np.eye(3))
    draw._volume(volume)
    window=vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(240,240);window.AddRenderer(scene)
    camera=scene.GetActiveCamera();camera.SetPosition(0,0,10);camera.SetFocalPoint(0,0,1)
    camera.SetViewUp(0,1,0);camera.SetParallelProjection(True);camera.SetParallelScale(1.5)
    scene.ResetCameraClippingRange();window.Render()
    path=tmp_path/'hole.png'
    export_png(path,window,PngSettings(480,480,2),mesh_items=draw._keepalive)
    pixels=np.asarray(Image.open(path).convert('RGB'))
    assert np.all(pixels[220:260,220:260]>245)
    assert area(draw.field_actors[0].GetMapper().GetInput())==pytest.approx(3.)
    # A white specular reflection can brighten an intact blue patch. Compare
    # with the same illuminated plane to test the removed geometry directly.
    draw.clear()
    draw.options.volume_hidden_regions=[]
    draw._volume(volume)
    control_path=tmp_path/'uncut.png'
    export_png(control_path,window,PngSettings(480,480,2),mesh_items=draw._keepalive)
    control=np.asarray(Image.open(control_path).convert('RGB')).astype(int)
    np.testing.assert_allclose(pixels[110:130,110:130], control[110:130,110:130], atol=2)
    uncut_center=control[220:260,220:260]
    assert np.mean(uncut_center[:,:,2]-uncut_center[:,:,0])>20
    assert area(draw.field_actors[0].GetMapper().GetInput())==pytest.approx(4.)
    window.Finalize()
