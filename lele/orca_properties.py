"""ORCA permanent dipoles and TD/TDA moments in classic and ORCA 6 tables."""
import re
import numpy as np
from .gaussian_properties import DipoleRecord, ElectronicSpectrum, Transition, TransitionContribution, AU_TO_DEBYE, N
from .gaussian_vibrations import _number
from .orca_results import COORDINATES, reference_at
from .output_text import read_output_lines
from .spectra import HC_EV_NM

STATE = re.compile(rf'^\s*STATE\s+(\d+):\s*E=\s*({N})\s*au\s+({N})\s*eV', re.I)
CONTRIBUTION = re.compile(rf'^\s*(\d+)([abAB]?)\s*(->|<-)\s*(\d+)([abAB]?)\s*:\s*({N})(?:\s*\(c=\s*({N})\))?')
MULTIPLICITIES = {1:'Singlet', 2:'Doublet', 3:'Triplet', 4:'Quartet', 5:'Quintet'}
ARROW_ROW = re.compile(r'^\s*(\d+)-(\d+)\s*([A-Za-z][\w\'\"]*)?\s*->\s*(\d+)-(\d+)\s*([A-Za-z][\w\'\"]*)?\s+(.+)$')


def _table_rows(lines, start):
    rows = []
    j = start+1
    while j < len(lines):
        text = lines[j].strip()
        arrow = ARROW_ROW.match(text)
        old = re.match(rf'^\s*(\d+)\s+({N})\s+({N})\s+(.+)$', text) if arrow is None else None
        if arrow:
            values = [_number(v) for v in re.findall(N, arrow[7])]
            if int(arrow[1]) == 0 and len(values) >= 3:
                rows.append(dict(number=int(arrow[4]), mult=int(arrow[5]), energy=values[0], wavelength=values[2],
                                 values=values[3:], forbidden='spin forbidden' in text.lower(),
                                 label=text.split(arrow[7], 1)[0].strip(), line=j+1))
        elif old:
            rows.append(dict(number=int(old[1]), mult=None, energy=_number(old[2])*HC_EV_NM/1.e7,
                             wavelength=_number(old[3]), values=[_number(v) for v in re.findall(N, old[4])],
                             forbidden='spin forbidden' in text.lower(), label=old[1], line=j+1))
        elif rows:
            break
        elif j-start > 10:
            break
        j += 1
    return rows, j


