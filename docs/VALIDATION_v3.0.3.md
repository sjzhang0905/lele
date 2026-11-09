# LELE v3.0.3 — Edit a site's element and fractional occupancy

Date: 2026-11-04. Baseline: the complete v3.0.2 source package.

## Use

Right-click an atom (including a Boundary display image), then use the default
**Element / occupancy** tab. The table has two columns, **Element** and
**Occupancy (0–1)**. Use **Add element** and **Remove row** to edit the site.

| Element | Occupancy |
| --- | --- |
| Fe | 0.6 |
| Ni | 0.3 |

This example has total occupancy 0.9 and vacancy 0.1. Occupancies are fractions,
not percentages. Empty rows are ignored; an incomplete row, invalid element,
duplicate element, negative/non-finite value, value above one or excessive
total disables **Set element / occupancy**. A zero total is a fully vacant
site; one zero-weight element retains its site identity. The remaining vacancy
is implicit, so there is no separate vacancy element to enter.

The **Index** tab retains Set index and the two-selected-atom index swap.
Species edits apply only to the clicked site in the current geometry frame,
even when more than one atom is selected. They keep the coordinates, atom IDs,
other frames, appearance overrides and existing bond topology. The representative
element used for site radius/bonding follows the highest probability (a tied
current representative is retained). Mixed-colour sectors still display all
components; the remaining vacancy uses the existing faint sector display.

Calculated frame energy, force and spin metadata are cleared even if only a
probability changes and the representative stays the same. A volumetric grid
calculated for the old composition is detached. Source calculation results
remain records of the original composition, explicitly noted in Results info.
Ctrl+Z restores the frame, its occupancy/energy metadata and the attached grid.
Cancel and unchanged edits do not add an undo entry or clear calculated data.
Species editing is disabled in vibration and trajectory-alignment views.

## Export behavior

| Output | Mixed/partial occupancy behavior |
| --- | --- |
| CIF | Preserve every site component, its probability and implicit vacancy. |
| POSCAR (Direct or Cartesian) | Reject until an explicitly ordered model is supplied. |
| XYZ / GJF | Reject until an explicitly ordered model is supplied. |
| LELE project | Preserve occupancies and the rest of the saved project state. |

These structure-export rules are unchanged from v3.0.2. The representative
element is not an automatic majority-element export policy. A pure replacement
such as Ni 1.0 can be exported to POSCAR; species blocks are rebuilt to match
the edited atoms without sorting or moving their coordinates. An attempted
mixed-occupancy export does not overwrite an existing destination file.

For the native VASP format, the [official POSCAR specification](https://vasp.at/wiki/POSCAR)
defines species counts and a corresponding explicit list of ion positions.
Fractional site probabilities must be resolved into a chosen microscopic model
before using this export workflow for a calculation input.

## Validation

- Complete suite with configured local reference fixtures: **1096 passed,
  78 subtests passed**, no failures or skips, in 66.60 seconds.
- **36 new regressions** cover the new editor and chemistry/export behavior;
  the existing atom-index/swap and mixed-occupancy tests also pass.
- The two-column occupancy and Index tabs were rendered and visually inspected
  with Qt offscreen. The example displays total 0.9 and vacancy 0.1, with the
  table, row controls, validation note and apply/cancel buttons fitting the dialog.
- Linux Qt offscreen / VTK EGL; Python 3.12.14, Qt 6.12.0, VTK 9.7.1.

New tests cover validation, exact source-value preservation, zero-weight sites,
single-site edits, composition/representative changes, frozen bonds, original
frame isolation, two-tab Qt controls, undo/cancel/no-op, mixed CIF and project
roundtrips, protected export destinations and corrected POSCAR species order.
The old index/swap and vacancy-edit regressions remain included.

Reproduction after installing `.[test]`:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests/test_atom_species_v303.py tests/test_structure_edits_v2120.py -q
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests -q
```

The source package contains the complete preceding release and these changes.
This validation does not claim a Windows executable build.
