# Changelog

## 3.0.0 — 2026-11-03

- Default PNG saving to 4× canvas resolution with Smooth edges enabled.
- Update application and package version to 3.0.0.

## 2.13.6 — 2026-11-03

- Fix high-resolution PNG corner axes shrinking or clipping at 3×/4× with smooth edges. Capture independent overlay renderers, actors and text properties so orientation-widget callbacks cannot reframe tiled exports or corrupt live billboard caches.
- Fit complete XYZ/abc corner labels inside their viewport with glyph-based pixel margins. Re-evaluate after camera rotation, font changes and canvas resizing, while keeping arrow geometry and scene bounds independent of text layout.
- Add rendered-image regressions for all 1×–4×/smoothing combinations, label margins at multiple fonts/rotations, and overlay restoration after failure.

## 2.13.5 — 2026-11-03

- Set default Ball and stick bond thickness to 7 and enlarge Default-palette H display radii by 15%, sharing the same radius between glyphs, labels, picking, selection and the legend.
- Mix a further 5% white into the current Default colors (approximately 14.5% white relative to the original palette).
- Add PNG resolution choices of 1×/2×/3×/4× or a custom width, with 3× and smooth edges enabled by default. Use supersampling, Lanczos downsampling, finer export meshes and scaled annotations. Restore the live scene after capture and replace an existing file only after a successful save.

## 2.13.4 — 2026-11-03

- Rename the Atom colours palette from Sibyl to Default and soften its source colors by mixing in 10% white, consistently across atoms, element-colored bonds, legends and the color editor. Keep the original reference RGB table intact and accept the former palette name in saved presets and projects.
- Reduce default ball-and-stick atom size from 60% to 50% and bond thickness from 11 to 9; initialize sliders from the render options. Keep pure-white background and Glossy lighting.

## 2.13.3 — 2026-11-03

