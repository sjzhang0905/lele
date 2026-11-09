# LELE v3.1.0 — Element component rows and occupancy percentages

Date: 2026-11-04. Baseline: the complete v3.0.4 source package.

## Atoms

The **Atoms** browser now has **Atom / show**, **Colour**, **T %** and
**Occupancy %（占据百分比）** columns. Occupancy is separate from display
transparency. Fractional occupancy 0.5 is shown as **50%**; ordinary fully
occupied atoms show **100%**. The atom-name column no longer appends a bracketed
composition such as `[Mn0.5/Sn0.5]`.

For a Mn/Sn mixed site, both components appear separately under their own
element groups:

| Element group | Atom row | Occupancy % | Coordinate |
| --- | --- | --- | --- |
| Mn | Mn1 · #1 | 50% | Site #1 coordinate |
| Sn | Sn1 · #1 | 50% | The same Site #1 coordinate |

If Sn was not previously present in the browser, its group and component row
are created automatically. If other Sn atoms already exist, the new component
joins that group once; their own fully occupied rows still show 100%.
Each row uses the component element's palette colour, unless its source site
has an explicit colour override. Hover either row to see its percentage,
Cartesian coordinates and the complete site occupancy, including any vacancy.
The existing right-click **Element / occupancy** editor still takes fractions
from 0 to 1; the new column displays those values as percentages.

The separate component rows refer to one shared physical site. Selecting Sn
selects that same coordinate and highlights the site once. The current Sn row
and colour-dialog starting colour remain Sn. Existing visibility, label,
transparency and per-site colour overrides continue to affect the shared site;
component rows stay synchronized. Element groups do not auto-expand on a click.
Vacancy remains implicit, rather than appearing as an invented element row.

These rows do not create extra coincident physical sites. The coordinate table
still has one position per source site, weighted composition stays correct,
and Boundary images retain their original source IDs. This prevents the new
browser representation from double-counting sites or changing export chemistry.

## Persistence and export

- Fraction edits refresh percentages immediately. Adding/removing a component
  refreshes the relevant element groups, including in-place Frame updates.
- Undo, deletion/reindexing by shared site and project reopening keep the
  component rows mapped to their coordinates.
- CIF continues to write all components at the common coordinate with their
  original occupancies. Reopening the CIF or LELE project restores both rows.
- POSCAR, XYZ and GJF retain v3.0.4's explicit maximum-occupancy/cancel choice.
  The export conversion affects only its copy and leaves the component rows
  and original fractions unchanged.

## Validation

- Complete suite with configured local reference fixtures: **1139 passed,
  78 subtests passed**, no failures or skips, in 66.78 seconds.
- **20 new regressions** cover full and fractional percentages, new and existing
  Sn groups, shared coordinates/IDs, in-place fraction changes, component
  removal/undo, selection and focus, visibility/transparency synchronization,
  component palette colours, implicit vacancy, CIF/project roundtrips,
  maximum-occupancy export isolation, deletion/undo and clearing the browser.
- The Atoms pane and coordinate table were rendered and visually inspected:
  Mn1 and Sn1 each show 50% in their own groups, the other Mn and O show 100%,
  and no bracketed composition appears in atom names. The full percentage
  column fits the existing sidebar. Sn selection retains the shared coordinate.
- A live Qt layout check confirms that adding/selecting the mixed component
  keeps the canvas at **948 × 620** and leaves the compact coordinate-column
  widths unchanged in a 1280 × 850 test window.
- Linux Qt offscreen / VTK EGL; Python 3.12.14, Qt 6.12.0, VTK 9.7.1.

The previous mixed-site UI regressions now check separate component rows and
the new percentage column, while retaining their coordinate, weighted
composition, frame switching, undo and export assertions.

Reproduction after installing `.[test]`:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests/test_component_rows_v310.py tests/test_mixed_export_v304.py -q
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
  python -m pytest tests -q
```

The source package contains the complete preceding release and these changes.
This validation does not claim a Windows executable build.
