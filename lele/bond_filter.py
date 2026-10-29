"""Reject nearly collinear long automatic edges shielded by two shorter bonds."""
import numpy as np


def prune_occluded(positions, edges, cell=None):
    lattice = np.zeros((3,3)) if cell is None else np.asarray(cell)
    adjacency = {}
    directed = set()
    for a,b,shift in edges:
        shift=tuple(shift); reverse=tuple(-v for v in shift)
        adjacency.setdefault(a,[]).append((b,shift))
        adjacency.setdefault(b,[]).append((a,reverse))
        directed.update(((a,b,shift),(b,a,reverse)))
    result=[]
    for a,b,shift in edges:
        p=positions[a];q=positions[b]+np.asarray(shift)@lattice
        length=np.linalg.norm(q-p);blocked=False
        for k,t in adjacency.get(a,[]):
            remaining=tuple(np.asarray(shift)-t)
            if (k,b,remaining) not in directed:continue
            middle=positions[k]+np.asarray(t)@lattice
            left=np.linalg.norm(middle-p);right=np.linalg.norm(q-middle)
            if .2 < left < .85*length and .2 < right < .85*length and left+right < 1.08*length:
                blocked=True;break
        if not blocked:result.append((a,b,tuple(shift)))
    return sorted(result)
