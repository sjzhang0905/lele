# LELE 0.9.1 validation

Date: 2026-10-26

## Source baseline

This release continues `ChemViewStudio_v0.9.0_plane_selection_delete_20261024.zip`.
The application is renamed to **LELE — Local Environment and Lattice Explorer**.
The new Python package is `lele`; the main window is `LELEWindow`.

## Completed checks

- Complete regression suite: **119 tests passed, 61 subtests passed**, with no
  failures, errors or skipped cases. The JUnit record contains 180 passed
  test/subtest entries.
- The existing 0.9.0 feature tests run under the renamed package. Three new
  tests cover copying legacy appearance settings, preserving an existing LELE
  file and skipping an invalid legacy file.
- All Python source files compile. Python files include shebangs and contain
  no Chinese comments or strings.
- Editable installation succeeds using `pyproject.toml`.
- A source distribution and a Python wheel build successfully.
- The built wheel contains `lele` and the `lele = lele.app:main` GUI entry
  point. Import and mocked startup checks verify the application name, full
  name, version, filename arguments and `python -m lele` entry point.
- Both GitHub workflow definitions parse as YAML. Current official Action
  documentation was checked for the referenced v7 actions.
- Remaining old application-name references in active Python files are the
  explicit legacy settings-directory names and their migration test. Archived
  documents retain the names and results of their historical releases.

## Commands

```text
python -m pip install --no-deps --no-build-isolation -e ".[test]"
python -m pytest tests -q --junitxml=reports/tests.xml
python -m build --no-isolation
```

The preparation environment already supplied the runtime and build dependencies.
Linux test environment variables were `QT_QPA_PLATFORM=offscreen` and
`VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`.

## Environment and limits

- Linux, Python 3.12, VTK 9.7.1, PySide6 6.12.0 and ASE 3.29.0.
- Qt workflow tests use real controls with a headless canvas where documented
  by the tests; independent VTK tests perform off-screen rendering.
- A native Windows GUI and PyInstaller executable have not been built or
  tested in this environment.
- This record describes local validation before the initial GitHub upload.
  Current workflow runs are listed in the repository's Actions tab.
- The repository is `sjzhang0905/lele`. Original project material uses the
  proprietary, all-rights-reserved source licence in the root LICENSE file;
  separately distributed executables retain their binary-only terms.
