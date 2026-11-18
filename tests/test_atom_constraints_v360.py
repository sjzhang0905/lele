"""Constraint provenance and axes must follow program semantics, not guesses."""
import numpy as np
import pytest

from lele.core import Frame
from lele.atom_constraints import read_input_constraints, qe_position_constraints, rotate_fixed_axes


def frame():return Frame(['C','H','O','H'],np.arange(12).reshape(4,3),np.eye(3)*10,(True,)*3)


def parse(kind,text):return read_input_constraints(kind,text.splitlines(),frame())


def test_qe_crystal_positions_flags_are_cartesian_and_missing_rows_are_free():
    result=qe_position_constraints(['C 0 0 0 0 1 0','H .1 .2 .3','O .2 .2 .2 1 1 1'])
    assert result['fixed_axes']==[[True,False,True],[False]*3,[False]*3]
    assert result['fixed_axes_basis']=='cartesian'
    assert not qe_position_constraints(['C 0 0 0'])
    with pytest.raises(ValueError):qe_position_constraints(['C 0 0 0 T F F'])


CP2K='''&FORCE_EVAL
 &SUBSYS
 &END
&END
&MOTION
 &CONSTRAINT
  &FIXED_ATOMS
   COMPONENTS_TO_FIX XZ
   LIST 1 3
   LIST 4
  &END
  &FIXED_ATOMS
   COMPONENTS_TO_FIX Y
   LIST 1
  &END
 &END
&END
'''


def test_cp2k_repeated_lists_and_sections_use_fractional_components():
    result=parse('cp2k_in',CP2K)
    assert result['fixed_axes']==[[True]*3,[False]*3,[True,False,True],[True,False,True]]
    assert result['fixed_axes_basis']=='direct'


def test_cp2k_continuation_and_no_fixed_false_inference():
    result=parse('cp2k_in',CP2K.replace('LIST 1 3','LIST 1 \\\n      3'))
    assert result['fixed_axes'][2]==[True,False,True]
    assert not parse('cp2k_in','&FORCE_EVAL\n&END')
    unknown=parse('cp2k_in',CP2K.replace('LIST 4','LIST 9'))
    assert 'fixed_axes' not in unknown and unknown['constraint_notes']


def test_cp2k_restraint_is_not_exact_fixing():
    text='&MOTION\n&CONSTRAINT\n&FIXED_ATOMS\nLIST 1\n&RESTRAINT\nK 1\n&END\n&END\n&END\n&END'
    result=parse('cp2k_in',text)
    assert 'fixed_axes' not in result and 'soft restraint' in result['constraint_notes'][0]


def test_external_constraint_sources_are_not_silently_treated_as_free():
    assert 'fixed_axes' not in parse('cp2k_in',CP2K+'@INCLUDE other_constraints.inc\n')
    assert 'fixed_axes' not in parse('siesta_in','%include other.fdf\n%block GeometryConstraints\natom 1\n%endblock')


def test_orca_zero_based_ranges_and_internal_coordinates():
    result=parse('orca_in','%geom Constraints\n{ C 0 C }\n{ Z 1:2 C }\n{ B 0 1 1.2 C }\nend\nend')
    assert result['fixed_axes']==[[True]*3,[False,False,True],[False,False,True],[False]*3]
    assert result['fixed_axes_basis']=='cartesian'
    assert any('internal-coordinate' in n for n in result['constraint_notes'])


def test_orca_hydrogen_only_and_md_cartesian():
    result=parse('orca_in','%geom optimizehydrogens true\nend')
    assert result['fixed_axes']==[[True]*3,[False]*3,[True]*3,[False]*3]
    result=parse('orca_in','Constraint Add Cartesian 1 X Target 2.0\nConstraint Add Cartesian 3 YZ')
    assert result['fixed_axes'][1]==[True,False,False]
    assert result['fixed_axes'][3]==[False,True,True]
    assert not any(any(r) for r in parse('orca_in','Constraint Add Cartesian 1\nConstraint Remove All')['fixed_axes'])


