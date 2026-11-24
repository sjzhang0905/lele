from pathlib import Path

import numpy as np
import pytest

from lele.atom_constraints import edited_constraints, fixed_atom_indices
from lele.core import Frame
from lele.formats import export_frame, load_document
from test_periodic_fragment_ui_v171 import gui

EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'
POSCAR = '''surface
1.0
5 0 0
0 5 0
0 0 5
O H O
1 1 1
Selective Dynamics
Cartesian
0 0 0 F T F
1 0 0 F F F
0 1 0 T T T
'''


def test_fix_clear_and_selection_are_real_shortcuts_preserving_metadata_and_undo(gui, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from lele.core import Volume
    frame = Frame(['O','H','H'], [[0,0,0],[1,0,0],[0,1,0]], energy_ev=-3.25,
                  info={'fixed_axes': [[True,False,True], [False]*3, [True]*3], 'fixed_axes_basis': 'cartesian'})
    grid = Volume(np.arange(27).reshape(3,3,3), np.zeros(3), np.eye(3))
    gui.attach(frame, second_frame=frame.clone(), volume=grid)
    w = gui.window
    gui.select([1])
    w.show()
    gui.app.processEvents()
    w.vtk.setFocus()
    ctrl = Qt.KeyboardModifier.ControlModifier
    def key(modifiers):
        QTest.keyClick(w.vtk, Qt.Key.Key_F, modifiers)
        gui.app.processEvents()
    key(ctrl)
    assert fixed_atom_indices(w.frame) == [1, 2]
    assert fixed_atom_indices(w.doc.frames[1]) == [2]
    key(ctrl | Qt.KeyboardModifier.AltModifier)
    assert w.selection == [1, 2]
    key(ctrl | Qt.KeyboardModifier.ShiftModifier)
    assert fixed_atom_indices(w.frame) == []
    assert w.frame.info['fixed_axes'][0] == [True,False,True]
    w.undo_edit()
    assert fixed_atom_indices(w.frame) == [1,2] and w.doc.volume is grid and w.frame.energy_ev == -3.25
    assert w.frame.bond_snapshot is None and not w.doc.modified
    w.save_project_to(tmp_path/'fixed.lele')
    from lele.project_file import load_project
    stored = load_project(tmp_path/'fixed.lele')['documents'][0]['document']
    assert fixed_atom_indices(stored.frames[0]) == [1, 2]


def test_vasp_constraints_edit_merge_export_and_gaussian_roundtrip(tmp_path):
    p = tmp_path/'POSCAR'
    p.write_text(POSCAR)
    frame = load_document(p).frames[0]
    assert fixed_atom_indices(frame) == [1]
    frame.info.update(edited_constraints(frame, [2], True))
    frame.info.update(edited_constraints(frame, [1], False))
    for target in ('poscar-direct', 'poscar-cartesian'):
        out = tmp_path/(target+'.vasp')
        export_frame(frame, out, target, merge_same_elements=True)
        reread = load_document(out).frames[0]
        assert reread.symbols == ['O','O','H']
        assert reread.info['fixed_axes'] == [[True,False,True], [True]*3, [False]*3]
    gjf = tmp_path/'converted.gjf'
    notices = export_frame(frame, gjf, 'gjf')
    assert 'Partial constraints' in ' '.join(notices)
    assert fixed_atom_indices(load_document(gjf).frames[0]) == [2]
    frame.info.update(edited_constraints(frame, [0,2], False))
    export_frame(frame, gjf, 'gjf')
    assert fixed_atom_indices(load_document(gjf).frames[0]) == []
    assert ' -1 ' not in gjf.read_text()


def test_gjf_to_poscar_and_skew_cartesian_partial(tmp_path):
    source = tmp_path/'water.gjf'
    source.write_text('# opt hf/sto-3g\n\nwater\n\n0 1\nO -1 0 0 0\nH 0 1 0 0\nH 0 0 1 0\n\n')
    f = load_document(source).frames[0]
    export_frame(f, tmp_path/'POSCAR', 'poscar-direct')
    assert fixed_atom_indices(load_document(tmp_path/'POSCAR').frames[0]) == [0]
    f.cell = np.array([[0,4.,0],[2.,1.,0],[.5,.5,6.]])
    f.pbc = (True,)*3
    f.info.update(fixed_axes=[[False,False,True],[True]*3,[False]*3], fixed_axes_basis='cartesian')
    export_frame(f, tmp_path/'POSCAR', 'poscar-cartesian')
    assert load_document(tmp_path/'POSCAR').frames[0].info['fixed_axes'] == f.info['fixed_axes']
    f.info['fixed_axes'][0] = [False,True,False]
    path = tmp_path/'conflict.vasp'
    with pytest.raises(ValueError, match='partial Cartesian'):
        export_frame(f, path, 'poscar-direct')
    assert not path.exists()


def test_gaussian_output_echo_job_boundaries_and_no_guess(tmp_path):
    text = (EXAMPLES/'synthetic_opt_freq.log').read_text()
    start = ' Charge = 0 Multiplicity = 1'
    geometry = '\n O   -1    0.0 0.0 0.0\n H 0  1.1 0.0 0.0\n H 0  -0.3 1.1 0.0\n'
    path = tmp_path/'job.log'
    path.write_text(text.replace(start, ' Symbolic Z-matrix:\n'+start+geometry, 1))
    frames = load_document(path).frames
    assert all(fixed_atom_indices(f) == [0] for f in frames if f.info['calculation_index'] == 0)
    assert all('fixed_axes' not in f.info for f in frames if f.info['calculation_index'] == 1)
    before = '                         Standard orientation:'
    path.write_text(text.replace(before, ' The following ModRedundant input section has been read:\n X 2 F\n B 1 3 F\n\n'+before,1))
    frames = load_document(path).frames
    assert fixed_atom_indices(frames[0]) == [1]


@pytest.mark.parametrize(('fixture','text','expected'), [
    ('synthetic_orca_full_v190.out','| 91> %geom Constraints\n| 92> { C 0 C }\n| 93> { B 0 1 C }\n| 94> end\n| 95> end\n',[0]),
    ('synthetic_cp2k_v240.out','&MOTION\n &CONSTRAINT\n &FIXED_ATOMS\n LIST 1\n &END\n &END\n&END\n',[0]),
    ('siesta_relax_demo.out','*** Dump of input data file ***\n%block GeometryConstraints\n atom 1\n%endblock GeometryConstraints\n*** End of input data file ***\n',[0]),
])
def test_echoed_input_in_output_loads_and_exports(tmp_path, fixture, text, expected):
    original = (EXAMPLES/fixture).read_text()
    path = tmp_path/'sample.out'
    start, rest = original.split('\n', 1)
    path.write_text(start+'\n'+text+rest)
    frame = load_document(path).frames[0]
    assert fixed_atom_indices(frame) == expected
    assert 'printed' in frame.info['fixed_axes_source']
    export_frame(frame, tmp_path/'check.gjf', 'gjf')
    assert fixed_atom_indices(load_document(tmp_path/'check.gjf').frames[0]) == expected


def test_xdatcar_with_flags_and_missing_output_flags(tmp_path):
    path = tmp_path/'XDATCAR'
    path.write_text(POSCAR.replace('Cartesian\n', 'Direct configuration= 1\n')+
                    'Direct configuration= 2\n0 0 0 F T T\n.2 0 0 T T T\n0 .2 0 F F F\n')
    assert [fixed_atom_indices(f) for f in load_document(path).frames] == [[1],[2]]
    doc = load_document(EXAMPLES/'synthetic_vasp_v210.OUTCAR')
    assert all('fixed_axes' not in f.info for f in doc.frames)


def test_qe_final_if_pos_is_associated_with_its_run(tmp_path):
    from test_long_operations_v270 import qe_text
    path = tmp_path/'job.pwo'
    job = ''.join(qe_text(2))
    path.write_text(job.replace('H 0 0 0\nH 0 0 1.00001000','H 0 0 0 0 0 0\nH 0 0 1.00001000 1 1 1') + job)
    frames = load_document(path).frames
    assert len(frames) == 4
    assert [fixed_atom_indices(f) for f in frames] == [[0], [0], [], []]


def test_nwchem_echo_freeze(tmp_path):
    from test_long_operations_v270 import nwchem_block
    path = tmp_path/'job.nwo'
    path.write_text('Northwest Computational Chemistry Package\n'
        '============================== echo of input deck ==============================\n'
        'constraints\nfix atom 2\nend\ntask dft optimize\n'
        '================================================================================\n'
        +nwchem_block(1)+' Total times  cpu: 1.0s\n')
    doc = load_document(path)
    assert fixed_atom_indices(doc.frames[-1]) == [1]


def test_freeze_columns_follow_unknown_atoms_from_old_project(tmp_path):
    frame = Frame(['H', 'O', 'H'], [[0,0,0], [0,0,1], [1,0,0]])
    frame.info.update(edited_constraints(frame, [1], True))
    assert frame.info['fixed_axes'] == [[None]*3, [True]*3, [None]*3]
    for ext,target in (('gjf','gjf'),('vasp','poscar-direct')):
        path = tmp_path/('model.'+ext)
        export_frame(frame, path, target)
        assert fixed_atom_indices(load_document(path).frames[0]) == [1]
