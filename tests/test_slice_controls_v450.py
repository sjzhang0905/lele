from pathlib import Path

import numpy as np
import pytest
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.core import Document, Frame, Volume
from lele.crystal_planes import default_plane
from lele.field_slice import contour_labels, contour_levels
from lele.plane_field import validate_plane_style
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.selection_geometry import fit_selection_plane
from test_periodic_fragment_ui_v171 import gui


def ramp():
    values = np.broadcast_to(np.arange(11.)[:,None,None], (11,8,5)).copy()
    return Volume(values, np.zeros(3), np.eye(3), 'Linear field', 'a.u.')


def test_two_dimensional_plot_count_labels_and_fixed_range(gui):
    from matplotlib.contour import QuadContourSet
    from lele.field_slice_dialog import FieldSliceDialog
    dialog = FieldSliceDialog(ramp(), gui.window)
    try:
        assert dialog.contour_count.value() == 7 and not dialog.contour_count.isEnabled()
        dialog.contours.setChecked(True)
        dialog.contour_count.setValue(4)
        dialog.canvas.draw()
        axes = dialog.figure.axes[0]
        lines = next(item for item in axes.collections if isinstance(item, QuadContourSet))
        np.testing.assert_allclose(lines.levels, [2,4,6,8])
        assert {text.get_text() for text in axes.texts} == {'2','4','6','8'}
        dialog.contour_labels.setChecked(False)
        dialog.contour_count.setValue(1)
        axes = dialog.figure.axes[0]
        assert not axes.texts
        lines = next(item for item in axes.collections if isinstance(item, QuadContourSet))
        np.testing.assert_allclose(lines.levels,[5])
        dialog.range_min.setText('2');dialog.range_max.setText('4')
        dialog.manual_range.setChecked(True)
        lines = next(item for item in dialog.figure.axes[0].collections if isinstance(item, QuadContourSet))
        np.testing.assert_allclose(lines.levels,[3])
        dialog.contours.setChecked(False)
        assert not any(isinstance(item, QuadContourSet) for item in dialog.figure.axes[0].collections)
        assert not dialog.contour_labels.isEnabled()
    finally:
        dialog.close()


@pytest.mark.parametrize('fitted',[False,True])
def test_canvas_contour_labels_lie_on_requested_field_values(fitted, tmp_path):
    volume = ramp()
    frame = Frame(['H']*3, [[2,1,2],[3,1,2],[2,2,2]], np.diag([10.,7.,4.]), (True,)*3)
    style = dict(field_contours=True, field_contour_count=4, field_contour_labels=True, field_legend=False)
    plane = {**default_plane(), **style}
    options = RenderOptions(axes_position='Off', volume_signs='None', fitted_plane_style=style if fitted else {},
                            lattice_planes=[] if fitted else [plane])
    path = save_project(tmp_path/'slice.lele', dict(documents=[dict(document=Document(Path('x'), 'test', [frame], volume),options=options)]))
    draw = MoleculeRenderer(vtkRenderer())
    draw.options = load_project(path)['documents'][0]['options']
    if fitted:
        draw.fitted_plane = fit_selection_plane(frame, range(3))
    def labels():
        return [a for a in draw.dynamic if a.GetObjectName() == 'lele-plane-contour-value']
    draw.set_scene(frame, volume)
    assert {a.GetInput() for a in labels()} == {'2','4','6','8'}
    for actor in labels():
        assert actor.GetPosition()[0] == pytest.approx(float(actor.GetInput()), abs=1e-4)
        assert actor.GetPosition()[2] == pytest.approx(2, abs=1e-4)
    stored = draw.options.fitted_plane_style if fitted else draw.options.lattice_planes[0]
    stored.update(field_contour_count=2, field_contour_labels=False)
    draw.set_scene(frame, volume)
    assert not labels()
    assert draw.plane_contour_actors[0].GetMapper().GetInputAlgorithm().GetNumberOfContours() == 2
    stored.update(field_contour_labels=True, field_range=[20,30])
    draw.set_scene(frame, volume)
    assert not labels() and not draw.plane_contour_actors


def test_controls_per_hkl_record_and_fitted_plane(gui):
    panel = gui.window.crystal_panel.planes
    panel.add_plane()
    panel.field_controls.contours.setChecked(True)
    panel.field_controls.contour_count.setValue(13)
    panel.field_controls.contour_labels.setChecked(True)
    panel.add_plane()
    assert not panel.field_controls.contour_count.isEnabled()
    assert panel.field_controls.contour_count.value() == 7
    panel.table.selectRow(0)
    assert panel.field_controls.contour_count.value() == 13 and panel.field_controls.contour_labels.isChecked()
    controls = gui.window.fitted_plane_controls
    controls.contours.setChecked(True)
    controls.contour_count.setValue(1)
    controls.contour_labels.setChecked(True)
    assert gui.window.render_options.fitted_plane_style['field_contour_count'] == 1
    assert gui.window.render_options.fitted_plane_style['field_contour_labels'] is True


def test_contours_on_flat_data_and_very_close_levels():
    assert not len(contour_levels([2,2],100))
    levels = contour_levels([1,1.00000001],100)
    assert len(set(contour_labels(levels).values())) == len(levels) == 100
    for count in (0,101,True,1.5):
        with pytest.raises(ValueError,match='Contour levels'):
            validate_plane_style(dict(field_contour_count=count))
