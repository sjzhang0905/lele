#!/usr/bin/env python3
"""Preserve appearance presets when upgrading from the previous application."""
from __future__ import annotations

import json
from pathlib import Path
import os

from PySide6.QtCore import QIODevice, QLockFile, QSaveFile, QStandardPaths

from .style_presets import BUILTIN_PRESETS, CUSTOM_KEY, validate_preset


def update_style_preset(path, name, values):
    """Change one named preset, preserving unrelated entries and other open sessions."""
    if not name or name == CUSTOM_KEY or name in BUILTIN_PRESETS:
        raise ValueError('Choose a user-defined preset.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(path) + '.lock')
    if not lock.tryLock(1000):
        raise OSError('Another LELE window is updating the display presets. Please try again.')
    try:
        presets = json.loads(path.read_text(encoding='utf-8')) if path.exists() else read_style_presets(path)
        if not isinstance(presets, dict):
            raise ValueError('Invalid display preset settings file.')
        if values is None:
            presets.pop(name, None)
        else:
            presets[name] = validate_preset(values)
        output = QSaveFile(str(path))
        data = json.dumps(presets, ensure_ascii=False, indent=2).encode('utf-8')
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            raise OSError(output.errorString())
        if output.write(data) != len(data) or not output.commit():
            raise OSError(output.errorString())
    finally:
        lock.unlock()


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
