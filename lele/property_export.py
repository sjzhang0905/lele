"""UTF-8 BOM CSVs of raw moments and transitions, preserving missing values."""
import csv
import json
from dataclasses import asdict
from pathlib import Path
import numpy as np
from ase.units import Hartree
from .gaussian_properties import AU_TO_DEBYE


def _moment(row,prefix,vector,unit):
    values=[None]*3 if vector is None else list(vector)
    for axis,value in zip('xyz',values):row[f'{prefix}_{axis}_{unit}']=value
    row[f'{prefix}_norm_{unit}']=None if vector is None else float(np.linalg.norm(vector))


def transition_rows(document,calculation=None):
    result=[]
    for i,spectrum in enumerate(document.electronic_spectra):
        if calculation is not None and i!=calculation:continue
        for t in spectrum.transitions:
            from .gaussian_properties import contribution_text
            row=dict(calculation=i+1,from_state=0,to_state=t.number,state_description=t.state,
                     calculation_label=spectrum.label,source_label=t.source_label,source_line=t.source_line,
                     major_transitions=contribution_text(t),contributions_json=json.dumps([asdict(c) for c in t.contributions]),
                     energy_eV=t.energy_ev,wavelength_nm=t.wavelength_nm,oscillator_strength=t.oscillator_strength,
                     dipole_strength_au2=t.dipole_strength_au2,
                     oscillator_strength_length=t.oscillator_strength_length,
                     oscillator_strength_velocity=t.oscillator_strength_velocity,
                     oscillator_strength_from_mu=None if t.electric_dipole_au is None else
                        float(2/3*t.energy_ev/Hartree*np.dot(t.electric_dipole_au,t.electric_dipole_au)))
            _moment(row,'electric',t.electric_dipole_au,'au')
            _moment(row,'electric',None if t.electric_dipole_au is None else t.electric_dipole_au*AU_TO_DEBYE,'D')
            _moment(row,'velocity',t.velocity_dipole_au,'au');_moment(row,'magnetic',t.magnetic_dipole_au,'au')
            result.append(row)
    return result


def write_rows(path,rows):
    if not rows:raise ValueError('No printed records to export')
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    return len(rows)


def export_transitions(path,document,calculation=None):
    return write_rows(path,transition_rows(document,calculation))


def export_dipoles(path,document):
    rows=[]
    for i,r in enumerate(document.dipoles,1):
        row=dict(kind=r.kind,record=i,calculation=None,from_state=None,to_state=r.state_number,
                 density=r.density,source_line=r.source_line,printed_norm_D=r.printed_total)
        _moment(row,'dipole',r.vector,'D');rows.append(row)
    for transition in transition_rows(document):
        row=dict(kind='electric transition',record=None,calculation=transition['calculation'],
                 from_state=0,to_state=transition['to_state'],density='',source_line=None,printed_norm_D=None)
        for axis in ['x','y','z','norm']:row['dipole_'+axis+'_D']=transition['electric_'+axis+'_D']
        rows.append(row)
    return write_rows(path,rows)
