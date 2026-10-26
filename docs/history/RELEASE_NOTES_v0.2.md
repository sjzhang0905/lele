# ChemView Studio v0.2 — change log

This source release supersedes v0.1.1, not a binary patch.

- User-selectable axis placement: hidden / camera-oriented bottom-left / true world origin.
- XYZ vs true nonorthogonal periodic a, b, c lattice directions, with GUI disabling abc for invalid/nonperiodic cells.
- Fixed VTK bottom-left event-coordinate handling for atom clicks; rendered-sphere projected-radius hit-testing; camera-nearest atom priority on overlap.
- 3D click selection now mirrors into the editable coordinate table; camera drags are ignored by picking.
- Labels visually centered on sphere projections and drawn in front of the sphere surface; size, color, boldness, Arial/Courier/Times or external TTF/OTF; atom labels support 1..N or separate indexing per chemical element.
- VTK offscreen test of world axes, orientation widget, picking, and label glyphs; 10 tests passed; 4 ASE-related tests skipped in current environment.
- Windows Qt GUI and PyInstaller EXE have NOT been tested on Windows here.

Run `start_windows.bat` for Python 3.12, then `build_windows.bat` to package. Launch from `dist/ChemViewStudio/ChemViewStudio.exe` (keep `_internal` folder).
