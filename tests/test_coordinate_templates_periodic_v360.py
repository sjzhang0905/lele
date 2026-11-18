"""Input coordinate replacement retains settings and reconstructs geometry."""
import numpy as np
import pytest
from lele.core import Frame
from lele.coordinate_templates_periodic import replace_periodic_coordinates
from lele.formats import load_document

CP2K='''# header stays
&GLOBAL
  PROJECT preserve
  RUN_TYPE GEO_OPT
&END GLOBAL
&FORCE_EVAL
  METHOD QS
  &DFT
    CHARGE 1
    &SCF
      EPS_SCF 1.0e-7
    &END SCF
  &END DFT
  &SUBSYS
    &CELL
      ABC [bohr] 12 13 14 # original cell comment
      ALPHA_BETA_GAMMA [deg] 90 90 90 # angle comment
      PERIODIC XYZ
    &END CELL
    &COORD
      UNIT bohr
      O_main 0 0 0 water # oxygen comment
      H_main 0 0 1 water
    &END COORD
    &KIND O_main
      ELEMENT O
      BASIS_SET DZVP
      POTENTIAL GTH-PBE
    &END KIND
    &KIND H_main
      ELEMENT H
      BASIS_SET DZVP
      POTENTIAL GTH-PBE
    &END KIND
  &END SUBSYS
&END FORCE_EVAL
&MOTION
  &GEO_OPT
    MAX_ITER 100
  &END GEO_OPT
&END MOTION
'''
QE='''&CONTROL
 calculation = 'relax', prefix = 'keep-me',
/
&SYSTEM
  ibrav=0, nat=2, ntyp=2, ecutwfc=60.0,
  input_dft='PBE',
/
&ELECTRONS
 conv_thr=1.0d-9,
/
ATOMIC_SPECIES
O 15.999 O.UPF
H 1.008 H.UPF
ATOMIC_POSITIONS crystal
! oxygen stays
O 0.0 0.0 0.0
H 0.0 0.0 0.1
CELL_PARAMETERS angstrom
  10 0 0 ! first vector
  0 10 0
  0 0 10
K_POINTS automatic
  2 2 2 0 0 0
'''
FDF='''SystemName keep-all
NumberOfAtoms 2
NumberOfSpecies 2
MeshCutoff 300 Ry
LatticeConstant 2.0 Ang
%block LatticeVectors
  5 0 0 # vector
  0 5 0
  0 0 5
%endblock LatticeVectors
%block ChemicalSpeciesLabel
  1 8 O
  2 1 H
%endblock ChemicalSpeciesLabel
AtomicCoordinatesFormat Fractional
%block AtomicCoordinatesAndAtomicSpecies
  0 0 0 1 # oxygen
  0 0 0.1 2
%endblock AtomicCoordinatesAndAtomicSpecies
%block kgrid.MonkhorstPack
2 0 0 0
0 2 0 0
0 0 2 0
%endblock kgrid.MonkhorstPack
'''

@pytest.fixture
def frame():
    return Frame(['O','H'],[[1.2,2.3,3.4],[2.1,3.2,4.3]],
                 [[0,9,0],[-8,1,0],[2,3,10]],(True,True,True))


def read(text,kind,tmp_path):
    path=tmp_path/{'cp2k_in':'cp2k.inp','qe_in':'pw.in','siesta_in':'siesta.fdf'}[kind]
    path.write_bytes(text.encode())
    return load_document(path).frames[0]


