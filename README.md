# LELE

**Local Environment and Lattice Explorer**

LELE is a desktop workbench for visualizing and editing molecular and periodic
structures, inspecting calculation outputs, and exploring atomic environments.
Version **0.9.1** introduces the LELE name and Python package, continuing the
features of ChemView Studio 0.9.0.

[中文说明](README_CN.md) · [Changes](CHANGELOG.md) · [License](LICENSE) · [Development and releases](docs/GITHUB_PREPARATION_CN.md)

Repository: [sjzhang0905/lele](https://github.com/sjzhang0905/lele)

## Current features

- Structure import and conversion through the bundled ChemStructConverter
  backend and ASE, including XYZ, Gaussian inputs, CIF and POSCAR.
- Native VTK rendering with nine appearance presets, editable element colours,
  saved custom styles, atom labels, unit cells and XYZ/abc axes.
- Atom selection, fragment selection, inversion, deletion and undo.
- Coordinate editing, distances, angles, dihedrals and fragment transforms.
- Least-squares planes from three or more selected atoms, with optional
  periodic images and rigid alignment of the structure and cell to XY.
- Frame navigation and playback for supported trajectories, including SIESTA
  output/ANI histories, and energy curves when corresponding energies exist.
- Geometric hydrogen-bond candidates and short-contact diagnostics.
- Signed CUBE isosurfaces, PNG screenshots and structure export.

Trajectory and energy availability depend on the input format and reader.
Distance-based bonds and hydrogen-bond candidates are geometric display aids.
Edits affect the active frame; use structure export to save edited coordinates.

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
   `LELE 0.9.1 - Local Environment and Lattice Explorer`.

To build an executable, run `build_windows.bat` after the first successful
launch. The result is `dist/LELE/LELE.exe`. Distribute the complete `dist/LELE`
directory, including `_internal`.

## Install from source

With repository access, clone the project and install it in a Python 3.11/3.12
environment:

```bash
git clone https://github.com/sjzhang0905/lele.git
cd lele
python -m pip install -e ".[test]"
python -m lele
```

Installation also provides the `lele` GUI entry point. Open files by passing
their paths, for example `python -m lele examples/water.xyz`.

## Quick example

Open `examples/selection_plane_demo.POSCAR` and select the first four Cu atoms.
The fitted plane appears automatically. In **Edit**, choose **Align fitted
plane to XY**. Use **Ctrl+I** to select the remaining O atom, **Delete** to
remove it, and **Ctrl+Z** to restore it.

## Tests and Windows builds

```bash
python -m pytest tests -q
```

Linux off-screen test runs use `QT_QPA_PLATFORM=offscreen` and
`VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow` with a compatible VTK build.

GitHub Actions definitions are included for Linux tests and a manually
triggered Windows build. The Windows workflow uploads `LELE-windows-x64` as a
workflow artifact; it does not publish a release. Test runs triggered by a push
or pull request are listed in the repository's **Actions** tab. The Windows
build is started separately using **Windows executable → Run workflow**.

See `docs/VALIDATION_v0.9.1.md` for the local checks and their limits.

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
