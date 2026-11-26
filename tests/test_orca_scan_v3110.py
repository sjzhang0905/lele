"""ORCA scan-point boundaries, final single points, incomplete paths and navigation."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from ase.units import Hartree
from lele.orca_results import read_orca_results
from lele.core import Document


def geometry(x):
    return ('CARTESIAN COORDINATES (ANGSTROEM)\n----------------\n'
            f'C 0 0 0\nO {x} 0 0\nH {x} 1 0\nH {x} 1 1\n\n')


def sample_text(simultaneous=True):
    text = ('ORCA VERSION 6.1\n| 1> ! HF def2-SVP Opt\n| 2> %geom\n| 3> Scan\n'
            '| 4> B 0 1 = 1.5, 1.7, 3\n| 5> end\n')
    if simultaneous:text += '| 6> Simul_Scan true\n'
    text += '* xyz 0 1\n* Relaxed Surface Scan *\nBond (1,0): range= 1.5 .. 1.7 steps = 3\n'
    if simultaneous:text += 'Angle (0,1,2): range= 90 .. 110 steps = 3\n'
    text += 'There will be 3 constrained geometry optimizations.\n'
    for n, value in enumerate((1.5, 1.6, 1.7), 1):
        text += f'* RELAXED SURFACE SCAN STEP {n} *\n* Bond (1,0) : {value:.8f} *\n'
        if simultaneous:text += f'* Angle (0,1,2) : {80+10*n:.8f} *\n'
        text += 'Initial Hessian InHess .... Almloef\n'
        text += 'GEOMETRY OPTIMIZATION CYCLE 1\n'+geometry(value)+f'FINAL SINGLE POINT ENERGY {-10-n*.1:.9f}\n'
        text += 'RMS gradient 0.001 0.0001 NO\n'
        if n < 3:
            text += 'THE OPTIMIZATION HAS CONVERGED\n'
            # Post-convergence final SP, different energy: endpoint must use this record.
            text += geometry(value)+f'FINAL SINGLE POINT ENERGY {-10-n*.1-.001:.9f}\n'
        else:
            # Truncated next geometry must not steal the previous evaluated energy.
            text += 'GEOMETRY OPTIMIZATION CYCLE 2\n'+geometry(value+.01)
    return text


@pytest.fixture
def parsed(tmp_path):
    path=tmp_path/'scan.out';path.write_text(sample_text())
    result=read_orca_results(path);frames=result.frames()
    return result,frames,path


def test_scan_boundaries_final_energies_and_unfinished_step(parsed):
    result,frames,_=parsed;run,=result.scans
    assert run.simultaneous and run.expected_points==3
    assert [c.atoms for c in run.coordinates]==[(1,0),(0,1,2)]
    assert [c.label for c in run.coordinates]==['Bond (2, 1)','Angle (1, 2, 3)']
    assert [c.unit for c in run.coordinates]==['Å','°']
    assert [p.values for p in run.points]==[(1.5,90.),(1.6,100.),(1.7,110.)]
    assert [p.converged for p in run.points]==[True,True,False]
    np.testing.assert_allclose([p.energy_ev/Hartree for p in run.points],[-10.101,-10.201,-10.3])
    assert [s.kind for s in result.stages]==['scan']*3
    assert result.stages[0].name == 'Scan step 1 · Bond (2, 1)=1.5 Å, Angle (1, 2, 3)=90 °'
    assert result.stages[-1].status=='Incomplete / not converged'
    for point in run.points:
        endpoint=frames[point.frame_index]
        assert endpoint.info['scan_step']==point.number
        assert endpoint.info['scan_coordinate_labels']==['Bond (2, 1)','Angle (1, 2, 3)']
        assert endpoint.info['scan_endpoint'] and endpoint.info['scan_converged']==point.converged
        assert endpoint.positions[1,0]==point.values[0]
        assert endpoint.energy_ev==point.energy_ev
    assert frames[-1].energy_ev is None
    assert frames[-1].info['scan_step']==3 and not frames[-1].info.get('scan_endpoint')


def test_equal_geometries_across_scan_boundaries_are_not_merged(tmp_path):
    text=sample_text(False).replace('1.60000000','1.50000000').replace('O 1.6','O 1.5').replace('H 1.6','H 1.5')
    path=tmp_path/'same.out';path.write_text(text)
    result=read_orca_results(path);frames=result.frames()
    first,second=result.scans[0].points[:2]
    assert first.frame_index!=second.frame_index
    assert frames[first.frame_index].info['stage_index']!=frames[second.frame_index].info['stage_index']


def test_project_roundtrip_preserves_scans(parsed,tmp_path):
    from lele.project_file import save_project,load_project
    from lele.render_options import RenderOptions
    result,frames,path=parsed
    document=Document(path,'ORCA output',frames,calculation_results=result)
    # Earlier projects cached these generated captions using native ORCA IDs.
    result.stages[0].name = 'Scan step 1 · Bond(1,0)=1.5 Å, Angle(0,1,2)=90 °'
    for frame in frames:
        frame.info['scan_coordinate_labels'] = ['Bond (1, 0) [ORCA index]', 'Angle (0, 1, 2) [ORCA index]']
    output=tmp_path/'scan.lele'
    save_project(output,{'documents':[{'document':document, 'options':RenderOptions()}], 'current_document':0})
    restored=load_project(output)['documents'][0]['document']
    scan=restored.calculation_results.scans[0]
    assert scan.simultaneous and scan.coordinates[0].label == 'Bond (2, 1)'
    assert scan.coordinates[0].atoms == (1, 0)
    assert restored.calculation_results.stages[0].name == 'Scan step 1 · Bond (2, 1)=1.5 Å, Angle (1, 2, 3)=90 °'
    assert restored.frames[scan.points[0].frame_index].info['scan_coordinate_labels'] == ['Bond (2, 1)', 'Angle (1, 2, 3)']
    assert scan.points[0].frame_index==result.scans[0].points[0].frame_index
    assert restored.frames[scan.points[-1].frame_index].info['scan_converged'] is False


def test_tree_separates_path_endpoints_and_per_step_histories(parsed):
    from PySide6.QtWidgets import QApplication
    from lele.files_tree import FileItem
    from lele.workflow_ui import populate_tree,sequence_for
    app=QApplication.instance() or QApplication([])
    result,frames,path=parsed;doc=Document(path,'ORCA output',frames,calculation_results=result)
    window=SimpleNamespace(_frame_tree_items={},_series_tree_items={},_vibration_tree_items={},doc=doc)
    root=FileItem(['scan.out'])
    assert populate_tree(window,0,doc,root)
    scan=root.child(0)
    assert 'simultaneous scan path' in scan.text(0)
    endpoints=scan.child(0)
    assert 'converged endpoints' in endpoints.text(0) and endpoints.childCount()==2
    assert 'Bond (2, 1)' in endpoints.child(0).text(0)
    assert scan.toolTip(0) == 'Bond (2, 1) (Å)\nAngle (1, 2, 3) (°)'
    histories=scan.child(2)
    assert histories.childCount()==3
    for i in range(3):
        history=histories.child(i)
        assert f'Scan step {i+1}' in history.text(0)
        assert 'Bond (2, 1)' in history.text(0)
        assert all(any(t in history.child(j).text(0) for t in ('Optimization cycle', 'Final optimized geometry', 'Latest evaluated geometry')) for j in range(history.childCount()))
    frame_index=result.scans[0].points[1].frame_index
    window.frame_index=frame_index;window.frame=frames[frame_index]
    assert all(frames[i].info['scan_step']==2 for i in sequence_for(window))


@pytest.mark.parametrize('final_coordinates_printed',[False,True])
def test_truncation_after_convergence_does_not_invent_final_endpoint(tmp_path,final_coordinates_printed):
    text=sample_text(False).split('THE OPTIMIZATION HAS CONVERGED',1)[0]+'THE OPTIMIZATION HAS CONVERGED\n'
    if final_coordinates_printed:text+=geometry(1.501)
    path=tmp_path/'truncated.out';path.write_text(text)
    result=read_orca_results(path);frames=result.frames();point,=result.scans[0].points
    assert not point.converged
    assert 'final endpoint energy not printed' in result.stages[0].status
    assert point.energy_ev/Hartree==pytest.approx(-10.1)
    assert frames[point.frame_index].positions[1,0]==1.5
    assert not frames[point.frame_index].info['scan_converged']
    if final_coordinates_printed:
        assert frames[-1].energy_ev is None and frames[-1].positions[1,0]==1.501
