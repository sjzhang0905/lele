# LELE v2.0.2 validation

Date: 2026-10-29 (Asia/Shanghai). Source delivery only; no GitHub commit, push,
merge or release was performed.

## Baseline and scope

The starting archive was LELE_v2.0.1.zip, SHA-256
`78259a3a2d73b4c8ed8bc14c9238debdb296b1b9ff6d3bb01237a3a69d23c407`.
The supplied independent acceptance report tested that same archive.
Its probes initially reproduced **3 failed / 4 passed**, covering A1 and A2.
B1 was a separate Windows launcher text defect.

## Results

| Check | Result | Evidence |
|---|---|---|
| Complete regression suite | **421 passed; 72 subtests passed**, 0 failures, 0 errors, 0 skips; 19.60 s | `qa_v2.0.2/full_v202.xml` |
| Original external acceptance probes, unchanged | **7 passed**, 0 failures; 0.43 s | `qa_v2.0.2/acceptance_v202.xml` |
| Added edit/geometry coverage | **23 passed** | `tests/test_edit_topology_v202.py` |
| Windows launcher text | Old v1.7.0 literal removed; compatibility message retained | Included in the 23 added tests |
| Python source/wheel build | Both built with setuptools; wheel version 2.0.2, GUI entry, three assets and MIT license present | Build metadata and archive checks |

The seven acceptance probes are also retained in the full suite as
`tests/test_acceptance_v201_regression.py`; the separate run is not seven
additional unique tests. JUnit reports 493 cases for the full suite because it
includes 421 tests and 72 subtests. The four original reproduction structures
are retained under `tests/fixtures/acceptance_v201/`.

## Verified behavior

- A1: equivalent skew and orthogonal representations give the same short-contact
  count. The reported contact is 0.474341649 Å, image shift (-2, 0, 0).
  The nearest-image geometry parameter is 1.594521872 Å, shift (-4, 0, 0).
  Returned original-basis shifts reconstruct the reported distances.
- Larger shear: a required shift (-20, 0, 0) is found. Minimum-image results
  match an independent bounded enumeration on all seven nonempty periodicity
  masks, with nonperiodic shifts constrained to zero. This is regression
  evidence on those inputs, not an exhaustive proof for arbitrary cells.
- A2: real cell-line geometry passed to the renderer follows the same rotation
  and translation as atoms. Both ordinary-cell and Boundary branches are
  checked with rotation plus translation. The external translation-only case
  places the 10 Å cell at x = -4…6 Å. Source coordinates remain unchanged.
- Editing: Alt+middle-button fragment motion does not merge nearby fragments;
  coordinate changes neither drop old long bonds nor add new close bonds.
  Explicit Ctrl+B and distance rebuilds remain effective and undoable.
- Deletion, clipboard transfer and supercell construction preserve the intended
  graph, including manually added periodic bonds moved away from their original
  nearest image before expansion. Periodic edits retain the original image edge. Undo restores graph and
  geometry; an unedited neighboring trajectory frame remains independent.

## Environment and limitations

Linux x86-64, Python 3.12.14; ASE 3.29.0, NumPy 2.3.5, SciPy 1.17.0,
PySide6 6.12.0, VTK 9.7.1, Matplotlib 3.10.8, Pillow 12.3.0, pytest 9.2.0.
Tests used Qt offscreen, VTK EGL and software rendering. The suite includes
VTK rendering/GIF checks and Qt workflow tests; some UI tests use a substitute
canvas while testing production application methods and widgets.

An extra attempt to start the unmodified production QVTK window under Qt
offscreen failed to initialize OpenGL and aborted with `std::bad_array_new_length`
before the added popup assertions. It is **not counted as a successful UI or
3D visual acceptance check**. The independent numerical renderer probes and
full regression run succeeded separately. No product changes were made to hide
this host graphics limitation.

The Windows launcher was inspected as text; its error branch was not executed
on Windows. No Windows EXE was built or tested. Rebuild with `build_windows.bat`
and perform a Windows graphics smoke check before distributing an executable.

## Reproduce

Install the project dependencies and pytest in Python 3.11/3.12, then run from
the extracted LELE directory:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
LIBGL_ALWAYS_SOFTWARE=1 python -m pytest tests -q

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests/test_acceptance_v201_regression.py -q
```

The first command requires a supported EGL/software-rendering environment;
on a desktop system use the normal Qt/display configuration instead.
