# Changelog

## 2.0.3 — 2026-10-29

- Add Ctrl+H and Edit-page/menu controls for an undoable dashed hydrogen bond
  between two selected atoms. Keep Ctrl+B and covalent fragment connectivity
  independent. Manual links work without enabling automatic candidates.
- Avoid duplicate automatic/manual lines and allow Ctrl+H to suppress an
  existing automatic candidate. Preserve manual image paths during edits,
  deletion, copy/paste, Boundary display, alignment and supercell construction.
- Retain an independent camera and full RenderOptions for each open document.
  Restore view direction, zoom, pan, projection, colours, labels, axes, fields,
  dipoles, Boundary and preset/custom state together with their controls.
- Route geometry, frequency, result-navigation and energy-only entries through
  the same document activation. Fit a new file once; returning to a file no
  longer resets its saved camera. Settings remain session-local.
- Add 16 regressions covering manual bonds and multi-document round trips.
  Full Linux regression: 437 tests and 72 subtests passed. Deliver the full
  source archive; Windows EXE requires a rebuild.

## 2.0.2 — 2026-10-29

- Search non-reduced periodic lattices using Minkowski reduction and a
  cutoff-derived neighbor list; map image shifts back to the input basis.
  Correct minimum images for fully and partially periodic structures.
- Apply display rotation and translation to unit-cell outlines, Boundary
  copies and fragment preview geometry without changing source coordinates.
- Remove the obsolete hardcoded version from the Windows Python error.
- Capture connectivity before geometry edits. Fragment gestures, coordinate
  changes, deletion, copy/paste and supercell construction preserve the graph;
  undo restores it. Periodic bonds retain their original image connection.
- Keep Ctrl+B as an explicit bond command and add Edit → Rebuild bonds from
  distances for an undoable rebuild with the current cutoff and manual overrides.
- Retain the seven independent acceptance probes and add 23 regressions.
  Full Linux regression: 421 tests and 72 subtests passed. The unchanged
  external acceptance probes also passed (7/7). No Windows EXE was built.

## 2.0.1 — 2026-10-29

- Compact the footer: Composition for periodic cells, electrons even/odd,
  concise atom/formula fields and measurements without colons. Keep detailed
  charge/parity provenance in the footer tooltip.
- Show only the short-contact count in a clickable footer control. Its dialog
  lists the source atom pairs, distances and periodic image translations,
  with a clearly identified geometry snapshot and an explicit empty state.
- Share one distinct-pair minimum-image contact enumeration between counts
  and details; image translations refer to the original coordinates.
- Add periodic cell volume as the absolute determinant in Å³ to Results / info,
  updating with frame changes while omitting it for nonperiodic structures.
- Retain all 2.0.0 features. Windows EXE still requires a Windows rebuild.

## 2.0.0 — 2026-10-28

- Find normal modes by selected atoms' squared Cartesian displacement share;
  filter imaginary modes and share thresholds, play modes, export shown rows,
  and render static displacement arrows with selected-atom and length controls.
- Monitor multiple distances, angles and dihedrals over stage-local trajectories,
  NEB paths or image histories. Add plane/vector angles and point-to-plane/line
  distances, explicit periodic images, dihedral unwrapping, statistics and CSV.
  Curve points navigate to the correct source frame and preserve the sequence.
- Align trajectory display to a reference using all atoms or a selected scaffold.
  Apply translation and proper rotation without changing source coordinates,
  cells, energies or structure exports; PNG and GIF reflect the aligned view.
  Disable alignment before coordinate/bond edits; incompatible atom orders are
  displayed unchanged with an explanatory note.
- Show every coordinate-free xTB energy record in the Files tree. Selecting a
  record shows its cycle, energy in Eh/eV/kcal/mol and source line; it never
  substitutes an unrelated final structure or a placeholder frame.
- Retain all previously delivered Gaussian/ORCA/xTB and NEB/GOAT/SOC features.
  Add 33 selection-analysis regressions. Full Linux regression: 380 tests and
  72 subtests passed; a real 175-cycle energy-only xTB file was checked in UI.

## 1.11.1 — 2026-10-28

- Load xTB energies/orbitals independently of coordinates. Energy-only documents
  have no placeholder geometry; show a results/source page with available data.
- Keep coordinate-only files usable without energy. Disable empty curve entries
  while retaining structure navigation, playback and exports.
