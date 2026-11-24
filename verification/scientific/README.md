# LELE scientific reference data

This collection tests periodic geometry in one, two, and three dimensions. It contains 12 original synthetic structures in XSF or extended XYZ, a case manifest, exact expected results, and a reference calculator. The coordinates and code use the included [MIT License](LICENSE).

| Cases | Verification |
| --- | --- |
| `slab-zero-c`, `slab-dependent-c`, `slab-vacuum` | Equivalent periodic distances for a zero, dependent, or oblique nonperiodic vector |
| `chain-b`, `tilted-yz`, `skew-xz` | Periodic axes in different row positions, normal displacement, and large original-basis image shifts |
| `bulk`, `molecule` | Full 3D and nonperiodic controls |
| `dependent-active`, `zero-active` | Rejection of the declared periodic basis when its active vectors are dependent |
| `infinite-chain`, `mic-tie` | A periodic self-bond with infinite winding, and two equally short images |

## Reproduce the data

From this directory, run:

```text
python reference.py
```

The script uses the Python standard library. It reads the included fixtures and compares its independently calculated results with `expected.json`. Use `python reference.py --regenerate` when updating the fixtures. From the LELE source directory, run `python -m pytest -q tests/test_scientific_validation.py` to check LELE's file loading and analysis against these results.

## Reference conventions

Cell vectors are rows in the order a, b, c. Atom indices start at zero. The Cartesian displacement from atom i to an image of atom j is `r[j] - r[i] + shift @ cell`. Distances use Å. Squared distances in the reference output are exact fractions in Å². The cutoff list includes directed neighbors and translated images of the same atom. Short contacts include each distinct pair once. The bond tests use the distance window declared in the manifest.

The independent calculator reads decimal coordinates as rational numbers. For each active lattice row it computes a dual vector $u_i$, with $a_j\cdot u_i=\delta_{ij}$. For an image at distance at most $R$, its integer coefficient satisfies $|s_i + (r_j-r_i)\cdot u_i| \le R\lVert u_i\rVert$. These bounds yield a finite enumeration containing every eligible shift, including shifts outside the adjacent cells. The calculator compares squared lengths exactly and records all ties. It tracks the image shifts along graph edges to identify winding.

The first collection targets geometric correctness. The structures are diagnostic fixtures. Their bond and contact distances are chosen to distinguish numerical cases.
