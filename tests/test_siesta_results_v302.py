"""SIESTA move provenance, including extra unevaluated coordinate blocks."""
from pathlib import Path

import numpy as np
import pytest

from lele.formats import load_document
from lele.siesta_results import read_siesta_records
from lele.result_availability import has_curve_data, results_text


def coordinates(x, final=False):
    return (f'outcoor: {"Final (unrelaxed) a" if final else "A"}tomic coordinates (fractional):\n'
            f'{x} .25 .3 1 1 H\n\n')


def cell(a=4):
    return f'outcell: Unit cell vectors (Ang):\n{a} 0 0\n0 5 0\n0 0 6\n'


def fire_output():
    return ('Executable : siesta\nWelcome to SIESTA\nNumberOfAtoms 1\n'
            'siesta: Atomic coordinates (Bohr) and species\nsiesta: 0 1 2 1 1\n\n'
            'Begin FIRE opt. move = 0\n' + coordinates(.1) + cell(4) +
            'siesta: Etot = -9.0\nscf: 1 -1000 -1001 0.0\n'
            'SCF cycle converged after 12 iterations\nsiesta: E_KS(eV) = -10.1\n'
            'Begin FIRE opt. move = 1\n' + coordinates(.2) + cell(8) +
            'SCF cycle converged after 9 iterations\nsiesta: E_KS(eV) = -10.2\n' +
            coordinates(.21, final=True) + 'siesta: Etot = -10.200001\n'
            'siesta: Final energy (eV):\nsiesta: Total = -10.200001\n'
            'siesta: FreeEng = -10.21\nJob completed\n')


def test_fire_moves_pair_only_evaluated_geometries_and_use_their_own_cell(tmp_path):
    path = tmp_path/'fire.out'
    path.write_text(fire_output())
    frames, note, results = read_siesta_records(path)
    assert [f.energy_ev for f in frames] == [None, -10.1, -10.2, None]
    assert [s.frame_index for s in results.steps] == [1, 2]
    assert [s.cycle for s in results.steps] == [0, 1]
    assert [s.energy_ev for s in results.steps] == [-10.1, -10.2]
    assert [s.geometry.energy_ev for s in results.steps] == [-10.1, -10.2]
    np.testing.assert_allclose(frames[1].positions, [[.4, 1.25, 1.8]])
    np.testing.assert_allclose(frames[2].positions, [[1.6, 1.25, 1.8]])
    assert results.steps[-1].info['free_energy_ev'] == -10.21
    assert results.jobs[0].energy_ev == -10.200001
    assert results.jobs[0].termination == 'Normal termination'
    assert not any(s.converged for s in results.steps)
    assert results.stages[0].status == 'Not confirmed'
    assert 'unrelaxed' in note and 'last calculated' in note
    assert frames[-1].info['structure_label'] == 'Final unrelaxed coordinates'


def test_document_exposes_energy_curve_and_roundtrips_results(tmp_path):
    from lele.project_file import save_project, load_project
    path = tmp_path/'fire.out'; path.write_text(fire_output())
    document = load_document(path)
    assert has_curve_data(document)
    assert document.calculation_results.program == 'SIESTA'
    assert 'Total energy: -10.200001000 eV' in results_text(document)
    archive = tmp_path/'fire.lele'
    from lele.render_options import RenderOptions
    save_project(archive, {'documents': [{'document': document, 'options':RenderOptions()}]})
    restored = load_project(archive)['documents'][0]['document']
    assert [s.frame_index for s in restored.calculation_results.steps] == [1, 2]
    assert restored.calculation_results.steps[0].info['scf_cycles'] == 12
    assert restored.frames[-1].energy_ev is None


def test_final_total_single_point_and_energy_only_documents(tmp_path):
    for geometry in (True, False):
        path = tmp_path/f'single_{geometry}.out'
        path.write_text('Welcome to SIESTA\n' +
                        (cell()+coordinates(.2) if geometry else '') +
                        'siesta: Final energy (eV):\nsiesta: Total = -12.25\n')
        document = load_document(path)
        assert len(document.frames) == int(geometry)
        assert has_curve_data(document)
        assert document.calculation_results.steps[0].energy_ev == -12.25


def test_missing_move_geometry_preserves_energy_without_borrowing_structure(tmp_path):
    path = tmp_path/'partial.out'
    path.write_text('Welcome to SIESTA\nNumberOfAtoms 2\nBegin FIRE opt. move = 0\n' +
                    coordinates(.1) + cell() + 'siesta: E_KS(eV) = -20.0\n')
    document = load_document(path)
    assert document.frames == []
    step = document.calculation_results.steps[0]
    assert step.energy_ev == -20 and step.frame_index is None and step.geometry is None


def test_restart_and_concatenated_jobs_remain_distinct(tmp_path):
    path = tmp_path/'restart.out'
    one = 'Executable : siesta\nSiesta Version: 5.4\nWelcome to SIESTA\n'
    one += 'Begin FIRE opt. move = 0\n'+coordinates(.2)+cell()+'siesta: E_KS(eV) = -10\n'
    one += 'Begin FIRE opt. move = 0\n'+coordinates(.3)+cell()+'siesta: E_KS(eV) = -11\n'
    path.write_text(one+one)
    frames, _, results = read_siesta_records(path)
    assert len(frames) == len(results.steps) == 4
    assert [s.job_index for s in results.steps] == [0, 0, 1, 1]
    assert len(results.jobs) == 2 and len(results.stages) == 4


def test_max_frames_still_enforced(tmp_path):
    path = tmp_path/'fire.out'; path.write_text(fire_output())
    with pytest.raises(ValueError, match='frame limit'):
        read_siesta_records(path, 2)


@pytest.mark.parametrize('message,confirmed', [('FIRE optimization converged', True),
    ('FIRE optimization not converged', False), ('SCF cycle converged after 7 iterations', False)])
def test_geometry_convergence_requires_an_affirmative_ionic_message(tmp_path,message,confirmed):
    path=tmp_path/'status.out'
    path.write_text('Welcome to SIESTA\nBegin FIRE opt. move = 0\n'+coordinates(.2)+cell()+
                    'siesta: E_KS(eV) = -1\n'+message+'\nJob completed\n')
    frames,_,results=read_siesta_records(path)
    assert results.steps[0].converged is confirmed
    assert bool(frames[0].info.get('optimization_converged')) is confirmed
