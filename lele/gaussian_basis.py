"""Gaussian AO/MO evaluation in atomic units, with explicit shell ordering.

Cartesian s/p/d/f and real spherical d/f follow Gaussian/Molden order. Higher
angular momenta are retained in source metadata but deliberately not evaluated.
Only real, non-relativistic Gaussian orbitals are supported.
"""
from dataclasses import dataclass, field
from math import factorial, pi, sqrt
import numpy as np
from ase.units import Bohr
from .core import Volume
from .output_text import check_load_cancelled, load_progress

CART = {
 0: [(0,0,0)], 1: [(1,0,0),(0,1,0),(0,0,1)],
 2: [(2,0,0),(0,2,0),(0,0,2),(1,1,0),(1,0,1),(0,1,1)],
 3: [(3,0,0),(0,3,0),(0,0,3),(1,2,0),(2,1,0),(2,0,1),(1,0,2),(0,1,2),(0,2,1),(1,1,1)]}
PURE = {
 2: [{(0,0,2):2,(2,0,0):-1,(0,2,0):-1}, {(1,0,1):1}, {(0,1,1):1}, {(2,0,0):1,(0,2,0):-1}, {(1,1,0):1}],
 3: [{(0,0,3):2,(2,0,1):-3,(0,2,1):-3}, {(1,0,2):4,(3,0,0):-1,(1,2,0):-1}, {(0,1,2):4,(2,1,0):-1,(0,3,0):-1}, {(2,0,1):1,(0,2,1):-1}, {(1,1,1):1}, {(3,0,0):1,(1,2,0):-3}, {(2,1,0):3,(0,3,0):-1}]}


def shell_polynomials(l, pure=False):
    if pure and l >= 2:
        if l not in PURE: raise ValueError(f'Spherical angular momentum l={l} is not supported for orbital surfaces.')
        return PURE[l]
    if l not in CART: raise ValueError(f'Cartesian angular momentum l={l} is not supported for orbital surfaces.')
    return [{p:1.} for p in CART[l]]


def _moment(n, exponent):
    if n % 2: return 0.
    k=n//2
    return factorial(2*k)*sqrt(pi)/(4**k*factorial(k)*exponent**(k+.5))


def polynomial_overlap(poly, exponent):
    return sum(c*d*np.prod([_moment(a+b, exponent) for a,b in zip(p,q)])
               for p,c in poly.items() for q,d in poly.items())


@dataclass
class GaussianShell:
    center: np.ndarray  # Bohr
    angular_momentum: int
    exponents: np.ndarray
    coefficients: np.ndarray
    pure: bool = False

    @property
    def size(self):
        l=self.angular_momentum
        return 2*l+1 if self.pure else (l+1)*(l+2)//2

    def evaluate(self, points):
        delta=points-np.asarray(self.center)
        r2=np.sum(delta*delta,axis=1)
        polynomials=shell_polynomials(self.angular_momentum,self.pure)
        reference=polynomials[0]
        norms=np.array([1/sqrt(polynomial_overlap(reference,2*a)) for a in self.exponents])
        weights=np.asarray(self.coefficients)*norms
        overlap=sum(w*v*polynomial_overlap(reference,a+b)
                    for a,w in zip(self.exponents,weights) for b,v in zip(self.exponents,weights))
        if not np.isfinite(overlap) or overlap<=0: raise ValueError('Invalid Gaussian contraction normalization.')
        radial=sum(w*np.exp(-a*r2) for a,w in zip(self.exponents,weights))/sqrt(overlap)
        reference_norm=polynomial_overlap(reference,2.)
        values=[]
        # Homogeneous same-l polynomials share the radial factor; their
        # relative normalization is independent of the primitive exponent.
        for poly in polynomials:
            angular=sum(c*np.prod(delta**np.asarray(p),axis=1) for p,c in poly.items())
            factor=sqrt(reference_norm/polynomial_overlap(poly,2.))
            values.append(radial*angular*factor)
        return np.asarray(values).T


@dataclass
class GaussianWavefunction:
    positions: np.ndarray  # Angstrom
    shells: list[GaussianShell]
    coefficients: dict  # channel -> (nmo, nao), source order
    orbitals: list  # (channel, 1-based number, occupation, energy eV)
    source_format: str
    unsupported_reason: str = ''
    metadata: dict = field(default_factory=dict)

    @property
    def can_evaluate(self): return bool(self.shells and self.coefficients and not self.unsupported_reason)

    def evaluate_points(self, channel, number, points):
        """MO amplitude (Bohr^-3/2), points in Bohr, source 1-based MO."""
        if not self.can_evaluate: raise ValueError(self.unsupported_reason or 'No Gaussian basis/MO coefficients were supplied.')
        matrix=self.coefficients[channel]
        if not 1<=number<=len(matrix): raise ValueError('Orbital number outside source range.')
        coefficients=matrix[number-1];result=np.zeros(len(points));start=0
        for shell in self.shells:
            check_load_cancelled()
            block=coefficients[start:start+shell.size]
            if np.any(block):result += shell.evaluate(points) @ block
            start+=shell.size
        return result

    def evaluate_orbital(self, channel, number, spacing=.25, padding=3., max_points=2_000_000):
        """Return an Angstrom-positioned grid of signed MO amplitudes."""
        if not np.isfinite(spacing) or spacing<=0 or not np.isfinite(padding) or padding<=0:
            raise ValueError('Grid spacing and padding must be finite positive values.')
        origin=np.min(self.positions,axis=0)-padding
        extent=np.ptp(self.positions,axis=0)+2*padding
        shape=np.maximum(2,np.ceil(extent/spacing).astype(int)+1)
        count=int(np.prod(shape))
        if count>max_points: raise ValueError(f'Orbital grid has {count:,} points; increase spacing (limit {max_points:,}).')
        data=np.empty(count,dtype=np.float32)
        progress=load_progress('Evaluating molecular orbital',count)
        for start in range(0,count,8192):
            stop=min(start+8192,count)
            indices=np.array(np.unravel_index(np.arange(start,stop),tuple(shape))).T
            points=(origin+indices*spacing)/Bohr
            data[start:stop]=self.evaluate_points(channel,number,points)
            progress(stop)
        return Volume(data.reshape(tuple(shape)),origin,np.eye(3)*spacing)
