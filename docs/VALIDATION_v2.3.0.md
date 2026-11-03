# LELE 2.3.0 validation — 2026-10-29

Built on the completed 2.2.0 source. Linux validation uses CPython 3.12.14,
ASE 3.29.0, NumPy 2.3.5, SciPy 1.17.0, PySide6 6.12.0, Matplotlib 3.10.8
and VTK 9.7.1, with Qt offscreen and native EGL rendering.
No Windows executable was built or tested here.

## Element-pair rules

Check symmetric ordinary bonds and directed center/ligand coordination,
wildcard specificity, last-row precedence, disabled rows, inclusive distance
limits, invalid elements/ranges and only-listed mode. Explicit long bonds
bypass the default occlusion pruning; unlisted pairs retain the existing
fallback. Manual links and removals continue to override inference.

Check periodic TiO6 with three unique O source sites and six distinct ligand
images. Verify rule changes invalidate Boundary geometry caches without moving
atoms. Apply to all frames through the live Qt panel, inherit rules in a newly
opened file, freeze bonds during coordinate editing, and undo geometry followed
by rule application. Check the editor fits a 354-pixel sidebar without horizontal
scrolling.

## Polyhedron metrics and interface

- An ideal periodic TiO6 octahedron has CN=6, lengths=2 Å, volume=32/3 Å³,
  D=0, quadratic elongation=1, angle variance=0 and ECoN=6.
- An ideal tetrahedron has volume=8/3 Å³, quadratic elongation=1 and zero angle
  variance. Uniform scaling doubles lengths and multiplies volume by eight.
- Axial octahedral elongation increases D and quadratic elongation while
  retaining zero angle variance; an angular perturbation increases variance.
- Planar shells retain zero volume and leave shape-specific metrics blank;
  empty shells retain CN=0/ECoN=0 with undefined lengths and volume. Boundary
  repeats and HKL cuts do not alter source-coordinate metrics.
- Trajectory records retain zero coordination and gaps on atom-order changes,
  anchored to the analyzed reference frame's element sequence.
- Live Qt checks cover ligand-image CSV, metric CSV, curve frame navigation and
  actual show/grab painting. The last check guards against shadowing the Qt
  QPaintDevice.metric virtual method with a combo-box attribute.

Metric definitions were checked against the
[VESTA official manual, chapter 11](https://jp-minerals.org/vesta/en/doc/VESTAch11.html).
Quadratic elongation and edge-angle variance are implemented only for recognized
tetrahedra and octahedra containing the central atom; octahedral trans angles
are excluded. ECoN follows the documented minimum-distance-weighted average
length. Coordination membership follows LELE's active geometric rules.

## Portable projects

Round-trip synthetic XYZ, Gaussian modes/properties, ORCA full results,
NEB/GOAT/SOC, xTB energy-only, g-xTB, and standalone VASP geometry/energy/modes.
Check volume arrays, atom appearance, frozen and manual ordinary/periodic
bonds, dashed annotations, complex SOC values, nonfinite result metadata,
geometry-parameter definitions and shared document/reference identities.
Save restored objects again to check retained data types and fields.

Live Qt checks restore multiple documents, active frame and selection, separate
display options/cameras, element rules, Boundary, HKL and source previews after
deleting the original source file. Active frequency references retain edits,
arrows, amplitude/speed and camera, with animation paused. Energy-only project
restoration retains the selected result without creating a structure. Appending
a project preserves already open document objects and edited coordinates.

Reject unsupported schemas/classes, object arrays, invalid indices/cameras and
malformed files before mutating the open session. An interrupted replacement
keeps the previous project bytes and removes the temporary file. Snapshot
decoding uses a fixed class registry and numeric NPY arrays with allow_pickle=False.

## Native previews and actual inputs

The two-document synthetic project
`examples/v230_coordination_project.lele` contains periodic SrTiO3 and a five-frame
TiO6 axial-distortion trajectory. The source files in this example use portable
relative names. Native rendering of its saved and restored view is **pixel-identical**
at 1000×750 with 2× supersampling, including polyhedra, Boundary, colors, camera
and the (111) cut. These previews were inspected visually:

- `examples/v230_pair_rules.png`
- `examples/v230_polyhedron_analysis.png`
- `examples/v230_polyhedron_curve.png`
- `examples/v230_project_view.png`

The supplied OUTCAR_opt and XDATCAR each retain all 20 frames and 166 atoms.
Explicit Co/Fe/Mn/Ni/Zn → O rules with 0–2.7 Å and only-listed mode yield 68
analyzed centers: CN2=4, CN3=11, CN4=16, CN5=23, CN6=14 for each first frame.
These are geometric counts under this chosen cutoff, not chemical valences.
OUTCAR_freq retains 25 four-atom frames and 12 modes.

A combined project round-trip preserves every coordinate, cell, energy,
frequency and available displacement exactly, with all original source paths
deliberately unavailable. A live restored window opens all three documents and
the selected VASP mode, paused. See
[`qa_v2.3.0/acceptance_v230.json`](qa_v2.3.0/acceptance_v230.json).
Actual user coordinates and their private project are not bundled.

## Full regression

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=docs/qa_v2.3.0/full_v230.xml
```

Result: **542 tests and 78 subtests passed**, zero failures and zero skips,
including **45 new regressions**. Existing startup, frozen topology, Boundary,
PNG/GIF, document views and scientific-format checks remain included.
Report: [`qa_v2.3.0/full_v230.xml`](qa_v2.3.0/full_v230.xml).
