# LELE 4.0.1 verification

Linux regression passed 2,397 tests and 78 subtests. 14 tests requiring external fixtures were skipped. [Regression report](regression.xml)

The baseline XSF fixture exposes an independent rank-two lattice with translations of 10 and 8 Å. The original pair difference is 9.55 Å. Its shortest image has displacement (−0.45, 0, 0) Å and source shift (−1, 0, 0). Version 4.0.0 returned the original difference and omitted this contact and bond. Version 4.0.1 matches the reference for minimum images, neighbors, contact, bond, and fragment geometry.

The 12 [scientific reference cases](../scientific/README.md) load through LELE and compare against an independent exact-arithmetic calculator. Additional tests cover Boundary image picking, a fragment supercell, periodic distance selection, CP2K inline geometry parsing, preservation of Miller-plane guards, and LELE project round trips. The installed 4.0.1 wheel was checked with all three corresponding slab representations. Runtime validation used Linux.
