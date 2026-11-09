"""Long-run CP2K regression coverage for the selective stdout scanner."""
import numpy as np
import pytest
from ase.units import Hartree
from lele.cp2k_results import read_cp2k_output, read_cp2k_xyz
from lele.output_text import LoadCancelled, output_read_session


def test_long_md_keeps_every_printed_geometry_energy_and_source(tmp_path):
    path = tmp_path / 'md.out'
    lines = ['CP2K| version string: CP2K', ' GLOBAL| Run type MD',
             ' GLOBAL| Project name molecular_dynamics', ' - Atoms: 1',
             ' cell| Vector a [angstrom]: 10 0 0',
             ' CELL| Vector b [angstrom]: 0 11 0',
             ' CELL| Vector c [angstrom]: 0 0 12', ' cell| Periodicity XZ']
    sources = []
    for step in range(1201):
        lines += [f' MD| Step number {step}',
                  ' MODULE QUICKSTEP: ATOMIC COORDINATES IN ANGSTROM', '',
                  ' Atom Kind Element Z X Y Z', f' 1 1 H 1 0 0 {step / 1000:.6f}', '',
                  ' SCF WAVEFUNCTION OPTIMIZATION']
        lines += [' 1 OT CG 0.15E+00 0.10E-04 -1.0000000 -0.10E-08'] * 4
        lines += [' SCF run converged in 4 steps',
                  f' energy| Total FORCE_EVAL ( QS ) energy [hartree] {-10 - step / 1000:.6f}']
        sources.append(len(lines))
        lines += [' MD| Temperature [K] 300.0', ' MD| CPU time per MD step 1.0']
    path.write_text('\n'.join(lines) + '\n')
    results = read_cp2k_output(path)
    frames = results.frames()
    assert len(results.steps) == len(frames) == 1201
    assert results.stages[0].kind == 'md'
    for i, (step, frame) in enumerate(zip(results.steps, frames)):
        assert step.cycle == step.frame_index == i
        assert step.source_line == sources[i] == frame.info['source_line']
        assert frame.energy_ev / Hartree == pytest.approx(-10 - i / 1000)
        assert frame.info['cp2k_scf_converged'] is True
        assert frame.info['cp2k_project'] == 'molecular_dynamics'
        assert frame.pbc == (True, False, True)
        np.testing.assert_array_equal(frame.cell, np.diag([10, 11, 12]))
        assert frame.positions[0, 2] == pytest.approx(i / 1000)
    frames[-1].positions[0, 2] = 999
    assert results.steps[-1].geometry.positions[0, 2] == pytest.approx(1.2)


def test_cp2k_scanner_cancels_during_nonrecord_diagnostics(tmp_path):
    path = tmp_path / 'md.out'
    path.write_text('CP2K| version string: CP2K\n' + ' SCF diagnostic ignored by the reader\n' * 3000)
    cancelled = False
    def progress(label, value, total):
        nonlocal cancelled
        if label == 'CP2K: geometry, energies and properties':
            cancelled = True
    with output_read_session(cancelled=lambda: cancelled, progress=progress):
        with pytest.raises(LoadCancelled):
            read_cp2k_output(path)


def test_cp2k_xyz_repeated_frame_collection_is_independent(tmp_path):
    path = tmp_path / 'md-pos-1.xyz'
    path.write_text('1\n i = 7, time = 3.5, E = -1.25D+01\nH 0 0 1\n'
                    '1\n i = 8, time = 4.0, E = -1.24D+01\nH 0 0 2\n')
    results = read_cp2k_xyz(path)
    first = results.frames()
    first[-1].positions[0, 2] = 999
    second = results.frames()
    assert [step.cycle for step in results.steps] == [7, 8]
    assert second[-1].positions[0, 2] == 2
    assert second[-1].energy_ev == pytest.approx(-12.4 * Hartree)
    assert second[-1].info['time_fs'] == 4
