"""Qt/startup-safe defaults for crystal display controls."""
PLANE_MODES = ('Show only', 'Keep below', 'Keep above', 'Slab')
POLYHEDRA_KEYS = ('polyhedra_centers', 'polyhedra_ligands', 'polyhedra_search',
    'polyhedra_min_distance', 'polyhedra_max_distance', 'polyhedra_opacity',
    'polyhedra_edges', 'polyhedra_edge_color', 'polyhedra_show_atoms', 'polyhedra_show_vertices')


def default_plane():
    return dict(enabled=True, hkl=(0, 0, 1), offset=.5, unit='d', mode='Keep below',
                thickness=.5, show=True, color='#36A8D8', opacity=.20)
