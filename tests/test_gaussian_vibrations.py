"""Gaussian Opt+Freq, job/orientation association and reversible animation."""
from pathlib import Path
from math import pi

import numpy as np
import pytest

from lele.core import Frame, NormalMode
from lele.formats import load_document
from lele.gaussian_vibrations import read_gaussian_vibrations

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'synthetic_opt_freq.log'


def read_text(tmp_path, text):
    path = tmp_path / 'example.log'
    path.write_text(text)
    return read_gaussian_vibrations(path)


def test_combined_optimization_and_frequency_preserve_both_results():
    doc = load_document(EXAMPLE)
    assert len(doc.frames) == 2
    assert len(doc.vibrations) == 1
    analysis = doc.vibrations[0]
    assert analysis.reference is not doc.frames[-1]
    np.testing.assert_allclose(analysis.reference.positions, doc.frames[-1].positions)
    assert len(analysis.modes) == 3
    first, second, last = analysis.modes
    assert [m.number for m in analysis.modes] == [1, 2, 3]
    assert [m.frequency_cm1 for m in analysis.modes] == [-250., 1500., 3600.]
    assert first.imaginary and not second.imaginary
    assert first.ir_intensity == 12.
    assert first.reduced_mass == 1.1
    assert first.force_constant == .4
    assert first.symmetry == 'A1'
    assert all(m.can_animate for m in analysis.modes)
    np.testing.assert_array_equal(first.displacements[1], [.15, .4, 0.])
    np.testing.assert_array_equal(second.displacements[1], [.8, .1, 0.])
    np.testing.assert_array_equal(last.displacements[1], [0., 0., .5])


def test_modes_use_standard_orientation_of_the_frequency_job(tmp_path):
    text = EXAMPLE.read_text()
    last = text.rfind('                         Standard orientation:')
    end = text.find(' SCF Done:', last)
    input_orientation = text[last:end].replace('Standard orientation:', 'Input orientation:')
    input_orientation = input_orientation.replace('0.960000', '4.960000')
    analyses, note = read_text(tmp_path, text[:last] + input_orientation + text[last:])
    assert not note
    assert analyses[0].reference.positions[1, 0] == .96


def test_input_orientation_is_supported_when_no_standard_orientation(tmp_path):
    analyses, _ = read_text(tmp_path, EXAMPLE.read_text().replace('Standard orientation:', 'Input orientation:'))
    assert len(analyses) == 1
    assert analyses[0].modes[0].can_animate
    assert analyses[0].reference.positions[2, 1] == .92


def test_distinct_frequency_jobs_keep_separate_geometries_and_mode_numbers(tmp_path):
    text = EXAMPLE.read_text()
    second = text[text.index(' --Link1--'):].replace('0.960000', '1.230000')
    second = second.replace('-250.0000', '-450.0000')
    analyses, _ = read_text(tmp_path, text + second)
    assert len(analyses) == 2
    assert [a.modes[0].number for a in analyses] == [1, 1]
    assert analyses[0].reference.positions[1, 0] == .96
    assert analyses[1].reference.positions[1, 0] == 1.23
    assert analyses[1].modes[0].frequency_cm1 == -450.


def test_frequency_only_and_single_mode_block_with_fortran_numbers(tmp_path):
    text = EXAMPLE.read_text()
    job = text[text.index(' --Link1--'):]
    job = job[:job.index(' Harmonic frequencies')]
    job += (' Harmonic frequencies (cm**-1)\n'
            ' 7\n A\n Frequencies -- -1.234567D+02\n'
            ' IR Inten -- 1.234D+01\n Atom AN X Y Z\n'
            ' 1 8 0.0D+00 1.0D-01 0.0D+00\n'
            ' 2 1 1.0D-01 0.0D+00 0.0D+00\n'
            ' 3 1 0.0D+00 0.0D+00 1.0D-01\n')
    analyses, note = read_text(tmp_path, job)
    assert not note
    assert len(analyses[0].modes) == 1
    mode = analyses[0].modes[0]
    assert mode.number == 7
    assert mode.frequency_cm1 == -123.4567
    assert mode.ir_intensity == 12.34
    assert mode.can_animate


