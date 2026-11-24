from pathlib import Path

import numpy as np
import pytest
from vtkmodules.util.numpy_support import vtk_to_numpy

from lele.core import Document, Frame, Volume
from lele.field_export import export_active_cube
from lele.field_pair import make_field_pair, read_pair_source, source_channels
from test_periodic_fragment_ui_v171 import gui

ROLES = {'esp': ('Density', 'ESP'), 'electron_hole': ('Electron', 'Hole')}


def cubes(directory, mode):
    frame = Frame(['H'], [[0,0,0]])
    paths = []
    for i, role in enumerate(ROLES[mode]):
        n = 11 if i == 0 else 19
        axis = np.linspace(-2, 2, n)
        basis = np.eye(3)*(axis[1]-axis[0])
        xyz = np.broadcast_arrays(*np.meshgrid(axis, axis, axis, indexing='ij'))
        x,y,z = xyz
        data = x-2*y+.5*z if role == 'ESP' else np.exp(-((x-.55*i)**2 + y*y + z*z))
        field = Volume(data, [-2]*3, basis, label=role, unit='Hartree' if role == 'ESP' else 'e/Bohr³')
        path = directory/(role+'.cube')
        export_active_cube(path, Document(path, 'fixture', [frame], field), frame)
        paths.append(path)
    return paths


def pair(paths, mode, levels):
    docs = [read_pair_source(path, role) for path,role in zip(paths, ROLES[mode])]
    return make_field_pair(mode, docs, [source_channels(d)[0][1] for d in docs], levels)


def vasp(path, arrays, atom='H'):
    header = f'test\n1\n2 0 0\n0 2 0\n0 0 2\n{atom}\n1\nDirect\n0 0 0\n'
    text = header+'\n'.join('\n3 3 3\n'+' '.join(str(x) for x in a.ravel(order='F'))+'\n' for a in arrays)
    path.write_text(text)
    return path


@pytest.mark.parametrize('count', [1,2,4])
def test_vasp_pair_native_units_spin_and_sign(tmp_path, count):
    values = np.arange(27, dtype=float).reshape(3,3,3)
    density = vasp(tmp_path/'CHGCAR', [8*values, values*-4])
    energies = [values+i*3 for i in range(count)]
    potential = vasp(tmp_path/'LOCPOT', energies)
    plot, layers = pair((density,potential),'esp',[1.2])
    np.testing.assert_allclose(plot.volumes[0].data, values)
    expected = -.5*(energies[0]+energies[1]) if count == 2 else -energies[0]
    np.testing.assert_allclose(plot.volumes[1].data, expected)
    assert plot.volumes[1].unit == 'V'
    assert len(layers) == 1 and layers[0]['dataset'] == 0 and layers[0]['map_dataset'] == 1
    assert layers[0]['map_palette'] == 'VMD RWB'
    with pytest.raises(ValueError):
        read_pair_source(density,'ESP')


def test_bad_pair_leaves_inputs_untouched(tmp_path):
    paths = cubes(tmp_path,'esp')
    a,b = [read_pair_source(p,r) for p,r in zip(paths,ROLES['esp'])]
    choices = [(0,),(0,)]
    with pytest.raises(ValueError, match='same file'):
        make_field_pair('esp', [a,a], choices, [.15])
    b.frames[0].positions += 1
    with pytest.raises(ValueError, match='coordinates differ'):
        make_field_pair('esp', [a,b], choices, [.15])
    b.frames[0].positions -= 1
    b.volume.origin += 50
    with pytest.raises(ValueError, match='overlap'):
        make_field_pair('esp', [a,b], choices, [.15])
    b.volume.origin -= 50
    with pytest.raises(ValueError, match='isovalue'):
        make_field_pair('esp',[a,b],choices,[2])
    assert len(a.volumes) == len(b.volumes) == 1


