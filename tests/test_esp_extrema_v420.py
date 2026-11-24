import numpy as np
import pytest
from ase.units import Bohr
from PIL import Image
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow

from lele.annotations import AnnotationRenderer, TextAnnotation, extremum_display_transform
from lele.core import Document, Frame, Volume
from lele.esp_extrema import read_extrema_points, make_extremum_labels
from lele.field_pair import make_field_pair
from lele.png_export import PngSettings, export_png
from lele.renderer import MoleculeRenderer
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('row', ['1 2 3', '1 2 3 4 5', '1 2 inf 4', '1 2 3 nan', '1 bad 3 4'])
def test_reject_partial_or_nonfinite_data(tmp_path, row):
    source = tmp_path/'bad.dat'
    source.write_text('1 2 3 4\n' + row)
    with pytest.raises(ValueError, match='Line 2'):
        read_extrema_points(source)


def test_header_comments_bohr_coordinates_and_signs(tmp_path):
    source = tmp_path/'points.csv'
    source.write_text('\ufeff# test\nX,Y,Z,value\n-1,2.5,3,2.54D+01\n0,1,2,-8.16 # min\n', encoding='utf-8')
    labels = make_extremum_labels(read_extrema_points(source), 'Bohr', .4, '#123456', np.eye(3), np.eye(3))
    np.testing.assert_allclose(labels[0].point, np.array([-1, 2.5, 3])*Bohr)
    assert [v.text for v in labels] == ['25.4', '-8.2']
    assert [v.value for v in labels] == [25.4, -8.16]
    source.write_text('  \n# empty')
    with pytest.raises(ValueError, match='no ESP extrema'):
        read_extrema_points(source)


@pytest.mark.parametrize('unit,expected', [('source units',''), ('Hartree/e','Hartree/e'), ('V','V')])
def test_esp_range_unit_and_explicit_auto(gui, tmp_path, unit, expected):
    from lele.field_mapping_dialog import FieldMappingWidget
    w = gui.window
    frame = Frame(['H'], [[0, 0, 0]])
    axis = np.linspace(-1, 1, 9)
    x, y, z = np.meshgrid(axis, axis, axis, indexing='ij')
    density = Volume(1-x*x-y*y-z*z, [-1]*3, np.eye(3)*.25, 'density', 'source units')
    potential = Volume(x, [-1]*3, np.eye(3)*.25, 'ESP', unit)
    docs = [Document(tmp_path/name, 'Gaussian CUBE', [frame], field)
            for name, field in [('density.cube',density), ('esp.cube',potential)]]
    paired, layers = make_field_pair('esp', docs, [(0,), (0,)], [.5])
    w._document_views[id(paired)] = w._new_document_view(paired, surface_layers=layers)
    w._attach_loaded_document(paired)
    bar = w.renderer.field_scalar_bars[0]
    assert bar.GetLookupTable().GetRange() == pytest.approx((-.03, .03))
    assert (bar.GetTitle() or '') == expected
    np.testing.assert_array_equal(paired.volumes[1].data, x)
    widget = FieldMappingWidget(paired.volumes)
    widget.source.setCurrentIndex(widget.source.findData(1))
    assert widget.settings_value()['map_range'] == [-.03, .03]
    widget.automatic.setChecked(True)
    assert widget.settings_value()['map_range'] is None
    widget.set_settings(widget.settings_value())
    assert widget.automatic.isChecked()
    widget.minimum.setText('-.7')
    assert widget.settings_value()['map_range'] == [-.7, 1.]
    widget.deleteLater()


