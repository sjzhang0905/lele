# Volumetric input

## Supported grids

- Gaussian CUBE (`.cube`, `.cub`): atom geometry, origin, arbitrary voxel vectors,
  scalar fields, multiple values per voxel, and orbital-labelled channels.
  Positive grid counts mean Bohr and negative counts mean Å. Mixed signs are
  rejected. Geometry is converted to Å; scalar values remain in source units.
  CASTEP duplicate boundary planes are removed together with the corresponding
  cell extent. Explicit nonstandard XYZ loop orders are respected.
- VASP CHGCAR, CHG, PARCHG, AECCAR0/1/2: regular charge-density grids are divided
  by cell volume to give e/Å³. The average density times cell volume is the
  integrated regular-grid charge. PAW augmentation occupancy blocks are skipped,
  not plotted or combined with the regular field.
- VASP ELFCAR: dimensionless ELF values, without charge normalization.
- VASP LOCPOT: potential values in eV, without charge normalization.
- VASP two-channel collinear and four-channel noncollinear density files retain
  their separate total and magnetization fields. Four-channel LOCPOT files retain
  scalar and magnetic-potential components.

The VASP x-fastest ordering and CUBE per-voxel channel ordering are preserved.
VASP negative-volume scale factors and skew cells use ASE's geometry reader.
VASP 4 files must have identifiable elements in their title or a suitable
companion POTCAR/OUTCAR; element names are never guessed from atom counts.
Canonical VASP names and dotted/underscore suffixes are recognized, including
PARCHG.0001 and CHGCAR_spin.

## Validation and limits

The readers stream numeric blocks without storing the complete source text.
The default import budget is 64 million scalar values across all channels.
An explicitly supplied programmatic `max_points=None` disables that budget.
Malformed, truncated, nonfinite or oversized fields retain valid atomic geometry
with an explanatory note. They never expose partially read channels as complete.
Rendering requires at least two samples per axis. Source files are not changed.

Tests use controlled synthetic grids with known channel values and skew cells,
plus the existing CUBE regression suite. They do not establish compatibility
with every VASP producer/version or every external CUBE variant.
