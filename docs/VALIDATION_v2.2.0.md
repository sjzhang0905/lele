# LELE 2.2.0 validation — 2026-10-29

Implemented on the completed LELE 2.1.0 source, retaining its standalone VASP
readers and the preceding edit/view contracts. Linux validation uses CPython
3.12.14, ASE 3.29.0, NumPy 2.3.5, PySide6 6.12.0 and VTK 9.7.1 with Qt offscreen
and native EGL rendering. No Windows executable was built or tested here.

## Geometry and native rendering

- Verify reciprocal normals and d spacings against skew-cell fractional-plane
  equations, including negative and unreduced Miller indices, signed offsets,
  d/Å units and rotation/translation of the display frame.
- Verify below/above half-spaces, finite slabs, intersecting cuts, disabled
  planes, invalid (000) input and the six-active-face limit. Check ordered box
  intersections and two slab faces.
- Check a periodic TiO₆ octahedron with only three unique O source sites:
  six distinct ligand images, eight faces and twelve true edges. Check cube
  edges without triangulation diagonals and planar/collinear ligand sets.
- Exercise explicit center/ligand elements, exact distance limits, hidden
  centers, absent matching elements and molecular tetrahedra.
- Repeat complete shells through Boundary while preserving source atom IDs;
  rotate hulls and cuts with trajectory alignment; keep source coordinates,
  cell volume and complete structure exports unchanged.
- Render two atom glyphs natively before/after a (100) cut. Pixel assertions
  retain the allowed-side atom and remove the excluded-side atom. Verify
  clipping planes reach ordinary bond and scalar-isosurface mappers as well.
- Verify polyhedral faces receive clipping planes; clipped labels/selection
  use the retained atom-center region; atom-hidden polyhedra have no atom hits.
- Export/decode a two-frame native GIF combining polyhedra and Miller cuts.
- Keep ordinary manual/frozen bonds in Polyhedral style: a moved ligand's
  frozen long bond remains drawn, and an explicitly removed bond stays absent,
  while the independently calculated coordination hull updates.

## Interface and existing behavior

Qt checks exercise New/Apply/Clear planes, auto-centering, normal camera views,
invalid input retaining the previously applied state, element/distance/opacity
controls and per-document restoration. Molecular structures keep Polyhedral
controls but disable HKL controls when no periodic cell is available.

Existing startup tests verify the welcome page still paints before scientific
imports. Existing bond visibility, Boundary, selection, manual topology,
PNG/GIF, VASP, Gaussian/ORCA/xTB and document-view regressions are retained.

Native previews were inspected visually:

- `examples/v220_polyhedra.png`: 8 TiO₆ octahedra in 2×2×2 displayed cells,
  complete vertex atoms, translucent faces and cell outlines.
- `examples/v220_hkl_cut.png`: the same model cut by (111) at 2.4 d with a
  visible translucent cut plane. The example is an ideal cubic SrTiO₃ model.

The two Crystal pages were also inspected at the normal 354-pixel sidebar
width to check field labels, button placement and scrolling.

## Actual VASP structures

The 166-atom first frames from the supplied `OUTCAR_opt` and `XDATCAR` both
produce 64 coordination polyhedra under the default Auto/radii rules:
CN 3: 11; CN 4: 19; CN 5: 24; CN 6: 10. These counts describe the selected
geometric rules, not a chemical valence assignment. A centered (111) cut is
created on each actual skew cell. Source positions and cell arrays remain
exactly unchanged. Detailed results are in
[`qa_v2.2.0/crystal_real_v220.json`](qa_v2.2.0/crystal_real_v220.json).
Actual user coordinates are not bundled into the source distribution.

## Regression command

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=docs/qa_v2.2.0/full_v220.xml
```

Result: **497 tests and 78 subtests passed**, zero failures and zero skips,
including **32 new crystal-display regressions**. The final full report is
[`qa_v2.2.0/full_v220.xml`](qa_v2.2.0/full_v220.xml).