- Stop requiring geometry for calculation overviews and file status. Safely
  handle frame shortcuts and switching between data-only and structure files.
- Keep verified trajectory association optional; do not fill missing structures
  from an unrelated or unanchored neighboring file.
- Add ten independent-data regressions and examples. Full regression:
  347 tests and 72 subtests passed.

## 1.11.0 — 2026-10-28

- Read xTB/g-xTB optimization stdout, explicit final structures and Xmol
  optimization trajectories, including Hartree energies in XYZ comments.
- Match same-directory trajectory companions by the full cycle-energy sequence,
  atom order and final coordinates; keep unmatched cycles energy-only.
- Add xTB energy curves with cycle navigation, source energy units and complete
  CSV export, including cycles without coordinates. Keep ANC/gradient norms
  separate from Cartesian maximum/RMS convergence metrics.
- Preserve explicit HOMO/LUMO labels for fractional occupations, blank virtual
  occupations, original MO numbers, and separate alpha/beta tables and gaps.
  Retain the printed summary gap independently, merge repeated final tables,
  and continue opening orbitals only on request.
- Distinguish optimization convergence, Finished run and explicit normal
  termination; preserve precise final single-point and trajectory energy values.
- Verify all three supplied real xTB files and add 26 regressions plus synthetic
  examples and Qt previews. Full regression: 337 tests and 72 subtests passed.

## 1.10.0 — 2026-10-28

- Separate ORCA reactant/product preoptimization, NEB, TS refinement and final
  frequency stages; retain each stage's convergence and prevent later energies
  from overwriting an endpoint. Ignore warning banners when collecting input.
- Distinguish exact/model/read Hessians and optimizer updates, preserve parent
  cycles, and exclude numerical displacement coordinates/energies/properties
  from optimization histories. Separate optimization modes from final checks.
- Add source-labelled NEB path snapshots, fixed-image histories, force curves,
  CI and refined-TS access, energy units and CSV export. Match MEP XYZ to printed
  energy vectors and leave unmatched snapshots energy-only.
- Group result sequences in Files; navigation, playback and GIF export follow
  the current stage, path, image history or conformer ensemble.
- Add GOAT final-ensemble and XYZ reading, printed populations/degeneracies,
  Boltzmann populations at a chosen temperature, aligned same-order RMSD,
  conformer navigation and CSV export, including energy-only results.
- Add common TDDFT complex triplet/singlet SOC and printed sparse scalar SOC,
  component heatmaps, mixed-state coefficients, SOC-corrected absorption and
  CSV export while preserving separate spin-free TD/TDA results.
- Add synthetic examples, twenty workflow regressions and Qt screenshots;
  verify actual NEB/Hessian attachments and thirteen public ORCA outputs.

## 1.9.0 — 2026-10-28

- Open HOMO/LUMO only from the Files-page button or Analysis menu.
- Repeat the current selection measurement beside Short contacts, updating on
  selection, frame changes and coordinate edits.
- Extend common ORCA 4/5/6 outputs to isolated geometry histories, job and
  compound-job metadata, occupations, SCF cycles, spin and frequency summaries,
  convergence and clickable frame mapping.
- Read ORCA Cartesian normal modes, imaginary frequencies, IR/Raman tables and
  distinguish legacy printed T² from integrated km/mol intensities.
- Read permanent/state dipoles and classic/new electronic, velocity and magnetic
  transition-moment tables; retain signed contributions and printed weights.
- Match spin-local transition labels to global STATE numbers without duplicating
  triplets; preserve original labels in CSV and prevent cross-job property reuse.
- Accept UTF-8 BOM and Windows UTF-16 redirected text output.

## 1.8.0 — 2026-10-28

- Accumulate successive box selections and undo each completed addition through
  the shared selection/edit history; add Ctrl+A without overriding text editors.
- Draw a high-contrast unfilled dashed outline in a native VTK overlay layer.
- Fade connected bonds faster than atom spheres using squared endpoint opacity.
- Propagate atom colour, opacity, visibility and labels to compatible geometry
  frames and vibration references in the same file. Undo restores display maps
  independently of positions/bonds and remains valid after geometry undo.
- Read Gaussian/ORCA calculation segments, printed orbital occupations/energies
  and maximum/RMS convergence. Keep Gaussian charge/multiplicity per segment,
  including identical geometries belonging to different charge states (A1).
