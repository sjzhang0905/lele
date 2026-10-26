# LELE

**Local Environment and Lattice Explorer**

LELE is a desktop workbench for visualizing and editing molecular and periodic
structures, inspecting calculation outputs, and exploring atomic environments.
Version **1.0.0** displays the author contact below the welcome version and
includes the four-frame parrot gait, electron parity without a total electron
count, and standing-parrot application/Windows EXE icon. Commands remain grouped into menus, with X/Y/Z views and on-demand
plane fitting. LELE continues the features of ChemView Studio 0.9.0.

[中文说明](README_CN.md) · [Changes](CHANGELOG.md) · [License](LICENSE) · [Development and releases](docs/GITHUB_PREPARATION_CN.md)

Repository: [sjzhang0905/lele](https://github.com/sjzhang0905/lele)

Contact: [sjzhang0905@hotmail.com](mailto:sjzhang0905@hotmail.com)

## Current features

- A white startup page with the application name, version, shortcut reference
  and 乐乐 walking across the canvas; poses change every 0.8 seconds.
  The contact email appears immediately below the version and can be copied
  or clicked to open an email application.

- Structure import and conversion through the bundled ChemStructConverter
  backend and ASE, including XYZ, Gaussian inputs, CIF and POSCAR.
- Native VTK rendering with nine appearance presets, editable element colours,
  saved custom styles, atom labels, unit cells and XYZ/abc axes.
- Atom selection, fragment selection, inversion, deletion and undo.
- Coordinate editing, distances, angles, dihedrals and fragment transforms.
- On-demand least-squares planes from three or more selected atoms, with optional
  periodic images and rigid alignment of the structure and cell to XY.
- Frame navigation and playback for supported trajectories, including SIESTA
  output/ANI histories, and energy curves when corresponding energies exist.
- Total atom count, cell composition/formula, charge-aware electron parity, geometric hydrogen-bond
  candidates and short-contact diagnostics.
- Signed CUBE isosurfaces, PNG screenshots and structure export.

Trajectory and energy availability depend on the input format and reader.
Distance-based bonds and hydrogen-bond candidates are geometric display aids.
Edits affect the active frame; use structure export to save edited coordinates.

## Welcome canvas

Starting without files shows the welcome page and an empty Files tree. Use
**Open a file**, **Ctrl+O**, or drop files into the window. A successfully
loaded file switches to the 3D view and data inspector; a failed or cancelled
open leaves the welcome page visible. Command-line file arguments open directly.

The supplied artwork is kept in `lele/assets/lele_walk.png`. The first four
poses form the gait: **standing → left leg → standing → right leg**, repeated.
The trailing standing pose is omitted to avoid a double standing frame at
the cycle boundary. Poses are mirrored at display time so the bird faces right.
Each pose lasts **800 ms**;
the pose and horizontal position change together in a single jump. Between
frames the bird stays completely still. A **25.6-second** left-to-right pass
contains eight complete four-frame gaits and repeats while the page is visible.
The overhead name badge has been removed;
the caption “Meet 乐乐 · LELE's little explorer” remains below the animation.
The animation stops when the page is hidden.
The shortcut columns reflow and the page scrolls on smaller windows.

![Welcome header and contact](examples/welcome_preview.png)

## Planned extensions

The following are planned and are **not integrated in this release**:

- Surface, carbon-material and heterostructure builders from the author's tools.
- Expanded transformation-matrix and structure-processing utilities.
- Automated AIMD analysis, scientific plotting and SVG figure export.

## Run on Windows

Use **64-bit CPython 3.12** (recommended) or **3.11**.

1. Clone this repository, or extract its complete source archive.
2. Double-click `start_windows.bat` to create `.venv`, install dependencies and
   launch LELE.
3. Confirm that the title displays
   `LELE 1.0.0 - Local Environment and Lattice Explorer`.

To build an executable, run `build_windows.bat` after the first successful
launch. The result is `dist/LELE/LELE.exe`. Distribute the complete `dist/LELE`
directory, including `_internal`.

Both `build_windows.bat` and the Windows GitHub Actions build embed
`lele/assets/lele.ico` into the executable. The icon uses the first standing
pose, facing right on a transparent background, with sizes from 16 to 256 px.
The application window uses the same icon. Rebuild the executable to apply
the change; replacing source files does not alter an already-built EXE.

## Install from source

From the project directory, in a Python 3.11/3.12 environment:

```bash
python -m pip install -e ".[test]"
python -m lele
```

Installation also provides the `lele` GUI entry point. Open files by passing
their paths, for example `python -m lele examples/water.xyz`.

## Quick example

Open `examples/selection_plane_demo.POSCAR` and select the first four Cu atoms.
In the left **Edit** tab, click **Fit selected plane**, then **Align fitted
plane to XY**. Merely selecting atoms does not calculate or show a plane.
Changes to selection, fitted coordinates, cell or periodic-image option clear
the previous fit; click the fit button again to regenerate it. Use **Ctrl+I**
to select the remaining O atom, **Delete** to remove it, and **Ctrl+Z** to restore it.

## Menus and views

| Menu | Commands |
|---|---|
| File | Open, export structure, save PNG |
| Edit | Undo, fragment selection, invert/clear selection, delete atoms, toggle bonds, fit/align plane |
| View | Fit to window, isometry, X/Y/Z axis views, orthographic/perspective projection |
| Analysis | Energy curve |
| Help | Help and shortcuts |

The X/Y/Z views look from the positive axis toward the structure. They change
only the camera. Projection choices keep the current viewing direction, and
existing keyboard shortcuts remain available without opening a menu.

The bottom summary keeps the total atom count before the composition/formula,
then shows **Electron parity: Odd/Even** without a total electron number.
The net charge comes from the active frame or the **Net charge** input in
the Edit tab. Unknown charge is explicitly treated as neutral.

## Tests and Windows builds

```bash
python -m pytest tests -q
```

Linux off-screen test runs use `QT_QPA_PLATFORM=offscreen` and
`VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` with a compatible VTK build.

GitHub Actions definitions are included for Linux tests and a manually
triggered Windows build. The Windows workflow uploads `LELE-windows-x64` as a
workflow artifact; it does not publish a release. Test runs triggered by a push
or pull request are listed in the repository’s Actions tab. The Windows build
is started separately using Windows executable → Run workflow.

See `docs/VALIDATION_v1.0.0.md` for the local checks and their limits.

## Appearance settings

LELE uses the Qt application configuration directory under the stable
application name `LELE`. On first use, valid saved styles from known
ChemViewStudio/legacy launcher directories are copied into LELE's directory.
Existing LELE settings take priority and the original files are retained.

## Project history and notices

Earlier release notes and validation records are kept in `docs/history` under
their original project name. The bundled conversion backend retains its
ChemStructConverter name and attribution.

LELE's original source code, documentation and assets are **proprietary, with
all rights reserved**. This is not an open-source release. Use, modification
and redistribution require the author's written permission; see [LICENSE](LICENSE).

The existing binary-only terms in `licenses/BINARY_ONLY_LICENSE` apply to
separately distributed executables. Third-party components and dependencies
retain their own licences. See [SOURCE_NOTICE.md](SOURCE_NOTICE.md).
