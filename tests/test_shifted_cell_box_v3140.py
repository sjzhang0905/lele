"""Shifted replica boxes clip fields and plane extents without shifting data."""
from unittest.mock import patch

import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import Frame,Volume
from lele.crystal_settings import default_plane
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.selection_geometry import fit_selection_plane
from lele.supercell import make_supercell


def expanded():
    cell=np.array([[4.,0.,0.],[.8,6.,0.],[.4,.3,7.]])
    source=Frame(['Si']*3,np.array([[.1,.1,.4],[.2,.1,.4],[.1,.2,.4]])@cell,cell,(True,)*3)
    return make_supercell(source,(3,1,1),growth='alternating')


@pytest.mark.parametrize('preserve', [True,False])
def test_plane_polygons_cover_actual_shifted_or_legacy_box(preserve):
    frame=expanded();draw=MoleculeRenderer(vtkRenderer())
    draw.options=RenderOptions(axes_position='Off',show_volume=False,boundary_preserve_origin=preserve,
        lattice_planes=[{**default_plane(),'hkl':(0,0,1),'offset':.4}])
    draw.fitted_plane=fit_selection_plane(frame,range(3))
    with patch.object(draw,'_render_display_plane',return_value=None) as capture:
        draw.set_scene(frame)
    assert len(capture.call_args_list)==2
    planes={call.args[3]:np.asarray(call.args[0]) for call in capture.call_args_list}
    section=planes['HKL (0 0 1)']
    fractional=section@np.linalg.inv(frame.cell)
    np.testing.assert_allclose(fractional.min(axis=0),[-1/3 if preserve else 0.,0.,.4],atol=1.e-10)
    np.testing.assert_allclose(fractional.max(axis=0),[2/3 if preserve else 1.,1.,.4],atol=1.e-10)
    rectangle=planes['Fitted plane']
    from test_plane_fields_v370 import assert_covers_projection
    assert_covers_projection(rectangle,draw.fitted_plane,section)
    # The margin is symmetric about the shifted display box in its plane.
    box_center=np.array([1/6 if preserve else .5,.5,.5])@frame.cell
    normal=draw.fitted_plane.normal
    delta=rectangle.mean(axis=0)-box_center
    np.testing.assert_allclose(delta-(delta@normal)*normal,0.,atol=1.e-10)


@pytest.mark.parametrize('preserve', [True,False])
def test_periodic_field_clipping_planes_follow_shifted_box(preserve):
    frame=expanded();shape=np.array([12,6,7])
    data=np.broadcast_to(np.sin(np.arange(shape[0])*2*np.pi/shape[0])[:,None,None],shape).copy()
    field=Volume(data,np.zeros(3),frame.cell/shape[:,None],periodic=True)
    before=field.data.copy()
    draw=MoleculeRenderer(vtkRenderer())
    draw.options=RenderOptions(axes_position='Off',volume_signs='Positive',volume_iso=.25,
                              boundary_preserve_origin=preserve)
    draw.set_scene(frame,field)
    assert draw.field_actors
    expected=np.array([-1/3 if preserve else 0.,0.,0.])
    inverse=np.linalg.inv(frame.cell)
    for actor in draw.field_actors:
        planes=actor.GetMapper().GetClippingPlanes()
        assert planes.GetNumberOfItems()==6
        for axis in range(3):
            for side in range(2):
                origin=np.asarray(planes.GetItem(2*axis+side).GetOrigin())@inverse
                target=expected.copy();target[axis]+=side
                np.testing.assert_allclose(origin,target,atol=1.e-10)
    np.testing.assert_array_equal(field.data,before)
