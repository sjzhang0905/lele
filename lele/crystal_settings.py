"""Qt/startup-safe defaults for crystal display controls."""
PLANE_MODES = ('Show only', 'Keep below', 'Keep above', 'Slab')
DEFAULT_CONTOUR_COUNT = 7
MAX_CONTOUR_COUNT = 100
FIELD_STYLE_KEYS = ('field', 'field_palette', 'field_range', 'field_contours',
                    'field_contour_count', 'field_contour_labels', 'field_legend', 'field_resolution')
POLYHEDRA_KEYS = ('polyhedra_centers', 'polyhedra_ligands', 'polyhedra_search',
    'polyhedra_min_distance', 'polyhedra_max_distance', 'polyhedra_opacity',
    'polyhedra_edges', 'polyhedra_edge_color', 'polyhedra_show_atoms', 'polyhedra_show_vertices')


def default_plane():
    return dict(enabled=True, hkl=(0, 0, 1), offset=.5, unit='d', mode='Show only',
                thickness=.5, show=True, color='#36A8D8', opacity=.20,
                field=True, field_palette='Auto', field_range=None, field_contours=False,
                field_contour_count=DEFAULT_CONTOUR_COUNT, field_contour_labels=False,
                field_legend=True, field_resolution=256)
