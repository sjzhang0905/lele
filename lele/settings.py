#!/usr/bin/env python3
"""Preserve appearance presets when upgrading from the previous application."""
from __future__ import annotations

import json
from pathlib import Path
import os

from PySide6.QtCore import QStandardPaths

from .style_presets import BUILTIN_PRESETS, CUSTOM_KEY, validate_preset


def legacy_style_preset_paths():
    """Known Qt application directories; do not scan unrelated applications."""
    roots = []
    for location in (QStandardPaths.StandardLocation.GenericConfigLocation,
                     QStandardPaths.StandardLocation.GenericDataLocation):
        roots.extend(Path(p) for p in QStandardPaths.standardLocations(location))
    roots.extend(Path(os.environ[key]) for key in ('APPDATA', 'LOCALAPPDATA') if os.environ.get(key))
    names = ('ChemViewStudio', 'ChemView Studio', '__main__.py', 'launch_app.py')
    return list(dict.fromkeys(root / name / 'style_presets.json' for root in roots for name in names))


def read_style_presets(path: Path, *, legacy_paths=None):
    """Load valid presets and copy legacy settings once into LELE's directory.

    An existing LELE file always takes priority, even if it is empty. A failed
    migration write still allows the imported settings to be used this session.
    """
    path = Path(path)
    candidates = [path]
    if not path.exists():
        candidates.extend(legacy_style_preset_paths() if legacy_paths is None else legacy_paths)
    for candidate in candidates:
        try:
            data = json.loads(Path(candidate).read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                continue
        except (OSError, ValueError):
            continue
        valid = {}
        for name, values in data.items():
            if not isinstance(name, str) or not name or name in BUILTIN_PRESETS or name == CUSTOM_KEY:
                continue
            try:
                valid[name] = validate_preset(values)
            except ValueError:
                continue
        if Path(candidate) != path and valid:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(valid, indent=2), encoding='utf-8')
            except OSError:
                pass
        if Path(candidate) == path or valid:
            return valid
    return {}
