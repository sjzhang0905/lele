import csv

import numpy as np
import pytest

from lele.formats import load_document
from lele.import_paths import is_folder_import_candidate
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.vtst_dimer import records
from test_periodic_fragment_ui_v171 import gui

HEADER = ('vasp.6.4.0\n TITEL = PAW H\n ions per type = 1\n IBRION = 3\n'
          ' CHAIN: Running the Dimer method\n direct lattice vectors\n 5 0 0\n 0 5 0\n 0 0 5\n')


def evaluation(index, pos, e0, block, energy_first):
    forces = f' POSITION  TOTAL-FORCE (eV/Angst)\n -----\n {pos} 1 1  .2 0 0\n'
    summary = (' FREE ENERGIE OF THE ION-ELECTRON SYSTEM (eV)\n'
               f' free energy TOTEN = {e0-.125}\n energy without entropy= 3 energy(sigma->0) = {e0}\n')
    scf = f' ---- Iteration {index}( 1) ----\n energy without entropy = 123 energy(sigma->0) = 987\n'
    return scf + (summary+forces+block if energy_first else forces+block+summary)


@pytest.mark.parametrize('energy_first', [True,False])
def test_dimer_outcar_reads_only_centres_and_pairs_rotations(tmp_path, energy_first):
    path = tmp_path/'OUTCAR'
    path.write_text(HEADER+
        evaluation(1, 1, -1.0, ' Dimer: Itr 1 Rot 0\n Dimer: Central Point\n Dimer: F0 0.12\n',energy_first)+
        evaluation(2, 1.03, 7.0, ' Dimer: Itr 1 Rot 1\n Dimer: CN -.4\n Dimer: F0 .12\n Dimer: FN .08\n',energy_first)+
        evaluation(3, .97, 7.2, ' Dimer: Itr 1 Rot 1\n Dimer: Th 2.2\n',energy_first)+
        evaluation(4, 2, -2.0, ' Dimer: Itr 2 Rot 0\n Dimer: Central Point\n Dimer: F0 .002\n',energy_first)+
        ' reached required accuracy - stopping structural energy minimisation\n')
    doc = load_document(path)
    assert doc.format_name=='VASP VTST dimer OUTCAR'
    assert [f.energy_ev for f in doc.frames]==[-1,-2]
    assert [f.positions[0,0] for f in doc.frames]==[1,2]
    rows = list(records(doc.calculation_results))
    assert [(r['step'],r.get('rotation'),r['frame']) for r in rows]==[(1,1,0),(2,None,1)]
    assert [rows[0][k] for k in ('torque','curvature','angle','centre_energy')]==[.08,-.4,2.2,-1.125]
    assert 'curvature' not in rows[-1] and doc.frames[-1].info['optimization_converged']
    project=tmp_path/'dimer.lele'
    save_project(project,{'documents':[{'document':doc,'options':RenderOptions()}]})
    assert list(records(load_project(project)['documents'][0]['document'].calculation_results))==rows
    from lele.vasp_results import last_outcar_frame
    last = last_outcar_frame(path)
    assert last.energy_ev == -2 and last.positions[0,0] == 2


def test_dimcar_repeated_translations_csv_and_trailing_record(gui,tmp_path):
    path=tmp_path/'DIMCAR'
    path.write_text('Step Force Torque Energy Curvature Angle\n1 .3 .6 -5 -.9 20\n'
                    '1 .3 .2 -5 -1.2 4\n2 .02 .03 -4.8 -1.6 .1\n3 .0')
    assert is_folder_import_candidate(path)
    w=gui.window
    w._add_document_tree(0,w.doc)
    w._open_path_now(path)
    assert not w.doc.frames and 'Incomplete trailing record' in w.doc.note
    assert all(s.energy_ev is None for s in w.doc.calculation_results.steps)
    d=w.show_energy_curve()
    assert d.energy.currentData()=='centre_energy'
    assert d.energy.findData('e0')==-1
    d.metric_combo.setCurrentIndex(d.metric_combo.findData('curvature'))
    np.testing.assert_equal(d.lines[1].get_ydata(),[-.9,-1.2,-1.6])
    out=tmp_path/'dimer.csv';d._write_csv(out)
    with out.open(encoding='utf-8-sig') as f:
        a=list(csv.DictReader(f))
    assert [(r['Translation'],r['Rotation'],r['Centre frame'],r['Centre E0 (eV)']) for r in a]==[
        ('1','1','',''),('1','2','',''),('2','1','','')]
    d.close()
    with path.open('a') as f:
        f.write('\n4 .1 .1 -5 -1 .1\n')
    with pytest.raises(ValueError,match='line 5'):
        load_document(path)


def test_mode_reference_and_arrows(gui,tmp_path):
    center=tmp_path/'CENTCAR'; path=tmp_path/'NEWMODECAR'
    path.write_text('0 0 0\n0 1.0D+00 0\n')
    with pytest.raises(ValueError,match='CENTCAR'):
        load_document(path)
    center.write_text('test\n1\n8 0 0\n0 8 0\n0 0 8\nO H\n1 1\nSelective dynamics\nDirect\n.2 .2 .2 F F F\n.3 .2 .2 T T T\n')
    assert is_folder_import_candidate(center) and is_folder_import_candidate(path)
    w=gui.window;w._add_document_tree(0,w.doc)
    w._open_path_now(path)
    assert w.frame.symbols==['O','H'] and len(w.renderer.mode_arrow_actors)==1
    assert not w.doc.vibrations
    w._open_path_now(center)
    assert len(w.renderer.mode_arrow_actors)==0
    path.write_text('0 0 1\n')
    with pytest.raises(ValueError,match='per reference atom'):
        load_document(path)


def test_dimcar_vtst6_final_centre_and_restarted_run(tmp_path):
    path = tmp_path/'DIMCAR'
    header = 'Step Force Torque Energy Curvature Angle\n'
    path.write_text(header + '1 .4 .1 -5 -1.2 0\n2 .01 --- -4.9 --- ---\n'
                    + header + '1 .05 .04 -6 -.3 3\n1 .05 --- -6 --- ---\n')
    doc = load_document(path)
    rows = list(records(doc.calculation_results))
    assert [(r['job'],r['step'],r.get('rotation')) for r in rows] == [
        (1,1,1), (1,2,None), (2,1,1), (2,1,None)]
    assert rows[1]['centre_energy'] == -4.9 and rows[1]['force'] == .01
    assert 'torque' not in rows[-1] and 'angle' not in rows[-1]
    assert all(r['e0'] is None and r['frame'] is None for r in rows)
    path.write_text(header + '1 .01 --- -4.9 -1.2 ---\n')
    with pytest.raises(ValueError, match='line 2'):
        load_document(path)
