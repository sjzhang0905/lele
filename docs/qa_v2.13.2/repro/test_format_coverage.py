"""Independent import-routing checks of every advertised legacy input family."""
import numpy as np
import pytest
from ase import Atoms
from ase.io import read, write
from lele.formats import load_document


@pytest.mark.parametrize('suffix,fmt',[
    ('pdb','proteindatabank'),('mol','mol'),('sdf','sdf'),('xsf','xsf'),
    ('gen','gen'),('cfg','cfg'),('gro','gromacs'),('g96','gromos'),('traj','traj'),
    ('res','res'),('xsd','xsd'),('xtd','xtd'),('struct','struct'),('nw','nwchem-in')])
def test_advertised_generic_formats_accept_reference_writer_output(tmp_path,suffix,fmt):
    atoms=Atoms(['O','H','H'],positions=[[1,2,3],[1.75,2.5,3],[.25,2.5,3]],cell=[10,11,12],pbc=True)
    path=tmp_path/('water.'+suffix);write(path,atoms,format=fmt)
    oracle=read(path,format=fmt)
    document=load_document(path);assert document.frames
    frame=document.frames[0]
    assert frame.symbols==oracle.get_chemical_symbols()
    np.testing.assert_allclose(frame.positions,oracle.positions,atol=1.e-8)


@pytest.mark.parametrize('name,text,expected',[
    ('orca.inp','! HF STO-3G\n* xyz 0 1\nO 1 2 3\nH 1.75 2.5 3\nH .25 2.5 3\n*\n',[[1,2,3],[1.75,2.5,3],[.25,2.5,3]]),
    ('water.fdf','SystemName water\nNumberOfAtoms 3\nNumberOfSpecies 2\nLatticeConstant 1 Ang\n%block LatticeVectors\n10 0 0\n0 11 0\n0 0 12\n%endblock LatticeVectors\n%block ChemicalSpeciesLabel\n1 8 O\n2 1 H\n%endblock ChemicalSpeciesLabel\nAtomicCoordinatesFormat Ang\n%block AtomicCoordinatesAndAtomicSpecies\n1 2 3 1\n1.75 2.5 3 2\n.25 2.5 3 2\n%endblock AtomicCoordinatesAndAtomicSpecies\n',[[1,2,3],[1.75,2.5,3],[.25,2.5,3]]),
    ('water.mol2','@<TRIPOS>MOLECULE\nwater\n3 2 1 0 0\nSMALL\nUSER_CHARGES\n@<TRIPOS>ATOM\n1 O1 1 2 3 O.3 1 MOL -0.8\n2 H1 1.75 2.5 3 H 1 MOL 0.4\n3 H2 .25 2.5 3 H 1 MOL 0.4\n@<TRIPOS>BOND\n1 1 2 1\n2 1 3 1\n',[[1,2,3],[1.75,2.5,3],[.25,2.5,3]]),
    ('water.pqr','ATOM 1 O WAT 1 1.000 2.000 3.000 -0.8 1.5\nATOM 2 H1 WAT 1 1.750 2.500 3.000 0.4 1.2\nATOM 3 H2 WAT 1 0.250 2.500 3.000 0.4 1.2\nEND\n',[[1,2,3],[1.75,2.5,3],[.25,2.5,3]])])
def test_explicit_inline_molecular_and_siesta_inputs(tmp_path,name,text,expected):
    path=tmp_path/name;path.write_text(text)
    frame=load_document(path).frames[0]
    assert frame.symbols==['O','H','H']
    np.testing.assert_allclose(frame.positions,expected,atol=1.e-10)


def test_siesta_xv_geometry_and_bohr_units(tmp_path):
    from ase.units import Bohr
    path=tmp_path/'water.xv'
    path.write_text('20 0 0 0 0 0\n0 21 0 0 0 0\n0 0 22 0 0 0\n3\n1 8 1 2 3 0 0 0\n2 1 2 2 3 0 0 0\n2 1 0 2 3 0 0 0\n')
    frame=load_document(path).frames[0]
    assert frame.symbols==['O','H','H']
    np.testing.assert_allclose(frame.positions,np.array([[1,2,3],[2,2,3],[0,2,3]])*Bohr,atol=1.e-10)


@pytest.mark.parametrize('line',[
    'ATOM  1 O ASN 1 1.000 2.000 3.000 -0.8 1.5',
    'HETATM 1 O ASN 1 1.000 2.000 3.000 -0.8 1.5',
    'ATOM      1  O   WAT A   1       1.000   2.000   3.000 -0.8000 1.5000'])
def test_pqr_atom_name_is_oxygen_regardless_of_residue_and_spacing(tmp_path,line):
    # APBS PQR accepts whitespace-separated fields and an optional chain ID:
    # https://apbs.readthedocs.io/en/latest/formats/pqr.html
    path=tmp_path/'oxygen.pqr';path.write_text(line+'\n')
    frame=load_document(path).frames[0]
    assert frame.symbols==['O']
    np.testing.assert_allclose(frame.positions,[[1,2,3]],atol=1.e-10)
