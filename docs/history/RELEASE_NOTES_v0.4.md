# ChemView Studio v0.4 — multi-select, bonds, geometry

- Unlimited atom selection: click toggles each atom; selection order is meaningful for alignment. Coordinates table supports multiple rows. Right **click** clears all selections; right **drag** rolls the camera.
- Ctrl+B / button: toggle selected internal bonds. Two atoms always toggle, even when far apart; 3+ atoms clear all internal visible bonds if any are present, otherwise restore automatic distance-based bonds. This is a **visual bond display override**, not a chemical bond order editor and not written to POSCAR/XYZ/CIF. Undo via Ctrl+Z.
- One selected atom: Move to (0,0,0) translates all atoms. Cell vectors are unchanged. Attached CUBE volume origin translates as well.
- Two selected atoms: Align (first -> second) to X/Y/Z or periodic a/b/c. Rotates around the first selected atom, preserving distances. XYZ rigidly rotates atoms, cell vectors, and attached grid. abc rotates **atoms only** relative to fixed periodic cell; this changes their alignment to the lattice, and is disabled for files with an attached CUBE grid.
- Ctrl+Z restores geometry, cell, volume axes and bond overrides for the edited frame.

## Verification
Automated tests in `tests/test_edit_actions.py` cover bond toggles, rotation, lattice and undo state handling. This Linux environment lacks PySide6 and ASE, so **Windows GUI is not yet verified**.