- Open molecular HOMO/LUMO summaries automatically when printed orbital tables
  are found; default to eV and show alpha/beta channels separately.
- Add calculation overviews and energy/convergence plots with point-to-frame
  navigation, scan-endpoint filtering, source thresholds and CSV export.
- Read signed excited-state orbital contributions, preserve forward/backward
  rows and printed ORCA weights, and expose them in tables and CSVs.
- Add synthetic Gaussian/ORCA examples and actual Qt/VTK rendering previews.

## 1.7.2 — 2026-10-28

- Render bottom-left XYZ/abc letters directly as billboards in the overlay
  renderer, keeping their anchors and marker size stable during camera gestures.
- Hide Gaussian's unknown-symmetry `-?Sym` placeholder in the excited-state
  table while retaining real symmetry labels and the original CSV description.
- Let dipole Scale accept typed decimals; commit on Enter or focus loss and
  preserve unfinished input during redraws.
- Keep axis and dipole shaft/head widths fixed when vector lengths change.
- Replace platform-dependent filled rubber bands with masked, transparent,
  dashed selection outlines; add Ctrl+Shift+B to toggle and Esc to exit.
- Verify atom/bond transparency linkage through the real appearance editor,
  undo and Boundary copies; clarify the lower-endpoint opacity rule.
- Change Boundary from fractional clipping to full-cell integer ranges. Repeat
  every atom in each original-sized cell and draw the internal unit-cell edges.
  Keep source coordinates, cell vectors and source IDs unchanged.
- Add GUI, native-rendering and geometry regressions plus synthetic previews.

## 1.7.1 — 2026-10-28

- Make Ctrl+G build a real, undoable supercell when completing a finite
  cross-boundary fragment. Map each selected periodic image to its own atom ID.
- Refresh Coordinates, the Atoms panel and atom counts from that expanded
  frame; Ctrl+I, coordinate edits, copy/paste, deletion and export use its atoms.
- Reuse the existing supercell rules for skew cells, partial periodicity,
  per-atom display settings, manual bonds, charge, energy and volume detachment.
- Preserve the original frame, selection and attached field for Ctrl+Z; leave
  other trajectory frames unchanged and avoid repeating an already complete
  fragment. Selection wholly inside a cell still creates no geometry edit.
- Update the coordinate-table test double for the shared element-list refresh
  introduced by the previous A2/A3 repair.

## 1.7.0 — 2026-10-27

- Reimplement the missing 1.4/1.5 feature set while retaining 1.6.0 real supercells.
- Restore 2× supersampling/Lanczos, shared sampled palettes and optional GIF
  dithering; preserve atomic cancellation, timing and live camera/playback.
- Restore source-directory save defaults and camera-facing corner-axis letters.
- Preserve ASE eV internally; display molecular-program energy in kcal/mol and
  periodic-program energy in eV. Clear stale energy after nonrigid edits.
- Restore Gaussian Raman activities, IR/Raman/UV-Vis simulated spectra and raw
  transition tables, distinct from sampled spectrum curves.
- Read length/velocity/magnetic transition tables separately; distinguish SCF,
  excited permanent and electric transition moments. Add typed arrows, PNGs,
  dipole CSVs and transition CSVs with units and oscillator-strength checks.
- Filter occluded long automatic bonds while preserving rings and manual links.
- Restore cross-file atom clipboard/paste placement, native rectangle selection,
  disclosure-only atom-group expansion and fractional Boundary displays with
  source atom IDs, styles, periodic bonds, picking, PNG and GIF exports.
- Add synthetic examples, native rendering evidence and regressions. Source is
  a verified reimplementation, not a byte-for-byte recovery of the lost files.
- Post-acceptance repair: atom paste now detaches stale volumetric fields while
  preserving them for Undo, and immediately refreshes the Edit-page element
  selector when pasted atoms introduce a new element.

## 1.6.0 — 2026-10-27 (rebuild from 1.3.0)

- Rebuild from the available 1.3.0 source after the intervening local sources
  became unavailable. The missing 1.4.0/1.5.0 changes are not included.
- Add Edit → Build supercell: repeat the current periodic frame along a/b/c,
  enlarge the actual unit cell, and export the resulting full structure.
- Support skew lattices, optional periodic coordinate wrapping and partial PBC.
  Preview the new atom count and cap interactive supercells at 50,000 atoms.
