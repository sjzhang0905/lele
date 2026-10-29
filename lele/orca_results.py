"""Printed ORCA 4/5/6 geometry, job metadata and molecular orbital tables."""
import re
import numpy as np
from ase.data import chemical_symbols
from ase.units import Bohr, Hartree
from .core import Frame
from .calculation_results import (CalculationJob, CalculationResults, CalculationStep, Orbital, OrbitalSet,
                                  CalculationStage, HessianEvent, NUMBER)
from .gaussian_vibrations import _number
from .output_text import read_output_lines

JOB = re.compile(r'^\s*(?:\*+\s*)?(?:JOB NUMBER\s*[:=]?\s*\d+|COMPOUND JOB\s+\d+)\b', re.I)
COORDINATES = re.compile(r'CARTESIAN COORDINATES\s*\((ANGSTROEM|ANGSTROM|A\.U\.|BOHR)\)', re.I)
FREQUENCY = re.compile(rf'^\s*(\d+)\s*:\s*({NUMBER})\s+cm(?:\*\*|\^)?-1', re.I)
BASIS = re.compile(r'^(?:ma-def2-|def2-|(?:d-)?aug-|cc-p|[3-6]-\d|sto-|pc(?:seg)?-|sarc|x2c|ano|dhf|lanl|[dtq]zp)', re.I)


def job_ranges(lines):
    """Ignore echoed input; compound-job wrappers contain no calculation."""
    starts = [0]
    terminated = False
    content = False
    for i, line in enumerate(lines):
        if re.match(r'^\s*\|\s*\d+>', line):
            continue
        if JOB.match(line):
            if content:
                starts.append(i)
            else:
                starts[-1] = i
            content = terminated = False
            continue
        if terminated and (re.search(r'O\s+R\s+C\s+A', line) or 'INPUT FILE' == line.strip()):
            starts.append(i)
            content = terminated = False
        if COORDINATES.search(line) or 'FINAL SINGLE POINT ENERGY' in line:
            content = True
        if 'ORCA TERMINATED NORMALLY' in line.upper() or 'ORCA finished by error termination' in line:
            terminated = True
    return [(start, starts[i+1] if i+1 < len(starts) else len(lines)) for i, start in enumerate(starts)]


def reference_at(results, line):
    """No geometry or property can leak from an earlier calculation job."""
    job = next((j for j in reversed(results.jobs) if j.start_line <= line), None)
    if job is None:
        return None
    step = next((s for s in reversed(results.steps)
                 if s.job_index == job.index and s.source_line <= line and s.geometry is not None), None)
    if step is None:
        return None
    frame = step.geometry.clone()
    frame.energy_ev = step.energy_ev
    return frame


def _coordinates(lines, start):
    heading = COORDINATES.search(lines[start])
    au = heading[1].upper() in ('A.U.', 'BOHR')
    symbols, positions = [], []
    j = start + 1
    for j in range(start+1, len(lines)):
        fields = lines[j].split()
        if not fields or set(lines[j].strip()) == {'-'}:
            if symbols:
                break
            continue
        if au and fields[0].upper() in ('NO', 'NR'):
            continue
        try:
            if au:
                symbol, xyz = fields[1], fields[-3:]
                if not fields[0].isdigit() or len(fields) < 5:
                    break
            else:
                if len(fields) != 4:
                    break
                symbol, xyz = fields[0], fields[1:]
            symbol = symbol.title()
            if symbol not in chemical_symbols:
                break
            values = [_number(v) for v in xyz]
        except (ValueError, IndexError):
            break
        symbols.append(symbol)
        positions.append(values)
    if not symbols:
        return None, j
    return Frame(symbols, np.asarray(positions) * (Bohr if au else 1.)), j


