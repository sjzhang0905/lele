"""Display settings that can be edited before the 3D backend is loaded."""
from dataclasses import dataclass, field
from .lighting import (DEFAULT_HIGHLIGHT_BRIGHTNESS, DEFAULT_HIGHLIGHT_SIZE,
                       DEFAULT_LIGHT_ENABLED, DEFAULT_LIGHT_INTENSITIES, DEFAULT_LIGHT_POSITIONS)

MIN_ISOVALUE = 1e-12
DEFAULT_SURFACE_OPACITY = .5
WHITE_BACKGROUND = '#FFFFFF'


@dataclass
class RenderOptions:
    style: str = 'Ball and stick'
    atom_palette: str = 'Default'
    bond_palette: str = 'Element'
    surface_finish: str = 'Glossy'
    element_colors: dict[str, str] = field(default_factory=dict)
    atom_scale: float = 0.45
    space_filling_radii: str = 'Atomic'
    space_filling_scale: float = 1.0
    bond_scale: float = 0.05
    bond_model: str = 'Chemcraft pair ranges'
    bond_cutoff: float = 0.88
    background: str = WHITE_BACKGROUND
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
    volume_opacity: float = DEFAULT_SURFACE_OPACITY
    volume_signs: str = "Both"
    volume_independent_negative: bool = False
    volume_negative_iso: float = .035
    volume_positive_color: str = '#80E666'  # VMD lime (0.5, 0.9, 0.4)
    volume_negative_color: str = '#00C2FF'  # VMD cyan3 (0.0, 0.76, 1.0)
    volume_independent_opacity: bool = False
    volume_negative_opacity: float = DEFAULT_SURFACE_OPACITY
    volume_representation: str = 'Surface'
    volume_line_width: float = 1.0
    volume_smooth_normals: bool = True
    volume_surfaces: list[dict] = field(default_factory=list)
    volume_hidden_regions: list[dict] = field(default_factory=list)
    show_volume: bool = True
    dipole_mode: str = 'Off'
    dipole_source: str = 'permanent'
    dipole_scale: float = .3
    boundary_enabled: bool = True
    boundary_bounds: tuple = ((0.,1.),(0.,1.),(0.,1.))
    boundary_preserve_origin: bool = True
    lattice_planes: list[dict] = field(default_factory=list)
    fitted_plane_style: dict = field(default_factory=dict)
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
    light_enabled: tuple = DEFAULT_LIGHT_ENABLED
    light_intensities: tuple = DEFAULT_LIGHT_INTENSITIES
    light_positions: tuple = DEFAULT_LIGHT_POSITIONS
    highlight_size: float = DEFAULT_HIGHLIGHT_SIZE
    highlight_brightness: float = DEFAULT_HIGHLIGHT_BRIGHTNESS

    def __post_init__(self):
        # Projects saved before 2.13.4 use the palette's former name.
        if self.atom_palette == 'Sibyl':
            self.atom_palette = 'Default'
        if not 0 <= self.highlight_size <= 100:
            raise ValueError('Highlight size must lie between 0 and 100.')
        if not 0 <= self.highlight_brightness <= 100:
            raise ValueError('Highlight brightness must lie between 0 and 100.')