@pytest.mark.parametrize('kind,text',[('cp2k_in',CP2K),('qe_in',QE),('siesta_in',FDF)])
def test_periodic_replacement_preserves_rotated_cell_positions_and_settings(kind,text,frame,tmp_path):
    old_positions=frame.positions.copy();old_cell=frame.cell.copy()
    result=replace_periodic_coordinates(text,kind,frame)
    actual=read(result,kind,tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-11)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-11)
    assert actual.symbols==frame.symbols
    np.testing.assert_array_equal(frame.positions,old_positions)
    np.testing.assert_array_equal(frame.cell,old_cell)
    if kind=='cp2k_in':
        assert result[:result.index('    &CELL')]==text[:text.index('    &CELL')]
        assert result[result.index('    &KIND'):]==text[text.index('    &KIND'):]
        for fragment in ('water # oxygen comment','# original cell comment','# angle comment','UNIT bohr','PERIODIC XYZ'):
            assert fragment in result
    elif kind=='qe_in':
        assert result[:result.index('ATOMIC_POSITIONS')]==text[:text.index('ATOMIC_POSITIONS')]
        assert result[result.index('K_POINTS'):]==text[text.index('K_POINTS'):]
    else:
        assert result[:result.index('%block LatticeVectors')]==text[:text.index('%block LatticeVectors')]
        assert result[result.index('%block kgrid'):]==text[text.index('%block kgrid'):]


@pytest.mark.parametrize('kind,text',[('cp2k_in',CP2K),('qe_in',QE),('siesta_in',FDF)])
def test_molecule_to_periodic_template_gets_30_angstrom_cell(kind,text,frame,tmp_path):
    frame.pbc=(False,)*3;frame.cell=np.zeros((3,3))
    actual=read(replace_periodic_coordinates(text,kind,frame),kind,tmp_path)
    np.testing.assert_allclose(actual.cell,np.eye(3)*30,atol=1.e-10)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


def test_cp2k_scaled_coordinates_and_explicit_bohr_cell(frame,tmp_path):
    text=CP2K.replace('ABC [bohr] 12 13 14 # original cell comment\n      ALPHA_BETA_GAMMA [deg] 90 90 90 # angle comment',
                      'A [bohr] 12 0 0\n      B [bohr] 0 13 0\n      C [bohr] 0 0 14').replace('UNIT bohr','SCALED TRUE')
    result=replace_periodic_coordinates(text,'cp2k_in',frame)
    assert 'SCALED TRUE' in result and 'A [bohr]' in result
    actual=read(result,'cp2k_in',tmp_path)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


def test_cp2k_periodic_none_preserves_integration_cell(frame,tmp_path):
    text=CP2K.replace('PERIODIC XYZ','PERIODIC NONE').replace('UNIT bohr','SCALED TRUE')
    old=read(text,'cp2k_in',tmp_path)
    result=replace_periodic_coordinates(text,'cp2k_in',frame)
    assert text[text.index('    &CELL'):text.index('    &COORD')]==result[result.index('    &CELL'):result.index('    &COORD')]
    actual=read(result,'cp2k_in',tmp_path)
    assert not any(actual.pbc)
    np.testing.assert_array_equal(actual.cell,old.cell)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


@pytest.mark.parametrize('kind,text',[('cp2k_in',CP2K),('qe_in',QE),('siesta_in',FDF)])
def test_crlf_preserved_and_plain_element_reorder_allowed(kind,text,frame,tmp_path):
    frame.symbols=['H','O'];frame.info['atom_order_edited']=True
    if kind=='cp2k_in':text=text.replace(' water','')
    text=text.replace('\n','\r\n')
    result=replace_periodic_coordinates(text,kind,frame)
    assert '\n' not in result.replace('\r\n','')
    actual=read(result,kind,tmp_path)
    assert actual.symbols==['H','O']
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


@pytest.mark.parametrize('kind,text',[
    ('cp2k_in',CP2K+'@INCLUDE external.inp\n'),
    ('cp2k_in',CP2K.replace('ABC [bohr] 12 13 14','ABC [bohr] $A 13 14')),
    ('cp2k_in',CP2K+CP2K),
    ('cp2k_in',CP2K.replace('PERIODIC XYZ','PERIODIC XYZ\n      MULTIPLE_UNIT_CELL 2 1 1')),
    ('qe_in',QE.replace('ibrav=0','ibrav=1')),
    ('qe_in',QE.replace('ATOMIC_POSITIONS crystal','ATOMIC_POSITIONS crystal_sg')),
    ('siesta_in',FDF+'%include geometry.fdf\n'),
    ('siesta_in',FDF+'AtomicCoordinatesOrigin COP\n'),
    ('siesta_in',FDF+'%block Zmatrix\nmolecule\n%endblock Zmatrix\n'),
])
def test_ambiguous_or_indirect_input_rejected(kind,text,frame):
    with pytest.raises(ValueError):replace_periodic_coordinates(text,kind,frame)