@pytest.mark.parametrize('text',['%geom FixFrags {1} end','%geom\nConstraints\n{ C 9 C }\nend\nend'])
def test_orca_ambiguous_or_invalid_constraints_not_guessed(text):
    result=parse('orca_in',text)
    assert 'fixed_axes' not in result and result['constraint_notes']


GAUSSIAN='''# B3LYP/6-31G Opt=ModRedundant

test

0 1
C -1 0 0 0
H 0 1 0 0
O 0 0 1 0
H 0 0 0 1

X 3 F
2 F
1 A
B 1 2 F

'''


def test_gaussian_freeze_codes_and_modredundant_are_one_based():
    result=parse('gaussian_in',GAUSSIAN)
    assert result['fixed_axes']==[[False]*3,[True]*3,[True]*3,[False]*3]
    assert result['fixed_axes_basis']=='cartesian'
    assert any('internal-coordinate' in n for n in result['constraint_notes'])


def test_gaussian_readopt_optimizes_list_not_freezes_list():
    text=GAUSSIAN.replace('ModRedundant','ReadOpt').split('X 3 F')[0]+'noatoms atoms=1-3 notatoms=H\n\n'
    result=parse('gaussian_in',text)
    assert result['fixed_axes']==[[False]*3,[True]*3,[False]*3,[True]*3]


def test_gaussian_nonstandard_rigid_code_is_unknown_not_frozen():
    result=parse('gaussian_in',GAUSSIAN.replace('Opt=ModRedundant','Opt').replace('C -1','C -2'))
    assert result['fixed_axes'][0]==[None]*3
    assert result['constraint_notes']


def test_gaussian_nofreeze_and_absent_markers():
    result=parse('gaussian_in',GAUSSIAN.replace('Opt=ModRedundant','Opt=NoFreeze'))
    assert result['fixed_axes']==[[False]*3]*4
    clean=GAUSSIAN.split('X 3 F')[0].replace('Opt=ModRedundant','Opt')
    clean=clean.replace('C -1 ','C ').replace('H 0 1 0 0','H 1 0 0').replace('O 0 0 1 0','O 0 1 0').replace('H 0 0 0 1','H 0 0 1')
    assert not parse('gaussian_in',clean)


def test_siesta_position_range_and_axis_direction():
    result=parse('siesta_in','%block Geometry.Constraints\nposition from 1 to 3 step 2\natom 2 0. 0. 1.\ncellvector B\n%endblock')
    assert result['fixed_axes']==[[True]*3,[False,False,True],[True]*3,[False]*3]
    assert result['constraint_notes']


def test_siesta_nonaxis_direction_does_not_become_two_fixed_axes():
    result=parse('siesta_in','%block GeometryConstraints\natom 1 1. 1. 0.\n%endblock')
    assert 'fixed_axes' not in result and result['constraint_notes']


def test_nwchem_named_disabled_and_default_constraints():
    text='constraints unused\nfix atom 4\nend\nconstraints mine\nfix atom 1 3:4\nend\nset constraints mine\ntask dft optimize'
    result=parse('nwchem_in',text)
    assert result['fixed_axes']==[[True]*3,[False]*3,[True]*3,[True]*3]
    result=parse('nwchem_in','constraints\nfix atom 1\ndisable\nend\ntask dft optimize')
    assert result['fixed_axes']==[[False]*3]*4


def test_absent_constraints_remain_unknown_for_all_formats():
    for kind in ('orca_in','qe_in','cp2k_in','siesta_in','nwchem_in','xyz','cif'):
        assert 'fixed_axes' not in parse(kind,'')


