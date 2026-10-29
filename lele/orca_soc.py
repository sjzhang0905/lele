"""Printed complex SOC elements, mixed states and corrected absorption tables."""
from dataclasses import dataclass, field
import re
import numpy as np
from .gaussian_vibrations import _number
from .calculation_results import NUMBER
from .output_text import read_output_lines


@dataclass
class SOCElement:
    bra: str
    ket: str
    components: dict
    source_line: int

    @property
    def norm(self):return float(np.sqrt(sum(abs(v)**2 for v in self.components.values())))


@dataclass
class SOCState:
    number: int
    energy_cm: float | None = None
    energy_ev: float | None = None
    composition: list = field(default_factory=list)


@dataclass
class SOCAnalysis:
    source_line: int
    label: str
    elements: list = field(default_factory=list)
    states: list = field(default_factory=list)
    transitions: list = field(default_factory=list)
    stabilization_cm: float | None = None
    note: str = 'Couplings are printed complex matrix elements in cm⁻¹. Missing entries are not zero-filled; the displayed norm is not an ISC rate.'


def read_soc(path):
    lines=read_output_lines(path);analyses=[];analysis=None;state=None;section='';i=0
    vector=re.compile(rf'^\s*(\d+)\s+(\d+)\s+\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)\s+\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)\s+\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)')
    def ensure(line):
        nonlocal analysis
        if analysis is None:
            analysis=SOCAnalysis(line,'ORCA SOC');analyses.append(analysis)
        return analysis
    while i<len(lines):
        line=lines[i];upper=line.upper()
        if 'CALCULATED SOCME BETWEEN TRIPLETS AND SINGLETS' in upper:
            analysis=SOCAnalysis(i+1,'Triplet–singlet SOC');analyses.append(analysis);section='vector'
        elif 'NONZERO SOC MATRIX ELEMENTS' in upper:
            ensure(i+1);section='scalar'
        elif 'Eigenvalues of the SOC matrix' in line:ensure(i+1);section='energies'
        elif 'Eigenvectors of the SOC matrix' in line:ensure(i+1);section='states'
        elif 'SOC CORRECTED' in upper or 'SPIN ORBIT CORRECTED' in upper:
            if 'ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC' in upper:ensure(i+1);section='spectrum'
            elif 'SPECTRUM' in upper or 'SPECTRA' in upper:section=''
        stabilization=re.search(rf'SOC stabilization of the ground state:\s*({NUMBER})',line)
        if stabilization:ensure(i+1).stabilization_cm=_number(stabilization[1])
        if section=='vector':
            m=vector.match(line)
            if m:
                values=[_number(m[k]) for k in range(3,9)]
                ensure(i+1).elements.append(SOCElement('T'+m[1],'S'+m[2],dict(zip(('Z','X','Y'),[complex(*values[k:k+2]) for k in (0,2,4)])),i+1))
        elif section=='scalar':
            f=line.split()
            if len(f)==10:
                try:
                    values=[_number(x) for x in f]
                    ensure(i+1).elements.append(SOCElement('B%s/R%s/S%s/Ms%s'%tuple(f[:4]),'B%s/R%s/S%s/Ms%s'%tuple(f[4:8]),{'H':complex(*values[8:])},i+1))
                except ValueError:pass
        elif section=='energies':
            m=re.match(rf'^\s*(\d+):\s*({NUMBER})\s+({NUMBER})\s*$',line)
            if m:ensure(i+1).states.append(SOCState(int(m[1]),_number(m[2]),_number(m[3])))
        elif section=='states':
            m=re.match(rf'^\s*STATE\s+(\d+):\s*({NUMBER})',line)
            if m:
                state=next((s for s in ensure(i+1).states if s.number==int(m[1])),None)
                if state is None:state=SOCState(int(m[1]),_number(m[2]));analysis.states.append(state)
            else:
                m=re.match(rf'^\s*({NUMBER})\s+({NUMBER})\s+({NUMBER})\s*:\s*(.+)$',line)
                if m and state is not None:
                    state.composition.append(dict(weight=_number(m[1]),real=_number(m[2]),imag=_number(m[3]),basis=m[4].strip()))
        elif section=='spectrum':
            m=re.match(r'^\s*(\d+)\s+(\d+)\s+(.+)$',line)
            if m:
                try:values=[_number(v) for v in re.findall(NUMBER,m[3])]
                except ValueError:values=[]
                if len(values)>=4:
                    item=dict(from_state=int(m[1]),to_state=int(m[2]),energy_cm=values[0],wavelength_nm=values[1],oscillator_strength=values[2],dipole_strength=values[3],source_line=i+1)
                    pairs=re.findall(rf'\(\s*({NUMBER})\s*,\s*({NUMBER})\s*\)',m[3])
                    if len(pairs)==3:item['complex_dipole']={a:[_number(v[0]),_number(v[1])] for a,v in zip('XYZ',pairs)}
                    # Prefer the later full complex table over a duplicate real display.
                    old=next((r for r in analysis.transitions if r['from_state']==item['from_state'] and r['to_state']==item['to_state']),None)
                    if old is None:analysis.transitions.append(item)
                    elif 'complex_dipole' in item:old.update(item)
        i+=1
    return [a for a in analyses if a.elements or a.states or a.transitions]