@pytest.mark.parametrize('kind,text',[
    ('cp2k_in',CP2K+'\n&MOTION\n &CONSTRAINT\n  &FIXED_ATOMS\n   LIST 1\n  &END\n &END\n&END\n'),
    ('qe_in',QE.replace('H 0.0 0.0 0.1','H 0.0 0.0 0.1 0 1 1')),
    ('siesta_in',FDF+'%block GeometryConstraints\n atom 1\n%endblock GeometryConstraints\n'),
])
def test_reordered_atoms_with_target_specific_settings_rejected(kind,text,frame):
    frame.info['atom_order_edited']=True
    with pytest.raises(ValueError,match='Atom order changed'):replace_periodic_coordinates(text,kind,frame)


def test_qe_flags_survive_when_order_unchanged(frame,tmp_path):
    text=QE.replace('H 0.0 0.0 0.1','H 0.0 0.0 0.1 0 1 1')
    result=replace_periodic_coordinates(text,'qe_in',frame)
    assert ' 0 1 1\n' in result
    actual=read(result,'qe_in',tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


def test_fdf_latticeparameters_become_explicit_vectors(frame,tmp_path):
    text=FDF.replace('%block LatticeVectors\n  5 0 0 # vector\n  0 5 0\n  0 0 5\n%endblock LatticeVectors',
                     '%block LatticeParameters\n  5 5 5 90 90 90 # cell comment\n%endblock LatticeParameters')
    result=replace_periodic_coordinates(text,'siesta_in',frame)
    assert '# cell comment' in result and 'LatticeParameters' not in result
    actual=read(result,'siesta_in',tmp_path)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


def test_cp2k_restart_quoted_kinds_and_non_geometry_continuations(frame,tmp_path):
    text=CP2K.replace('&KIND O_main','&KIND "O_main"').replace('ELEMENT O','ELEMENT "O"')
    text+='&MOTION\n &CONSTRAINT\n  &FIXED_ATOMS\n   LIST 1 \\\n      2\n  &END\n &END\n&END\n'
    result=replace_periodic_coordinates(text,'cp2k_in',frame)
    assert result[result.index('    &KIND'):]==text[text.index('    &KIND'):]
    actual=read(result,'cp2k_in',tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


@pytest.mark.parametrize('pos_unit,cell_unit,alat',[
    ('angstrom','bohr',None),('bohr','angstrom',None),
    ('alat','alat',5.0),
])
def test_qe_unit_modes(pos_unit,cell_unit,alat,frame,tmp_path):
    text=QE.replace('ATOMIC_POSITIONS crystal','ATOMIC_POSITIONS '+pos_unit).replace('CELL_PARAMETERS angstrom','CELL_PARAMETERS '+cell_unit)
    if alat is not None:text=text.replace('ibrav=0,','ibrav=0, celldm(1)='+str(alat)+',')
    actual=read(replace_periodic_coordinates(text,'qe_in',frame),'qe_in',tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)


@pytest.mark.parametrize('explicit_a',[None,5.0])
def test_qe_alat_conversions_follow_documented_units_without_changing_parameters(explicit_a,frame,tmp_path):
    text=QE.replace('ATOMIC_POSITIONS crystal','ATOMIC_POSITIONS alat')
    if explicit_a is not None:
        text=text.replace('ibrav=0,','ibrav=0, A=5.0,').replace('CELL_PARAMETERS angstrom','CELL_PARAMETERS alat')
    result=replace_periodic_coordinates(text,'qe_in',frame)
    assert result[:result.index('ATOMIC_POSITIONS')]==text[:text.index('ATOMIC_POSITIONS')]
    lines=result.splitlines();start=lines.index('ATOMIC_POSITIONS alat')
    values=[line.split() for line in lines[start+1:] if line.strip() and not line.startswith('!')][:2]
    xyz=np.asarray([[float(x) for x in row[1:4]] for row in values])
    np.testing.assert_allclose(xyz*(explicit_a or np.linalg.norm(frame.cell[0])),frame.positions,atol=1.e-10)
    actual=read(result,'qe_in',tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)


@pytest.mark.parametrize('unit',['Ang','Bohr','ScaledCartesian','NotScaledCartesianAng','NotScaledCartesianBohr'])
def test_fdf_coordinate_units(unit,frame,tmp_path):
    text=FDF.replace('AtomicCoordinatesFormat Fractional','AtomicCoordinatesFormat '+unit)
    actual=read(replace_periodic_coordinates(text,'siesta_in',frame),'siesta_in',tmp_path)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)


def test_fdf_missing_cell_added_as_explicit_30_angstrom_box(frame,tmp_path):
    start=FDF.index('LatticeConstant');end=FDF.index('%block ChemicalSpeciesLabel')
    text=(FDF[:start]+FDF[end:]).replace('AtomicCoordinatesFormat Fractional','AtomicCoordinatesFormat Ang')
    frame.pbc=(False,)*3
    result=replace_periodic_coordinates(text,'siesta_in',frame)
    assert 'LatticeConstant 1.0 Ang' in result
    actual=read(result,'siesta_in',tmp_path)
    np.testing.assert_allclose(actual.cell,np.eye(3)*30,atol=1.e-10)
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)