def read_orca_properties(path, results):
    lines = read_output_lines(path)
    dipoles, spectra, batch = [], [], []
    spectrum = last = None
    spin = 'Excited state'
    dipole_state = None
    job_starts = {job.start_line-1 for job in results.jobs}
    numerical=[(e.source_line,e.end_line or len(lines)) for e in results.hessians if e.kind.startswith('Numerical exact')]

    def new_spectrum(line, description):
        job = next((j for j in reversed(results.jobs) if j.start_line <= line), None)
        label = 'ORCA '+description+('' if job is None else f' · job {job.index+1}')
        value = ElectronicSpectrum(reference_at(results, line), source_line=line, label=label)
        spectra.append(value)
        batch.append(value)
        return value

    def find_target(row, table_line):
        candidates = [t for s in batch for t in s.transitions]
        target = None
        if row['mult'] is not None:
            name = MULTIPLICITIES.get(row['mult'], f'Multiplicity {row["mult"]}')
            target = next((t for t in candidates if t.number == row['number'] and t.state.startswith(name)), None)
            manifold = [t for t in candidates if t.state.startswith(name)]
            if target is None and 1 <= row['number'] <= len(manifold):
                target = manifold[row['number']-1]
            group = next((s for s in batch if name in s.label), None)
        else:
            name = 'Excited state'
            group = batch[0] if batch else None
            # Classic tables number spin manifolds consecutively, even when
            # their STATE blocks independently restart at 1.
            if len(batch) > 1 and 1 <= row['number'] <= len(candidates):
                target = candidates[row['number']-1]
            else:
                target = next((t for t in candidates if t.number == row['number']), None)
        if target is None:
            if group is None:
                group = new_spectrum(table_line, name)
            if row['energy'] <= 0 or row['wavelength'] <= 0:
                return None
            target = Transition(row['number'], name, row['energy'], row['wavelength'], None, source_line=row['line'])
            group.transitions.append(target)
        target.source_label = row['label']
        target.energy_ev, target.wavelength_nm = row['energy'], row['wavelength']
        return target

    i = 0
    while i < len(lines):
        line = lines[i]
        upper = line.upper()
        if any(start<=i+1<=end for start,end in numerical):
            i+=1
            continue
        if i in job_starts or COORDINATES.search(line):
            batch = []
            spectrum = last = None
            spin = 'Excited state'
            dipole_state = None
        header = re.search(r'(?:TD-?DFT|SF-TDA|CIS|TDA|ROCIS).*EXCITED STATES', upper)
        if header:
            spin = 'Singlet' if 'SINGLETS' in upper else 'Triplet' if 'TRIPLETS' in upper else 'Excited state'
            if any(spin in s.label for s in batch):
                batch = []
            spectrum = last = None
        state = STATE.match(line)
        if state:
            number, energy = int(state[1]), _number(state[3])
            if energy > 0:
                mult = re.search(r'\bMult\s+(\d+)', line, re.I)
                description = MULTIPLICITIES.get(int(mult[1]), 'Multiplicity '+mult[1]) if mult else spin
                symmetry = re.search(r'\bSym:\s*(\S+)', line, re.I)
                if symmetry:
                    description += '-'+symmetry[1]
                if spectrum is None or (spectrum.transitions and number <= spectrum.transitions[-1].number):
                    if spectrum is not None:
                        batch = []
                    spectrum = new_spectrum(i+1, description.split('-', 1)[0])
                last = Transition(number, description, energy, HC_EV_NM/energy, None, source_line=i+1)
                spectrum.transitions.append(last)
        contribution = CONTRIBUTION.match(line)
        if contribution and last is not None:
            last.contributions.append(TransitionContribution(int(contribution[1]), int(contribution[4]),
                None if contribution[7] is None else _number(contribution[7]), contribution[2].upper(),
                contribution[5].upper(), contribution[3], _number(contribution[6])))
        # An NTO occupation is not a canonical-orbital excitation coefficient.
        if 'NATURAL TRANSITION ORBITALS' in upper:
            last = None
        if 'EXCITED STATE DIPOLE MOMENTS' in upper:
            density = 'ORCA unrelaxed' if 'UNRELAXED' in upper else 'ORCA relaxed' if 'RELAXED' in upper else 'ORCA'
            j = i+1
            seen = False
            while j < len(lines):
                row = re.match(rf'^\s*IROOT\s*=\s*(\d+):\s*({N})\s+({N})\s+({N})\s+({N})\s+({N})', lines[j])
                if row:
                    root = int(row[1])
                    vector = np.asarray([_number(row[k]) for k in (3,4,5)]) * AU_TO_DEBYE
                    dipoles.append(DipoleRecord(reference_at(results, j+1), vector, _number(row[6]), j+1,
                        density, root if root else None, 'excited permanent' if root else 'permanent'))
                    seen = True
                elif seen:
                    break
                elif j-i > 8:
                    break
                j += 1
            last = None
            i = max(i+1, j)
            continue
        explicit_state = re.search(r'(?:EXCITED STATE PROPERTIES(?: FOR)?(?: STATE)?|DIPOLE MOMENT.*STATE)\s*[:=]?\s*(\d+)', upper)
        if explicit_state:
            dipole_state = int(explicit_state[1])
        dipole = re.match(rf'^\s*Total Dipole Moment(?:\s*\(([^)]+)\))?\s*:\s*({N})\s+({N})\s+({N})', line, re.I)
        if dipole:
            vector = np.asarray([_number(dipole[k]) for k in (2,3,4)])
            if not dipole[1] or 'debye' not in dipole[1].lower():
                vector *= AU_TO_DEBYE
            total = float(np.linalg.norm(vector))
            for following in lines[i+1:i+8]:
                norm = re.search(rf'Magnitude\s*\(Debye\)\s*:\s*({N})', following, re.I)
                if norm:
                    total = _number(norm[1])
                    break
            dipoles.append(DipoleRecord(reference_at(results, i+1), vector, total, i+1, 'ORCA', dipole_state,
                                        'permanent' if dipole_state is None else 'excited permanent'))
            dipole_state = None
        table = None
        if 'ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS' in upper:
            table = 'electric'
        elif 'ABSORPTION SPECTRUM VIA TRANSITION VELOCITY DIPOLE MOMENTS' in upper:
            table = 'velocity'
        elif line.strip().upper().startswith('CD SPECTRUM'):
            table = 'magnetic'
        if table is not None:
            if 'SOC' in upper or 'SPIN ORBIT CORRECTED' in upper:
                i+=1
                continue
            last = None
            rows, j = _table_rows(lines, i)
            for row in rows:
                target = find_target(row, i+1)
                if target is None:
                    continue
                values = row['values']
                if row['forbidden']:
                    if table == 'electric':
                        target.oscillator_strength = target.oscillator_strength_length = 0.
                    elif table == 'velocity':
                        target.oscillator_strength_velocity = 0.
                    continue
                if table == 'electric' and len(values) >= 5:
                    target.oscillator_strength = target.oscillator_strength_length = values[0]
                    target.dipole_strength_au2 = values[1]
                    target.electric_dipole_au = np.asarray(values[2:5])
                elif table == 'velocity' and len(values) >= 5:
                    target.oscillator_strength_velocity = values[0]
                    target.velocity_dipole_au = np.asarray(values[2:5])
                elif table == 'magnetic' and len(values) >= 4 and target.magnetic_dipole_au is None:
                    target.magnetic_dipole_au = np.asarray(values[1:4])
            i = max(i+1, j)
            continue
        i += 1
    return dipoles, spectra
