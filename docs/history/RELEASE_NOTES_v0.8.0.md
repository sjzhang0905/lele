# ChemView Studio v0.8.0 — Display style presets

## New features

- Nine ready-to-use presets in the left **Style** tab: Classic ball and stick, Glossy molecule, Crystal (VESTA inspired), Soft pastel, Dark presentation, Monochrome print, Space filling (CPK), Stick model, and Thin wireframe.
- Presets control only drawing style, atom-size scale, bond thickness, atom/bond palette, shading, and background. In particular, they do **not** change geometric bond cutoff, manual added/removed bonds, molecular coordinates, cell vectors, labels, axes, hydrogen bonds, or volumetric settings.
- Editable color palettes (**Element / Pastel / Monochrome**), bond colors (**Element / Neutral gray**), and surface finishes (**Balanced / Glossy / Matte**).
- Any manual adjustment to preset-controlled properties activates **Custom (manual)**. Selecting Custom again restores the last manually customized appearance.
- **Save current appearance as preset** persists named presets as `style_presets.json` in the OS-specific Qt application configuration directory. The built-in presets cannot be overwritten. Saved presets are offered in the selection list next time.
- Space-filling now uses an approximate van der Waals radius set (instead of enlarged covalent radii) for common elements. Unlisted elements use a radius fallback.

## Running and validation

Install 64-bit Python 3.12, run `start_windows.bat`, and then optionally `build_windows.bat`. The title and `dist/ChemViewStudio/VERSION.txt` identify v0.8.0.

The style model, VTK off-screen rendering, and repository regression tests have been run in Linux. PySide6 is not available in this build environment, and the Windows desktop/EXE has not been tested.

All presets are original parameter combinations inspired by common molecular visualization modes; no Chemcraft program assets or proprietary code are included.
