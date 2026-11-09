# LELE v3.0.1 — Step labels, final structure and Boundary defaults

Date: 2026-11-04. Baseline: v3.0.0, upstream commit `e83359d`.

## Corrected behavior

- OUTCAR rows were initially built with generic Frame labels, while selection refresh used the printed optimization cycle and renamed the selected row to Step. Both paths now use one formatter, including energies and convergence status. Printed cycle zero is retained; plain XYZ trajectories keep Frame labels, and custom NEB/conformer labels remain intact.
- A newly opened multi-frame document displays its last available structure. Selecting the file node, or its geometry group, also selects that final structure. Explicit child-step navigation and saved project frame selections remain available. Truncated final ionic records cannot replace a valid geometry, and energy-only outputs still open without a structure.
- Enable boundary display is checked by default and enabled in the renderer. The initial range is one original cell, `[0, 1)` along each lattice direction. Manually disabling it persists across step changes.
- The one-cell default retains original cell-outline ordering under display alignment, world-origin abc axes, explicit periodic fragment previews, and stored camera clipping during file switching and appearance changes.

## Validation

- 8 new GUI regressions cover stable OUTCAR labels, initial and file-node final-step selection, explicit step selection, lazy long-file paging, ordinary XYZ labels, cycle zero, truncated outputs, energy-only outputs, and the Boundary checkbox/renderer state.
- A 521-frame OUTCAR opens on frame 521 while materializing only the last 9 tree rows; the first two pages remain deferred.
- The new tests plus 5 existing Boundary/axes/fragment/camera regressions: **13 passed**.
- Complete regression suite with configured local example fixtures: **1027 passed, 78 subtests passed**, no failures, in 75.28 seconds.
- Linux Qt offscreen / VTK EGL; Python 3.12.14, Qt 6.12.0, VTK 9.7.1.

Reproduction after installing `.[test]`:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests/test_frame_defaults_v301.py -q
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests -q
```

The source package includes the complete previous release and these fixes. This validation does not claim a Windows executable build.
