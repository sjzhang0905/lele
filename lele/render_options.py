"""Display settings that can be edited before the 3D backend is loaded."""
from dataclasses import dataclass, field

MIN_ISOVALUE = 1e-12


@dataclass
class RenderOptions:
    style: str = 'Ball and stick'
    atom_palette: str = 'Element'
    bond_palette: str = 'Element'
    surface_finish: str = 'Balanced'
    element_colors: dict[str, str] = field(default_factory=dict)
    atom_scale: float = 0.60
    bond_scale: float = 0.11
    bond_cutoff: float = 1.18
    background: str = '#F7F8FA'
    bonds: bool = True
    hydrogen_bonds: bool = False
    unit_cell: bool = True
    labels: str = 'None'
    label_font: str = 'Arial'
    label_font_file: str = ''
    label_font_size: int = 15
    label_color: str = '#18212F'
    label_bold: bool = True
    axes_position: str = 'Corner'  # Off, Corner (overlay), Origin (0,0,0)
    axes_basis: str = 'XYZ'       # XYZ or abc (requires periodic lattice)
    axes_length: float = 2.5     # Cartesian axis length in Angstrom at origin
    volume_iso: float = 0.035
    volume_opacity: float = 0.65
    show_volume: bool = True
    dipole_mode: str = 'Off'
    dipole_source: str = 'permanent'
    dipole_scale: float = .3
    boundary_enabled: bool = False
    boundary_bounds: tuple = ((0.,1.),(0.,1.),(0.,1.))
