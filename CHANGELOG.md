# Changelog

## 1.0.1 — 2026-10-26

- Switch original LELE source, documentation, assets and author-distributed
  binaries to the MIT License. Update package metadata and distribution
  notices, and archive the superseded binary-only terms as historical text.
- Add a selectable, clickable GitHub repository URL below the contact email
  on the welcome page.
- Set the application, package and Windows launcher version to 1.0.1.
- Include the MIT license and source/distribution notice in Windows build outputs.

## 1.0.0 — 2026-10-26

- Display sjzhang0905@hotmail.com immediately below the welcome version;
  support copying the address and opening the user's email application.
- Set the application and package version to 1.0.0 and include the author
  email in package metadata.
- Bring the white welcome page, four-frame step animation, grouped menus,
  X/Y/Z views, manual plane fitting, atom count, electron parity and standing
  parrot icon into the GitHub source release, retaining the proprietary license.

## 0.9.5 — 2026-10-26

- Repeat the four-frame standing / left leg / standing / right leg gait,
  dropping the redundant trailing standing pose. Keep 800 ms per frame and
  use 32 steps (25.6 seconds) per canvas pass so both loop boundaries remain
  aligned to complete gaits. Regenerate the animation-only GIF preview.
- Restore electron parity and the frame-specific net-charge control. Display
  Odd/Even and the charge assumption, without showing the total electron count.
- Extract the first standing pose into a transparent multi-size Windows icon.
  Set the application/window icon and Windows taskbar identity; embed the ICO
  through both local and GitHub Actions Windows builds. Include it in wheels.
- Print the actual built version from VERSION.txt instead of a stale hardcoded
  version in the Windows build script.

## 0.9.4 — 2026-10-26

- Replace the wide command toolbar with File, Edit, View, Analysis and Help
  menus, preserving existing keyboard shortcuts.
- Replace Front/Top/Side commands with X/Y/Z views from each positive axis.
  Move orthographic/perspective projection choices into View > Projection
  and keep their checked state in sync with the camera.
- Put the current frame's total atom count before its cell composition/formula.
  Remove electron-count display and its charge-counting control from the UI.
- Generate a best-fit plane only through the Fit selected plane button or
  menu command. Invalidate it after selection, fitted-coordinate, cell,
  periodic-image option or frame changes. Keep explicit XY alignment and undo.

## 0.9.3 — 2026-10-26

- Change the parrot walk to discrete steps: every 800 ms, pose and position
  update together. Keep the bird stationary between frames.
- Remove the overhead 乐乐 badge; retain the caption below the animation.
- Update timing regression checks and regenerate the welcome previews.

## 0.9.2 — 2026-10-26

- Replace the empty black startup canvas with a pure-white welcome page.
- Show the centralized application name, full name and version above the
  supplied parrot, named 乐乐, and the currently supported shortcut reference.
- Animate five right-facing poses at 800 ms per pose with smooth, looping
  left-to-right travel across the canvas. Stop both clocks when hidden.
- Keep the empty Files tree document-free; switch to the 3D view and data
  inspector only after a file loads. Defer VTK initialization until then.
- Support the welcome open button, existing Ctrl+O and file drops. Reflow
  shortcut columns and allow vertical scrolling in smaller windows.
- Include the artwork in source, wheel and PyInstaller distributions.

## 0.9.1 — 2026-10-26

- Rename the application to **LELE — Local Environment and Lattice Explorer**.
- Rename the Python package to `lele` and the main window to `LELEWindow`.
- Update the launcher, help title, default screenshot name and Windows build
  output to use LELE. Centralize the runtime name and version.
- Set a stable Qt application name and import valid legacy display presets
  without overwriting LELE settings.
- Add Python packaging metadata, English/Chinese READMEs, Git rules and GitHub
  Actions definitions for tests and manual Windows builds.
- Archive earlier release notes and validation records under `docs/history`.
- Establish the `sjzhang0905/lele` source repository and add proprietary,
  all-rights-reserved source licensing alongside the existing binary terms.

The source tree continues the fitted-plane, selection, deletion, undo and
appearance features of 0.9.0. Surface/heterostructure builders and automated
AIMD analysis remain planned extensions.
