"""Optional independent libcint/PySCF numerical checks (not a runtime dependency).

Run with PySCF installed and OMP_NUM_THREADS=1. Synthetic basis inputs compare
all s/p/d/f components, signed contracted primitives, MO mixtures and phases.
FCHK is generated from PySCF basis data using Gaussian's documented order.
This is not validation against a real Gaussian/ORCA production output.
"""
import numpy as np
import pytest
pyscf = pytest.importorskip('pyscf')
from pyscf import gto
from pyscf.tools import molden
from lele.molden_input import read_molden
from lele.fchk_input import read_fchk


def reference_case(cart):
    mol = gto.M(atom='He .2 .1 -.1', unit='Bohr', verbose=0, cart=cart,
                basis={'He':[[l, [1.3, .7], [.4, -.2]] for l in range(4)]})
    n = mol.nao_nr()
    # Signed mixtures expose relative AO phase/order errors, not just magnitudes.
    coeff = np.random.default_rng(82).normal(size=(n, 4))
    points = np.random.default_rng(9).normal(size=(100, 3))
    ao = mol.eval_gto('GTOval_cart' if cart else 'GTOval_sph', points)
    return mol, coeff, points, ao @ coeff


@pytest.mark.parametrize('cart', [False, True])
def test_molden_against_pyscf_libcint(tmp_path, cart):
    mol, coeff, points, expected = reference_case(cart)
    path = tmp_path/'independent.molden'
    molden.from_mo(mol, str(path), coeff, ene=np.arange(4)*.1, occ=np.zeros(4))
    doc = read_molden(path)
    actual = np.column_stack([doc.wavefunction.evaluate_points('alpha', i+1, points) for i in range(4)])
    np.testing.assert_allclose(actual, expected, rtol=2e-11, atol=2e-12)


@pytest.mark.parametrize('cart', [False, True])
def test_fchk_against_pyscf_libcint(tmp_path, cart):
    mol, coeff, points, expected = reference_case(cart)
    if cart:
        coeff = mol.intor('int1e_ovlp').diagonal()[:,None]**.5 * coeff
    coeff = coeff[molden.order_ao_index(mol)]
    records = ['Independent synthetic FCHK', 'SP RHF custom']
    def scalar(name, typ, value):records.append(f'{name:<43} {typ} {value}')
    def array(name, typ, values):
        values = np.asarray(values).ravel()
        records.append(f'{name:<43} {typ} N= {len(values)}')
        for i in range(0,len(values),5):
            records.append(' '.join(str(int(x)) if typ=='I' else f'{x:.16e}' for x in values[i:i+5]))
    scalar('Number of atoms','I',1)
    scalar('Number of basis functions','I',mol.nao_nr())
    scalar('Number of alpha electrons','I',1)
    scalar('Number of beta electrons','I',1)
    array('Atomic numbers','I',[2]);array('Current cartesian coordinates','R',mol.atom_coords())
    array('Shell types','I',[l if cart or l<2 else -l for l in range(4)])
    array('Number of primitives per shell','I',[2]*4)
    array('Shell to atom map','I',[1]*4)
    array('Primitive exponents','R',[mol.bas_exp(i) for i in range(4)])
    array('Contraction coefficients','R',[mol.bas_ctr_coeff(i).ravel() for i in range(4)])
    array('Coordinates of each shell','R',[mol.atom_coord(0)]*4)
    array('Alpha Orbital Energies','R',np.arange(4)*.1)
    array('Alpha MO coefficients','R',coeff.T)
    path=tmp_path/'independent.fchk';path.write_text('\n'.join(records)+'\n')
    doc=read_fchk(path)
    actual=np.column_stack([doc.wavefunction.evaluate_points('restricted',i+1,points) for i in range(4)])
    np.testing.assert_allclose(actual,expected,rtol=2e-11,atol=2e-12)
