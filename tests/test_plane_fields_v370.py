"""Analytical arbitrary-plane sampling, complete extents and native rendering."""
from copy import deepcopy
import numpy as np
import pytest
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkRenderer
from lele.core import Frame,Volume
from lele.crystal_planes import default_plane,miller_plane,plane_polygon,validate_planes
from lele.plane_field import (fitted_plane_polygon,field_covered_polygon,plane_grid,
                              plane_color_limits,validate_plane_style)
from lele.plane_field_rendering import sampled_plane_mesh
from lele.renderer import MoleculeRenderer
from lele.selection_geometry import fit_selection_plane
from lele.render_options import RenderOptions


def linear_volume():
    basis=np.array([[.16,.03,0],[0,.15,.02],[.03,0,.2]])
    shape=(25,26,21);origin=np.array([-.4,.3,-.2])
    points=np.moveaxis(np.indices(shape),0,-1)@basis+origin
    return Volume(points@[.2,-.3,.7]+.15,origin,basis,'Difference density','e/Å³')


def test_new_hkl_is_show_only_with_valid_slice_style():
    p=default_plane();assert p['mode']=='Show only' and p['field']
    assert validate_planes([p])[0]['field_resolution']==256
    with pytest.raises(ValueError,match='color limits'):
        validate_planes([{**p,'field_range':[1,-1]}])
    with pytest.raises(ValueError,match='resolution'):
        validate_plane_style({'field_resolution':1})


def test_oblique_analytic_scalar_samples_and_clipped_domain():
    volume=linear_volume();normal=np.array([.3,.7,.4]);normal/=np.linalg.norm(normal)
    origin=volume.origin+np.array([12,12,10])@volume.voxel_vectors
    polygon=plane_polygon(np.eye(3)*100,normal,origin,bounds=((-1,1),)*3)
    covered=field_covered_polygon(polygon,volume)
    assert len(covered)>=3
    mesh,reduced=sampled_plane_mesh(volume,polygon,normal,64)
    xyz=vtk_to_numpy(mesh.GetPoints().GetData());values=vtk_to_numpy(mesh.GetPointData().GetScalars())
    np.testing.assert_allclose(values,xyz@[.2,-.3,.7]+.15,atol=1e-6)
    np.testing.assert_allclose((xyz-origin)@normal,0,atol=1e-7)
    index=(xyz-volume.origin)@np.linalg.inv(volume.voxel_vectors)
    assert np.min(index)>=-2e-5 and np.all(index<=np.array(volume.data.shape)-1+2e-5)
    assert len(xyz)>100


def test_periodic_slice_repeats_across_boundary_without_modifying_grid():
    n=12;cell=np.array([[3.,0,0],[.8,3.,0],[.2,.4,3.]])
    data=np.broadcast_to(np.cos(2*np.pi*np.arange(n)[:,None,None]/n),(n,n,n)).copy()
    volume=Volume(data,[0,0,0],cell/n,'difference','e/Å³',True)
    original=volume.data.copy()
    plane=miller_plane(cell,(0,0,1),.4)
    polygon=plane_polygon(cell,plane.normal,plane.origin,bounds=((-1,2),(0,1),(0,1)))
    mesh,_=sampled_plane_mesh(volume,polygon,plane.normal)
    xyz=vtk_to_numpy(mesh.GetPoints().GetData());values=vtk_to_numpy(mesh.GetPointData().GetScalars())
    fractional=xyz@np.linalg.inv(cell)
    assert fractional[:,0].min()==pytest.approx(-1,abs=1e-6)
    assert fractional[:,0].max()==pytest.approx(2,abs=1e-6)
    from lele.field_mapping import sample_field
    np.testing.assert_allclose(values,sample_field(volume,xyz+cell[0]),atol=1e-6)
    np.testing.assert_array_equal(volume.data,original)


