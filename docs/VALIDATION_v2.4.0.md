# LELE 2.4.0 validation — 2026-10-30

Implemented on 2.3.1, retaining its VASP E0-only policy. Linux validation uses
CPython 3.12.14, ASE 3.29.0, NumPy 2.3.5, PySide6 6.12.0 and VTK 9.7.1,
with Qt offscreen and native EGL support. No Windows executable was built or
tested here.

## Automated checks

32 new CP2K tests cover independent input/restart metadata, coordinate units,
KIND aliases, partial periodicity, scaled coordinates and scalar substitution;
external-only and unsupported/conditional inputs without invented structures;
stdout energy-only, structure-only and gradient-only records; absent/truncated
coordinates and complete trailing geometry; separate concatenated runs and
printed cell-vector precision; standard XYZ Hartree energies/time, missing
energy/cell, incomplete tails and frame limits; final SCF MO tables with separate
k-point/spin channels; TDDFPT final tables, signed length/velocity forms, Berry
source labeling and component magnitudes without fabricated vectors/amplitudes;
live Qt curves, CSV, geometry-free spectra/painting and project round trips.

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=docs/qa_v2.4.0/full_v240.xml
```

Result: **583 tests and 78 subtests passed**, zero failures and zero skips.
Report: [full_v240.xml](qa_v2.4.0/full_v240.xml).

## Actual files

Each of the five supplied files was copied into an isolated temporary directory
and loaded with no companion file available. Frames, coordinates, cells and
energies exactly match loading the same file from the shared upload directory.

- Input and restart each expose one 128-atom periodic structure and their own
  settings, without an assumed energy.
- Optimization stdout exposes 135 FORCE_EVAL energy records but only one printed
  coordinate table. The first record has geometry; 134 later energy records
  remain geometry-free. All 135 energies match the source Hartree values exactly
  after conversion to internal eV. Optimization metrics retain printed thresholds
  and Hartree/bohr or bohr units.
- XYZ exposes 134 complete 128-atom frames and 134 printed Hartree E values.
  No cell or periodicity is imported from nearby files.
- TDDFT stdout contains two CP2K runs: two frames, two energies and two final MO
  snapshots with five k-point channels each. The final spectrum has 200 lines.
  Its first line is 0.05885 eV, f=0.112133, with component magnitudes
  [8.5119, 2.3051, 0.10344] au. All magnitudes remain source metadata, with no
  electric/velocity vector and no fabricated configuration coefficient.

Live Qt acceptance verifies a 135-point record curve and CSV with only one
linked coordinate frame, five orbital channels, the 200-transition spectrum and
CSV, and exact project round trips for all five documents. The report contains
counts and validation outcomes, not user coordinates:
[actual_cp2k_v240.json](qa_v2.4.0/actual_cp2k_v240.json).

Synthetic curve and spectrum previews were rendered and visually inspected for
labels, units, controls, tabular magnitudes and export actions. Synthetic inputs
and a portable three-document project are bundled as examples. Actual input,
restart, trajectory and output files are not included in the source archive.

## Scope

This is an independent printed-data reader, not a CP2K calculation engine or
complete implementation of every CP2K format/module. External preprocessing,
binary wavefunctions, CP2K vibrational-mode formats and automatic companion-file
association are outside this release. Missing values remain missing; unknown
moment forms retain labeled components instead of invented vector directions.
Standard XYZ uses the normal Angstrom/Hartree convention; custom output units
that are absent from a file cannot be inferred from neighbouring input files.
