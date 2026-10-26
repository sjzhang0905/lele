# ChemView Studio 0.2.1 — POSCAR group-label correction

- New atom label mode: `VESTA (POSCAR groups)`.
- Preserve original VASP5 POSCAR declared species-block boundaries, even when adjacent blocks have the same chemical symbol.
- Regression example: Li Li Fe Zr P O / 10 5 14 1 16 64 -> Li1..Li10, Li1..Li5, Fe1..Fe14, Zr1, P1..P16, O1..O64.
- Other files fall back to numbering by chemical element, without inventing site equivalence.
- Previous GUI frame-arrow navigation, 3D atom click handling, and right-mouse camera roll are NOT changed in this incremental correction; these remain to be fixed/validated.
- Windows GUI has not been executed in the current environment.
