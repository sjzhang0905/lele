#!/usr/bin/env python3
"""Display-only presets for the LELE renderer.

Presets intentionally omit bond_cutoff, label settings, axes, hydrogen-bond
visibility, and unit-cell display. None of those change on preset selection.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
import re

STYLE_KEYS = (
    'style', 'atom_scale', 'bond_scale', 'background', 'bonds',
    'atom_palette', 'bond_palette', 'surface_finish', 'element_colors',
    'space_filling_radii', 'space_filling_scale',
)

STYLE_MODES = ('Ball and stick', 'Space filling', 'Sticks', 'Wireframe', 'Polyhedral')
ATOM_PALETTES = ('Default', 'GaussView style (Chemcraft)', 'Element', 'Pastel', 'Monochrome', 'Legacy LELE')
BOND_PALETTES = ('Element', 'Neutral gray')
SURFACE_FINISHES = ('Balanced', 'Glossy', 'Matte')
CUSTOM_KEY = '__custom__'


def _preset(style='Ball and stick', atom_scale=.5, bond_scale=.07,
            background='#FFFFFF', bonds=True, atom_palette='Default',
            bond_palette='Element', surface_finish='Glossy',
            space_filling_radii='Atomic', space_filling_scale=1.):
    return dict(style=style, atom_scale=atom_scale, bond_scale=bond_scale,
                background=background, bonds=bonds, atom_palette=atom_palette,
                bond_palette=bond_palette, surface_finish=surface_finish,
                element_colors={}, space_filling_radii=space_filling_radii,
                space_filling_scale=space_filling_scale)


BUILTIN_PRESETS = OrderedDict([
    ('Classic ball and stick', _preset()),
    ('Glossy molecule', _preset(atom_scale=.76, bond_scale=.14,
                               background='#FFFFFF', surface_finish='Glossy')),
    ('Crystal (VESTA inspired)', _preset(atom_scale=.48, bond_scale=.075,
                                       background='#FFFFFF', surface_finish='Matte')),
    ('Coordination polyhedra (VESTA inspired)', _preset(style='Polyhedral', atom_scale=.28,
                                       bond_scale=.05, bonds=False, background='#FFFFFF', surface_finish='Matte')),
    ('Soft pastel', _preset(atom_scale=.67, bond_scale=.11,
                            background='#EDF2FA', atom_palette='Pastel',
                            bond_palette='Neutral gray', surface_finish='Matte')),
    ('Dark presentation', _preset(atom_scale=.75, bond_scale=.14,
                                  background='#141B29', surface_finish='Glossy')),
    ('Monochrome print', _preset(atom_scale=.58, bond_scale=.09,
                                 background='#FFFFFF', atom_palette='Monochrome',
                                 bond_palette='Neutral gray', surface_finish='Matte')),
    ('Space filling (VESTA)', _preset(style='Space filling', atom_scale=1.0,
                                   bond_scale=.11, bonds=False, background='#FFFFFF')),
    ('Stick model', _preset(style='Sticks', atom_scale=.50,
                            bond_scale=.17, background='#FAFAFB')),
    ('Thin wireframe', _preset(style='Wireframe', atom_scale=.60,
                               bond_scale=.038, background='#FFFFFF')),
])


def snapshot(options):
    """Copy only visual preset parameters from RenderOptions."""
    return {key: deepcopy(getattr(options, key)) for key in STYLE_KEYS}


def validate_preset(values):
    """Validate a saved user preset before it is applied to render options."""
    optional = {'element_colors', 'space_filling_radii', 'space_filling_scale'}
    if not isinstance(values, dict) or not all(k in values for k in STYLE_KEYS if k not in optional):
        raise ValueError('Incomplete style preset')
    # v0.8.0 files predate per-preset element colours.
    normalized = {k: values[k] for k in STYLE_KEYS if k not in optional}
    normalized['space_filling_radii'] = values.get('space_filling_radii', 'Atomic')
    normalized['space_filling_scale'] = values.get('space_filling_scale', 1.)
    if normalized['space_filling_radii'] not in ('Atomic', 'Ionic', 'van der Waals'):
        raise ValueError('Invalid VESTA radius type')
    colors = values.get('element_colors', {})
    if not isinstance(colors, dict):
        raise ValueError('Invalid element colours')
    for symbol, value in colors.items():
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z][a-z]?', symbol):
            raise ValueError('Invalid element symbol')
        if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
            raise ValueError('Invalid element colour')
    normalized['element_colors'] = dict(colors)
    if normalized['style'] not in STYLE_MODES:
        raise ValueError('Unsupported rendering style')
    if normalized['atom_palette'] == 'Sibyl':
        normalized['atom_palette'] = 'Default'
    if normalized['atom_palette'] not in ATOM_PALETTES:
        raise ValueError('Unsupported atom palette')
    if normalized['bond_palette'] not in BOND_PALETTES:
        raise ValueError('Unsupported bond palette')
    if normalized['surface_finish'] not in SURFACE_FINISHES:
        raise ValueError('Unsupported surface finish')
    for key, lo, hi in (('atom_scale', .20, 1.8), ('space_filling_scale', .20, 1.8), ('bond_scale', .03, .35)):
        value = normalized[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
            raise ValueError(f'Invalid {key}')
        normalized[key] = float(value)
    c = normalized['background']
    if not isinstance(c, str) or len(c) != 7 or c[0] != '#':
        raise ValueError('Invalid background colour')
    try:
        int(c[1:], 16)
    except ValueError as exc:
        raise ValueError('Invalid background colour') from exc
    if not isinstance(normalized['bonds'], bool):
        raise ValueError('Invalid bonds flag')
    return normalized


def apply_preset(options, values):
    for key, value in validate_preset(values).items():
        setattr(options, key, value)


def mix_color(hex_color, white_share):
    """Return a pastel shade; input colour is left unchanged."""
    raw = hex_color.lstrip('#')
    source = (int(raw[i:i+2], 16) for i in (0, 2, 4))
    return '#' + ''.join(f'{round(x*(1-white_share)+255*white_share):02X}' for x in source)


def element_palette_color(options, symbol, *, for_bond=False):
    """Shared palette lookup for the renderer and the preloaded color editor."""
    if for_bond and options.bond_palette == 'Neutral gray':return '#969CA8'
    scheme=options.atom_palette
    if scheme=='Monochrome':return '#ABB6C6'
    from .core import LEGACY_ELEMENT_COLORS,colour
    default=LEGACY_ELEMENT_COLORS.get(symbol,'#A9AEB5') if scheme=='Legacy LELE' else colour(symbol)
    if scheme in ('Default', 'Sibyl'):
        from .sibyl_palette import SIBYL_COLORS
        default=mix_color(mix_color(SIBYL_COLORS.get(symbol,default),.10),.05)
    base=options.element_colors.get(symbol,default)
    return mix_color(base,.43) if scheme=='Pastel' else base
