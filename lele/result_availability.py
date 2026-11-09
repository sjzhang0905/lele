"""Independent geometry, energy and curve availability for loaded documents."""
from math import isfinite


def finite(value):
    return value is not None and isfinite(value)


def has_calculation_data(results):
    return bool(results is not None and (results.orbitals or
        (results.program == 'VASP' and results.steps) or
        (results.program == 'CP2K' and results.jobs) or
        any(finite(s.energy_ev) for s in results.steps) or
        any(finite(j.energy_ev) or j.frequency_count for j in results.jobs)))


def has_curve_data(document):
    if document is None:return False
    if any(finite(f.energy_ev) for f in document.frames):return True
    results=document.calculation_results
    if results is None or results.program!='xTB':
        if any(finite(f.info.get('cartesian_'+key+'_ev_ang')) for f in document.frames for key in ('max_force','rms_force')):return True
    if results is None:return False
    if any(finite(s.energy_ev) for s in results.steps):return True
    return results.program!='xTB' and any(finite(pair[0]) for s in results.steps for pair in s.convergence.values())


def results_text(document):
    from ase.units import Hartree
    from .energy_units import program_energy_unit
    lines=[f'File: {document.path.name}',f'Reader: {document.format_name}',
           ('Structure: not present for the selected energy record.' if document.frames else
            'Structure: not present in this file.')]
    results=document.calculation_results
    if results is not None:
        count=sum(finite(s.energy_ev) for s in results.steps)
        lines.append(f'Energy records: {count}')
        for job in results.jobs:
            lines.extend(['',f'Job {job.index+1}'+(' · '+job.method if job.method else '')])
            if finite(job.energy_ev):
                if program_energy_unit(results.program) == 'eV':
                    lines.append(f'{"E0 (σ→0)" if results.program=="VASP" else "Total energy"}: {job.energy_ev:.9f} eV')
                else:
                    lines.append(f'Total energy: {job.energy_ev/Hartree:.12f} Eh')
                    lines.append(f'              {job.energy_ev*23.0605478306:.8f} kcal/mol')
            lines.append('Run status: '+job.termination)
            if results.program == 'CP2K':
                if job.charge is not None:lines.append(f'Charge: {job.charge}')
                if job.multiplicity is not None:lines.append(f'Multiplicity: {job.multiplicity}')
                if job.route:lines.append('Run / input: '+job.route)
        if results.program == 'VASP' and not count:
            lines.append('E0 (σ→0): not printed in the available ionic records.')
        for row in getattr(results, 'frequency_records', []):
            prefix=(f'q {row["q_index"]} {row["qpoint"]} · ' if 'qpoint' in row else '')
            lines.append(prefix+f'Mode {row["number"]}: {row["frequency_cm1"]:.6f} cm⁻¹'+
                         (' · imaginary' if row['frequency_cm1'] < 0 else ''))
        for stage in results.stages:lines.append(stage.name+': '+stage.status)
        if results.orbitals:lines.append(f'Orbital / gap results: {len(results.orbitals)}')
    if document.electronic_spectra:
        lines.append(f'Electronic spectra: {len(document.electronic_spectra)} · printed transitions: '+
                     str(sum(len(s.transitions) for s in document.electronic_spectra)))
    if document.note:lines+=['',document.note]
    if document.nmr_results:
        lines.append(f'NMR: {len(document.nmr_results)} dataset(s) · Analysis → NMR spectrum / shielding table')
        lines.extend(f'  {r.program}: {r.label} · {len(r.nuclei)} printed nuclei' for r in document.nmr_results)
    return '\n'.join(lines)
