#!/usr/bin/env python3
"""Run previously optional producer-file checks without bundling private data."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
NODES = [
    'test_acceptance_extended_v2121.py::test_supplied_chemcraft_cif_without_spacegroup_metadata',
    'test_acceptance_extended_v2121.py::test_supplied_poscar1_preserves_all_selective_flags_and_rows',
    'test_boundary_surface_v354.py::test_actual_chgcar_periodic_meshes_keep_boundary_repetition',
    'test_chgcar_gui_v352.py::test_supplied_chgcar_renamed_exact_original_grid',
    'test_cif_spacegroup_v357.py::test_supplied_dpa_cif_matches_explicit_operations',
    'test_coordinate_reorientation_v2110.py::test_actual_poscar_pair_is_a_rigid_reorientation',
    'test_coordinate_reorientation_v2110.py::test_local_axes_match_supplied_rotation_script_without_pymatgen',
    'test_delta_acceptance_v2131.py::test_palette_against_original_tcl',
    'test_delta_acceptance_v2131.py::test_user_poscar_vacuum_append_and_export',
    'test_molden_and_legend_v280.py::test_actual_124_atom_example_all_frequencies_and_frozen_rows',
    'test_qe_v2100.py::test_real_supplied_qe_files',
    'test_real_wavecar_reference_v321.py::test_real_wavecar_independent_direct_sum',
    'test_independent_orbitals_v320.py',
]
FILES = {
    'LELE_CHEMCRAFT_CIF_EXAMPLE': '22.cif',
    'LELE_CHGCAR_EXAMPLE': 'CHGCAR',
    'LELE_DPA_CIF_EXAMPLE': 'DPA-1044209.cif',
    'LELE_ROTATION_SCRIPT': 'rotate_structure_from_analyzer_v32_v33_csv_v13_20260809.py',
    'QA_SIBYL_TCL': 'Sibyl.tcl',
    'LELE_CP2K_MOLDEN_EXAMPLE': 'COF2_O2_a_freq-VIBRATIONS-1.mol',
    'LELE_REAL_WAVECAR': 'WAVECAR',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', type=Path, help='Original samples directory (also searches LELE/ and work/)')
    parser.add_argument('--out', type=Path, default=ROOT / 'verification/v3.10.0/external')
    args = parser.parse_args()
    for module in ('pyscf', 'pymatgen.io.vasp.outputs', 'pytest_timeout'):
        try:
            present = importlib.util.find_spec(module) is not None
        except ModuleNotFoundError:
            present = False
        if not present:
            parser.error('Install the QA dependencies first: pip install pyscf pymatgen pytest-timeout')

    def locate(name):
        for directory in (args.samples, args.samples / 'LELE', args.samples / 'work'):
            path = directory / name
            if path.is_file():
                return path.resolve()
        parser.error(f'Missing original sample: {name}')

    inputs = {name: locate(name) for name in FILES.values()}
    env = dict(os.environ)
    # Keep optional OUTCAR evidence explicit; an unrelated inherited path
    # must never be silently compared to this WAVECAR.
    env.pop('LELE_REAL_OUTCAR', None)
    for variable, name in FILES.items():
        env[variable] = str(inputs[name])
    for variable, names in (
        ('LELE_ROTATION_EXAMPLE_DIR', ('POSCAR1', 'POSCAR2')),
        ('LELE_QE_EXAMPLE_DIR', ('01_vc-relax.in', 'job.out', 'job.out03', 'matdyn.modes')),
    ):
        paths = [locate(name) for name in names]
        if len({path.parent for path in paths}) != 1:
            parser.error(f'{names} must share one directory')
        inputs.update(zip(names, paths))
        env[variable] = str(paths[0].parent)
    env.update(QT_QPA_PLATFORM='offscreen', VTK_DEFAULT_OPENGL_WINDOW='vtkEGLRenderWindow',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    before = {name: digest(path) for name, path in inputs.items()}
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    xml_path = output / 'supplement_final.xml'
    command = [sys.executable, '-m', 'pytest', *('tests/' + node for node in NODES),
               '-q', '--timeout=120', '--tb=short', f'--junitxml={xml_path}']
    with (output / 'supplement_final.log').open('w') as stream:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    after = {name: digest(path) for name, path in inputs.items()}
    tree = ET.parse(xml_path).getroot() if xml_path.is_file() else None
    cases = [] if tree is None else tree.findall('.//testcase')
    summary = {
        'requested_previous_skips': 16,
        'expanded_cases': len(cases),
        'failed': sum(case.find('failure') is not None for case in cases),
        'errors': sum(case.find('error') is not None for case in cases),
        'skipped': sum(case.find('skipped') is not None for case in cases),
        'inputs_unchanged': before == after,
        'input_sha256': before,
        'outcar_comparison': 'Not requested; no matching OUTCAR was supplied for this WAVECAR.',
        'pytest_exit_code': result.returncode,
    }
    (output / 'supplement_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))
    return 0 if (result.returncode == 0 and len(cases) == 19
                 and not summary['skipped'] and before == after) else 1


if __name__ == '__main__':
    raise SystemExit(main())