def test_ase_cartesian_scaled_and_mixed_constraints():
    from ase import Atoms
    from ase.constraints import FixAtoms,FixCartesian,FixScaled
    from lele.atom_constraints import from_ase_constraints
    atoms=Atoms('CHHH',positions=np.zeros((4,3)),cell=np.eye(3))
    atoms.set_constraint([FixAtoms(indices=[0]),FixCartesian(1,mask=(True,False,True))])
    assert from_ase_constraints(atoms)['fixed_axes'][1]==[True,False,True]
    assert from_ase_constraints(atoms)['fixed_axes_basis']=='cartesian'
    atoms.set_constraint(FixScaled(1,mask=(True,False,True)))
    assert from_ase_constraints(atoms)['fixed_axes_basis']=='direct'
    atoms.set_constraint([FixScaled(1,mask=(True,False,True)),FixCartesian(2,mask=(False,True,False))])
    assert 'fixed_axes' not in from_ase_constraints(atoms)


def test_rotation_of_partial_cartesian_mask_is_not_misrepresented():
    f=frame();f.info.update(fixed_axes=[[True,False,False],[True]*3,[False]*3,[None]*3],fixed_axes_basis='cartesian')
    angle=np.pi/4;rotation=np.array([[np.cos(angle),-np.sin(angle),0],[np.sin(angle),np.cos(angle),0],[0,0,1]])
    rotate_fixed_axes(f,rotation)
    assert f.info['fixed_axes'][0]==[None]*3
    assert f.info['fixed_axes'][1]==[True]*3
    assert f.info['fixed_axes'][2]==[False]*3


def test_direct_constraints_follow_rotating_cell():
    f=frame();f.info.update(fixed_axes=[[True,False,False]]*4,fixed_axes_basis='direct')
    rotate_fixed_axes(f,np.eye(3),cell_rotated=True)
    assert f.info['fixed_axes']==[[True,False,False]]*4


@pytest.mark.parametrize('coordinates',[
    'O 0 0 0\nH 0 0 1\nH 0 1 0',
    'O -1 0 0 0\nH 0 0 0 1\nH 0 0 1 0',
])
def test_gaussian_load_document_accepts_integer_cartesian_and_freeze_codes(tmp_path,coordinates):
    from lele.formats import load_document
    path=tmp_path/'cartesian.gjf'
    original='%mem=2GB\n# hf/sto-3g\n\nkeep this title\n\n0 1\n'+coordinates+'\n\n'
    path.write_text(original)
    loaded=load_document(path).frames[0]
    assert loaded.symbols==['O','H','H']
    np.testing.assert_array_equal(loaded.positions,[[0,0,0],[0,0,1],[0,1,0]])
    if '-1' in coordinates:assert loaded.info['fixed_axes']==[[True]*3,[False]*3,[False]*3]
    assert path.read_text()==original


def test_gaussian_zmatrix_keeps_original_semantics(tmp_path):
    from lele.atom_constraints import read_gaussian_atoms
    path=tmp_path/'internal.gjf'
    path.write_text('# hf/sto-3g\n\nwater\n\n0 1\nO\nH 1 1.0\nH 1 1.0 2 90.0\n\n')
    atoms=read_gaussian_atoms(path)
    assert len(atoms)==3
    assert atoms.get_distance(0,1)==pytest.approx(1)
    assert atoms.get_angle(1,0,2)==pytest.approx(90)


@pytest.mark.parametrize('units',['Bohr','AU','(Rad,AU)'])
def test_gaussian_atomic_units_and_lowercase_tv(tmp_path,units):
    from ase.units import Bohr
    from lele.formats import load_document
    path=tmp_path/'bohr.gjf'
    path.write_text('# hf/sto-3g Units='+units+'\n\nT\n\n0 1\nH -1 0 0 1 ! retained comment\nTv 0 0 10\n\n')
    f=load_document(path).frames[0]
    assert f.positions[0,2]==pytest.approx(Bohr)
    assert f.cell[0,2]==pytest.approx(10*Bohr)
    assert f.info['fixed_axes']==[[True]*3]


def test_gaussian_comma_cartesian_and_atom_properties(tmp_path):
    from lele.formats import load_document
    path=tmp_path/'comma.gjf'
    text='# hf/sto-3g opt\n\nT\n\n0,1\nH(Iso=2),-1,0,0,1 ! original\n\n'
    path.write_text(text)
    f=load_document(path).frames[0]
    assert f.symbols==['H'] and f.info['fixed_axes']==[[True]*3]
    assert path.read_text()==text


