"""Acceptance expectations; failures are intentional evidence of unfixed defects.

Run from the unpacked LELE source root:
  PYTHONPATH=. python -m pytest /path/to/test_independent_acceptance.py -q
"""
from pathlib import Path
import numpy as np
import pytest
from lele.formats import load_document


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding='utf-8')
    return path


QE_HEADER = '''Program PWSCF v.7.3.1 starts
 number of atoms/cell = 2
 lattice parameter (alat) = 10.0 a.u.
 crystal axes: (cart. coord. in units of alat)
 a(1) = ( 1.0 0.0 0.0 )
 a(2) = ( 0.0 1.0 0.0 )
 a(3) = ( 0.0 0.0 1.0 )
 positions (alat units)
 1 H tau( 1) = ( 0.0 0.0 0.0 )
 2 H tau( 2) = ( 0.0 0.0 0.2 )
! total energy = -2.00000000 Ry
'''


@pytest.mark.parametrize('ending,expected', [
    ('The maximum number of steps has been reached.\nEnd of BFGS Geometry Optimization\nJOB DONE.\n', False),
    ('bfgs converged in 2 scf cycles and 1 bfgs steps\nEnd of BFGS Geometry Optimization\nJOB DONE.\n', True),
    ('JOB DONE.\n', False),
], ids=['A1_maxsteps_is_not_converged', 'positive_convergence', 'normal_exit_only'])
def test_qe_optimization_status(tmp_path, ending, expected):
    doc = load_document(write(tmp_path, 'qe_status.pwo', QE_HEADER + ending))
    assert bool(doc.frames[-1].info.get('optimization_converged')) is expected


def cp2k_input(cell_repeat='', topology_repeat='', angles=''):
    return f'''&GLOBAL
 RUN_TYPE ENERGY
&END GLOBAL
&FORCE_EVAL
 METHOD QS
 &SUBSYS
  &CELL
   ABC 4 4 4
   {cell_repeat}
   {angles}
  &END CELL
  &COORD
   He 1 1 1
  &END COORD
  &TOPOLOGY
   {topology_repeat}
  &END TOPOLOGY
 &END SUBSYS
&END FORCE_EVAL
'''


@pytest.mark.parametrize('cell_repeat,topology_repeat,natoms,cell_x', [
    ('MULTIPLE_UNIT_CELL 2 1 1', '', 1, 8),
    ('', 'MULTIPLE_UNIT_CELL 2 1 1', 2, 4),
    ('MULTIPLE_UNIT_CELL 2 1 1', 'MULTIPLE_UNIT_CELL 2 1 1', 2, 8),
    ('', '', 1, 4),
], ids=['A2_cell_only', 'A2_topology_only', 'both_repeat', 'no_repeat'])
def test_cp2k_cell_and_coordinate_repetitions_are_independent(tmp_path, cell_repeat, topology_repeat, natoms, cell_x):
    doc = load_document(write(tmp_path, 'repeat.inp', cp2k_input(cell_repeat, topology_repeat)))
    frame = doc.frames[0]
    assert len(frame.symbols) == natoms
    np.testing.assert_allclose(frame.cell, np.diag([cell_x, 4, 4]))


@pytest.mark.parametrize('keyword', ['ALPHA_BETA_GAMMA', 'ANGLES'])
def test_cp2k_angle_alias_preserves_cell(tmp_path, keyword):
    doc = load_document(write(tmp_path, 'angles.inp', cp2k_input(angles=f'{keyword} 90 90 120')))
    a, b, c = doc.frames[0].cell
    gamma = np.degrees(np.arccos(np.dot(a,b) / np.linalg.norm(a) / np.linalg.norm(b)))
    assert gamma == pytest.approx(120.)
    assert abs(np.linalg.det(doc.frames[0].cell)) == pytest.approx(64*np.sin(2*np.pi/3))


def test_siesta_inline_fractional_input(tmp_path):
    text = '''NumberOfAtoms 2
NumberOfSpecies 1
LatticeConstant 4 Ang
%block ChemicalSpeciesLabel
1 14 Si
%endblock ChemicalSpeciesLabel
%block LatticeVectors
1 0 0
0 1 0
0 0 1
%endblock LatticeVectors
AtomicCoordinatesFormat Fractional
%block AtomicCoordinatesAndAtomicSpecies
0 0 0 1
0.25 0.25 0.25 1
%endblock AtomicCoordinatesAndAtomicSpecies
'''
    doc = load_document(write(tmp_path, 'siesta.fdf', text))
    assert doc.frames[0].symbols == ['Si', 'Si']
    np.testing.assert_allclose(doc.frames[0].positions, [[0,0,0],[1,1,1]])
    np.testing.assert_allclose(doc.frames[0].cell, np.eye(3)*4)
    assert all(doc.frames[0].pbc)
