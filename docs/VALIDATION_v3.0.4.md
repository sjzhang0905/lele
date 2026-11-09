# LELE v3.0.4 — Mixed-site UI and confirmed maximum-occupancy export

Date: 2026-11-04. Baseline: the complete v3.0.3 source package.

## Editing and display

A normal structure can be changed into a mixed or partly vacant structure from
the right-click **Element / occupancy** editor. The following views now make
that state explicit:

- **Atoms** shows a compact component list on a mixed site's row, for example
  `Ni1 · #1 [Fe0.3/Ni0.6/□0.1]`; □ denotes vacancy. Hover the row for the full
  description; selecting one site also shows all probabilities in the wrapping
  appearance summary. Groups still use the representative element and list each source
  site once. Refreshing fractions on the same Frame also refreshes the text.
- **Coordinates** retains its compact four-column layout and numeric XYZ
  values. A label such as `1 Ni*` marks a mixed/partial site. Hover the site or
  coordinate cell for every element fraction and the vacancy. Atom identifiers,
  source-site counts and row selection remain unchanged.
- The **element-colour selector** includes minority elements, even if they are
  not any site's representative. The atom legend also includes those elements.
- The footer uses the occupancy-weighted composition and reports electron
  parity as unknown for a fractional model. Undo, frame switching and project
  reopening restore the corresponding rows, markers and descriptions.

## Export choice

CIF exports preserve the full component probabilities and implicit vacancies.
They do not ask for a conversion. A saved LELE project also retains the model.

For a mixed/partial model exported to **XYZ, Gaussian GJF, POSCAR Direct or
POSCAR Cartesian**, the program asks:

- **Use highest-occupancy element（使用最大占据元素）** — export a separate ordered copy with each site's highest-
  occupancy element at full occupancy. A tie keeps the current representative
  when possible, otherwise the first tied component. Partial vacancy fractions
  are ignored. A completely vacant site has no occupied element and is omitted.
- **Cancel（取消）** — stop before opening the save picker. Escape or closing the dialog
  also cancels. Cancel is the default button.

Only the exported copy is converted. The current frame, its fractions,
coordinates, selection, display and undo history stay intact. Surviving sites
keep their order and positions. POSCAR species blocks are rebuilt and the
surviving selective-dynamics flags are retained. If every site is vacant,
export fails without overwriting a destination.

For Python callers, the default remains conservative:

```python
export_frame(frame, path, 'poscar-direct', occupancy_policy='maximum')
```

The explicit policy selects this projection for non-CIF targets; it does not
convert a CIF export. Omitting the policy still rejects an unsupported mixed-
occupancy target. This prevents a programmatic export from silently choosing
an ordered model.

## Validation

- Complete suite with configured local reference fixtures: **1119 passed,
  78 subtests passed**, no failures or skips, in 67.47 seconds.
- **23 new regressions** cover the mixed-site display and confirmed export
  workflow. The display-independent coordinate test double now supports the
  same tooltip API as Qt; all existing geometry/coordinate assertions pass.
- The Atoms pane, compact coordinate table and export confirmation were rendered
  and visually inspected. Full fractions remain readable in the selected-site
  summary even when a long tree row is elided. The export prompt uses the app's
  English interface labels and clearly describes partial/complete vacancy and
  source-model preservation.
- Linux Qt offscreen / VTK EGL; Python 3.12.14, Qt 6.12.0, VTK 9.7.1.

Checks include both unchanged and changed representative elements; row text,
coordinate tooltips, source counts, minority colours/legend, composition and
electron parity; same-frame probability refresh; frame switching and undo;
normal POSCAR → right-click edit → mixed CIF roundtrip → project restore;
confirmed roundtrips through all four non-CIF export modes; ties, partial and
complete vacancy, atom ordering, POSCAR constraints, cancellation/default/close,
and source-model isolation. Prior default-rejection tests remain intact.

Reproduction after installing `.[test]`:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests/test_mixed_export_v304.py tests/test_atom_species_v303.py -q
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests -q
```

The source package contains the complete preceding release and these changes.
This validation does not claim a Windows executable build.
