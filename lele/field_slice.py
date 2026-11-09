"""Grid-plane sections in physical coordinates, including oblique voxel bases.

These are planes parallel to two grid vectors, not arbitrary Cartesian planes.
Periodic end points are duplicated only for display; slice statistics exclude them.
"""
from dataclasses import dataclass
import numpy as np


@dataclass
class FieldSlice:
    values: np.ndarray
    x: np.ndarray
    y: np.ndarray
    origin: np.ndarray
    u: np.ndarray
    v: np.ndarray
    xyz: np.ndarray
    axis: int
    fraction: float
    sample_index: float
    minimum: float
    maximum: float
    mean: float


def grid_plane_slice(volume, axis=2, fraction=.5, *, max_points=2_000_000):
    """Linear interpolation between grid planes; distances are Angstrom.

    Fraction 0..1 spans one full cell for periodic data, or first to last sample
    for nonperiodic data. Only the normal grid index is interpolated. No spline
    interpolation, smoothing, density normalization or unit conversion occurs.
    """
    if axis not in (0,1,2): raise ValueError('Slice axis must be 0, 1 or 2.')
    if not np.isfinite(fraction) or not 0 <= fraction <= 1:
        raise ValueError('Slice fraction must be between 0 and 1.')
    data=np.asarray(volume.data);basis=np.asarray(volume.voxel_vectors,float)
    if data.ndim != 3 or min(data.shape)<2: raise ValueError('A 3D grid is required.')
    if not np.isfinite(basis).all() or not np.isfinite(volume.origin).all():
        raise ValueError('Non-finite grid geometry.')
    axes=[i for i in range(3) if i!=axis]
    shape=[data.shape[i]+int(volume.periodic) for i in axes]
    if shape[0]*shape[1]>max_points: raise ValueError('Slice exceeds the display memory limit.')
    a,b=basis[axes];length=np.linalg.norm(a);cross=np.cross(a,b);area=np.linalg.norm(cross)
    if length<1e-12 or area<1e-12: raise ValueError('The slice grid vectors are degenerate.')
    u=a/length;v=np.cross(cross/area,u)
    coordinate=float(fraction)*(data.shape[axis] if volume.periodic else data.shape[axis]-1)
    low=int(np.floor(coordinate));weight=coordinate-low
    if volume.periodic:
        left=low%data.shape[axis];right=(low+1)%data.shape[axis]
    else:
        left=min(low,data.shape[axis]-1);right=min(left+1,data.shape[axis]-1)
    values=(1-weight)*np.take(data,left,axis=axis)+weight*np.take(data,right,axis=axis)
    if not np.isfinite(values).all(): raise ValueError('Slice contains non-finite values.')
    minimum=float(values.min());maximum=float(values.max());mean=float(values.mean(dtype=np.float64))
    if volume.periodic: values=np.pad(values,((0,1),(0,1)),mode='wrap')
    i,j=np.meshgrid(np.arange(shape[0]),np.arange(shape[1]),indexing='ij')
    x=i*length+j*np.dot(b,u);y=j*np.dot(b,v)
    origin=np.asarray(volume.origin,float)+coordinate*basis[axis]
    xyz=origin+i[...,None]*a+j[...,None]*b
    return FieldSlice(values,x,y,origin,u,v,xyz,axis,float(fraction),coordinate,minimum,maximum,mean)


def export_slice_csv(section, filename, unit='source-file units'):
    """Atomically write exact slice samples; cancellation preserves destination."""
    import csv
    import os
    import tempfile
    from pathlib import Path
    from .output_text import check_load_cancelled, load_progress
    path=Path(filename)
    temporary=None
    try:
        report=load_progress('Exporting slice samples',section.values.size)
        with tempfile.NamedTemporaryFile(mode='w',newline='',encoding='utf-8',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as stream:
            temporary=Path(stream.name)
            writer=csv.writer(stream);writer.writerow(['x_A','y_A','z_A','value','unit'])
            for index,(xyz,value) in enumerate(zip(section.xyz.reshape(-1,3),section.values.ravel())):
                if index%1024==0:check_load_cancelled();report(index)
                writer.writerow([*map(float,xyz),float(value),unit])
            stream.flush();os.fsync(stream.fileno())
        check_load_cancelled()
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:
            try:temporary.unlink()
            except FileNotFoundError:pass


def display_slice_samples(section, max_axis=201):
    """Bound plotting cost only; return selected samples and whether reduced."""
    if max_axis<2:raise ValueError('At least two display points per axis are required.')
    shape=section.values.shape
    axes=[np.unique(np.linspace(0,n-1,min(n,max_axis)).round().astype(int)) for n in shape]
    selection=np.ix_(*axes)
    return section.x[selection],section.y[selection],section.values[selection],any(n>max_axis for n in shape)
