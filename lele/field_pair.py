"""Build independent ESP or electron–hole plots from explicitly assigned scalar fields."""
from itertools import product
from pathlib import Path

import numpy as np

from .core import Document, Volume
from .field_mapping import DEFAULT_ESP_RANGE, DEFAULT_PALETTE, suggested_isovalue, validate_field_geometry
from .grid_memory import scalar_limit
from .output_text import check_load_cancelled
from .render_options import DEFAULT_SURFACE_OPACITY


ROLES = {'esp': ('Density', 'ESP'), 'electron_hole': ('Electron', 'Hole')}
TITLES = {'esp': 'Electrostatic potential (ESP)', 'electron_hole': 'Electron–hole distribution'}
ELECTRON_COLOR = '#80E666'
HOLE_COLOR = '#00C2FF'


def read_pair_source(path, role):
    from .volumetric_input import read_cube_document, read_vasp_volume_document
    from .vasp_volume_detection import is_vasp_volume, named_vasp_volume_kind
    path = Path(path).expanduser().resolve(strict=True)
    if path.suffix.lower() in ('.cube', '.cub'):
        document = read_cube_document(path)
    elif role in ('Density', 'ESP') and is_vasp_volume(path):
        allowed = ('CHGCAR', 'CHG') if role == 'Density' else ('LOCPOT',)
        kind = named_vasp_volume_kind(path) or allowed[0]
        if kind not in allowed:
            raise ValueError(f'For {role}, choose a CUBE or a VASP {" / ".join(allowed)} file.')
        document = read_vasp_volume_document(path, kind=kind)
    else:
        formats = {'Density': 'CUBE, CHGCAR or CHG', 'ESP': 'CUBE or LOCPOT'}
        raise ValueError(f'Choose a {formats.get(role, "CUBE")} file for {role}.')
    if document.volume is None or not document.volumes:
        raise ValueError(f'{path.name}: {document.note or "No complete scalar grid."}')
    return document


def source_channels(document):
    """The electrostatic scalar excludes spin magnetization and magnetic potential."""
    if document.format_name == 'VASP LOCPOT':
        count = len(document.volumes)
        if count == 2:
            return [('Scalar potential (mean of spin up and down)', (0, 1))]
        if count not in (1, 4):
            raise ValueError(f'Unrecognized LOCPOT layout with {count} channels.')
        return [('Scalar potential', (0,))]
    if document.format_name in ('VASP CHGCAR', 'VASP CHG'):
        return [('Total density', (0,))]
    return [(field.label or f'Field {i+1}', (i,)) for i, field in enumerate(document.volumes)]


def proposed_level(field, role, bounds=None):
    from ase.units import Bohr
    nominal = .001 if role == 'Density' else .002
    if field.unit == 'e/Å³':
        nominal /= Bohr**3
    return suggested_isovalue(field.data if bounds is None else bounds, nominal)


def _role_field(document, channels, role):
    if channels not in [indices for _, indices in source_channels(document)]:
        raise ValueError(f'Choose an available dataset for {role}.')
    base = document.volumes[channels[0]]
    data, unit = base.data, base.unit
    provenance = dict(base.provenance, pair_role=role, source_path=str(document.path),
                      source_channels=[i+1 for i in channels])
    if document.format_name == 'VASP LOCPOT':
        # LOCPOT is a one-electron potential energy in eV. For a +e probe
        # reverse its sign; file generation (LVHAR) determines the terms.
        if len(channels) == 2:
            data = -.5 * data - .5 * document.volumes[channels[1]].data
        else:
            data = -data
        unit = 'V'
        provenance['convention'] = 'Positive probe; minus the VASP scalar electron potential energy (eV).'
    else:
        from .field_arithmetic import unit_spec
        try:
            family = unit_spec(unit)[0]
        except ValueError:
            family = None  # Standard CUBEs need the role selected by the user.
        accepted = ('potential', 'electrostatic potential') if role == 'ESP' else ('density',)
        if family is not None and family not in accepted:
            raise ValueError(f'{document.path.name}: the selected {role} dataset carries incompatible units ({unit}).')
    if not np.isfinite(data).all() or abs(np.linalg.det(base.voxel_vectors)) < 1.e-15:
        raise ValueError(f'{role} requires finite data and independent grid vectors.')
    return Volume(data, base.origin, base.voxel_vectors, f'{role} · {document.path.name}',
                  unit, base.periodic, provenance=provenance)


def _grid_bounds(field):
    corners = np.array(list(product(*[(0, n-1) for n in field.data.shape])))
    points = field.origin + corners @ field.voxel_vectors
    return points.min(axis=0), points.max(axis=0)


def make_field_pair(mode, sources, choices, levels):
    """Return a new two-grid document and its editable surface specifications."""
    roles = ROLES[mode]
    left, right = sources
    if left.path == right.path and choices[0] == choices[1]:
        raise ValueError('The two roles refer to the same file and dataset. Choose two distinct fields.')
    selected_size = sum(doc.volumes[indices[0]].data.size for doc, indices in zip(sources, choices))
    if selected_size > scalar_limit():
        raise ValueError('The two selected fields exceed the available memory budget.')
    validate_field_geometry(left.frames[0], right.frames[0], np.eye(3), np.zeros(3),
                            periodic=left.volume.periodic and right.volume.periodic)
    fields = []
    for doc, indices, role in zip(sources, choices, roles):
        check_load_cancelled()
        fields.append(_role_field(doc, indices, role))
    if mode == 'esp' and not fields[1].periodic:
        lo, hi = _grid_bounds(fields[0])
        lo2, hi2 = _grid_bounds(fields[1])
        if np.any(np.maximum(lo, lo2) > np.minimum(hi, hi2) + 2.e-4):
            raise ValueError('The density and ESP grids do not overlap in space.')
    layers = []
    for index in range(1 if mode == 'esp' else 2):
        field = fields[index]
        value = float(levels[index])
        low, high = float(field.data.min()), float(field.data.max())
        if not np.isfinite(value) or not low < value < high:
            raise ValueError(f'{roles[index]} needs an isovalue strictly between {low:.7g} and {high:.7g} {field.unit}.')
        if mode == 'esp' and value <= 0:
            raise ValueError('Use a positive electron-density isovalue for the ESP surface.')
        layer = dict(dataset=index, value=value, visible=True, style='Surface',
                     color=(ELECTRON_COLOR, HOLE_COLOR)[index], opacity=DEFAULT_SURFACE_OPACITY)
        if mode == 'esp':
            layer.update(map_dataset=1, map_palette=DEFAULT_PALETTE,
                         map_range=list(DEFAULT_ESP_RANGE), map_legend=True)
        layers.append(layer)
    note = '\n'.join(f'{field.label} ({field.unit}) — {doc.path}' for field, doc in zip(fields, sources))
    if right.format_name == 'VASP LOCPOT':
        note += '\nESP = −LOCPOT for a positive test charge. Use ionic + Hartree LOCPOT (LVHAR = .TRUE.).'
    result = Document(left.path, TITLES[mode], [left.frames[0].clone()], fields[0], note)
    result.volumes = fields
    return result, layers
