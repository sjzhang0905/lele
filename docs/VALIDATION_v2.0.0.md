# LELE 2.0.0 validation

- Full Linux Qt/VTK regression: **380 tests + 72 subtests passed**.
  Machine-readable result: `qa_v2.0.0/full_v200.xml`.
- Added 33 cases for selected-atom Cartesian displacement shares, missing data,
  filtering/playing/exporting modes, selected-atom static arrows, every geometric
  monitor type, explicit periodic images, undefined-geometry gaps, unwrapped
  dihedrals, curve-to-source navigation, and NEB image-history sequence scope.
- Verified proper display rotations (determinant +1), translation, selected
  scaffolds, chiral/linear/single-atom cases, atom-order mismatch handling,
  unchanged source coordinates/cells/energies and the GIF alignment path.
- Rechecked the supplied 175-cycle g-xTB output after removing only the printed
  final geometry: all **175** energy steps appear in the Files tree and are
  individually selectable; the document has zero structure frames. Source
  molecular coordinates and output contents are not distributed in the package.
- Inspected four artificial-data Qt previews and two actual EGL VTK renders for
  the energy tree, mode browser, vibration controls, geometry curves, aligned
  molecule and displacement arrows. See `examples/v200_*.png`.
- Adjusted two existing lightweight GUI test doubles for the new optional
  display-alignment interface. Existing coordinate/fragment assertions remain.
- Windows executable: build configuration retained; no Windows executable was
  built or exercised in this Linux environment.
