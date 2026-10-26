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
)

STYLE_MODES = ('Ball and stick', 'Space filling', 'Sticks', 'Wireframe')
ATOM_PALETTES = ('Element', 'Pastel', 'Monochrome')
BOND_PALETTES = ('Element', 'Neutral gray')
SURFACE_FINISHES = ('Balanced', 'Glossy', 'Matte')
CUSTOM_KEY = '__custom__'


def _preset(style='Ball and stick', atom_scale=.6, bond_scale=.11,
            background='#F7F8FA', bonds=True, atom_palette='Element',
            bond_palette='Element', surface_finish='Balanced'):
    return dict(style=style, atom_scale=atom_scale, bond_scale=bond_scale,
                background=background, bonds=bonds, atom_palette=atom_palette,
                bond_palette=bond_palette, surface_finish=surface_finish,
                element_colors={})


BUILTIN_PRESETS = OrderedDict([
    ('Classic ball and stick', _preset()),
    ('Glossy molecule', _preset(atom_scale=.76, bond_scale=.14,
                               background='#FFFFFF', surface_finish='Glossy')),
    ('Crystal (VESTA inspired)', _preset(atom_scale=.48, bond_scale=.075,
                                       background='#FFFFFF', surface_finish='Matte')),
    ('Soft pastel', _preset(atom_scale=.67, bond_scale=.11,
                            background='#EDF2FA', atom_palette='Pastel',
                            bond_palette='Neutral gray', surface_finish='Matte')),
    ('Dark presentation', _preset(atom_scale=.75, bond_scale=.14,
                                  background='#141B29', surface_finish='Glossy')),
    ('Monochrome print', _preset(atom_scale=.58, bond_scale=.09,
                                 background='#FFFFFF', atom_palette='Monochrome',
                                 bond_palette='Neutral gray', surface_finish='Matte')),
    ('Space filling (CPK)', _preset(style='Space filling', atom_scale=1.0,
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
    if not isinstance(values, dict) or not all(
            k in values for k in STYLE_KEYS if k != 'element_colors'):
        raise ValueError('Incomplete style preset')
    # v0.8.0 files predate per-preset element colours.
    normalized = {k: values[k] for k in STYLE_KEYS if k != 'element_colors'}
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
    if normalized['atom_palette'] not in ATOM_PALETTES:
        raise ValueError('Unsupported atom palette')
    if normalized['bond_palette'] not in BOND_PALETTES:
        raise ValueError('Unsupported bond palette')
    if normalized['surface_finish'] not in SURFACE_FINISHES:
        raise ValueError('Unsupported surface finish')
    for key, lo, hi in (('atom_scale', .20, 1.8), ('bond_scale', .03, .35)):
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
