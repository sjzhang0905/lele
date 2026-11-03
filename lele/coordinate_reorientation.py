"""Rigid coordinate changes of an entire crystal, including periodic images.

Cell vectors and positions are rows: r_new = r_old @ R.T + t. R is a proper
Cartesian column-vector rotation; lattice-vector indices never change.
"""
import numpy as np
from .periodic_geometry import minimum_image,periodic_basis
from .output_text import load_progress,check_load_cancelled


def proper_rotation(matrix):
    rotation=np.asarray(matrix,dtype=float)
    if rotation.shape!=(3,3) or not np.isfinite(rotation).all():
        raise ValueError('Enter a finite 3 × 3 rotation matrix.')
    if (not np.allclose(rotation@rotation.T,np.eye(3),atol=1.e-8,rtol=0)
            or not np.isclose(np.linalg.det(rotation),1.,atol=1.e-8,rtol=0)):
        raise ValueError('The matrix must be orthogonal with determinant +1; scaling, shear and reflection are not rotations.')
    return rotation.copy()


def local_axis_rotation(frame,origin,x_atom,z_atom,*,nearest_images=True):
    """Z is exact; X is the X-hint projected perpendicular to Z (script convention)."""
    ids=(origin,x_atom,z_atom)
    if len(set(ids))!=3 or any(i<0 or i>=len(frame.symbols) for i in ids):
        raise ValueError('Choose three different atoms: origin, X hint, then Z direction.')
    x=frame.positions[x_atom]-frame.positions[origin]
    z=frame.positions[z_atom]-frame.positions[origin]
    shifts=[]
    for vector in (x,z):
        _,shift=minimum_image(vector,frame) if nearest_images else (vector,(0,0,0))
        shifts.append(shift)
    x=x+np.asarray(shifts[0])@frame.cell
    z=z+np.asarray(shifts[1])@frame.cell
    nx,nz=np.linalg.norm(x),np.linalg.norm(z)
    if min(nx,nz)<1.e-10:raise ValueError('Coincident atoms or periodic images cannot define an axis.')
    angle=float(np.degrees(np.arccos(np.clip(x@z/(nx*nz),-1.,1.))))
    z=z/nz;x=x-(x@z)*z
    if np.linalg.norm(x)<1.e-8*nx:
        raise ValueError('The X and Z directions are parallel; choose a non-collinear X hint.')
    x=x/np.linalg.norm(x);y=np.cross(z,x);y=y/np.linalg.norm(y);x=np.cross(y,z)
    rotation=proper_rotation(np.stack([x,y,z]))
    return rotation,{'selection':list(ids),'raw_x_z_angle_deg':angle,
                     'axis_image_shifts':[list(s) for s in shifts],'axes_convention':'Z exact; X projected perpendicular to Z'}


def transform_complete_frame(frame,rotation,translation,*,nearest_origin=None,volume=None,details=None):
    """Validate and prepare before mutation; preserve metric, image bonds and PBC.

    nearest_origin selects each atom's closest periodic representative around a
    point in the OLD Cartesian frame. It changes image representatives only.
    """
    rotation=proper_rotation(rotation)
    translation=np.asarray(translation,dtype=float)
    if translation.shape!=(3,) or not np.isfinite(translation).all():
        raise ValueError('Translation must be a finite Cartesian triplet.')
    cell=frame.cell.copy();positions=frame.positions.copy()
    shifts=np.zeros((len(frame.symbols),3),dtype=int)
    if nearest_origin is not None and periodic_basis(frame) is not None:
        origin=np.asarray(nearest_origin,dtype=float)
        if origin.shape!=(3,) or not np.isfinite(origin).all():raise ValueError('Invalid image center.')
        report=load_progress('Crystal reorientation: nearest periodic images',len(positions))
        for i,point in enumerate(positions):
            if i%256==0:report(i);check_load_cancelled()
            vector,shift=minimum_image(point-origin,frame)
            positions[i]=origin+vector;shifts[i]=shift
        report(len(positions));check_load_cancelled()
    new_positions=positions@rotation.T+translation
    new_cell=cell@rotation.T
    edges=frame.periodic_bond_snapshot
    if edges is not None:
        edges=tuple((i,j,tuple(int(v) for v in np.asarray(s)+shifts[i]-shifts[j])) for i,j,s in edges)
    hbonds={pair:tuple(int(v) for v in np.asarray(s)+shifts[pair[0]]-shifts[pair[1]])
            for pair,s in frame.hbond_added.items()}
    record={'rotation':rotation.tolist(),'row_rotation':rotation.T.tolist(),
            'translation':translation.tolist(),'cell_rotated':True,
            'nearest_images':nearest_origin is not None and periodic_basis(frame) is not None,
            'image_shifts':shifts.tolist(),'convention':'r_new = (r_old + image_shift @ cell_old) @ R.T + translation'}
    if details:record.update(details)
    frame.positions=new_positions;frame.cell=new_cell
    frame.periodic_bond_snapshot=edges;frame.hbond_added=hbonds
    if edges is not None and np.any(shifts):
        frame.bond_snapshot=frozenset((i,j) for i,j,s in edges if i!=j and not any(s))
    forces=frame.info.get('qe_forces_ev_ang')
    if forces is not None:
        forces=np.asarray(forces)@rotation.T
        frame.info['qe_forces_ev_ang']=forces
        if forces.size:
            frame.info['cartesian_max_force_ev_ang']=float(np.abs(forces).max())
            frame.info['cartesian_rms_force_ev_ang']=float(np.sqrt(np.mean(forces**2)))
    elif not np.allclose(rotation,np.eye(3),atol=1.e-12,rtol=0):
        # Component maxima cannot be rotated without the original force vectors.
        frame.info.pop('cartesian_max_force_ev_ang',None)
    frame.info.pop('plane_alignment',None)
    frame.info['coordinate_reorientation']=record
    if volume is not None:
        volume.origin=volume.origin@rotation.T+translation
        volume.voxel_vectors=volume.voxel_vectors@rotation.T
    return record


def reorient_from_atoms(frame,origin,x_atom,z_atom,*,nearest_images=True,volume=None):
    rotation,details=local_axis_rotation(frame,origin,x_atom,z_atom,nearest_images=nearest_images)
    center=frame.positions[origin].copy()
    return transform_complete_frame(frame,rotation,-center@rotation.T,
        nearest_origin=center if nearest_images else None,volume=volume,details=details)
