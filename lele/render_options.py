"""Display settings that can be edited before the 3D backend is loaded."""
from dataclasses import dataclass, field

MIN_ISOVALUE = 1e-12


@dataclass
class RenderOptions:
    style: str = 'Ball and stick'
    atom_palette: str = 'Default'
    bond_palette: str = 'Element'
    surface_finish: str = 'Glossy'
    element_colors: dict[str, str] = field(default_factory=dict)
    atom_scale: float = 0.50
    space_filling_radii: str = 'Atomic'
    space_filling_scale: float = 1.0
    bond_scale: float = 0.07
    bond_model: str = 'Chemcraft pair ranges'
    bond_cutoff: float = 1.0
    background: str = '#FFFFFF'
    bonds: bool = True
    hydrogen_bonds: bool = False
    unit_cell: bool = True
    labels: str = 'None'
    atom_legend: bool = False  # Legacy v2.7 project field; main-canvas overlay is no longer used.
    label_font: str = 'Arial'
    label_font_file: str = ''
    label_font_size: int = 15
    label_color: str = '#18212F'
    label_bold: bool = True
    axes_position: str = 'Corner'  # Off, Corner (overlay), Origin (0,0,0)
    axes_basis: str = 'Auto'      # Auto: periodic abc, molecular XYZ; explicit XYZ / abc
    axes_length: float = 2.5     # Cartesian axis length in Angstrom at origin
    volume_iso: float = 0.035
    volume_opacity: float = 0.65
    show_volume: bool = True
    dipole_mode: str = 'Off'
    dipole_source: str = 'permanent'
    dipole_scale: float = .3
    boundary_enabled: bool = False
    boundary_bounds: tuple = ((0.,1.),(0.,1.),(0.,1.))
    lattice_planes: list[dict] = field(default_factory=list)
    polyhedra_centers: str = 'Auto'
    polyhedra_ligands: str = 'Auto'
    polyhedra_search: str = 'Covalent radii'
    polyhedra_min_distance: float = 0.
    polyhedra_max_distance: float = 3.
    polyhedra_opacity: float = .35
    polyhedra_edges: bool = True
    polyhedra_edge_color: str = '#334155'
    polyhedra_show_atoms: bool = True
    polyhedra_show_vertices: bool = True
    element_pair_rules: list[dict] = field(default_factory=list)
    pair_rules_only: bool = False

    def __post_init__(self):
        # Projects saved before 2.13.4 use the palette's former name.
        if self.atom_palette == 'Sibyl':
            self.atom_palette = 'Default'
