"""Display complete translated unit cells without changing the source structure."""
from dataclasses import dataclass
from itertools import product
import math
import numpy as np
from .core import Frame, unit_cell_edges
from .periodic_geometry import periodic_basis,normalized_positions,periodic_bonds

MAX_DISPLAY_ATOMS=50_000
MAX_CANDIDATE_TILES=4096
FACE_TOLERANCE=1.e-8

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


def boundary_view(frame,bounds,cutoff=1.0):
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
    phonon=frame.info.get('_qe_phonon_preview')
    graph_frame=frame
    if phonon is not None:
        graph_frame=frame.clone();graph_frame.positions=np.asarray(phonon['reference_positions']).copy()
    base,floors=normalized_positions(graph_frame)
    # Full-cell copies keep their historical ordering. Only boundary atoms
    # receive additional images on the inclusive outer display faces.
    sources=list(np.tile(np.arange(n,dtype=int),count))
    shifts=[tile for tile in tiles for _ in range(n)]
    image_map={(i,tile):k*n+i for k,tile in enumerate(tiles) for i in range(n)}
    fractional=base@np.linalg.inv(cell)
    for i in range(n):
        choices=[]
        for axis,(lo,hi) in enumerate(limits):
            values=list(range(int(lo),int(hi)))
            if frame.pbc[axis]:
                if abs(fractional[i,axis])<=FACE_TOLERANCE:values.append(int(hi))
                elif abs(fractional[i,axis]-1)<=FACE_TOLERANCE:values.insert(0,int(lo)-1)
            choices.append(values)
        for tile in product(*choices):
            if (i,tile) in image_map:continue
            if len(sources)>=MAX_DISPLAY_ATOMS:
                raise ValueError('Boundary including face images exceeds 50,000 display atoms.')
            image_map[i,tile]=len(sources);sources.append(i);shifts.append(tile)
    sources=np.asarray(sources,dtype=int)
    shifts=np.asarray(shifts,dtype=int).reshape(-1,3)
    positions=base[sources]+shifts@cell
    if phonon is not None:
        from .qe_phonons import phonon_offsets
        state={**phonon,'real':np.asarray(phonon['real'])[sources],
               'imaginary':np.asarray(phonon['imaginary'])[sources]}
        positions+=phonon_offsets(state,shifts-floors[sources])
    source_images={}
    for (source,tile),index in image_map.items():
        source_images.setdefault(source,[]).append((tile,index))
    periodic_edges=periodic_bonds(graph_frame,cutoff)
    edges=set()
    for a,b,shift in periodic_edges:
        for tile,index in source_images.get(a,()):
            other=image_map.get((b,tuple(np.asarray(tile)+shift)))
            if other is not None:
                pair=tuple(sorted((index,other)))
                if pair[0]!=pair[1]:edges.add(pair)
    styles={i:frame.atom_appearance[source] for i,source in enumerate(sources) if source in frame.atom_appearance}
    from .site_occupancy import subset_info
    display=Frame([frame.symbols[i] for i in sources],positions,
                  frame.cell.copy(),(False,False,False),info=subset_info(frame.info,sources),atom_appearance=styles)
    from .hydrogen_bonds import repeat_hydrogen_bonds
    repeat_hydrogen_bonds(frame, display, tiles, image_map=image_map)
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
    if len(tiles) == 1:
        offset = np.asarray(tiles[0]) @ cell
        lines = [(p + offset, q + offset) for p, q in unit_cell_edges(cell)]
    return BoundaryView(display,sources,shifts.reshape(-1,3),sorted(edges),lines,tiles)
