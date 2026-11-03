"""Slab vacuum measured between outermost atomic planes along a cell normal."""
import numpy as np


def slab_vacuum(frame,axis=None):
    if not any(frame.pbc) or abs(np.linalg.det(frame.cell))<1.e-9 or not frame.symbols:
        raise ValueError('Vacuum adjustment needs atoms and a valid periodic cell.')
    if axis is None:
        previous=frame.info.get('vacuum_adjustment')
        if previous is not None:
            confirmed=slab_vacuum(frame,previous['axis'])
            if confirmed.get('surface_source')=='confirmed':return confirmed
        candidates=[slab_vacuum(frame,i) for i in range(3)]
        return max(candidates,key=lambda x:x['gap'])
    axis=int(axis)
    if axis not in (0,1,2):raise ValueError('Choose a, b or c as the vacuum direction.')
    others=[i for i in range(3) if i!=axis]
    normal=np.cross(frame.cell[others[0]],frame.cell[others[1]])
    normal/=np.linalg.norm(normal)
    if normal@frame.cell[axis]<0:normal=-normal
    from .site_occupancy import site_species
    active=[i for i in range(len(frame.symbols)) if sum(site_species(frame,i).values())>1.e-12]
    if not active:raise ValueError('No occupied atomic sites are available to locate slab surfaces.')
    height=float(normal@frame.cell[axis]);raw=frame.positions[active]@normal
    previous=frame.info.get('vacuum_adjustment',{})
    offsets=np.sort(raw-raw.min())
    stored=np.asarray(previous.get('slab_surface_offsets',[]),dtype=float)
    matches=(stored.shape==offsets.shape and np.allclose(stored,offsets,atol=1.e-7,rtol=0))
    if 'slab_surface_offsets' not in previous and previous.get('axis')==axis:
        # v2.12.0 projects recorded the confirmed thickness and final gap.
        # Reuse that evidence only while both still match the actual geometry.
        matches=(np.isclose(np.ptp(raw),previous.get('thickness',np.nan),atol=1.e-7,rtol=0)
                 and np.isclose(height-np.ptp(raw),previous.get('new_gap',np.nan),atol=1.e-7,rtol=0))
    if previous.get('axis')==axis and matches:
        thickness=float(np.ptp(raw));gap=height-thickness
        if gap>=-1.e-8:
            return dict(axis=axis,normal=normal,height=height,gap=max(0.,gap),thickness=thickness,
                        lower=float(raw.min()),upper=float(raw.max()),split=False,surface_source='confirmed')
    wrapped=np.mod(raw,height);values=np.sort(wrapped)
    gaps=np.diff(np.r_[values,values[0]+height]);k=int(np.argmax(gaps))
    gap=float(gaps[k]);thickness=height-gap
    # Coordinates split across the periodic boundary require image changes to
    # keep the same slab; those cannot be hidden in a fixed-coordinate edit.
    split=float(np.ptp(raw))>thickness+1.e-6
    lower=float(values[(k+1)%len(values)]);upper=lower+thickness
    return dict(axis=axis,normal=normal,height=height,gap=gap,thickness=thickness,
                lower=lower,upper=upper,split=split)


def change_vacuum(frame,gap,axis=None):
    result=slab_vacuum(frame,axis);gap=float(gap)
    if not np.isfinite(gap) or gap<0:raise ValueError('Vacuum spacing must be a finite non-negative value.')
    if abs(gap-result['gap'])<=1.e-10:return {**result,'changed':False}
    if result['split']:
        raise ValueError('The slab crosses the cell boundary. Keeping every Cartesian coordinate fixed cannot preserve this slab while changing its vacuum; first choose contiguous periodic representatives explicitly.')
    if result['thickness']+gap<1.e-6:raise ValueError('The requested vacuum would make the cell singular.')
    cell=frame.cell.copy();cell[result['axis']]+=(gap-result['gap'])*result['normal']
    frame.cell=cell
    frame.energy_ev=None
    for key in ('optimization_converged','energy_source','qe_total_energy_ry','qe_energy_source_line',
                'qe_forces_ev_ang','cartesian_max_force_ev_ang','cartesian_rms_force_ev_ang','coordinate_reorientation','plane_alignment'):
        frame.info.pop(key,None)
    frame.info['vacuum_adjustment']={**{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in result.items()},'new_gap':gap}
    from .site_occupancy import site_species
    active=[i for i in range(len(frame.symbols)) if sum(site_species(frame,i).values())>1.e-12]
    projections=frame.positions[active]@result['normal']
    frame.info['vacuum_adjustment']['slab_surface_offsets']=np.sort(projections-projections.min()).tolist()
    return {**result,'changed':True}