- Keep the footer at its native editor height while measurement controls are hidden, so selecting two to four atoms or clearing selection never changes the canvas size. Derive the height from polished Qt control size hints for the active font/style.
- Use pure white (#FFFFFF) for new render options, the default Classic ball and stick preset, and the Light background button.

## 2.13.2 — 2026-11-03

- Parse PQR ATOM/HETATM whitespace fields consistently, with optional chain IDs, tabs, large coordinates and a separate fixed-column fallback. Preserve elements and coordinates from the same record layout; report malformed atom rows instead of silently losing atoms. Distinguish common biomolecular atom labels from ion element names.
- Share normalized CUBE header input between legacy atom conversion and native field loading. Support all-negative Angstrom grid counts without rewriting source files; use consistent units for atoms, origin, voxel vectors and cell. Preserve scalar field values, signed atom-count labels, ASE field ordering and CASTEP boundary-plane handling.
- Retain valid CUBE geometry when the field is incomplete, too large or multi-channel, with an explicit availability note. Reject invalid/mixed grid units and propagate cancellation.
- Add PQR/CUBE regression and export/project checks; retain the full-acceptance independent assertions. See docs/VALIDATION_v2.13.2.md for current results and reproduction.

## 2.13.1 — 2026-11-03

- Fix skew-cell CIF import at periodic faces: keep wrapped matching coordinates strictly inside the KD-tree's half-open [0,1) box when floating-point remainder rounds to 1. Do not move source Cartesian coordinates.
- Write native CIF site components with double-precision round-trip occupancies and coordinates. Preserve minority-component source row order, including interleaved rows, and append new component rows after existing ones. Keep strict overoccupancy validation and P1 symmetry-expanded export.
- Preserve surviving atom identities on paste; assign fresh identities to added atoms and supercell replicas. Geometry monitors and appearance synchronization use partial validated identity mappings so an unrelated deleted/replaced atom does not redirect an O–H monitor. Selected alignment/vibration/coordination atoms use the same mapping, while missing identities remain unavailable.
- Preserve original per-atom POSCAR block membership when reindexing; independent adjacent blocks of the same element stay separate. Carry block and CIF component-row metadata through projects, deletion, reindexing, clipboard operations and supercells.
- Retain the independent 11-case delta acceptance unchanged and add 31 regressions. Full Linux suite: 912 tests and 78 subtests pass with private examples enabled. Recheck production Qt/VTK defaults, axes, index dialogs, vacuum, footer and selection outlines.

## 2.13.0 — 2026-11-02

- Default to Glossy lighting and the 111-element H–Rg palette extracted from the supplied Sibyl.tcl. Share palette lookup between native atom/bond rendering, legends and the color editor, including before a 3D view exists. Keep existing explicitly saved palettes, finishes and atom overrides.
- Remove the welcome-page Open a file / Ctrl+O button and the drop-a-structure hint. Retain File → Open, Ctrl+O, drag/drop, the parrot animation and shortcut table.
- Add an automatic axes basis, defaulting to true abc cell vectors for valid periodic structures and XYZ for molecules or invalid cells. Support explicit choices, per-document switching, native render exports and project persistence.
- Preserve current atom order in all five structure export formats and remove element sorting from both legacy POSCAR writers. Appended atoms retain addition order; explicit reindexing still defines the current row order. Preserve the prior selective-dynamics and species-block fixes.
- Add 18 regressions and update startup/style assertions for the requested UI/default changes. Full suite: 870 tests plus 78 subtests pass with private examples enabled. Verify actual startup, periodic/molecular axis switching, the supplied RGB values and export order with the production Qt/VTK path.

## 2.12.1 — 2026-11-02

- Fix A1: rebuild CIF site probabilities from each input species' unique symmetry orbit, merging periodic aliases and equivalent orbit representatives without losing minority species or double-counting redundant representatives. Preserve compositions and probabilities on CIF round trips; reject conflicting equivalent occupancies.
- Fix A2: retain per-atom, per-axis VASP selective-dynamics flags through import, edits, reindexing and projects. Write both Direct and Cartesian POSCAR without sorting atoms, preserving consecutive species blocks and constraints.
- Fix A3: share validated source-identity mappings across geometry curves, appearance synchronization, display alignment, vibration selections, coordination trajectories and dipole fitting. New monitors capture their reference identities in projects; unmappable targets leave gaps or are skipped.
- Fix B1: confirming the existing vacuum is a true no-op, preserving energy, convergence and undo history. Keep the original precision when the dialog's rounded value is untouched.
- Fix B2: retain confirmed slab surface projections after changing vacuum, so an external gap smaller than internal layer spacings can be reopened and edited. Store this evidence in projects and recognize matching v2.12.0 vacuum records.
- Fix B3: queue summary alignment from actual window/status-bar layout events and apply pending layout geometry before calculating corrections.
- Fix B4: infer P1 when an unnamed CIF explicitly supplies only identity operations, including Chemcraft input without occupancy columns. Report unnamed nonidentity symmetry without guessing a group.
- Retain the independent 12-case acceptance assertions and add 34 regressions. Full Linux suite: 852 tests and 78 subtests pass with the supplied private examples; native window/click/dialog checks pass. Preserve the unfilled green dashed selection outline.

## 2.12.0 — 2026-11-02

- Preserve CIF fractional and mixed-site occupancies through symmetry expansion, projects, Boundary, supercells, deletion and the native clipboard. Render species-proportional sphere sectors and a pale vacancy sector; include minority species in the legend, weighted composition and an unknown integer-electron parity. Preserve occupancy in CIF export and reject silent conversion to fully occupied calculation inputs.
- Add right-click atom index dialogs with 1-based move-to-index and two-selection index swap. Reorder coordinates, species, occupancies, force vectors, appearance and ordinary/hydrogen-bond indices together; preserve current-frame scalar results and atom order in POSCAR export. Empty-space right-click still clears selection; right-drag still rolls the camera.
- Detect slab outermost atomic planes and the largest periodic vacuum gap along the three cell normals. Adjust only the chosen cell vector's normal component, preserving all Cartesian coordinates, in-plane components and the other two cell vectors. Reject boundary-split slabs that cannot meet the fixed-coordinate requirement; support undo and clear invalidated calculation data.
- Dynamically align the bottom summary with the coordinate-pane left edge as the window layout changes.
- Replace the selected-atom wire mesh with an unfilled, thick green dashed camera-facing outline. Preserve atom colors and center labels; use explicit line gaps across native VTK backends.

## 2.11.0 — 2026-11-02

- Fix periodic XYZ pair alignment: use the nearest periodic bond and rotate coordinates and lattice together. Keep the first atom fixed and co-rotate attached volume grids. Clearly label a/b/c as fixed-cell relative-geometry edits.
- Add origin/X/Z crystal reorientation with automatic proper rotation and Z-priority Gram–Schmidt axes matching the supplied rotation script. Accept a pasted row-vector rotation matrix, preview its values and reject collinear axes, scale, shear and reflection.
- Center periodic atom representatives around the selected origin with the complete lattice metric; remap frozen ordinary/hydrogen-bond image shifts, preserve scalar energies and convergence for rigidly equivalent periodic structures, and rotate available QE force vectors.
- Preserve reorientation matrices in frame information and projects, support undo of cell/coordinates/grids, process nearest-image centering with background progress, and preserve atom order in reoriented POSCAR exports.
- Add synthetic geometry, live GUI, project/export round-trip, supplied-script convention and actual POSCAR1/POSCAR2 compatibility regressions. Retain the v2.10.1 acceptance fixes.

## 2.10.1 — 2026-11-02

- Fix A1: require explicit QE BFGS convergence, with failed/max-step/error exits taking priority within their PWSCF job. Keep normal process completion separate from optimization status and retain convergence only on matching final-coordinate reprints.
- Fix A2: independently read CP2K CELL and TOPOLOGY MULTIPLE_UNIT_CELL. Use the original unit cell for fractional coordinates and replica translations; preserve CP2K's X-fastest replica order, atom kinds and periodic axes. Explain mismatched repeated-topology input compatibility in the import note.
- Fix A3: support CP2K ANGLES as an ALPHA_BETA_GAMMA alias, including explicit degree/radian units. Report invalid angles instead of silently showing an orthogonal or degenerate cell.
- Retain the independent acceptance expectations as permanent regressions, correct the old QE success fixture, and extend coverage to failure priority, separate jobs, oblique cells, unequal repeats, invalid geometry and project round trips.

## 2.10.0 — 2026-10-30

- Add dedicated QE PW input/results objects. Preserve parsed namelists, species, cells and source Rydberg energies; retain variable-cell ionic histories and distinct final SCF evaluations, Cartesian force summaries and confirmed geometry convergence. Keep ASE-compatible unit conversion and the existing linear trajectory API.
- Recognize PHONON stdout independently of PWSCF, including nonstandard suffixes; retain each q-point frequency set and its available reference without inventing displacement vectors. Keep frequency-only results usable when geometry is absent.
- Import normalized matdyn .modes as standalone results. Add explicit reference-structure, frame and alat association. Keep all q-point occurrences and complex vector components, without additional mass weighting. Do not merge PHONON and matdyn frequency sets.
- Animate phonons with Bloch phase across Boundary cells; support polarization arrows, participation analysis, q-labeled frequency trees/CSV, project persistence and native PNG/GIF export. Keep reference coordinates and source results intact.
- Add synthetic and supplied-file coverage. Do not redistribute the four private input files; include their acceptance record and production rendering.

## 2.9.0 — 2026-10-30

- Use Chemcraft's built-in GaussView-style compatibility palette as the new default, with its actual source named in the UI. A Gaussian-authored full RGB table remains unavailable; no claim of exact native GaussView matching is made.
- Use ordinary-bond upper limits extracted from Chemcraft b816bt, excluding hydrogen-bond records. Share pair lookup across finite and periodic connectivity, fragment operations and edits. Default distance multiplier is 1.00; explicit pair rules, manual bonds and frozen edited graphs remain authoritative. Offer the earlier covalent-radius model separately.
- Use VESTA 3.5.8 Atomic radii for space filling, with Ionic and van der Waals alternatives. Space-filling size is independent of ball-and-stick size and defaults to 100%. Store these choices per document and in projects/presets; restore legacy projects with their previous covalent-radius search model.
- Document numeric provenance, coverage and the limits of compatibility. Distribute extracted numeric facts and a reproducible extractor, without upstream application binaries or configuration files.

## 2.8.0 — 2026-10-30

- Import independent CP2K-compatible Molden vibration files by content, preserving reference coordinate units, mode numbers/frequencies and frozen zero vectors. Integrate animation, mode arrows, selection participation, GIF and project persistence. Keep standard MDL .mol reading separate.
- Replace the main-canvas atom-legend overlay with a nonmodal window containing only unbonded element samples and labels; add independent PNG export and explicit refresh from the current structure. Legacy project flags remain readable without restoring the overlay.
- Preserve source units for optional Molden INT values and use the actual intensity unit in frequency tooltips.

## 2.7.0 — 2026-10-30

- Remove repeated history scans in CP2K, xTB, Quantum ESPRESSO and geometry-free NWChem module continuations; retain complete frame and scientific records. Add parsing/cancellation phases for other supported outputs and streaming trajectories.
- Add delayed progress for project I/O, structure/CSV/PNG export, spectra, geometry curves, mode/coordination analysis and large view/table updates. Keep Qt/VTK work on the GUI thread with cooperative checkpoints.
- Show converged on identified successful geometry optimization frames; clear stale status after structural edits and retain it through undo.
- Add View → Atom legend: one unbonded visible sample per element, fixed camera overlay, PNG/GIF support and per-document/project persistence.
- List both contact emails side by side on the welcome page. Document CP2K primary/replica logs and Molden vibration output organization.

## 2.6.0 — 2026-10-30

- Bond cutoff now supports 0.10–5.00 with a precise numeric field. Explicit changes rebuild automatic/frozen bonds for the active document, retaining manual ordinary/dashed overrides and element-pair rules.
- Move the atom/composition/contact summary and selection measurement into one bottom status strip; use the freed space for the structure canvas.
- Edit selected distances, angles and dihedrals numerically (Enter/Set). Move the last-selected terminal bonded fragment rigidly; reject rings, extra fixed-atom paths and infinite periodic networks without partial edits. Preserve image shifts and support undo; clear stale non-rigid geometry energies.
- Parse scientific outputs in a cancellable worker even below 4 MiB. Long imports display phase, phase percentage and elapsed time; structure/view attachment stays on the GUI thread.
- Speed up long ORCA optimizations with gated metadata matching, block coordinate conversion, indexed source-line/geometry lookup, optional-section checks and shared load-local source text. Retain all frames and original scientific values.

## 2.5.0 — 2026-10-30

- Remove the default 750-frame cap across native CP2K, VASP, Gaussian/ORCA,
  xTB, SIESTA and generic multi-image imports. Also remove cumulative xTB/NEB
  trajectory-record limits. Explicit caller-supplied API limits remain optional;
  the application supplies none. All loaded frames remain editable in memory.
- Stream native CP2K/plain XYZ and XDATCAR blocks with array-based numeric
  conversion. Preserve variable cells, Fortran exponents, incomplete-tail
  handling, source record mapping and extended-XYZ metadata through ASE.
- Share decoded output lines only within one load; skip absent optional
  property sections. Scan VASP tags/species once and avoid repeated regex work
  on irrelevant CP2K SCF rows. Keep VASP E0-only and CP2K FORCE_EVAL policies.
- Replace per-leaf copies/hashes of whole frame sequences with shared indexes.
  Build long frame/energy tree entries on expansion in 256-record pages,
  retaining numeric navigation, playback, stage/NEB sequences and projects.
- Parse scientific files of 4 MiB or larger in a cancellable background worker.
  GUI/VTK updates remain on the main thread; queued files retain their order,
  and cancelled imports do not attach partial documents.
- Add 22 long-file regressions. Full Linux suite: 605 tests plus 78 subtests
  pass. Eight supplied CP2K/VASP documents remain value-for-value identical to
  2.4.0. Include reproducible synthetic parser benchmarks and validation notes.

## 2.4.0 — 2026-10-30

- Add independent CP2K input/text-restart, stdout and standard XYZ readers.
  Read inline coordinates, cells/units/periodicity, KIND aliases, charge and
  multiplicity. Preserve settings-only inputs when coordinates are external
  or unsupported; do not open referenced files or evaluate executable input.
- Retain all printed FORCE_EVAL energies and optimization gradients/steps with
  their thresholds and source units. Link only available coordinates; keep
  geometry-free energy/gradient records and structure-only records. Separate
  concatenated CP2K runs. Do not infer trajectory cells from adjacent files.
- Convert standard CP2K XYZ E comments from Hartree to internal eV, preserving
  printed step/time metadata. Keep the last printed MO table per SCF evaluation,
  with separate k-point/spin channels rather than merged orbital indices.
- Add final TDDFPT energies, oscillator strengths, printed moment form, optional
  excitation amplitudes and raw k-point auxiliary fields. Component magnitudes
  from KERNEL NONE output remain magnitudes: no invented arrows, phase or
  excitation coefficients. Preserve unknown/Berry forms as labeled source data.
- Add CP2K record curves and CSV, source-aware transition tables/CSV, results-only
  spectrum/export controls and portable project serialization for CP2K results.
- Add synthetic fixtures/project, inspected Qt previews and 32 CP2K regressions.
  Full Linux validation: 583 tests and 78 subtests passed. The five supplied
  files pass isolated single-file loads, GUI/CSV and project round-trip checks.
  VASP E0-only behavior and prior features remain covered.

## 2.3.1 — 2026-10-30

- Use only VASP E0: OSZICAR E0= and OUTCAR energy(sigma->0). Remove fallback
  to TOTEN/F or energy without entropy, and remove energy-kind selection.
- Label result pages, overview columns and curves as E0. Curve CSV contains one
  energy column, energy_E0_eV, alongside frame/source-line and force fields.
  Missing E0 remains blank in CSV and a gap in the plotted curve. A structure
  without E0 keeps its geometry and any available force records.
- Open old .lele snapshots using the same E0-only policy, including saved mode
  references. Preserve energies already cleared by geometry editing. Retain
  original output text and source metadata independently of displayed energy.
- Add 9 E0 regressions; full Linux validation: 551 tests and 78 subtests passed.
  See docs/VASP_E0_v2.3.1_CN.md for actual-file and project-roundtrip checks.

## 2.3.0 — 2026-10-29

- Add Crystal → Pair rules: element-specific minimum/maximum distances,
  wildcards, enabled rows, separate ordinary-bond and directed coordination
  controls, and an optional only-listed mode. More specific rows win, then the
  last row. Explicit Apply rebuilds all document frames, keeps manual bond
  overrides and supports undo; geometry editing still preserves frozen bonds.
- Add coordination/polyhedron analysis: CN, periodic ligand distances/image
  shifts, hull volume, Baur distortion, Hoppe ECoN, and applicable tetrahedral/
  octahedral quadratic elongation and angle variance. Export summaries, ligands
  and frame-linked trajectory curves to CSV, retaining zero coordination and
  gaps when atom sequences or metric applicability differ.
- Add portable .lele project snapshots with all loaded structures and parsed
  scientific results, edited topology, atom appearance, per-document display
  options/cameras, cuts, alignment, geometry parameters and paused active modes.
  Retain source-text previews up to 180 KB. Source files are optional on restore.
  Open appends restored documents, preserving work already in the session.
- Use atomic writes and a fixed data-class registry with JSON and numeric NPY
  arrays; loading does not use pickle or extract files. Validate before updating
  the open session. Preserve existing PNG shortcuts.
- Fix transient out-of-range frame access during settings synchronization when
  changing from a long trajectory to a shorter file; keep the text preview in
  sync for programmatic document changes.
- Add a portable two-document example, native/Qt previews and 45 regressions.
  Full Linux validation: 542 tests and 78 subtests passed. Actual VASP snapshot
  checks preserve all coordinates, cells, energies and modes without source
  files; the synthetic saved/restored native view is pixel-identical.

## 2.2.0 — 2026-10-29

- Add Crystal → HKL planes with Miller indices, signed offsets in d or Å,
  below/above cuts, finite-thickness slabs, multiple-plane intersections,
  translucent plane faces/edges, automatic centering and normal camera views.
- Use reciprocal-cell normals for skew lattices. Clip atom glyphs, ordinary
  bonds, polyhedra and scalar isosurfaces in the same display coordinates,
  including Boundary copies and trajectory alignment. Filter labels and atom
  selection by the retained center region. Source coordinates/exports stay intact.
- Add Polyhedral style and a VESTA-inspired preset. Search explicit central/
  ligand elements using covalent radii or a distance range; complete periodic
  ligand shells and repeat center polyhedra with Boundary. Render translucent
  hull faces, true face edges and optional corner atoms with original atom IDs.
- Render planar ligand shells as polygons; omit collinear shells. Exclude
  coplanar triangulation diagonals from edges. Use center atom colours and retain
  ordinary manual/frozen bonds in every style, independently of coordination rules.
- Keep crystal controls Qt-only until preload. Restore cut and polyhedron
  settings per open document, and include them in PNG/GIF rendering.
- Add synthetic SrTiO3 examples, native preview images and 32 crystal regressions.
  Full Linux validation: 497 tests and 78 subtests passed. See the validation
  report for real-input checks and Windows acceptance limitations.

## 2.1.0 — 2026-10-29

- Add standalone VASP OUTCAR, XDATCAR and OSZICAR readers, including renamed
  OUTCAR_opt/OUTCAR_freq files. Do not read neighbouring calculation files.
- Retain ionic structures, cells, species blocks (including repeated elements),
  Cartesian force metrics, σ→0 energies, TOTEN and energies without entropy.
  Exclude electronic SCF summaries from ionic records and preserve source lines.
- Open energy-only output in the results page, preserve geometry-only navigation,
  and never match missing coordinates/energies to unrelated records.
- Read real and imaginary VASP modes with their printed reference geometry.
  Convert dynamical-matrix eigenvectors using POMASS; prefer the already divided
  table when printed. Distinguish finite-displacement structures from optimization.
- Add an energy-definition selector and CSV export retaining all three VASP
  energy values, source records and optional geometry links. Support variable-cell
  XDATCAR headers and retain complete frames from partially written files.
- Add 28 dedicated parser/UI regressions and synthetic example files. Validate
  the three supplied real files against ASE independently; see validation notes.

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
