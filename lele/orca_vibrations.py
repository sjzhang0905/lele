"""ORCA harmonic frequencies, printed Cartesian modes, IR and Raman tables."""
import re
import numpy as np
from .core import NormalMode, VibrationalAnalysis
from .gaussian_vibrations import _number
from .orca_results import COORDINATES, FREQUENCY, NUMBER, reference_at, ReferenceIndex
from .output_text import read_output_lines, check_load_cancelled, load_progress


def _normal_modes(lines, start, analysis):
    size = 3 * len(analysis.reference.symbols)
    by_number = {mode.number: mode for mode in analysis.modes}
    columns, rows = [], {}

    def commit():
        if len(rows) != size or set(rows) != set(range(size)):
            return
        matrix = np.asarray([rows[i] for i in range(size)])
        for column, number in enumerate(columns):
            if number in by_number:
                by_number[number].displacements = matrix[:, column].reshape(-1, 3).copy()

    j = start+1
    while j < len(lines):
        text = lines[j].strip()
        fields = text.split()
        if fields and all(s.isdigit() for s in fields):
            commit()
            columns, rows = [int(s) for s in fields], {}
        elif columns and fields and fields[0].isdigit():
            try:
                if len(fields) == len(columns)+1:
                    index = int(fields[0])
                    if index in rows:
                        break
                    rows[index] = [_number(v) for v in fields[1:]]
            except ValueError:
                pass
        elif rows and text and set(text) != {'-'}:
            break
        elif not columns and j-start > 16:
            break
        j += 1
    commit()
    return j


def _strengths(lines, start, analysis, kind):
    by_number = {mode.number: mode for mode in analysis.modes}
    header = ''
    seen = False
    j = start+1
    while j < len(lines):
        text = lines[j].strip()
        if re.search(r'\bMode\b', text, re.I):
            header = text
        match = re.match(r'^\s*(\d+):\s*(.*)', lines[j])
        if match:
            try:
                values = [_number(v) for v in re.findall(NUMBER, match[2])]
                mode = by_number.get(int(match[1]))
                if mode is not None and len(values) >= 2:
                    if kind == 'Raman':
                        mode.raman_activity = values[1]
                    else:
                        integrated = re.search(r'\bInt(?:ensity)?\b', header, re.I)
                        value_column = 1 + bool(re.search(r'\beps\b', header, re.I)) if integrated else 1
                        if len(values) > value_column:
                            mode.ir_intensity = values[value_column]
                            mode.ir_intensity_unit = 'km/mol' if integrated else 'printed T²'
                seen = True
            except ValueError:
                pass
        elif seen and text and set(text) != {'-'}:
            break
        elif not seen and j-start > 10:
            break
        j += 1
    return j


def read_orca_vibrations(path, results):
    lines = read_output_lines(path)
    if not any('VIBRATIONAL FREQUENCIES' in line.upper() for line in lines):return [], ''
    index=ReferenceIndex(results)
    progress=load_progress('ORCA: vibrational frequencies',len(lines))
    analyses, notices = [], []
    analysis = None
    job_starts = {job.start_line-1 for job in results.jobs}
    i = 0
    while i < len(lines):
        check_load_cancelled()
        progress(i)
        line = lines[i]
        text = line.strip().upper()
        if i in job_starts or ('CARTESIAN COORDINATES' in text and COORDINATES.search(line)):
            analysis = None
        if text == 'VIBRATIONAL FREQUENCIES':
            reference = reference_at(results, i+1,index)
            modes = []
            j = i+1
            while j < len(lines):
                match = FREQUENCY.match(lines[j])
                if match:
                    modes.append(NormalMode(int(match[1]), _number(match[2])))
                elif modes and lines[j].strip() and set(lines[j].strip()) != {'-'}:
                    break
                elif not modes and j-i > 12:
                    break
                j += 1
            if reference is not None and modes:
                analysis = VibrationalAnalysis(reference, modes, i+1,
                    'ORCA mode numbers are retained as printed (starting at 0). '
                    'Printed Cartesian vectors are used directly and scaled only for animation.')
                analyses.append(analysis)
                stage=next((s for s in reversed(results.stages) if s.start_line<=i+1 and (s.end_line is None or i+1<=s.end_line)),None)
                if stage is not None:
                    analysis.stage_index=stage.index
                    analysis.purpose='Final frequency verification' if stage.kind=='frequency' else ''
                    event=next((e for e in reversed(results.hessians) if e.source_line<=i+1 and e.stage_index==stage.index and 'exact' in e.kind.lower()),None)
                    if event is not None and stage.kind!='frequency':
                        analysis.cycle=event.cycle
                        analysis.purpose=f'Optimization Hessian · {stage.name} · cycle {event.cycle}'
                    if analysis.purpose:analysis.note=analysis.purpose+'. '+analysis.note
            elif modes:
                notices.append(f'ORCA frequencies at line {i+1} have no reference geometry in their calculation segment.')
            i = max(i+1, j)
            continue
        if analysis is not None and text == 'NORMAL MODES':
            i = max(i+1, _normal_modes(lines, i, analysis))
            continue
        if analysis is not None and text in ('IR SPECTRUM', 'RAMAN SPECTRUM'):
            i = max(i+1, _strengths(lines, i, analysis, 'IR' if text == 'IR SPECTRUM' else 'Raman'))
            continue
        i += 1
    progress(len(lines))
    for analysis in analyses:
        analysis.modes = [mode for mode in analysis.modes if mode.frequency_cm1 != 0 or mode.can_animate]
        if any(mode.frequency_cm1 != 0 and mode.displacements is None for mode in analysis.modes):
            analysis.note += ' Missing/incomplete displacement columns are not animated.'
        if any(mode.ir_intensity is not None and mode.ir_intensity_unit != 'km/mol' for mode in analysis.modes):
            analysis.note += ' Legacy IR T² values are retained in printed units for relative spectra.'
    return [analysis for analysis in analyses if analysis.modes], ' '.join(notices)
