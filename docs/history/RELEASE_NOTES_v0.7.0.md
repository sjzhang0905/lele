# ChemView Studio 0.7.0

- Added an explicit Isometry / Perspective toolbar selector. Isometry means orthographic camera along Cartesian [1, 1, 1]; it is camera-only.
- Added SIESTA multi-frame parsing from printed .out coordinate sections and .ANI fallback.
- Added strictly count-matched energy extraction from SIESTA .out Etot or compatible .MDE step tables.
- Added a bottom formula and conservative unpaired-electron status that refreshes with the active frame.
- Added synthetic SIESTA .out/.ANI/.MDE regression fixtures and isometric-camera coverage.

Limitations: arbitrary .MDE layouts, binary SIESTA .MD cell histories, and unrecorded steps are not reconstructed. An .ANI trajectory has no per-step lattice; borrowed constant lattice requires user verification for variable-cell calculations. Windows GUI has not been physically acceptance-tested.