def _route(job, parts):
    job.route = ' '.join(parts)
    tokens = job.route.split()
    controls = {'uks','rks','uhf','rhf','rohf','roks','opt','optts','copt','freq','anfreq','numfreq',
                'sp','engrad','tightscf','verytightscf','slowconv','rijcosx','ri','d3','d3bj','d4',
                'tightopt','verytightopt','normalopt','looseopt','usesym','nosym','smallprint','miniprint',
                'largeprint','noprintmos','noautostart','autostart','moread','nocosx','defgrid1','defgrid2','defgrid3'}
    for token in tokens:
        lower = token.lower()
        if lower in {'rks','uks','rhf','uhf','rohf','roks'}:
            job.wavefunction = token.upper()
        if re.match(r'^(?:tight|verytight|loose|normal)?(?:opt|optts|copt)$', lower):
            job.tasks.add('Optimization')
        if lower in ('freq','numfreq','anfreq'):
            job.tasks.add('Frequency')
        if lower in ('td','tddft','cis','tda','std-dft','stda'):
            job.tasks.add('Excited states')
        if lower == 'irc':
            job.tasks.add('IRC')
        solvent = re.match(r'(?:cpcm|cosmo|smd)\(([^)]+)\)', token, re.I)
        if solvent:
            job.solvent = solvent[1]
        if BASIS.match(token):
            if not job.basis and not re.search(r'/(?:c|j|jk|cabs)$', token, re.I):
                job.basis = token
        elif (not job.method and lower not in controls and not solvent
              and not re.match(r'^(?:pal\d+|%|print|no|grid|finalgrid|normal|tight|verytight|loose)', lower)):
            job.method = token


def _orbitals(lines, start, job, step_index):
    snapshot = OrbitalSet(job.index, start+1, step_index=step_index,
                          numbering='0-based ORCA orbital numbers, as printed')
    channel = 'Restricted'
    row = re.compile(rf'^\s*(\d+)\s+({NUMBER})\s+({NUMBER})\s+({NUMBER})(?:\s+\S+)?\s*$')
    seen, j = False, start+1
    while j < len(lines):
        text = lines[j].strip()
        upper = text.upper()
        if 'SPIN UP' in upper or 'SPIN ALPHA' in upper:
            channel = 'Alpha'
        elif 'SPIN DOWN' in upper or 'SPIN BETA' in upper:
            channel = 'Beta'
        else:
            match = row.match(text)
            if match:
                snapshot.channels.setdefault(channel, []).append(
                    Orbital(int(match[1]), _number(match[2]), _number(match[4])))
                seen = True
            elif text and set(text) != {'-'} and not ('NO' in upper and 'OCC' in upper):
                if seen or j-start > 10:
                    break
        j += 1
    return snapshot if seen else None, j


