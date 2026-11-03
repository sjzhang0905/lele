# LELE 2.9 display reference data

The new defaults combine a GaussView-style compatibility palette, ordinary-bond
upper limits from Chemcraft, and VESTA Atomic space-filling radii. Each is an
independent setting; this does not reproduce another program's rendering or
complete chemical interpretation.

## Color provenance and fidelity

The palette is extracted from `schemes3/gv.bin`, named **GaussView style** by
Chemcraft's own `schemes3/schemdat.txt`, in the official Windows b816bt ZIP:

- <https://www.chemcraftprog.com/download.html>
- <https://www.chemcraftprog.com/files/Chemcraft_b816bt_win64.zip>

The visible name is **GaussView style (Chemcraft)**. This is a compatibility
palette supplied by Chemcraft, not an independently verified Gaussian-authored
RGB export. We did not infer base colors from shaded spheres or JPEG pixels.
It covers H through Sg; unsupported elements retain LELE's neutral fallback.
Examples: H `#C7C7C7`, C `#727272`, N `#0000FF`, O `#FF4040`, F `#80FFFF`,
Cl `#80FF00`. Custom per-element and per-atom colors take precedence.
**Legacy LELE** is also available in the Atom colours selector.

GaussView documents its color controls and factory reset, without providing a
complete numeric RGB table in the material retrieved for this change:
<https://gaussian.com/wp-content/uploads/dl/gv6.pdf>.

## Ordinary bonds

The same official Chemcraft package supplies `bonds5.bin`, format marker 790.
The numeric extraction reads the triangular table over indices 0..105,
separates ordinary bond records from hydrogen-bond records, and takes the
largest squared distance limit for each ordinary element pair. LELE uses its
square root as that pair's unscaled upper distance. The nominal equilibrium
length is not used as a minimum distance. Different ordinary bond types are
combined into connectivity; LELE does not infer a chemical bond order.

Examples of extracted ordinary upper limits, in Angstrom:

| Pair | Upper limit at ×1.00 |
| --- | ---: |
| C–C | 1.8922663660 |
| C–H | 1.3672190753 |
| O–H | 1.4300000000 |
| Ti–O | 2.6811844398 |
| Fe–O | 2.5262715610 |
| Cu–Cu | 3.2650868289 |

Format interpretation is based on a consistent parse of the pinned distribution;
it has not been compared against every pair in the Chemcraft GUI. Chemcraft's
own documentation confirms editable tables for automatic distance identification:
<https://www.chemcraftprog.com/news.html> and
<https://www.chemcraftprog.com/help/ccbasicinfo.html>.

**Bond search → Chemcraft pair ranges**, **Bond cutoff × → 1.00** is the new
default. The multiplier scales ordinary upper limits. Explicit element-pair
rules retain their absolute distance ranges; manual links and exclusions keep
their precedence. Geometry edits keep frozen connectivity. An explicit model
or cutoff change rebuilds this document's automatic graphs and retains manual
overrides. The existing LELE 0.2 Å short-distance guard and collinear occlusion
filter remain in automatic searches. Automatic hydrogen bonds continue to use
the separately labeled geometric criteria; Chemcraft hydrogen-bond records do
not become ordinary bonds.

Supported pairs cover H..Db. A supported pair with no ordinary record is
disabled. For species beyond that table, the fallback at ×1.00 is
`1.18 * (covalent_radius_A + covalent_radius_B)`. The alternative **Covalent
radii** search uses the sum of LELE's covalent radii directly, with 1.18 as its
initial multiplier. Projects saved before 2.9 restore that earlier model and
their saved multiplier, preserving their original bond inference.

## VESTA radii

Values were read from `elements.ini` in the official stable VESTA **3.5.8**
distribution, with the source's Atomic, van der Waals and representative Ionic
columns identified separately:

- <https://jp-minerals.org/vesta/en/download.html>
- <https://jp-minerals.org/vesta/archives/3.5.8/VESTA-gtk3.tar.bz2>
- <https://jp-minerals.org/vesta/en/doc/VESTAch5.html>
- <https://jp-minerals.org/vesta/en/doc/VESTAch12.html>

**Space filling (VESTA)** defaults to **Atomic**, **Atom size 100%**. The
rendered radius is the selected table radius multiplied by the independent
space-filling size. Changing ball-and-stick size does not change this value.
All three radius types are selectable; selecting space filling does not imply
van der Waals radii. Ionic values represent VESTA's preset oxidation states
and coordination numbers and do not adapt automatically to chemical valence.

| Element | Atomic / Å | van der Waals / Å | Ionic / Å |
| --- | ---: | ---: | ---: |
| H | 0.46 | 1.20 | 0.200 |
| C | 0.77 | 1.70 | 0.150 |
| N | 0.74 | 1.55 | 1.460 |
| O | 0.74 | 1.52 | 1.400 |
| Cu | 1.28 | 1.88 | 0.730 |

Coverage is H..Am, plus D and XX. Unsupported elements use the source table's
XX placeholder (Atomic 0.8 Å, van der Waals 1.0 Å, Ionic 0.8 Å). Atom legends,
PNG/GIF rendering and picking use the same rendered sizes as the main scene.

## Reproducibility

`lele/_display_reference_values.py` contains numeric facts in LELE's own
representation and SHA256 hashes of the three input data files. No original
Chemcraft/VESTA configuration, images or executable is distributed in this
source package. With locally obtained official inputs, regenerate it using:

```bash
python tools/extract_display_reference_data.py /path/to/reference_inputs
```

That directory must contain `bonds5.bin`, `gv.bin` and `elements.ini` from the
specified versions. The extractor validates the pinned layouts before writing.
