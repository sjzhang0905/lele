# ChemView Studio v0.6.1 — fixed-cell coordinate editing

## Interaction contract

- Ordinary mouse gestures and Fit/Isometric/Front/Top/Side change **camera only**. All atomic Cartesian positions and all lattice vectors remain untouched.
- Alt+left / Alt+right / Alt+middle transform the currently connected fragment atoms only. The other atoms, lattice vectors, and camera remain untouched. Coordinate table refreshes on gesture end.
- Move selected atom to origin translates all atomic Cartesian positions and keeps lattice vectors unchanged. If a CUBE field is attached, the voxel origin translates together to maintain field alignment.
- Align first-to-second along X/Y/Z/a/b/c rotates **atomic Cartesian positions only** around the first selected atom. The lattice and camera stay fixed in every axis mode. The GUI refreshes Cartesian coordinates; Direct coordinates are recomputed from the unchanged cell during POSCAR export.
- Alignment is blocked for files with attached CUBE volume because atom-only rotation would invalidate the grid-to-atom relationship. Ordinary Alt fragment editing still leaves the volume fixed, by design.
- The new mode changes periodic atom-to-lattice geometry. It is not a passive re-labeling of the same periodic structure. Bond vectors across periodic boundaries are still treated using the displayed-cell coordinates (no new minimum-image handling in this patch).
- Export does not forcibly wrap fractional positions into [0, 1); fractional values outside that interval remain valid periodic coordinates.

## Validation

Python unit/regression tests and syntax compilation can run without Windows; ASE and PySide6 GUI and actual Windows mouse gestures require separate local validation.