- Preserve atom colours, visibility, transparency, labels and POSCAR block
  metadata. Map manual bonds to their actual periodic image paths.
- Scale known cell charge; clear source energy and unestablished multiplicity.
  Detach the old volume and restore it with coordinates and metadata on Undo.
- Keep other trajectory frames unchanged. Add backend, export round-trip,
  native-rendering and Qt workflow checks plus a Chinese supercell guide.

## 1.3.0 — 2026-10-27

- Add File → Export animation GIF for geometry/optimization trajectories and
  the selected vibration mode, using the current camera, colours and labels.
- Let users set output width, FPS and looping; retain the canvas aspect ratio.
  Add trajectory frame range, stride and forward/backward playback, and
  vibration amplitude and cycle duration controls.
- Render one complete vibration cycle without a repeated final pose. Avoid
  repeated trajectory endpoints during forward/backward looping and distribute
  GIF timing ticks to avoid accumulated frame-rate rounding errors.
- Use a separate native offscreen canvas and stream frames to a temporary file.
  Show cancellable progress, preserve existing files on cancellation/error,
  and restore live playback without changing source coordinates or camera.
- Add Pillow as an explicit dependency, preload its encoder after first paint,
  and verify updated dependencies in Windows launch/build helpers.
- Add decoded-image/native-rendering regressions, options-dialog checks and
  synthetic export previews. Advance application and package to 1.3.0.

## 1.2.0 — 2026-10-27

- Read Gaussian harmonic frequencies, IR intensities, reduced masses, force
  constants and Cartesian normal-mode vectors alongside the geometry history.
  Associate each frequency calculation with its own printed orientation,
  including combined Opt+Freq and multiple Link1 jobs.
- Group geometry/optimization frames and frequency calculations in the Files
  tree. List every printed mode, mark imaginary frequencies, and start a
  reversible vibration preview when a mode is selected with mouse or keyboard.
- Add pause/resume, stop/reset, amplitude and visual speed controls. Retain
  reference connectivity, camera orientation and source coordinates during
  animation; show reference coordinates in the table and structure exports.
- Keep incomplete modes visible with animation disabled. Separate reference
  geometry from editable optimization frames, and stop vibration on frame/file
  changes or application closing. Retain per-atom appearance and undo.
- Add a synthetic Opt+Freq example, an animation preview and regression tests.
  Update application, welcome page, package and launcher version to 1.2.0.

## 1.1.1 — 2026-10-27

- Accept precise decimal and scientific-notation isovalues with up to 12
  decimal places, instead of the four-decimal input limit. Allow values down
  to 1e-12 while retaining the existing arrow step.
- Commit typed values on Enter, Apply or focus loss so intermediate digits do
  not trigger isosurface reconstruction. Keep keyboard/clipboard editing and
  the up/down controls available, with an input hint beside the field.
- Update the application, welcome page, package and launcher notices to 1.1.1.

## 1.1.0 — 2026-10-27

- Advance application, welcome page, package metadata and launcher notices to
  1.1.0 for the feature release containing the following UI/startup changes.

- Add an Atoms sidebar tab with element groups, original atom indices, per-atom
  visibility, colour, transparency, label modes and custom text. Support applying
  settings to multiple atoms or an entire element group.
- Keep display overrides on their owning frame, preserve them through undo and
  reindex them when atoms are deleted. Apply them consistently to periodic
  replicas, bond/hydrogen-bond drawing, labels, highlights and mouse picking.
- Split the lower inspector into two resizable equal columns. Keep compact,
  editable coordinates and the existing text/info tabs on the left; reserve a
  blank panel on the right. Keep the atom/composition/parity summary across both.

- Show the welcome window before importing NumPy, SciPy, ASE or VTK, then
  automatically preload libraries/readers in a worker thread after first paint.
  Prepare the hidden 3D canvas on the GUI thread and report readiness in the
  status bar; welcome animation and menus remain available during imports.
- Queue files selected during startup, including command-line files, and open
  them when ready. Preserve display settings and reuse the prepared backend.
- Keep imports alive safely through application shutdown, handle loading
  failures and retries, and avoid creating canvases after a window is closed.
- Test first-paint ordering, worker/GUI thread separation, responsiveness,
  file queues, early closing, settings transfer and backend reuse.

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
