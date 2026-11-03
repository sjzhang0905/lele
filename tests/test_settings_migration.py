#!/usr/bin/env python3
"""Preserve user appearance settings through the LELE application rename."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Requires PySide6')
class SettingsMigrationTests(unittest.TestCase):
    def test_legacy_colours_are_copied_and_the_source_is_retained(self):
        from lele.settings import read_style_presets
        from lele.style_presets import BUILTIN_PRESETS
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'ChemViewStudio' / 'style_presets.json'
            new = Path(directory) / 'LELE' / 'style_presets.json'
            old.parent.mkdir()
            preset = {**BUILTIN_PRESETS['Classic ball and stick'], 'atom_palette': 'Sibyl',
                      'element_colors': {'O': '#123456'}}
            old.write_text(json.dumps({'My oxygen': preset}), encoding='utf-8')
            original = old.read_bytes()
            loaded = read_style_presets(new, legacy_paths=[old])
            self.assertEqual(loaded['My oxygen']['element_colors'], {'O': '#123456'})
            self.assertEqual(loaded['My oxygen']['atom_palette'], 'Default')
            self.assertEqual(json.loads(new.read_text()), loaded)
            self.assertEqual(old.read_bytes(), original)

    def test_existing_lele_file_wins_over_legacy_settings(self):
        from lele.settings import read_style_presets
        from lele.style_presets import BUILTIN_PRESETS
        with tempfile.TemporaryDirectory() as directory:
            old = Path(directory) / 'old.json'
            new = Path(directory) / 'new.json'
            old.write_text(json.dumps({'Old': BUILTIN_PRESETS['Soft pastel']}), encoding='utf-8')
            new.write_text('{}', encoding='utf-8')
            self.assertEqual(read_style_presets(new, legacy_paths=[old]), {})
            self.assertEqual(new.read_text(), '{}')

    def test_invalid_legacy_file_does_not_hide_the_next_valid_file(self):
        from lele.settings import read_style_presets
        from lele.style_presets import BUILTIN_PRESETS
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'bad.json'
            good = Path(directory) / 'good.json'
            new = Path(directory) / 'new.json'
            bad.write_text('not json', encoding='utf-8')
            good.write_text(json.dumps({'Valid': BUILTIN_PRESETS['Glossy molecule']}), encoding='utf-8')
            self.assertIn('Valid', read_style_presets(new, legacy_paths=[bad, good]))


if __name__ == '__main__':
    unittest.main()
