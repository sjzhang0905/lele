# LELE v2.0.3 validation

Date: 2026-10-29 (Asia/Shanghai). Starting source: LELE_v2.0.2.zip,
SHA-256 `575a8d2b3a6f99981e0e1d5038db37b06a01a80ca0fe0b758a4cc49b4be92de6`.

## Results

| Check | Result | Evidence |
|---|---|---|
| Full regression suite | **437 passed; 72 subtests passed**, 0 failures/errors/skips; 21.38 s | `qa_v2.0.3/full_v203.xml` |
| New hydrogen-bond and file-view workflows | **16 passed** | `tests/test_hydrogen_bonds_and_views_v203.py` |
| Retained independent v2.0.1 acceptance probes | Included in the full suite and rerun separately | `qa_v2.0.3/acceptance_v203.xml` |

JUnit counts 509 cases because it includes the 437 tests and 72 subtests.
The separate seven-probe run repeats tests already included in the full suite;
it is not seven additional unique tests.

## User-visible regressions checked

- Native Qt Ctrl+H creates/removes a manual dashed connection. Ctrl+B changes
  only ordinary bonds, and Ctrl+Z restores each operation independently.
- Manual connections are rendered even when automatic hydrogen bonds are off.
  They do not join covalent fragments. An automatic candidate can be suppressed
  by Ctrl+H; adding a manual link does not draw duplicate lines.
- Manual periodic-image paths remain fixed when coordinates move. Clone,
  copy/paste, deletion/undo, wrapped/unwrapped supercells and Boundary copies
  preserve/remap the intended connections.
- The actual dashed line segments follow display rotation and translation with
  ordinary and Boundary scenes. Existing opacity/hidden-endpoint tests pass.
- A → B → A → B through real file-tree signals restores both complete camera
  snapshots and independent render parameters. Assertions cover direction,
  focal point, up vector, zoom, perspective/orthographic projection, window
  centre and clipping, plus element/per-atom colours and control states.
- Display round trips cover presets, manual colours, atom size, bond cutoff,
  automatic hydrogen bonds, labels/fonts, axes, isovalue/opacity/visibility,
  dipole controls and Boundary ranges. A nonperiodic file's axes fallback does
  not overwrite the periodic file's saved settings.
- Opening a new XYZ, visiting energy-only nodes (including a mixed document),
  entering a frequency from another file, and analysis-result navigation all
  retain the returning file's view. A frequency entry cannot reset it twice.
- The original startup first-paint/preload, editing, periodic geometry, export,
  rendering/GIF and independent acceptance regressions remain in the full run.

## Environment and limits

Linux x86-64, Python 3.12.14, ASE 3.29.0, NumPy 2.3.5, SciPy 1.17.0,
PySide6 6.12.0, VTK 9.7.1, Matplotlib 3.10.8, Pillow 12.3.0, pytest 9.2.0.
Tests use Qt offscreen, VTK EGL and software rendering.

UI workflow tests use production window methods, Qt widgets/actions and a real
VTK scene/camera, with a substitute canvas that suppresses native-window
rendering. Dashed-line checks inspect geometry sent into the renderer.
The full suite also includes independent offscreen rendering/GIF tests; these
do not constitute a Windows embedded-window visual acceptance check.

No Windows EXE was built or run. Rebuild using `build_windows.bat` for Windows
delivery. No GitHub commit, push, merge or release was performed. View settings
and manual link overrides are session data, not a new persistent project format.

## Reproduce

From the extracted source with project dependencies and pytest installed:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
LIBGL_ALWAYS_SOFTWARE=1 python -m pytest tests -q

QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests/test_hydrogen_bonds_and_views_v203.py -q
```

On a desktop, use the normal Qt/display configuration when offscreen EGL is
unavailable. Source ZIP integrity and Python wheel/source build metadata are
checked during packaging.