@pytest.mark.parametrize('change', ['truncated', 'wrong_element', 'missing_row', 'nan'])
def test_incomplete_or_inconsistent_displacements_are_not_animated(tmp_path, change):
    text = EXAMPLE.read_text()
    if change == 'truncated':
        text = text[:text.index('     3   1    -0.35')]
    elif change == 'wrong_element':
        text = text.replace('     2   1     0.15', '     2   6     0.15')
    elif change == 'missing_row':
        text = '\n'.join(line for line in text.splitlines() if not line.startswith('     2   1     0.15'))
    else:
        text = text.replace('     0.15   0.40', '      nan   0.40')
    analyses, _ = read_text(tmp_path, text)
    assert len(analyses[0].modes) == 3
    assert all(m.displacements is None and not m.can_animate for m in analyses[0].modes)
    assert 'incomplete Cartesian displacements' in analyses[0].note


def test_earlier_complete_modes_survive_a_later_truncated_block(tmp_path):
    text = EXAMPLE.read_text().replace(' Normal termination of Gaussian 16\n', '')
    text += ' 4\n A\n Frequencies -- 4000.00\n Atom AN X Y Z\n 1 8 0.1 0.2 0.3\n'
    analyses, _ = read_text(tmp_path, text)
    assert len(analyses[0].modes) == 4
    assert all(m.can_animate for m in analyses[0].modes[:3])
    assert not analyses[0].modes[-1].can_animate


def test_supplementary_high_precision_and_low_frequency_summary_are_not_duplicates(tmp_path):
    text = EXAMPLE.read_text().replace(' Frequencies --   -250.0000',
              ' Frequencies --- -250.0000 1500.0000 3600.0000\n Frequencies --   -250.0000')
    analyses, _ = read_text(tmp_path, text)
    assert len(analyses[0].modes) == 3


def test_later_job_without_orientation_does_not_reuse_earlier_geometry(tmp_path):
    text = EXAMPLE.read_text() + '\n --Link1--\n Harmonic frequencies (cm**-1)\n Frequencies -- 25.00\n'
    analyses, note = read_text(tmp_path, text)
    assert len(analyses) == 1
    assert 'without a reference orientation' in note


def test_missing_displacement_table_does_not_skip_a_job_boundary(tmp_path):
    text = EXAMPLE.read_text()
    text = text[:text.index('  Atom  AN')]
    text += (' Normal termination of Gaussian 16\n Link1: Proceeding to internal job step number 3\n'
             ' Harmonic frequencies (cm**-1)\n 1\n A\n Frequencies -- 150.0\n')
    analyses, note = read_text(tmp_path, text)
    assert len(analyses) == 1
    assert len(analyses[0].modes) == 3
    assert not analyses[0].modes[0].can_animate
    assert 'without a reference orientation' in note


def test_missing_optional_intensity_does_not_prevent_animation(tmp_path):
    text = '\n'.join(line for line in EXAMPLE.read_text().splitlines() if 'IR Inten    --' not in line)
    analyses, _ = read_text(tmp_path, text)
    assert analyses[0].modes[0].ir_intensity is None
    assert analyses[0].modes[0].can_animate


def test_visual_oscillation_is_normalized_symmetric_and_does_not_mutate_source():
    analysis = read_gaussian_vibrations(EXAMPLE)[0][0]
    mode, reference = analysis.modes[0], analysis.reference
    original, vectors = reference.positions.copy(), mode.displacements.copy()
    positive = mode.positions_at(reference, pi / 2, .6)
    negative = mode.positions_at(reference, 3 * pi / 2, .6)
    assert np.linalg.norm(positive - original, axis=1).max() == pytest.approx(.6)
    np.testing.assert_allclose(positive - original, original - negative)
    np.testing.assert_allclose(mode.positions_at(reference, 2 * pi, .6), original, atol=1e-15)
    np.testing.assert_array_equal(reference.positions, original)
    np.testing.assert_array_equal(mode.displacements, vectors)


def test_zero_vector_and_mismatched_geometry_cannot_produce_false_motion():
    reference = Frame(['H'], [[0, 0, 0]])
    zero = NormalMode(1, 100., [[0, 0, 0]])
    assert not zero.can_animate
    np.testing.assert_array_equal(zero.positions_at(reference, pi / 2, 1.), reference.positions)
    with pytest.raises(ValueError, match='atom count'):
        NormalMode(1, 100., [[1, 0, 0], [0, 1, 0]]).positions_at(reference, 0., .3)


def test_non_gaussian_files_do_not_gain_frequency_results():
    assert load_document(EXAMPLE.parent / 'water_trajectory.xyz').vibrations == []