@pytest.mark.parametrize('mode', ['esp','electron_hole'])
def test_two_file_dialog_canvas_and_portable_project(gui,tmp_path,monkeypatch,mode):
    from PySide6.QtWidgets import QDialog
    from lele.field_pair_dialog import FieldPairDialog
    from lele.project_file import load_project
    paths = cubes(tmp_path,mode)
    w = gui.window
    original = w.doc
    w.render_options.volume_signs = 'None'
    w.render_options.show_volume = False
    def choose(dialog):
        for i, path in enumerate(paths):
            monkeypatch.setattr('lele.field_pair_dialog.QFileDialog.getOpenFileName',lambda *_, p=path:(str(p),''))
            dialog.browse(i)
            if dialog.levels[i] is not None:
                dialog.levels[i].setText('.48')
        assert dialog.plot_button.isEnabled()
        dialog.plot_button.click()
        assert not dialog.error.text(), dialog.error.text()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(FieldPairDialog,'exec',choose)
    action = w.esp_action if mode == 'esp' else w.electron_hole_action
    action.trigger()
    assert w.doc is not original and len(w.doc.volumes) == 2 and not original.volumes
    assert len(w.renderer.field_actors) == (1 if mode == 'esp' else 2)
    assert len(w.renderer.field_scalar_bars) == (1 if mode == 'esp' else 0)
    assert all(actor.GetProperty().GetOpacity() == .5 for actor in w.renderer.field_actors)
    menu = w._loaded_file_menu(w.doc)
    action_labels = [action.text() for action in menu.actions()]
    assert ('Add ESP extrema…' in action_labels) == (mode == 'esp')
    menu.deleteLater()
    if mode == 'esp':
        mapper = w.renderer.field_actors[0].GetMapper()
        mapper.Update()
        mesh = mapper.GetInput()
        coords = vtk_to_numpy(mesh.GetPoints().GetData())
        values = vtk_to_numpy(mesh.GetPointData().GetScalars())
        np.testing.assert_allclose(values, coords@[1.,-2.,.5],atol=2e-5)
    else:
        a,b = w.render_options.volume_surfaces
        assert (a['dataset'],b['dataset']) == (0,1) and a['color'] != b['color']
    saved = tmp_path/'view.lele'
    w.save_project_to(saved)
    for p in paths:
        p.unlink()
    entry = load_project(saved)['documents'][-1]
    np.testing.assert_array_equal(entry['document'].volumes[1].data,w.doc.volumes[1].data)
    w.change_frame(0,switch_doc=0)
    assert w.render_options.volume_signs == 'None' and not w.render_options.show_volume
    monkeypatch.setattr(FieldPairDialog,'exec',lambda _self: QDialog.DialogCode.Rejected)
    action.trigger()
    assert w.doc is original and len(w.documents) == 2


def test_esp_cube_roles_and_signed_hole(tmp_path):
    density, potential = cubes(tmp_path, 'esp')
    with pytest.raises(ValueError,match='incompatible units'):
        pair((potential, density),'esp',[.1])
    electron, hole = cubes(tmp_path, 'electron_hole')
    h = read_pair_source(hole, 'Hole')
    h.volume.data *= -1
    export_active_cube(hole, h, h.frames[0])
    plot, layers = pair((electron, hole),'electron_hole',[.48,-.48])
    assert layers[0]['value'] > 0 > layers[1]['value']
    assert plot.volumes[1].data.max() <= 0


def test_pair_dialog_from_empty_window_and_switch_during_input(gui,tmp_path,monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from lele.field_pair_dialog import FieldPairDialog
    paths = cubes(tmp_path, 'esp')
    w = gui.window
    w._unload_document(w.doc)
    assert w.doc is None and w.esp_action.isEnabled()
    errors = []
    def fill():
        dialog = next(d for d in QApplication.topLevelWidgets() if isinstance(d,FieldPairDialog) and d.isVisible())
        try:
            dialog.load_source(0, paths[0])
            # The form is independent of the active structure and selection.
            w._attach_loaded_document(read_pair_source(paths[0], 'Density'))
            dialog.load_source(1, paths[1])
            dialog.levels[0].setText('.48')
            dialog.plot()
        except BaseException as exc:
            errors.append(exc)
            dialog.reject()
    QTimer.singleShot(0, fill)
    w.esp_action.trigger()
    assert not errors
    assert len(w.documents) == 2 and len(w.renderer.field_scalar_bars) == 1


def test_vasp_renamed_files_keep_role_units(tmp_path):
    values = np.arange(27,dtype=float).reshape(3,3,3)
    a=vasp(tmp_path/'density.grid',[8*values])
    b=vasp(tmp_path/'potential.grid',[values])
    doc,_=pair((a,b),'esp',[.5])
    np.testing.assert_allclose(doc.volumes[1].data,-values)
    assert doc.volumes[1].unit=='V'
