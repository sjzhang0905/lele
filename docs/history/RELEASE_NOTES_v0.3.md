# ChemView Studio v0.3.0

Windows 64-bit / Python 3.12 source release (PySide6 + VTK).

## Changes

- Removed `Element + index (per element)` from Atom labels; retained POSCAR-group-aware VESTA numbering.
- Switched frame navigation from `itemClicked` to `currentItemChanged`; tree selection stays synchronized with playback and navigation.
- Added Qt-native pointer event handling for atom click selection, including Windows DPI-aware conversion to VTK display pixels.
- Right-drag now rolls the camera clockwise / counterclockwise instead of zooming. Left-drag and mouse wheel retain existing behavior.
- Added explicit window version and `dist/ChemViewStudio/VERSION.txt` on packaging to detect stale builds.

## Validation

- 22 unit tests: 18 passed, 4 skipped (ASE unavailable here).
- Native Qt mouse event methods exercised with substitute widgets; not a genuine Windows Qt GUI acceptance run (PySide6 unavailable in testing environment).
- Actual provided POSCAR header checked for duplicate Li block numbering.

## Windows verification

1. Unpack in a **new folder** and launch `start_windows.bat`. Check window title says v0.3.
2. Open `examples/water_trajectory.xyz`. Click a Frame in the left tree, then press Up/Down while its tree remains focused. The rendered geometry and spinbox must change together.
3. Click oxygen/hydrogen spheres: they should be highlighted and the coordinate row selected. Click again to unselect.
4. Drag with right mouse button horizontally: scene should roll around the screen axis; object size should remain unchanged. Left drag still rotates and wheel still zooms.
5. Load the supplied POSCAR: use `VESTA (POSCAR groups)` and confirm first ten Li labels Li1..Li10, second five restart Li1..Li5.
6. Run `build_windows.bat` and launch **only** `dist/ChemViewStudio/ChemViewStudio.exe`. Confirm `VERSION.txt` shows v0.3.

If a click still does nothing, look for the status-bar message (either atom number or `No atom at cursor`). If there is no message, Qt mouse events are not reaching the expected widget and a Windows-specific event log is needed.
