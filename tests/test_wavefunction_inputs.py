from pathlib import Path
import numpy as np
import pytest
from ase.units import Bohr,Hartree
from lele.fchk_input import read_fchk
from lele.molden_input import read_molden
from lele.gaussian_basis import GaussianShell,GaussianWavefunction,polynomial_overlap,shell_polynomials


def fchk_text(unrestricted=False):
    lines=['Hydrogen fixture','SP UHF STO-1G']
    def field(name,kind,value):
        if isinstance(value,list):
            lines.append(f'{name:<40}   {kind}   N= {len(value):12d}')
            lines.append(' '.join(str(v) for v in value))
        else:lines.append(f'{name:<40}   {kind}   {value}')
    field('Number of atoms','I',1);field('Charge','I',0);field('Multiplicity','I',2)
    field('Atomic numbers','I',[1]);field('Current cartesian coordinates','R',[0,0,2])
    field('Number of basis functions','I',1);field('Number of alpha electrons','I',1);field('Number of beta electrons','I',0)
    field('Total Energy','R','-0.4D+00');field('Shell types','I',[0]);field('Number of primitives per shell','I',[1]);field('Shell to atom map','I',[1]);field('Primitive exponents','R',[1]);field('Contraction coefficients','R',[1])
    field('Alpha Orbital Energies','R',[-.5]);field('Alpha MO coefficients','R',[1])
    if unrestricted:field('Beta Orbital Energies','R',[.1]);field('Beta MO coefficients','R',[1])
    return '\n'.join(lines)+'\n'


def molden_text():
    return '''[Molden Format]
[Atoms] Angs
H 1 1 0 0 0
[GTO]
1 0
s 1 1.0
1.0 1.0
[MO]
Sym= A1
Ene= -0.5
Spin= Alpha
Occup= 1.0
1 1.0
Sym= A1
Ene= 0.1
Spin= Beta
Occup= 0.0
1 1.0
'''


def test_fchk_units_spin_and_surface(tmp_path):
    p=tmp_path/'h.fchk';p.write_text(fchk_text(True));doc=read_fchk(p)
    assert doc.frames[0].positions[0,2]==pytest.approx(2*Bohr)
    assert doc.frames[0].energy_ev==pytest.approx(-.4*Hartree)
    assert set(doc.calculation_results.orbitals[0].channels)=={'alpha','beta'}
    wf=doc.wavefunction
    assert wf.can_evaluate
    assert wf.evaluate_points('alpha',1,np.array([[0,0,2]]))[0]==pytest.approx((2/np.pi)**.75)
    grid=wf.evaluate_orbital('alpha',1,spacing=.5,padding=1)
    assert grid.data.shape==(5,5,5)
    assert np.isfinite(grid.data).all()


def test_fchk_restricted_open_shell_occupation(tmp_path):
    p=tmp_path/'h.fch';p.write_text(fchk_text());doc=read_fchk(p)
    assert doc.calculation_results.orbitals[0].channels['restricted'][0].occupation==1


def test_molden_read(tmp_path):
    p=tmp_path/'h.molden';p.write_text(molden_text());doc=read_molden(p)
    assert doc.wavefunction.can_evaluate
    assert doc.calculation_results.orbitals[0].channels['alpha'][0].energy_ev==pytest.approx(-.5*Hartree)
    assert doc.wavefunction.evaluate_points('alpha',1,np.zeros((1,3)))[0]==pytest.approx((2/np.pi)**.75)


def test_molden_flags_and_sparse_coefficients(tmp_path):
    p=tmp_path/'d.molden';text=molden_text().replace('[GTO]','[5D]\n[GTO]').replace('s 1 1.0','d 1 1.0')
    p.write_text(text);wf=read_molden(p).wavefunction
    assert wf.shells[0].size==5
    assert wf.coefficients['alpha'].shape==(1,5)
    assert wf.evaluate_points('alpha',1,np.array([[0.,0.,1.]]))[0]>0
    assert wf.evaluate_points('alpha',1,np.array([[1.,0.,0.]]))[0]<0


def test_cartesian_and_pure_basis_orthonormality():
    # Accurate tensor Gauss-Hermite integration for e^-2r² primitive products.
    x,w=np.polynomial.hermite.hermgauss(16)
    coords=np.array(np.meshgrid(x,x,x,indexing='ij')).reshape(3,-1).T/np.sqrt(2)
    weights=np.einsum('i,j,k->ijk',w,w,w).ravel()/2**1.5
    for l in range(4):
        for pure in (False,True):
            if pure and l<2:continue
            shell=GaussianShell(np.zeros(3),l,np.array([1.]),np.array([1.]),pure)
            values=shell.evaluate(coords)*np.exp(np.sum(coords**2,axis=1))[:,None]
            overlap=values.T@(values*weights[:,None])
            np.testing.assert_allclose(np.diag(overlap),1,atol=1e-12)
            if pure or l<2:np.testing.assert_allclose(overlap,np.eye(shell.size),atol=1e-12)


