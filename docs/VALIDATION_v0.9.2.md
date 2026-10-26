# LELE 0.9.2 validation

Date: 2026-10-26

## Scope

Baseline: `LELE_v0.9.1_GitHub_ready_20261026.zip`.
This update adds the white startup page, the supplied parrot artwork and its
animation, the current shortcut reference, and the required packaging data.

## Completed checks

- Full regression suite: **126 tests passed, 61 subtests passed**, with no
  failures or skips (187 passed JUnit entries).
- Seven new tests exercise empty startup, document-free Files state, no early
  VTK initialization, opening with the welcome button and Ctrl+O, file drops,
  command-line paths, failed opens, real 800 ms pose timing, paused hidden
  animation, rightward travel, name placement and responsive shortcut columns.
- A real Qt main window was rendered at 1380 x 850 with the native VTK widget
  hidden. The welcome canvas is white, the Files tree is empty and the native
  VTK interactor is uninitialized until a file is opened.
- The welcome canvas was visually inspected at its normal width; live layout
  tests cover 1020, 760 and 510 pixel widths with three, two and one shortcut
  columns respectively. No horizontal scrolling is needed.
- All five crops share a baseline, contain one complete bird and face right.
  The source strip is unchanged. Pose duration is 800 ms; each smooth travel
  cycle lasts 24 seconds. The supplied PNG needs no extra runtime dependency.
- A source distribution and wheel build successfully. Both include
  `lele/assets/lele_walk.png`. Its wheel bytes match the supplied artwork.
- A welcome page was instantiated using only the extracted wheel on
  `PYTHONPATH` from outside the source tree, and all five poses loaded.
- Both the local Windows build script and the GitHub Windows workflow include
  `--collect-data lele` for PyInstaller. The package-data and source-manifest
  declarations include the artwork.
- Runtime version, README instructions and Windows launch/build messages use
  0.9.2. Windows batch files retain CRLF line endings.

## Preview files

- `examples/welcome_preview.png`: rendered welcome canvas.
- `examples/welcome_preview.gif`: 24-second rendered preview; 200 ms preview
  samples preserve the exact 800 ms pose duration. Runtime horizontal movement
  uses Qt's smooth property animation rather than the preview sampling rate.

## Environment and limits

Linux, Python 3.12.14, PySide6 6.12.0, VTK 9.7.1 and ASE 3.29.0.
Qt uses the offscreen platform and standalone VTK tests use EGL.

The preinstalled VTK 9.3.1 X11 build could not run the headless rendering tests;
the complete passing run used VTK 9.7.1 instead. Embedded Qt/VTK OpenGL rendering
cannot be validated on this offscreen Qt surface. File-opening workflow tests
therefore use real Qt controls and a real VTK scene with a headless canvas;
independent VTK rendering tests remain part of the passing full suite.

A native Windows GUI and a Windows PyInstaller executable have not been run
or built here. GitHub workflows have not been executed and no repository
changes have been pushed. Run `build_windows.bat` to rebuild an existing EXE
from the updated source.

The screenshots used an installed CJK font for the name 乐乐. The application
uses system font fallback (including Microsoft YaHei UI on Chinese Windows);
no downloaded font is part of this source package.

## Commands

```text
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow python -m pytest tests -q
python -m build --no-isolation
```
