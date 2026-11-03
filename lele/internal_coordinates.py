"""Rigid terminal-fragment edits of a selected distance, angle or dihedral."""
from collections import deque
from dataclasses import dataclass
import numpy as np
from .core import Frame, measure, visible_bonds, canonical_pair
from .fragment import rotation_about_axis


@dataclass
class InternalEdit:
    positions: np.ndarray
    moving: list
    periodic_edges: tuple | None
    hbond_added: dict


def plan_internal_edit(frame, selected, target, cutoff=1.0):
    """Validate first; never mutate a structure when a ring/network blocks it.

    The selected joint is cut only for graph traversal. Ordinary bonds, including
    manual overrides, constrain the moving side; dashed annotations do not.
    Periodic finite fragments are unwrapped before rotation. Image shifts are
    updated along with coordinates, without changing the lattice or connectivity.
    """
    ids=[int(i) for i in selected]
    quantity,_=measure(frame,ids)
    target=float(target)
    if not np.isfinite(target):raise ValueError('Enter a finite target value.')
    if quantity=='distance' and target<=0:raise ValueError('Bond length must be positive.')
    if quantity=='angle' and not 0<=target<=180:raise ValueError('Bond angle must be between 0 and 180 degrees.')
    if quantity=='dihedral' and not -180<=target<=180:raise ValueError('Dihedral must be between -180 and 180 degrees.')
    cut=canonical_pair(*(ids[:2] if len(ids)==2 else ids[1:3]))
    fixed=set(ids[:-1] if len(ids)<4 else ids[:2])
    from .periodic_geometry import periodic_basis,periodic_bonds,normalized_positions
    periodic=periodic_basis(frame) is not None
    if periodic:
        _,floors=normalized_positions(frame)
        edges=[(i,j,tuple(int(x) for x in np.asarray(s)+floors[i]-floors[j]))
               for i,j,s in periodic_bonds(frame,cutoff)]
        if sum(canonical_pair(i,j)==cut for i,j,_ in edges if i!=j)>1:
            raise ValueError('This joint connects multiple periodic images. Its fragment cannot move independently without breaking bonds.')
    else:
        edges=[(i,j,(0,0,0)) for i,j in visible_bonds(frame,cutoff)]
    graph=[[] for _ in frame.symbols]
    for i,j,shift in edges:
        if i!=j and canonical_pair(i,j)==cut:continue
        graph[i].append((j,np.asarray(shift,dtype=int)))
        graph[j].append((i,-np.asarray(shift,dtype=int)))
    shifts={ids[-1]:np.zeros(3,dtype=int)};todo=deque([ids[-1]])
    while todo:
        i=todo.popleft()
        if i in fixed:
            raise ValueError('A ring or another bond path connects the moving fragment to a fixed selected atom. This value cannot be changed without breaking bonds.')
        for j,s in graph[i]:
            wanted=shifts[i]+s
            if j in shifts:
                if not np.array_equal(shifts[j],wanted):
                    raise ValueError('The moving fragment belongs to an infinite periodic bonded network and cannot move independently.')
            else:shifts[j]=wanted;todo.append(j)
    if len(ids)==4 and ids[2] in shifts:
        origin=shifts[ids[2]].copy()
        shifts={i:s-origin for i,s in shifts.items()}
    moving=sorted(shifts)
    positions=frame.positions.copy()
    if periodic:
        for i in moving:positions[i]+=shifts[i]@frame.cell
    probe=Frame(frame.symbols,positions,frame.cell,frame.pbc)
    _,current=measure(probe,ids)
    if quantity=='distance':
        direction=positions[ids[1]]-positions[ids[0]]
        length=float(np.linalg.norm(direction))
        if length<1.e-12:raise ValueError('Coincident atoms do not define a movement direction.')
        positions[moving]+=direction/length*(target-length)
    else:
        if quantity=='angle':
            pivot=positions[ids[1]].copy()
            first=positions[ids[0]]-pivot;last=positions[ids[2]]-pivot
            axis=np.cross(first,last)
            if np.linalg.norm(axis)<1.e-10*np.linalg.norm(first)*np.linalg.norm(last):
                basis=np.eye(3)[int(np.argmin(np.abs(first)))]
                axis=np.cross(first,basis)
            delta=target-current
        else:
            pivot=positions[ids[2]].copy();axis=positions[ids[2]]-positions[ids[1]]
            delta=(target-current+180)%360-180
        rotation=rotation_about_axis(axis,delta)
        positions[moving]=(positions[moving]-pivot)@rotation.T+pivot
        if len(ids)==4 and ids[2] in shifts:positions[ids[2]]=frame.positions[ids[2]]
    _,actual=measure(Frame(frame.symbols,positions,frame.cell,frame.pbc),ids)
    error=(actual-target+180)%360-180 if quantity=='dihedral' else actual-target
    if abs(error)>1.e-5:raise ValueError('The selected geometry does not define a stable edit direction.')
    new_edges=None;hbonds=dict(frame.hbond_added)
    if periodic:
        zero=np.zeros(3,dtype=int)
        new_edges=tuple((i,j,(0,0,0) if i!=j and canonical_pair(i,j)==cut else
            tuple(int(x) for x in np.asarray(s)+shifts.get(i,zero)-shifts.get(j,zero))) for i,j,s in edges)
        hbonds={pair:tuple(int(x) for x in np.asarray(s)+shifts.get(pair[0],zero)-shifts.get(pair[1],zero))
                for pair,s in hbonds.items()}
    return InternalEdit(positions,moving,new_edges,hbonds)
