# LELE 2.1.0 validation — 2026-10-29

## Scope and environment

Implemented on the supplied LELE 2.0.3 archive. Validation uses Linux,
CPython 3.12.14, ASE 3.29.0, NumPy 2.3.5, PySide6 6.12.0, VTK 9.7.1 and
Matplotlib 3.10.8, with Qt offscreen and native VTK EGL rendering.
No Windows executable was built or tested in this environment.

The initially installed VTK 9.3.1 crashed while rendering the existing native
animation-export test without a display. The validation environment was updated
to an EGL-capable VTK before running the successful full suite. This did not
change the application's declared dependencies or renderer implementation.

## Supplied actual VASP outputs

Each file was copied into an otherwise empty directory and opened alone.
The following frame counts and values were obtained without companion files:

| Input | Atoms | Complete structures | Energy records | Modes | Imaginary |
| --- | ---: | ---: | ---: | ---: | ---: |
| OUTCAR_opt | 166 | 20 | 20 | 0 | 0 |
| XDATCAR | 166 | 20 | 0 | 0 | 0 |
| OUTCAR_freq | 4 | 25 | 25 | 12 | 3 |

All structures were independently compared with explicit ASE `vasp-out` /
`vasp-xdatcar` readers. For all three files, coordinate and cell differences
were exactly zero. The OUTCAR default energies also differed by exactly zero
at every ionic step. This verifies geometry/energy parsing; the VASP mode
parser is checked separately against its printed frequency/vector tables.

`OUTCAR_opt` first/last σ→0 energies are -941.77455196 / -941.77525006 eV.
Its last TOTEN is -941.81055434 eV. The cell volume is 6301.446817676562 Å³.
Its printed optimization completion marker is retained in the stage status.

`OUTCAR_freq` retains 25 finite-displacement calculation structures. The 12
normal modes use their own printed XYZ reference; the matched reference energy
is -19.53619395 eV. All 12 vectors can animate. The three printed `f/i` modes
are retained as negative frequencies. POMASS is 14/1 for the two element groups;
raw mass-weighted eigenvectors are divided by the corresponding square roots.

Input hashes and exact per-file comparison results are retained in
[`qa_v2.1.0/vasp_real_v210.json`](qa_v2.1.0/vasp_real_v210.json).
Actual user input coordinates are not bundled into the source distribution.

## Independent records and interface checks

- Remove all energy summaries from the actual optimization output: 20 complete
  structures remain, all with missing energy. Printed force data remain usable.
- Construct a coordinate-free excerpt from the 20 actual ionic summaries:
  20 energy records remain, zero structures are created, and all curve points
  remain available without a coordinate link.
- Open all actual files in the Qt interface. Navigate to the last optimization
  frame, show the cell volume, plot all 20 ionic records and export CSV retaining
  all three energies and the correct frame numbers.
- Open XDATCAR as a structure-only trajectory. Its frame controls remain usable
  and its empty energy curve is disabled.
- Select real and imaginary modes in OUTCAR_freq. The mode uses the periodic
  reference structure, and the matching navigation frame is the undisplaced
  reference rather than the last finite-displacement structure.
- Switch between the actual structures and the derived pure-energy/geometry
  inputs. The canvas and controls reflect the selected file's available data.
- Export the actual VASP reference mode as an eight-frame GIF and two XDATCAR
  frames as a trajectory GIF using native VTK. Both GIFs decode with the expected
  number of frames. Temporary actual-input renderings were not bundled.

These source-specific Qt checks use the existing test harness, which supplies
a Qt widget plus a VTK scene with live window rendering suppressed. Native GIF
export and the full native render tests exercise actual EGL rendering separately.
They do not replace acceptance testing on a Windows desktop.

## Regression suite

Command:

```bash
QT_QPA_PLATFORM=offscreen VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
python -m pytest tests -q --junitxml=docs/qa_v2.1.0/full_v210.xml
```

Result: **465 tests and 72 subtests passed**, with zero failures or skips.
This includes **28 VASP parser/interface regressions**. The full report is
[`qa_v2.1.0/full_v210.xml`](qa_v2.1.0/full_v210.xml).
VASP regressions cover energy/structure independence; missing individual energy
kinds; SCF versus ionic TOTEN; source line and frame mapping; incomplete tables;
unmatched initial geometry; concatenated jobs and blank preambles; fixed-width
lattice values; raw/divided mode deduplication and truncated vectors; frequency
results without geometry; repeated elements; Cartesian/direct coordinates;
variable/negative-volume cell scales; equal-position timesteps; explicit frame
limits; standalone OSZICAR summaries; energy plots/CSV; mode selection; and the
existing legacy structure converter's XDATCAR compatibility.

See the feature guide for the 750-frame limit and the reader's explicit limits
on absent cell/species data, unprinted intensities and unsupported output types.
