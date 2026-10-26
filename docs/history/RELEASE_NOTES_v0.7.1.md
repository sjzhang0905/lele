# ChemView Studio v0.7.1 — periodic fragments, hydrogen bonds, electron parity

## Functional changes

1. **Electron parity**: the bottom summary now reports odd/even *electron count* instead of an inferred unpaired-electron state. Total electrons are computed from the complete atomic numbers minus integer net charge; when charge is absent the program explicitly assumes a neutral system. Use Edit > Net charge to correct this assumption. Electron parity alone does not establish spin state.
2. **Close atomic contacts**: the bottom summary reports whether any *two distinct atoms* are separated by strictly less than 0.60 Angstrom, how many unique pairs, and the shortest pair. Periodic structures use minimum-image distances; an atom is not compared against its own periodic replicas.
3. **Hydrogen bonds**: Style > Show hydrogen bonds (dashed), default OFF. Geometric visualization only: N/O/F-H donor, N/O/F acceptor, H...A from 1.4 to 2.7 Angstrom, D...A <=3.5 Angstrom, D-H...A angle >=120 degrees. Includes nearest periodic images, but does not change the covalent bond graph, fragment selection or exported structure.
4. **Periodic Select Fragment (Ctrl+G)**: finds covalent connections across periodic boundaries, using minimum-image graph edges and the same normal distance cutoff plus manual bond overrides. Finite fragments are reconstructed with continuous Cartesian coordinates in a **visual supercell**. Extra periodic copies of the primitive-cell atoms are displayed, and one enlarged external unit-cell box encloses the highlighted fragment without an internal lattice seam. The input geometry/cell and Coordinates table are unchanged. Selection still references original base atom indices.
5. **Infinite periodic networks**: not representable as one finite isolated fragment. A graph-winding check displays an explanatory message instead of silently truncating the network or spawning unlimited images. The interactive visualization is limited to 27 unit cells / 75,000 displayed atoms.
6. **Ctrl+B**: periodic-image covalent bonds now count as connected internal bonds when toggling within the selected set.

## Scope and limitations

- A supercell preview is a visualization, not a saved supercell. Export continues to write the original frame unless the user has performed an explicit geometry edit.
- Alt+mouse fragment manipulation continues to edit selected base atoms only and leave the lattice fixed; the temporary periodic preview is cleared when editing begins.
- Hydrogen bond candidates are inferred by geometry, not energies or wavefunctions. Unusual hydrogen bonds (e.g. involving sulfur or halogens) are outside the initial criteria.
- Windows GUI and Windows PyInstaller executable are not verified in this environment. Python/VTK off-screen rendering and non-GUI regression tests are available.

## Validation

Run `python -m pytest -q` in the extracted source directory. A realistic periodic boundary-crossing fragment demo is in `examples/periodic_water_boundary.POSCAR`.

## Windows launch

Install CPython 3.12 x64, run `start_windows.bat`, then build with `build_windows.bat`. The version indicator in the application title and in `dist/ChemViewStudio/VERSION.txt` must show 0.7.1.