def test_cp2k_ambiguous_same_element_kinds_reordered_refused(frame):
    text=CP2K.replace(' water','').replace('  &END SUBSYS','    &KIND O_other\n      ELEMENT O\n    &END KIND\n  &END SUBSYS')
    frame.info['atom_order_edited']=True
    with pytest.raises(ValueError,match='multiple KIND'):replace_periodic_coordinates(text,'cp2k_in',frame)


@pytest.mark.parametrize('mode',['A','a','celldm','implicit'])
def test_qe_coordinate_prepare_and_load_end_to_end_with_alat(mode,frame,tmp_path):
    from lele.coordinate_update import prepare_coordinate_update
    text=QE.replace('ATOMIC_POSITIONS crystal','ATOMIC_POSITIONS alat')
    if mode in ('A','a'):
        text=text.replace('ibrav=0,',f'ibrav=0, {mode}=5.0,').replace('CELL_PARAMETERS angstrom','CELL_PARAMETERS alat')
    elif mode=='celldm':
        text=text.replace('ibrav=0,','ibrav=0, celldm(1)=9.0,').replace('CELL_PARAMETERS angstrom','CELL_PARAMETERS alat')
    path=tmp_path/'pw.in';path.write_bytes(text.encode())
    before=path.read_bytes()
    original=load_document(path)
    plan=prepare_coordinate_update(path,frame)
    assert path.read_bytes()==before
    assert plan.new_bytes.decode()[:text.index('ATOMIC_POSITIONS')]==text[:text.index('ATOMIC_POSITIONS')]
    actual=plan.validated_document.frames[0]
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)
    assert original.frames[0].info['qe_alat_ang']>0


def test_qe_rejects_double_lattice_parameter_declaration(frame,tmp_path):
    text=QE.replace('ibrav=0,','ibrav=0, A=5.0,')
    with pytest.raises(ValueError,match='specified twice'):replace_periodic_coordinates(text,'qe_in',frame)
    with pytest.raises(ValueError,match='specified twice'):read(text,'qe_in',tmp_path)


