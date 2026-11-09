import numpy as np
import pytest
from lele.core import Volume
from lele.field_slice import grid_plane_slice


def test_skew_slice_coordinates_and_linear_interpolation():
    indices=np.indices((3,4,5));data=2*indices[0]+3*indices[1]-indices[2]
    basis=np.array([[1.,0.,0.],[.5,2.,0.],[.2,.3,3.]])
    vol=Volume(data,[1,2,3],basis)
    section=grid_plane_slice(vol,2,.375)
    assert section.sample_index==1.5
    np.testing.assert_allclose(section.values,2*indices[0,:,:,0]+3*indices[1,:,:,0]-1.5)
    np.testing.assert_allclose(section.xyz[2,3],vol.origin+2*basis[0]+3*basis[1]+1.5*basis[2])
    np.testing.assert_allclose(section.x, np.indices((3,4))[0]+.5*np.indices((3,4))[1])
    np.testing.assert_allclose(section.y,2*np.indices((3,4))[1])
    np.testing.assert_allclose(section.xyz,section.origin+section.x[...,None]*section.u+section.y[...,None]*section.v)


def test_periodic_boundary_and_stats_do_not_duplicate_edges():
    data=np.arange(24).reshape(2,3,4)
    volume=Volume(data,[0,0,0],np.eye(3),periodic=True)
    start=grid_plane_slice(volume,0,0);end=grid_plane_slice(volume,0,1)
    assert start.values.shape==(4,5)
    np.testing.assert_array_equal(start.values,end.values)
    assert start.mean==pytest.approx(data[0].mean())
    np.testing.assert_allclose(end.origin,[2,0,0])
    mid=grid_plane_slice(volume,0,.75)
    np.testing.assert_allclose(mid.values[:-1,:-1],(data[0]+data[1])/2)


@pytest.mark.parametrize('axis',[0,1,2])
def test_axes_consistent(axis):
    vol=Volume(np.arange(24).reshape(2,3,4),[2,3,4],[[1,.1,0],[0,2,.2],[.3,0,3]])
    section=grid_plane_slice(vol,axis,1)
    np.testing.assert_array_equal(section.values,np.take(vol.data,-1,axis=axis))
    np.testing.assert_allclose(section.xyz,section.origin+section.x[...,None]*section.u+section.y[...,None]*section.v,atol=1e-14)


def test_limits_and_invalid_inputs():
    volume=Volume(np.zeros((2,3,4)),[0,0,0],np.eye(3))
    for fraction in [-.1,1.1,float('nan')]:
        with pytest.raises(ValueError):grid_plane_slice(volume,0,fraction)
    with pytest.raises(ValueError,match='memory'):grid_plane_slice(volume,0,.5,max_points=3)
    with pytest.raises(ValueError):grid_plane_slice(volume,4,.5)
    volume.voxel_vectors[:]=0
    with pytest.raises(ValueError,match='degenerate'):grid_plane_slice(volume,0,.5)


def test_dialog_ranges_and_export(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication,QFileDialog
    from lele.field_slice_dialog import FieldSliceDialog
    app=QApplication.instance() or QApplication([])
    volume=Volume(np.arange(24).reshape(2,3,4),[1,2,3],np.eye(3),label='Test',unit='e/Å³')
    dialog=FieldSliceDialog(volume)
    assert dialog.section is not None
    dialog.contours.setChecked(True)
    dialog.manual_range.setChecked(True)
    dialog.range_min.setText('9');dialog.range_max.setText('1');dialog.redraw()
    assert 'Min < Max' in dialog.note.text()
    dialog.range_min.setText('-1e-3');dialog.range_max.setText('30');dialog.redraw()
    target=tmp_path/'slice.csv'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a: (str(target),''))
    dialog.export_csv()
    text=target.read_text();assert 'x_A,y_A,z_A,value,unit' in text and 'e/Å³' in text
    dialog.close()


def test_atomic_export_cancel_preserves_destination(tmp_path):
    from lele.field_slice import export_slice_csv
    from lele.output_text import output_read_session,LoadCancelled
    volume=Volume(np.zeros((40,40,2)),[0,0,0],np.eye(3))
    section=grid_plane_slice(volume,2,0)
    target=tmp_path/'slice.csv';target.write_text('original')
    calls=[0]
    def cancel():
        calls[0]+=1
        return calls[0]>1
    with output_read_session(cancel,None):
        with pytest.raises(LoadCancelled):export_slice_csv(section,target)
    assert target.read_text()=='original'
    assert list(tmp_path.iterdir())==[target]


def test_atomic_export_write_error_preserves_destination(tmp_path,monkeypatch):
    import os
    from lele.field_slice import export_slice_csv
    volume=Volume(np.zeros((2,2,2)),[0,0,0],np.eye(3));section=grid_plane_slice(volume)
    target=tmp_path/'slice.csv';target.write_text('original')
    def fail(*a):raise OSError('disk full')
    monkeypatch.setattr(os,'replace',fail)
    with pytest.raises(OSError):export_slice_csv(section,target)
    assert target.read_text()=='original';assert list(tmp_path.iterdir())==[target]


def test_bounded_display_preserves_exact_section():
    from lele.field_slice import display_slice_samples
    volume=Volume(np.arange(210*220*2).reshape(210,220,2),[0,0,0],np.eye(3))
    section=grid_plane_slice(volume,2,0)
    x,y,data,reduced=display_slice_samples(section)
    assert reduced and data.shape==(201,201)
    assert section.values.shape==(210,220)
    assert x[-1,-1]==209 and y[-1,-1]==219
    assert data[-1,-1]==section.values[-1,-1]
