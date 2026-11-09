# LELE v3.0.2 — Atom labels, Boundary images, SIESTA energies and VESTA colours

Date: 2026-11-04. Baseline: the complete v3.0.1 source package.

## Use

1. Select atoms in the canvas, coordinate table or **Atoms** browser. In **Atoms → Selected labels**, use **Labels**, **Indices**, **Both** or **Hide**. Only those atoms' display overrides change; the **Labels** tab still controls the global default. The existing Label selector also supports custom text and returning to the global setting. Ctrl+Z restores the previous appearance.
2. With Boundary enabled, a periodic atom on a face appears on both sides; an atom on an edge has four images and a corner atom has eight. Every image retains the same source atom index. Selection highlights the images together; source atom counts and exported structure coordinates do not increase. Face detection uses a fractional-coordinate tolerance of 1e-8. Nonperiodic directions do not gain endpoint images.
3. Opening a new structure initializes Boundary to enabled, with one original cell, from 0 to 1 along each axis. Changes belong to that document. Switching back restores its own range and enabled state. Opening a saved project restores the project's recorded settings.
4. Open a SIESTA output, then **Energy / geometry convergence** or the calculation overview. Evaluated ionic moves carry their printed energies; the file tree retains the printed move number, including move 0. Initial coordinates and explicitly final unrelaxed coordinates are named separately and receive no borrowed energy. Energy records with no compatible printed structure remain selectable results. The source note identifies the last evaluated move and final reported total when available.
5. Select **VESTA** under **Atom colours**. This uses the upstream colours directly; the existing Default palette keeps its softened colours. Per-element/custom atom overrides continue to take precedence.

## SIESTA provenance

The supplied SIESTA 5.4.2 output was checked locally: 444 source atoms,
103 printed structures, 101 FIRE moves (0–100), and 101 E_KS energies.
All 101 evaluated structures now have their corresponding energies. The initial
and final unrelaxed structures retain no assigned energy. The last evaluated
E_KS is -543764.9260 eV; the separately printed final total is
-543764.925959 eV. SCF table iterations do not become ionic moves, and a normal
job termination is not treated as proof of geometry convergence.

The raw user output is not redistributed. Small synthetic regression fixtures
cover the same ordering, extra structures, an intermediate energy decomposition,
variable cells printed after fractional coordinates, restarts, incomplete
geometry, energy-only output and project serialization. ANI/MDE count-matching
fallbacks remain supported.

## VESTA colour source

The numeric RGB facts were read from `VESTA-win64/elements.ini` in the official
[VESTA 3.5.8 download](https://jp-minerals.org/vesta/archives/3.5.8/VESTA-win64.zip).
The table's SHA-256 is
`e77dd5dafe975347cf587d553bd26067961f9b954efd08e6bc33745b39104d99`.
Components are rounded from 0–1 to 8-bit RGB. The palette includes the printed
H/D entries and uses the table's XX grey for elements absent from that table.
Only numeric colour facts and attribution are included; the upstream ini file
and application are not redistributed.

The [VESTA manual](https://jp-minerals.org/vesta/en/doc/VESTAch18.html) describes
the default element settings. The [SIESTA tutorial](https://docs.siesta-project.org/projects/siesta/en/latest/tutorials/basic/first-encounter/index.html)
distinguishes electronic SCF iterations from the reported energy components.

## Validation

- Complete suite with the configured local reference fixtures: **1060 passed,
  78 subtests passed**, no failures or skips, in 64.90 seconds.
- 33 new regressions cover selected-atom shortcuts and undo, Boundary face/edge/
  corner images and original IDs, picking and counting, covalent/manual
  hydrogen links, limits, independent document settings and project restore,
  VESTA colour values, and SIESTA move/energy provenance and GUI curves.
- Existing Boundary, polyhedron, label and phonon tests now assert the inclusive
  outer images, including the Bloch phase on every extra equilibrium-cell image.
- The actual SIESTA file also passed Qt end-to-end checks: 101-point energy
  curve, 101-row CSV, 444 source atom rows, selected labels, VESTA switching,
  default last structure, independent one-cell Boundary and project roundtrip.
  Its final structure produced 469 display images for 444 source atoms.
- Linux Qt offscreen / VTK EGL; Python 3.12.14, Qt 6.12.0, VTK 9.7.1.

Reproduction after installing `.[test]`:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests/test_atom_display_ui_v302.py \
  tests/test_boundary_faces_v302.py tests/test_siesta_results_v302.py -q
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests -q
```

The source package includes the complete preceding release and these changes.
This validation does not claim a Windows executable build.