def test_fitted_extent_is_whole_skew_cell_and_expanded_boundary():
    cell=np.array([[6,0,0],[1.8,7,0],[.7,.2,8.]])
    f=Frame(['H']*3,np.array([[.2,.2,.5],[.25,.2,.5],[.2,.25,.5]])@cell,cell,(True,)*3)
    fit=fit_selection_plane(f,range(3))
    polygon=fitted_plane_polygon(f,fit,bounds=((-1,2),(0,2),(0,1)))
    frac=polygon@np.linalg.inv(cell)
    np.testing.assert_allclose([frac[:,0].min(),frac[:,0].max()],[-1,2],atol=1e-12)
    np.testing.assert_allclose([frac[:,1].min(),frac[:,1].max()],[0,2],atol=1e-12)
    np.testing.assert_allclose(frac[:,2],.5,atol=1e-12)
    assert np.ptp(polygon[:,0])>5*np.ptp(fit.corners[:,0])


def test_isolated_fit_fills_field_box_and_transforms_correctly():
    volume=linear_volume()
    source=Frame(['H']*3,volume.origin+np.array([[3,3,10],[4,3,10],[3,4,10]])@volume.voxel_vectors)
    fit=fit_selection_plane(source,range(3))
    polygon=fitted_plane_polygon(source,fit,volume=volume)
    index=(polygon-volume.origin)@np.linalg.inv(volume.voxel_vectors)
    np.testing.assert_allclose(index[:,2],10,atol=1e-10)
    np.testing.assert_allclose([index[:,0].min(),index[:,0].max()],[0,24],atol=1e-10)
    rotation=np.array([[0,1.,0],[-1.,0,0],[0,0,1.]])
    translation=np.array([2.,-1.,3.])
    frame=source.clone();frame.positions=source.positions@rotation+translation
    shifted=Volume(volume.data,volume.origin@rotation+translation,volume.voxel_vectors@rotation)
    actual=fitted_plane_polygon(frame,fit,volume=shifted,rotation=rotation,translation=translation)
    # Polygon order may start at a different vertex after a rotation.
    for point in polygon@rotation+translation:assert np.min(np.linalg.norm(actual-point,axis=1))<1e-9


def test_none_isosurfaces_still_renders_hkl_colors_contours_and_opacity():
    volume=linear_volume();cell=(np.array(volume.data.shape)-1)[:,None]*volume.voxel_vectors
    f=Frame(['H'],[volume.origin+[.3,.3,.3]@cell],cell,(True,)*3)
    renderer=MoleculeRenderer(vtkRenderer());renderer.options=RenderOptions(axes_position='Off',volume_signs='None',show_volume=False,
        lattice_planes=[{**default_plane(),'offset':.5,'opacity':.7,'field_contours':True}])
    renderer.set_scene(f,volume)
    assert not renderer.field_actors
    assert len(renderer.plane_field_actors)==len(renderer.plane_field_bars)==1
    assert len(renderer.plane_contour_actors)==1
    actor=renderer.plane_field_actors[0]
    assert actor.GetProperty().GetOpacity()==pytest.approx(.7)
    assert 'e/Å³' in renderer.plane_field_bars[0].GetTitle()
    data=actor.GetMapper().GetInput();xyz=vtk_to_numpy(data.GetPoints().GetData())
    np.testing.assert_allclose(vtk_to_numpy(data.GetPointData().GetScalars()),xyz@[.2,-.3,.7]+.15,atol=1e-6)
    before=deepcopy(volume.data)
    renderer.options.lattice_planes[0]['opacity']=0;renderer.set_scene(f,volume)
    assert not renderer.plane_field_actors and not renderer.lattice_plane_actors
    np.testing.assert_array_equal(volume.data,before)


def test_elf_defaults_zero_one_and_fixed_limits_are_exact():
    volume=Volume(np.zeros((2,2,2)),[0,0,0],np.eye(3),'ELF','dimensionless')
    style=validate_plane_style({})
    assert plane_color_limits(volume,[.2,.8],style)==('Viridis',(0.,1.))
    style=validate_plane_style({'field_range':[-.3,.6],'field_palette':'Blue-white-red'})
    assert plane_color_limits(volume,[.2,.8],style)==('Blue-white-red',(-.3,.6))