def read_orca_results(path):
    lines = read_output_lines(path)
    result = CalculationResults('ORCA', force_unit='Hartree/Bohr', displacement_unit='Bohr')
    for start, end in job_ranges(lines):
        job = CalculationJob(len(result.jobs), start+1)
        result.jobs.append(job)
        step = None
        stage = None
        cycle = None
        saddle = previous_geometry = None
        hessian_active = False
        hessian = None
        initial_hessian_file=''

        def start_stage(name, kind, line):
            nonlocal stage, step, cycle, previous_geometry, hessian_active, hessian
            if stage is not None:
                stage.end_line = line
            if hessian_active and hessian is not None:hessian.end_line=line
            stage = CalculationStage(len(result.stages), job.index, name, kind, line+1)
            result.stages.append(stage)
            step = None
            cycle = None
            previous_geometry = None
            hessian_active = False
            hessian = None
            return stage
        route_parts = []
        i = start
        while i < end:
            line = lines[i]
            lower = line.lower()
            route = re.match(r'^\s*(?:\|\s*\d+>\s*)?!\s*([^!].*)$', line)
            if route and not (route[1].rstrip().endswith('!') or (not re.match(r'^\s*\|',line) and stage is not None)):
                route_parts.append(route[1].split('#', 1)[0].strip())
                _route(job, route_parts)
            if re.search(r'\b(?:FAST-|LOOSE-)?NEB(?:-TS)?\b', job.route, re.I):
                job.tasks.add('NEB-TS' if 'NEB-TS' in job.route.upper() else 'NEB')
            heading_text = line.strip().strip('*').strip()
            named = {'REACTANT OPTIMIZATION':('Reactant preoptimization','reactant'),
                     'PRODUCT OPTIMIZATION':('Product preoptimization','product'),
                     'NEB OPTIMIZATION':('NEB path optimization','neb'),
                     'TS OPTIMIZATION':('Transition-state optimization','ts')}
            if heading_text in named:
                start_stage(*named[heading_text], i)
            if heading_text == 'SADDLE POINT (ANGSTROEM)':
                fake = list(lines[i:])
                fake[0] = 'CARTESIAN COORDINATES (ANGSTROEM)'
                saddle, _ = _coordinates(fake, 0)
            iteration = re.search(r'GEOMETRY OPTIMIZATION CYCLE\s+(\d+)', line)
            if iteration:
                if stage is None:
                    is_ts = bool(re.search(r'\bOptTS\b', job.route, re.I))
                    start_stage('Transition-state optimization' if is_ts else 'Geometry optimization', 'ts' if is_ts else 'optimization', i)
                cycle = int(iteration[1])
                if hessian is not None and hessian.kind.startswith('Initial:') and hessian.cycle is None:hessian.cycle=cycle
                previous_geometry = step.geometry.clone() if step is not None else (saddle.clone() if stage.kind=='ts' and saddle is not None else previous_geometry)
                step = None
                if previous_geometry is not None:
                    step = CalculationStep(job.index, i+1, previous_geometry.clone(), stage_index=stage.index, cycle=cycle)
                    result.steps.append(step)
            if heading_text in ('SCF HESSIAN','NUMERICAL HESSIAN','NUMERICAL FREQUENCIES'):
                if stage is None and 'Frequency' in job.tasks:start_stage('Frequency analysis','frequency',i)
                if stage is not None and stage.status=='Converged' and re.search(r'\b(?:freq|numfreq)\b', job.route, re.I):
                    start_stage('Final frequency verification','frequency',i)
                hessian_active = True
                reference = step.geometry.clone() if step is not None else reference_at(result,i+1)
                hessian = HessianEvent(i+1, None if stage is None else stage.index, cycle,
                    'Numerical exact' if 'NUMERICAL' in heading_text else 'Analytical exact', reference)
                result.hessians.append(hessian)
            stored_initial=re.search(r'Initial Hessian will be stored in\s*\.+\s*(\S+)',line)
            if stored_initial:initial_hessian_file=stored_initial[1]
            if 'Initial Hessian' in line and 'InHess' in line:
                if stage is None:
                    is_ts = bool(re.search(r'\bOptTS\b',job.route,re.I))
                    start_stage('Transition-state optimization' if is_ts else 'Geometry optimization','ts' if is_ts else 'optimization',i)
                kind='Initial: '+line.split('....')[-1].strip()
                if initial_hessian_file.endswith('.appr.hess'):kind+=' (approximate model)'
                hessian=HessianEvent(i+1,stage.index,cycle,kind,filename=initial_hessian_file)
                result.hessians.append(hessian)
            update = re.search(r'Updating the Hessian\s*\(([^)]+)\)',line)
            if update:
                hessian = HessianEvent(i+1,None if stage is None else stage.index,cycle,'Update '+update[1],
                                      None if step is None else step.geometry.clone())
                result.hessians.append(hessian)
            negative = re.search(r'Hessian has\s+(\d+)\s+negative eigenvalues',line)
            if negative and hessian is not None:
                hessian.negative_eigenvalues = int(negative[1])
            stored = re.search(r'Actual Hessian File stored as\s+(\S+)',line)
            if stored:
                if hessian is not None:
                    hessian.filename=stored[1]
                    hessian.end_line=i+1
                hessian_active=False
            xyz = re.search(r'\*\s*xyz(?:file)?\s+([-+]?\d+)\s+(\d+)', line, re.I)
            if xyz:
                job.charge, job.multiplicity = int(xyz[1]), int(xyz[2])
            charge = re.search(r'Total Charge\s+(?:Charge\s+)?[.:=]+\s*([-+]?\d+)\s*$', line, re.I)
            mult = re.search(r'^\s*Multiplicity\s+(?:Mult\s+)?[.:=]+\s*(\d+)\s*$', line, re.I)
            if charge:
                job.charge = int(charge[1])
            if mult:
                job.multiplicity = int(mult[1])
            basis = re.search(r'Your calculation utilizes the basis:\s*(.+)', line, re.I)
            if basis and (not job.basis or step is None):
                job.basis = basis[1].strip()
            solvent = re.search(r'(?:SMDsolvent\s+|Solvent\s*(?:[.:=]+)\s*)["\']?([\w-]+)', line, re.I)
            if solvent and solvent[1].lower() not in ('true','false','name','model'):
                job.solvent = solvent[1]
            if re.search(r'%tddft\b|TD-?DFT.*EXCITED STATES|CIS.*EXCITED STATES|SF-TDA', line, re.I):
                job.tasks.add('Excited states')
            if re.search(r'\bscan\b', line, re.I) and ('%' in line or '>' in line or 'surface' in lower):
                job.tasks.add('Scan')
            if 'trajectory step' in lower:
                job.tasks.add('Scan')
            heading = COORDINATES.search(line)
            if heading:
                geometry, j = _coordinates(lines, i)
                if hessian_active:
                    i=max(i+1,j)
                    continue
                # ORCA prints the same geometry again in Bohr immediately after Angstrom.
                if geometry is not None and not (heading[1].upper() in ('A.U.','BOHR') and step is not None
                    and step.geometry.symbols == geometry.symbols
                    and np.allclose(step.geometry.positions, geometry.positions, atol=2.e-5, rtol=0)):
                    if step is not None and step.energy_ev is None and not step.convergence:
                        step.geometry, step.source_line = geometry, i+1
                    else:
                        step = CalculationStep(job.index, i+1, geometry,
                            stage_index=None if stage is None else stage.index, cycle=cycle)
                        result.steps.append(step)
                    if hessian is not None and hessian.kind.startswith('Initial:') and hessian.reference is None:hessian.reference=geometry.clone()
                i = max(i+1, j)
                continue
            energy = re.search(rf'FINAL SINGLE POINT ENERGY\s+({NUMBER})', line)
            if energy and not hessian_active:
                job.energy_ev = _number(energy[1]) * Hartree
                if step is not None:
                    step.energy_ev = job.energy_ev
            cycles = re.search(r'SCF CONVERGED AFTER\s+(\d+)\s+CYCLES', line, re.I)
            if cycles:
                job.scf_cycles = int(cycles[1])
            spin = re.search(rf'Expectation value of <S\*\*2>\s*:\s*({NUMBER})', line)
            if spin:
                job.spin_squared = _number(spin[1])
            for label, key in [('MAX gradient','max_force'),('RMS gradient','rms_force'),
                               ('MAX step','max_displacement'),('RMS step','rms_displacement'),
                               ('MAX displacement','max_displacement'),('RMS displacement','rms_displacement')]:
                match = re.match(rf'\s*{label}\s+({NUMBER})\s+({NUMBER})', line, re.I)
                if match and step is not None:
                    step.convergence[key] = (_number(match[1]), _number(match[2]))
            if 'optimization cycle' in lower or 'geometry optimization' in lower:
                job.tasks.add('Optimization')
            if heading_text in ('THE OPTIMIZATION HAS CONVERGED','THE TS OPTIMIZATION HAS CONVERGED'):
                if stage is not None and stage.kind!='neb':
                    stage.status='Converged'
                    if step is not None:step.converged=True
            if 'THE NEB OPTIMIZATION HAS CONVERGED' in line and stage is not None and stage.kind=='neb':
                stage.status='Converged'
            if 'optimization did not converge' in lower and stage is not None:
                stage.status='Not converged (cycle limit)' if 'maximum' in lower else 'Not converged'
            if 'vibrational frequencies' == line.strip().lower():
                job.tasks.add('Frequency')
                j = i+1
                seen_frequency = False
                while j < end:
                    match = FREQUENCY.match(lines[j])
                    if match:
                        seen_frequency = True
                        value = _number(match[2])
                        if not hessian_active or (stage is not None and stage.kind=='frequency'):
                            job.frequency_count += 1
                            job.imaginary_modes += value < 0
                    elif seen_frequency and lines[j].strip() and set(lines[j].strip()) != {'-'}:
                        break
                    elif not seen_frequency and j-i > 12:
                        break
                    j += 1
            if 'orca terminated normally' in lower:
                job.termination = 'Normal termination'
                if stage is not None and stage.kind=='frequency':stage.status='Completed (printed frequencies)'
            if 'error termination' in lower or 'aborting the run' in lower:
                job.termination = 'Error termination'
            if line.strip() == 'ORBITAL ENERGIES':
                snapshot, j = _orbitals(lines, i, job, len(result.steps)-1 if step is not None else None)
                if snapshot is not None and not hessian_active:
                    result.orbitals.append(snapshot)
                i = max(i+1, j)
                continue
            i += 1
        if not job.tasks:
            job.tasks.add('Single point / properties')
        if JOB.match(lines[start]) and job.termination.startswith('Incomplete') and len(result.steps):
            job.termination = 'Compound segment; termination not printed'
        for record in (s for s in result.steps if s.job_index == job.index):
            if job.charge is not None:
                record.geometry.info['converter_charge'] = job.charge
            if job.multiplicity is not None:
                record.geometry.info['converter_mult'] = job.multiplicity
        for event in result.hessians:
            if event.reference is not None and event.stage_index is not None and result.stages[event.stage_index].job_index==job.index:
                if job.charge is not None:event.reference.info['converter_charge']=job.charge
                if job.multiplicity is not None:event.reference.info['converter_mult']=job.multiplicity
        if stage is not None:stage.end_line=end
    return result