def test_xtb_table_only_exact_fixed_atoms_not_generic_restraints():
    from lele.atom_constraints import xtb_fixed_table,xtb_fixed_constraints
    lines=['* 2 fixed atom positions, i.e. in gradient','','# Z position/Å','1 6 C 0 0 0','3 8 O 1 2 3']
    records=xtb_fixed_table(lines,0)
    assert records==[(0,6,'C'),(2,8,'O')]
    info=xtb_fixed_constraints(records,frame())
    assert info['fixed_axes']==[[True]*3,[False]*3,[True]*3,[False]*3]
    assert xtb_fixed_table(lines[:-1],0) is None
    assert 'fixed_axes' not in xtb_fixed_constraints([(1,6,'C')],frame())


@pytest.mark.parametrize('name,text,basis,flags',[
    ('orca.inp','! HF STO-3G Opt\n%geom Constraints\n{ C 0 C }\n{ Y 1 C }\nend\nend\n* xyz 0 1\nO 0 0 0\nH 0 0 1\n*\n',
     'cartesian',[[True]*3,[False,True,False]]),
    ('input.fdf','NumberOfAtoms 2\nNumberOfSpecies 2\nAtomicCoordinatesFormat Ang\n%block ChemicalSpeciesLabel\n1 8 O\n2 1 H\n%endblock\n%block AtomicCoordinatesAndAtomicSpecies\n0 0 0 1\n0 0 1 2\n%endblock\n%block GeometryConstraints\nposition 1\n%endblock\n',
     'cartesian',[[True]*3,[False]*3]),
    ('nwchem.inp','start example\ngeometry units angstrom\nO 0 0 0\nH 0 0 1\nend\nconstraints\nfix atom 1\nend\nbasis\n* library sto-3g\nend\ntask scf optimize\n',
     'cartesian',[[True]*3,[False]*3]),
    ('cp2k.inp','&FORCE_EVAL\n&SUBSYS\n&CELL\nABC 10 10 10\n&END\n&COORD\nO 0 0 0\nH 0 0 1\n&END\n&END\n&END\n&MOTION\n&CONSTRAINT\n&FIXED_ATOMS\nCOMPONENTS_TO_FIX YZ\nLIST 1\n&END\n&END\n&END\n',
     'direct',[[False,True,True],[False]*3]),
    ('POSCAR','water\n1\n10 0 0\n0 10 0\n0 0 10\nO H\n1 1\nSelective Dynamics\nCartesian\n0 0 0 F T F\n0 0 1 T T T\n',
     'direct',[[True,False,True],[False]*3]),
    ('qe.in',"&CONTROL\n calculation='relax',\n/\n&SYSTEM\n ibrav=0, nat=2, ntyp=2, ecutwfc=30,\n/\n&ELECTRONS\n/\nATOMIC_SPECIES\nO 16 O.UPF\nH 1 H.UPF\nCELL_PARAMETERS angstrom\n10 0 0\n0 10 0\n0 0 10\nATOMIC_POSITIONS crystal\nO 0 0 0 0 1 0\nH 0 0 .1 1 1 1\nK_POINTS gamma\n",
     'cartesian',[[True,False,True],[False]*3]),
])
def test_all_input_loaders_publish_constraint_metadata(tmp_path,name,text,basis,flags):
    from lele.formats import load_document
    path=tmp_path/name;path.write_text(text)
    f=load_document(path).frames[0]
    assert f.info['fixed_axes']==flags
    assert f.info['fixed_axes_basis']==basis
    assert path.read_text()==text
    if name=='orca.inp':assert f.info['source_kind']=='orca_in'


def test_siesta_list_and_clear_prev_preserve_earlier_constraints():
    result=parse('siesta_in','%block GeometryConstraints\natom 1 1. 0. 0.\natom [1 -- 3 step 2] 0. 1. 0.\nclear-prev 1\n%endblock')
    assert result['fixed_axes'][0]==[True,False,False]
    assert result['fixed_axes'][2]==[False,True,False]