def test_resolution_reduces_only_grid_and_source_stays_unchanged():
    volume=linear_volume();polygon=plane_polygon(np.eye(3)*100,[0,0,1],[0,0,1],bounds=((-1,1),)*3)
    original=volume.data.copy()
    _,_,_,count,reduced=plane_grid(polygon,[0,0,1],volume,16)
    assert count==(16,16) and reduced
    np.testing.assert_array_equal(original,volume.data)


def test_fitted_renderer_full_field_extent_with_hidden_isosurfaces():
    volume=linear_volume();frame=Frame(['H']*3,volume.origin+np.array([[3,3,10],[4,3,10],[3,4,10]])@volume.voxel_vectors)
    fit=fit_selection_plane(frame,range(3))
    renderer=MoleculeRenderer(vtkRenderer());renderer.options=RenderOptions(axes_position='Off',volume_signs='None',
        fitted_plane_style={'opacity':.85,'field_contours':True})
    renderer.fitted_plane=fit;renderer.set_scene(frame,volume)
    assert not renderer.field_actors and len(renderer.plane_field_actors)==1
    data=renderer.plane_field_actors[0].GetMapper().GetInput()
    xyz=vtk_to_numpy(data.GetPoints().GetData());index=(xyz-volume.origin)@np.linalg.inv(volume.voxel_vectors)
    np.testing.assert_allclose([index[:,0].min(),index[:,0].max()],[0,24],atol=2e-5)
    np.testing.assert_allclose([index[:,1].min(),index[:,1].max()],[0,25],atol=2e-5)
    np.testing.assert_allclose(index[:,2],10,atol=2e-5)
    assert renderer.plane_field_actors[0].GetProperty().GetOpacity()==pytest.approx(.85)


from test_periodic_fragment_ui_v171 import gui


def test_hkl_slice_controls_update_records_and_fitted_controls_are_compact(gui):
    from lele.crystal_panel import LatticePlanePanel
    panel=LatticePlanePanel();panel.add_plane()
    assert panel.mode.currentText()=='Show only'
    panel.field_controls.palette.setCurrentText('Viridis');panel.field_controls.fixed.setChecked(True)
    panel.field_controls.minimum.setValue(0);panel.field_controls.maximum.setValue(1)
    panel.field_controls.contours.setChecked(True);panel.opacity.setValue(.8)
    value=panel.selected_plane()
    assert value['field_palette']=='Viridis' and value['field_range']==[0,1]
    assert value['field_contours'] and value['opacity']==.8
    controls=gui.window.fitted_plane_controls
    assert controls.palette.width()==90 and controls.minimum.width()==140
    controls.opacity.setValue(.75)
    assert gui.window.render_options.fitted_plane_style['opacity']==.75
    controls.minimum.lineEdit().setText('-1e-5');controls.minimum.interpretText()
    assert controls.minimum.value()==pytest.approx(-1e-5)


def test_slice_cache_drops_previous_source_when_field_changes():
    volume=linear_volume();frame=Frame(['H']*3,volume.origin+np.array([[3,3,10],[4,3,10],[3,4,10]])@volume.voxel_vectors)
    renderer=MoleculeRenderer(vtkRenderer());renderer.options=RenderOptions(axes_position='Off',show_volume=False)
    renderer.fitted_plane=fit_selection_plane(frame,range(3));renderer.set_scene(frame,volume)
    original=vtk_to_numpy(renderer.plane_field_actors[0].GetMapper().GetInput().GetPointData().GetScalars()).copy()
    doubled=Volume(volume.data*2,volume.origin,volume.voxel_vectors)
    renderer.set_scene(frame,doubled)
    assert renderer._plane_field_source is doubled.data
    actual=vtk_to_numpy(renderer.plane_field_actors[0].GetMapper().GetInput().GetPointData().GetScalars())
    np.testing.assert_allclose(actual,2*original,atol=1e-6)
    assert all(item[0] is doubled.data for item in renderer._plane_field_cache.values())
    renderer.set_scene(frame)
    assert renderer._plane_field_source is None and not renderer._plane_field_cache
