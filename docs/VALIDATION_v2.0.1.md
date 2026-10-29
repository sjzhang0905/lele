# LELE 2.0.1 validation

- Full Linux Qt/VTK regression: **391 tests + 72 subtests passed**.
  See `qa_v2.0.1/full_v201.xml`.
- Added 11 cases covering contact details/count agreement, strict cutoff and
  empty geometry, contact image translations in wrapped and unwrapped source
  coordinates, skew cells, clickable footer details and geometry snapshots,
  frame-specific contact counts, frequency references, and periodic volumes.
- Confirmed that image shifts reconstruct the reported distance from original
  coordinates and that each distinct atomic pair is counted once.
- Confirmed cell volume by the absolute determinant for ordinary, skew and
  left-handed cells: frame scaling updates 24 Å³ to 192 Å³. Nonperiodic cells
  do not gain a periodic-volume entry.
- Inspected the compact single-line footer at 1380×850, colon-free selection
  measurement, underlined contact control and periodic contact detail window.
- Kept charge/parity provenance available in the footer tooltip. Updated old
  footer text expectations while retaining their charge/frame/undo checks.
- Previous 2.0.0 source members and features are retained. No GitHub push,
  commit or merge was performed for this update. Windows EXE was not built
  or exercised in this Linux environment.