def test_right_click_inactive_file_edit_move_undo_and_restore(gui, tmp_path, monkeypatch):
    from lele.annotation_dialog import AnnotationDialog
    from lele.dialog_policy import QDialog
    from lele.esp_extrema_dialog import EspExtremaDialog
    from lele.project_file import load_project
    from test_field_pair_v410 import cubes, pair
    w = gui.window
    target, layers = pair(cubes(tmp_path, 'esp'), 'esp', [.48])
    w._document_views[id(target)] = w._new_document_view(target, surface_layers=layers)
    w._attach_loaded_document(target)
    original = target.frames[0].positions.copy()
    target.annotations.append(TextAnnotation('Caption'))
    other = Document(tmp_path/'other.xyz', 'XYZ', [Frame(['O'], [[0,0,0]])])
    w._attach_loaded_document(other)
    source = tmp_path/'points.dat'
    source.write_text('1 2 3 24.75\n-2 4 0 -13.97\n')
    def accept_points(dialog):
        dialog.load_file(source)
        assert dialog.add_button.isEnabled()
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(EspExtremaDialog, 'exec', accept_points)
    menu = w._loaded_file_menu(target)
    next(a for a in menu.actions() if a.text() == 'Add ESP extrema…').trigger()
    assert w.doc is target and not other.annotations and not w.doc.modified
    assert [a.text for a in target.annotations] == ['Caption', '24.8', '-14.0']
    sites = w._annotation_manager.markers.GetMapper().GetInput()
    np.testing.assert_allclose(vtk_to_numpy(sites.GetPoints().GetData()), [[1,2,3],[-2,4,0]])
    assert not w._annotation_manager.markers.GetPickable()
    w._selected_annotation = 1
    def edit(dialog):
        assert dialog.content.isReadOnly()
        dialog.annotation.color = '#176ea0'
        dialog.height.setValue(.51)
        dialog.bold.setChecked(True)
        dialog.offsets[0][0].setValue(1.7)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(AnnotationDialog, 'exec', edit)
    assert w.edit_canvas_text()
    label = target.annotations[1]
    assert label.height == .51 and label.bold and label.color == '#176ea0'
    assert label.position[0] == pytest.approx(2.7)
    assert w._begin_annotation_gesture('pan', 12, 20)
    before = label.position.copy()
    assert w._move_annotation_gesture('pan', 20, 15)
    w._end_annotation_gesture('pan')
    assert not np.allclose(before, label.position) and label.point == [1,2,3]
    saved = tmp_path/'scene.lele'
    assert w.save_project_to(saved)
    source.unlink()
    restored = load_project(saved)['documents'][w._document_index(target)]['document']
    assert restored.annotations == target.annotations
    np.testing.assert_array_equal(restored.frames[0].positions, original)
    assert not restored.modified
    w.change_frame(0,switch_doc=w._document_index(other))
    assert w._annotation_manager.markers is None
    w.change_frame(0,switch_doc=w._document_index(target))
    assert w._annotation_manager.markers is not None
    w._selected_annotation = 1
    assert w.delete_canvas_text()
    assert w._annotation_manager.markers.GetMapper().GetInput().GetNumberOfPoints() == 1
    w.undo_edit()
    assert len(target.annotations) == 3
    w.undo_edit()  # drag
    w.undo_edit()  # appearance
    w.undo_edit()  # entire import
    assert target.annotations == [TextAnnotation('Caption')] and w._annotation_manager.markers is None
    menu.deleteLater()


def test_field_transform_and_real_hq_export(tmp_path):
    scene = vtkRenderer()
    scene.SetBackground(1,1,1)
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.AddRenderer(scene)
    window.SetSize(400, 240)
    draw = MoleculeRenderer(scene)
    manager = AnnotationRenderer(scene)
    source = Volume(np.ones((2,2,2)), [0,0,0], np.eye(3))
    rot = np.array([[0.,1,0],[-1,0,0],[0,0,1]])
    source.voxel_vectors = rot
    source.origin = np.array([1.,0,0])
    points = np.array([[-.55,0,0,12.64],[.55,0,0,-7.28]])
    labels = make_extremum_labels(points, 'Å', .28, '#a0007f', np.eye(3), rot)
    manager.set_annotations(labels, extremum_transform=extremum_display_transform(source, draw))
    centers = vtk_to_numpy(manager.markers.GetMapper().GetInput().GetPoints().GetData())
    np.testing.assert_allclose(centers, points[:,:3]@rot + source.origin)
    camera = scene.GetActiveCamera()
    camera.SetPosition(1,0,10)
    camera.SetFocalPoint(1,0,0)
    camera.SetViewUp(0,1,0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(1.3)
    scene.ResetCameraClippingRange()
    try:
        path = tmp_path/'marked.png'
        export_png(path, window, PngSettings(800,480,2))
        image = np.asarray(Image.open(path).convert('RGB')).astype(int)
        gold = (image[:,:,0] > 150) & (image[:,:,1] > 85) & (image[:,:,0] - image[:,:,2] > 85)
        magenta = (image[:,:,0] - image[:,:,1] > 65) & (image[:,:,2] - image[:,:,1] > 55)
        assert gold.sum() > 300 and magenta.sum() > 200
        for x, y, z in centers:
            scene.SetWorldPoint(x,y,z,1)
            scene.WorldToDisplay()
            u, v, _ = scene.GetDisplayPoint()
            u, v = round(u*2), 479-round(v*2)
            assert gold[v-5:v+5,u-5:u+5].any()
    finally:
        manager.clear()
        window.Finalize()
