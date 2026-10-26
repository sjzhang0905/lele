# ChemView Studio 0.5.0 — tabbed sidebar and live coordinate table

- Consolidated the former Files tree and right-hand settings panel into one left sidebar with six tabs: Files, Style, Axes, Labels, Field, Edit.
- Kept the large center VTK renderer and the bottom Coordinates / Source / Results inspector.
- Every geometry translation, alignment and manual coordinate-cell edit now uses a single refresh method that rebuilds the bottom table from the active in-memory Frame and retains atom selection.
- After an edit, the bottom Coordinates tab is shown automatically. Original input/output text remains unchanged.
- Qt signal blocking prevents table repaint from triggering spurious coordinate edits; undo re-renders the saved frame.
- Validation: 36 automated tests, 32 passing and 4 ASE-dependent skips. Windows GUI runtime has not been verified in this environment.

## Windows

1. Unpack into a fresh folder and run `start_windows.bat` using Python 3.12 x64.
2. Check the window title says 0.5 before testing.
3. Rebuild using `build_windows.bat` if you need an EXE.
4. Run from `dist/ChemViewStudio/ChemViewStudio.exe` and inspect VERSION.txt to verify the build version.