def test_contracted_normalization():
    shell=GaussianShell(np.zeros(3),0,np.array([.3,1.5]),np.array([.4,.8]))
    x=np.linspace(-8,8,101);points=np.array(np.meshgrid(x,x,x,indexing='ij')).reshape(3,-1).T
    norm=np.sum(shell.evaluate(points)[:,0]**2)*(x[1]-x[0])**3
    assert norm==pytest.approx(1,abs=1e-8)


@pytest.mark.parametrize('old,new', [('1.0 1.0','-1.0 1.0'), ('[Atoms] Angs','[Atoms]'),('1 1.0\nSym','2 1.0\nSym')])
def test_molden_malformed(tmp_path,old,new):
    p=tmp_path/'bad.molden';p.write_text(molden_text().replace(old,new))
    with pytest.raises(ValueError):read_molden(p)


def test_fchk_truncated(tmp_path):
    p=tmp_path/'bad.fchk';p.write_text(fchk_text()[:-3])
    with pytest.raises(ValueError):read_fchk(p)


def test_grid_limit_and_unsupported_shell(tmp_path):
    p=tmp_path/'h.molden';p.write_text(molden_text());wf=read_molden(p).wavefunction
    with pytest.raises(ValueError,match='limit'):wf.evaluate_orbital('alpha',1,spacing=.01)
    with pytest.raises(ValueError):wf.evaluate_orbital('alpha',1,spacing=0)
    p.write_text(molden_text().replace('s 1 1.0','g 1 1.0'))
    wf=read_molden(p).wavefunction
    assert not wf.can_evaluate
    assert 'l=4' in wf.unsupported_reason


def test_fchk_sp_and_pure_shells(tmp_path):
    p=tmp_path/'sp.fchk'
    text=fchk_text().replace('Number of basis functions                   I   1','Number of basis functions                   I   4')
    # Construct replacement through actual header lines, independent of padding.
    lines=text.splitlines()
    for i,line in enumerate(lines):
        if line.startswith('Number of basis functions'):lines[i]=f'{"Number of basis functions":<40}   I   4'
        if line.startswith('Shell types'):lines[i+1]='-1'
        if line.startswith('Alpha MO coefficients'):
            lines[i]=f'{"Alpha MO coefficients":<40}   R   N= 4';lines[i+1]='1 0 0 0'
    lines += [f'{"P(S=P) Contraction coefficients":<40}   R   N= 1','1.0']
    p.write_text('\n'.join(lines));wf=read_fchk(p).wavefunction
    assert [s.angular_momentum for s in wf.shells]==[0,1]
    assert wf.coefficients['restricted'].shape==(1,4)


def test_molden_bohr_and_obsolete_shell_scale(tmp_path):
    p=tmp_path/'h.molden'
    p.write_text(molden_text().replace('[Atoms] Angs','[Atoms] AU').replace('H 1 1 0 0 0','H 1 1 0 0 2').replace('s 1 1.0','s 1 2.0'))
    doc=read_molden(p)
    assert doc.frames[0].positions[0,2]==pytest.approx(2*Bohr)
    assert doc.wavefunction.shells[0].exponents[0]==1.


def test_fchk_skips_character_arrays(tmp_path):
    p=tmp_path/'h.fchk'
    text=fchk_text().replace('Number of atoms',f'{"Route":<40}   C   N= 13\n# arbitrary character data without numeric fields\nNumber of atoms',1)
    p.write_text(text)
    assert read_fchk(p).wavefunction.can_evaluate


def test_cancelled_orbital_evaluation(tmp_path):
    from lele.output_text import output_read_session,LoadCancelled
    p=tmp_path/'h.molden';p.write_text(molden_text());wf=read_molden(p).wavefunction
    cancelled=[False]
    with output_read_session(cancelled=lambda:cancelled[0]):
        cancelled[0]=True
        with pytest.raises(LoadCancelled):wf.evaluate_orbital('alpha',1)


@pytest.mark.parametrize('flag,size', [('[5D]',7),('[5D7F]',7),('[5D10F]',10),('[7F]',7),('[6D10F]',10)])
def test_molden_combined_spherical_convention(tmp_path,flag,size):
    p=tmp_path/'f.molden'
    p.write_text(molden_text().replace('[GTO]',flag+'\n[GTO]').replace('s 1 1.0','f 1').replace('1 0\ns','1\ns'))
    assert read_molden(p).wavefunction.shells[0].size==size


def test_molden_optional_gto_atom_zero(tmp_path):
    p=tmp_path/'h.molden';p.write_text(molden_text().replace('1 0\ns 1 1.0','1\ns 1'))
    assert read_molden(p).wavefunction.can_evaluate


def test_fchk_explicit_shell_centers(tmp_path):
    p=tmp_path/'h.fchk';p.write_text(fchk_text()+f'{"Coordinates of each shell":<40}   R   N= 3\n1 2 3\n')
    wf=read_fchk(p).wavefunction
    np.testing.assert_allclose(wf.shells[0].center,[1,2,3])
    assert wf.evaluate_points('restricted',1,np.array([[1,2,3]]))[0]==pytest.approx((2/np.pi)**.75)