@pytest.mark.parametrize('kind,template',[('cp2k_in',CP2K),('qe_in',QE),('siesta_in',FDF)])
@pytest.mark.parametrize('symbols',[['O','H','H'],['H']])
def test_plain_templates_allow_atom_count_change_and_roundtrip(kind,template,symbols,frame,tmp_path):
    from lele.coordinate_update import prepare_coordinate_update
    text=template.replace(' water','').replace(' # oxygen comment','').replace(' # oxygen\n','\n')
    if kind=='cp2k_in':text=text.replace('  &END SUBSYS','    &TOPOLOGY\n      NUMBER_OF_ATOMS 2\n    &END TOPOLOGY\n  &END SUBSYS')
    frame=Frame(symbols,np.arange(len(symbols)*3).reshape(-1,3)/3,frame.cell,frame.pbc)
    path=tmp_path/{'cp2k_in':'cp2k.inp','qe_in':'pw.in','siesta_in':'siesta.fdf'}[kind]
    path.write_bytes(text.encode())
    original=path.read_bytes();plan=prepare_coordinate_update(path,frame)
    assert path.read_bytes()==original
    actual=plan.validated_document.frames[0]
    assert actual.symbols==symbols
    np.testing.assert_allclose(actual.positions,frame.positions,atol=1.e-10)
    np.testing.assert_allclose(actual.cell,frame.cell,atol=1.e-10)
    result=plan.new_bytes.decode()
    if kind=='qe_in':
        assert f'nat={len(symbols)}' in result
        assert 'ecutwfc=60.0,' in result and "input_dft='PBE'" in result
    if kind=='siesta_in':assert f'NumberOfAtoms {len(symbols)}' in result
    if kind=='cp2k_in':assert f'NUMBER_OF_ATOMS {len(symbols)}' in result


@pytest.mark.parametrize('kind,text',[
    ('cp2k_in',CP2K),
    ('qe_in',QE.replace('H 0.0 0.0 0.1','H 0.0 0.0 0.1 0 1 1')),
    ('siesta_in',FDF),
])
def test_atom_count_change_rejects_row_metadata_or_comments(kind,text,frame):
    frame=Frame(['O','H','H'],[[0,0,0],[0,0,1],[1,0,0]],frame.cell,frame.pbc)
    with pytest.raises(ValueError):replace_periodic_coordinates(text,kind,frame)


@pytest.mark.parametrize('extra',[
    '&COLVAR\n &DISTANCE\n  ATOMS 1 2\n &END\n&END\n',
    '&QMMM\n MM_INDEX 1\n&END\n',
    '&CDFT\n ATOMIC_COEFF 1 1.0\n&END\n',
])
def test_cp2k_atom_indexed_sections_reject_reorder(extra,frame):
    frame.info['atom_order_edited']=True
    text=CP2K.replace(' water','')+extra
    with pytest.raises(ValueError,match='Atom order changed'):replace_periodic_coordinates(text,'cp2k_in',frame)


@pytest.mark.parametrize('extra',[
    '%block DM.InitSpin\n 1 +\n 2 -\n%endblock DM.InitSpin\n',
    'DM.InitSpin.AF true\n',
    'MD.FCfirst 1\nMD.FClast 2\n',
    '%block TS.Atoms.Buffer\n 1 2\n%endblock TS.Atoms.Buffer\n',
])
def test_siesta_atom_indexed_settings_reject_reorder(extra,frame):
    frame.info['atom_order_edited']=True
    with pytest.raises(ValueError,match='Atom order changed'):replace_periodic_coordinates(FDF+extra,'siesta_in',frame)


def test_siesta_semicolon_comments_remain_verbatim(frame):
    text=FDF.replace('0 0 0 1 # oxygen','0 0 0 1; oxygen').replace('5 0 0 # vector','5 0 0; vector')
    result=replace_periodic_coordinates(text,'siesta_in',frame)
    assert '; oxygen' in result and '; vector' in result
    # Comment markers may directly follow a numeric/species token.
    assert result.count(';')==2
