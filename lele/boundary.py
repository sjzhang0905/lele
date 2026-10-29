"""Display complete translated unit cells without changing the source structure."""
from dataclasses import dataclass
from itertools import product
import math
import numpy as np
from .core import Frame
from .periodic_geometry import periodic_basis,normalized_positions,periodic_bonds

MAX_DISPLAY_ATOMS=50_000
MAX_CANDIDATE_TILES=4096

@dataclass
class BoundaryView:
    frame: Frame
    source_indices: np.ndarray
    shifts: np.ndarray
    bonds: list
    cell_lines: list
    tiles: tuple

    def transformed(self, rotation, translation):
        """Apply one display rigid transform to atoms, cell and every edge."""
        display = self.frame.clone()
        display.positions = self.frame.positions @ rotation + translation
        display.cell = self.frame.cell @ rotation
        lines = [(p @ rotation + translation, q @ rotation + translation) for p, q in self.cell_lines]
        return BoundaryView(display, self.source_indices, self.shifts, self.bonds, lines, self.tiles)


def boundary_view(frame,bounds,cutoff=1.18):
    """Repeat full cells in integer [start, end) ranges, with shared face edges.

    Each copy has every source atom. The displayed frame retains the original
    cell vectors; it is not a larger computational supercell. Copies keep their
    source atom IDs for picking and appearance controls.
    """
    values=np.asarray(bounds,float)
    if values.shape!=(3,2) or not np.isfinite(values).all() or np.any(values[:,1]<=values[:,0]):
        raise ValueError('Each maximum must be greater than its minimum.')
    if not np.all(values==np.rint(values)):
        raise ValueError('Use integer cell ranges; the start is included and the end is excluded.')
    limits=values.astype(int)
    cell=periodic_basis(frame)
    if cell is None:raise ValueError('Boundary needs a valid periodic unit cell.')
    ranges=[range(int(lo),int(hi)) for lo,hi in limits]
    count=math.prod(len(r) for r in ranges)
    if count>MAX_CANDIDATE_TILES:raise ValueError('Boundary covers too many cells.')
    n=len(frame.symbols)
    if count*n>MAX_DISPLAY_ATOMS:raise ValueError('Boundary exceeds 50,000 display atoms.')
    tiles=tuple(product(*ranges))
    base,_=normalized_positions(frame)
    offsets=np.asarray(tiles,float)@cell
    positions=(base[None,:,:]+offsets[:,None,:]).reshape(-1,3)
    sources=np.tile(np.arange(n,dtype=int),count)
    shifts=np.repeat(np.asarray(tiles,int),n,axis=0)
    tile_indices={tile:k for k,tile in enumerate(tiles)}
    periodic_edges=periodic_bonds(frame,cutoff)
    edges=set()
    for k,tile in enumerate(tiles):
        for a,b,shift in periodic_edges:
            other=tile_indices.get(tuple(np.asarray(tile)+shift))
            if other is not None:
                pair=tuple(sorted((k*n+a,other*n+b)))
                if pair[0]!=pair[1]:edges.add(pair)
    styles={i:frame.atom_appearance[source] for i,source in enumerate(sources) if source in frame.atom_appearance}
    display=Frame([frame.symbols[i] for i in sources],positions,
                  frame.cell.copy(),(False,False,False),info=frame.info,atom_appearance=styles)
    from .hydrogen_bonds import repeat_hydrogen_bonds
    repeat_hydrogen_bonds(frame, display, tiles)
    # Keep each edge one original cell-vector long. Deduplicate shared edges
    # in lattice coordinates, so skew cells retain all internal boundaries.
    grid_edges=set()
    for tile in tiles:
        for axis in range(3):
            other=[k for k in range(3) if k!=axis]
            for u,v in product((0,1),repeat=2):
                p=list(tile);p[other[0]]+=u;p[other[1]]+=v
                q=p.copy();q[axis]+=1
                grid_edges.add((tuple(p),tuple(q)))
    lines=[(np.asarray(p)@cell,np.asarray(q)@cell) for p,q in sorted(grid_edges)]
    return BoundaryView(display,sources,shifts.reshape(-1,3),sorted(edges),lines,tiles)
