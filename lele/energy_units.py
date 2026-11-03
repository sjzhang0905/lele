"""ASE energies stay in eV; only the presentation layer changes units."""
import numpy as np
from ase.units import kcal, mol

EV_TO_KCAL_MOL = mol / kcal
MOLECULAR = ('gaussian', 'orca', 'nwchem', 'gamess', 'qchem', 'xtb', 'molpro')
PERIODIC = ('vasp', 'qe', 'espresso', 'siesta', 'cp2k', 'castep', 'abinit')


def energy_unit(frame, format_name=''):
    source=' '.join(str(v) for v in (frame.info.get('source_kind',''),frame.info.get('source_format',''),format_name)).lower()
    if any(name in source for name in MOLECULAR):return 'kcal/mol'
    if any(name in source for name in PERIODIC):return 'eV'
    return 'eV' if any(frame.pbc) else 'kcal/mol'


def display_energy(frame, format_name=''):
    unit=energy_unit(frame,format_name)
    value=frame.energy_ev
    if value is None or not np.isfinite(value):return None,unit
    return value*(EV_TO_KCAL_MOL if unit=='kcal/mol' else 1.),unit


def rigid_equivalent(old,new):
    if old.symbols!=new.symbols:return False
    if not len(old.symbols):return True
    if old.pbc!=new.pbc:return False
    if any(old.pbc):
        if min(abs(np.linalg.det(old.cell)),abs(np.linalg.det(new.cell)))<1.e-9:return False
        rotation=np.linalg.solve(old.cell,new.cell)
        if (not np.allclose(rotation@rotation.T,np.eye(3),atol=1.e-8,rtol=0)
                or not np.isclose(np.linalg.det(rotation),1.,atol=1.e-8,rtol=0)):return False
        # Translation is common modulo periodic lattice vectors. This remains
        # valid when atoms are recentered into different nearest images.
        delta=(new.positions-old.positions@rotation)@np.linalg.inv(new.cell)
        delta=delta-delta[0]
        axes=np.asarray(old.pbc,dtype=bool)
        delta[:,axes]-=np.rint(delta[:,axes])
        return np.allclose(delta@new.cell,0,atol=2.e-5,rtol=0)
    a=old.positions-old.positions.mean(axis=0);b=new.positions-new.positions.mean(axis=0)
    u,_,vt=np.linalg.svd(a.T@b);d=np.eye(3);d[-1,-1]=np.linalg.det(u@vt);r=u@d@vt
    return (np.allclose(a@r,b,atol=2e-5,rtol=0) and
            (not any(old.pbc) or np.allclose(old.cell@r,new.cell,atol=2e-5,rtol=0)))
