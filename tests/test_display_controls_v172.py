"""GUI and rendering regressions for the eight v1.7.2 display requests."""
from pathlib import Path

import numpy as np
import pytest

from lele.core import Frame
from lele.formats import load_document
from lele.renderer import MoleculeRenderer
from test_periodic_fragment_ui_v171 import gui


@pytest.mark.parametrize('basis', ['XYZ', 'abc'])
def test_corner_letters_are_billboards_outside_transform_assemblies(gui, basis):
    w = gui.window
    w.renderer.options.axes_basis = basis
    marker = w.renderer.make_corner_marker(w.frame)
    assert marker.IsA('vtkPropAssembly')
    assert [label.GetInput() for label in w.renderer.corner_labels] == list('XYZ' if basis == 'XYZ' else 'abc')
    assert all(label.IsA('vtkBillboardTextActor3D') for label in w.renderer.corner_labels)


@pytest.mark.parametrize('basis', ['XYZ', 'abc'])
def test_corner_text_stays_at_arrow_tips_during_native_camera_rotation(basis):
    from lele.animation_export import _OffscreenScene, GifSettings
    from lele.render_options import RenderOptions
    frame = Frame(['C'], [[0, 0, 0]], [[5, 0, 0], [1, 5, 0], [.5, .5, 6]], (True,) * 3)
    scene = _OffscreenScene(GifSettings(width=400, height=300, supersample=1),
                            RenderOptions(axes_basis=basis), None, (), (400, 300))
    try:
        image = scene.render(frame, None)
        image.close()
        labels = list(scene.draw.corner_labels)
        bounds = scene.marker.GetOrientationMarker().GetBounds()
        for angle in (0, 35, 70):
            scene.scene.GetActiveCamera().Azimuth(angle)
            scene.scene.GetActiveCamera().Roll(angle)
            # No marker recreation or UI refresh: this is a camera gesture.
            scene.window.Render()
            assert scene.draw.corner_labels == labels
            np.testing.assert_allclose(scene.marker.GetOrientationMarker().GetBounds(), bounds)
            renderer = scene.marker.GetRenderer()
            for label in labels:
                assert not label.GetUseBounds()
                renderer.SetWorldPoint(*label.GetPosition(), 1.)
                renderer.WorldToDisplay()
                # Texture anchors use integer device pixels; fractional
                # viewport origins add another rounding step (up to 2 px).
                np.testing.assert_allclose(label.GetAnchorDC()[:2], renderer.GetDisplayPoint()[:2], atol=2.)
    finally:
        scene.close()


def arrow_radii(vector):
    actor, (source, mapper, matrix) = MoleculeRenderer._arrow_actor(vector, '#ff0000')
    source.Update()
    points = source.GetOutput().GetPoints()
    local = np.array([points.GetPoint(i) for i in range(points.GetNumberOfPoints())])
    transform = np.array([[matrix.GetElement(i, j) for j in range(3)] for i in range(3)])
    world = local @ transform.T
    direction = np.asarray(vector) / np.linalg.norm(vector)
    perpendicular = world - np.outer(world @ direction, direction)
    return np.max(np.linalg.norm(perpendicular, axis=1)), actor.GetBounds()


@pytest.mark.parametrize('direction', [[1., 0, 0], [1., 2, -3]])
def test_arrow_geometry_keeps_width_when_length_changes(direction):
    direction = np.asarray(direction)
    direction /= np.linalg.norm(direction)
    short, _ = arrow_radii(direction)
    long, _ = arrow_radii(direction * 12)
    assert np.isclose(short, long, rtol=1e-6)


@pytest.mark.parametrize('raw, expected', [
    ('Singlet-?Sym', 'Singlet'), ('Triplet-?Sym', 'Triplet'),
    ('Singlet-A1', 'Singlet-A1'), ('Doublet-?Sym', 'Doublet'),
])
def test_transition_state_display_preserves_real_symmetry(raw, expected):
    from lele.gaussian_properties import transition_state_label
    assert transition_state_label(raw) == expected


def test_uv_table_cleans_unknown_symmetry_but_csv_keeps_the_source_value(gui):
    from lele.spectrum_dialog import SpectrumDialog
    from lele.property_export import transition_rows
    path = Path(__file__).resolve().parents[1] / 'examples/synthetic_properties.log'
    document = load_document(path)
    document.electronic_spectra[0].transitions[0].state = 'Singlet-?Sym'
    dialog = SpectrumDialog(document, 'UV-Vis', gui.window)
    gui.addCleanup(dialog.deleteLater)
    assert dialog.table.item(0, 0).text() == '1 Singlet'
    assert transition_rows(document)[0]['state_description'] == 'Singlet-?Sym'


def test_dipole_scale_can_be_typed_without_mid_edit_resets(gui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w = gui.window
    gui.attach_properties()
    w.dipole_action.trigger()
    w.show()
    gui.app.processEvents()
    scale = w.dipole_panel.scale
    assert not scale.keyboardTracking()
    for value in ('1.2345', '0.015'):
        old = w.render_options.dipole_scale
        editor = scale.lineEdit()
        editor.setFocus()
        editor.selectAll()
        QTest.keyClicks(editor, value)
        assert w.render_options.dipole_scale == old
        w.refresh_scene()
        assert value in editor.text()
        QTest.keyClick(editor, Qt.Key.Key_Return)
        assert np.isclose(w.render_options.dipole_scale, float(value), atol=1e-6)


def test_box_shortcut_toggles_mode_and_escape_cancels(gui):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    w = gui.window
    w.show()
    w.vtk.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    w.vtk.setFocus()
    gui.app.processEvents()
    assert w.box_select_action.shortcut().toString() == 'Ctrl+Shift+B'
    modifiers = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    QTest.keyClick(w.vtk, Qt.Key.Key_B, modifiers)
    assert w.box_select_action.isChecked() and w.box_select_button.isChecked()
    QTest.keyClick(w.vtk, Qt.Key.Key_B, modifiers)
    assert not w.box_select_action.isChecked()
    QTest.keyClick(w.vtk, Qt.Key.Key_B, modifiers)
    QTest.keyClick(w.vtk, Qt.Key.Key_Escape)
    assert not w.box_select_action.isChecked() and not w.box_select_button.isChecked()


def test_selection_outline_has_transparent_interior_and_dashed_edges(gui):
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from lele.selection_outline import SelectionOutline
    class Canvas(QWidget):
        def GetRenderWindow(self):return window
    canvas=Canvas();canvas.resize(240,180);gui.addCleanup(canvas.deleteLater)
    window=vtkRenderWindow();window.SetOffScreenRendering(True);window.SetSize(240,180)
    renderer=vtkRenderer();renderer.SetBackground(.3,.3,.3);window.AddRenderer(renderer)
    gui.addCleanup(window.Finalize)
    def capture():
        window.Render();shot=vtkWindowToImageFilter();shot.SetInput(window);shot.ReadFrontBufferOff();shot.Update()
        return vtk_to_numpy(shot.GetOutput().GetPointData().GetScalars()).reshape(180,240,-1)[::-1].copy()
    before=capture()
    outline=SelectionOutline(canvas);outline.setGeometry(QRect(25,25,160,100))
    outline.show()
    after=capture()
    np.testing.assert_array_equal(before[50:100,60:150],after[50:100,60:150])
    assert np.any(np.any(after[21:30,25:185]!=before[21:30,25:185],axis=2))
    assert outline.geometry.GetNumberOfLines()>12
    outline.hide();np.testing.assert_array_equal(capture(),before)
    outline.close()


@pytest.mark.parametrize('boundary', [False, True])
def test_atom_transparency_editor_immediately_updates_connected_bonds(gui, boundary):
    frame = Frame(['C'] * 3, [[2, 2, 2], [3.4, 2, 2], [4.8, 2, 2]],
                  np.eye(3) * 10, (True,) * 3)
    gui.attach(frame)
    w = gui.window
    w.render_options.axes_position = 'Off'
    w.render_options.unit_cell = False
    if boundary:
        w._apply_boundary(True, ((0, 2), (0, 1), (0, 1)))
    gui.select([1])
    w.atom_panel.transparency_spin.setValue(65)
    assert np.isclose(w.frame.atom_appearance[1].opacity, .35)
    tubes = [a for a in w.renderer.dynamic if a.IsA('vtkActor')
             and a.GetMapper().GetInputConnection(0, 0) is not None
             and a.GetMapper().GetInputConnection(0, 0).GetProducer().IsA('vtkTubeFilter')]
    assert tubes
    assert all(np.isclose(a.GetProperty().GetOpacity(), .35**2) for a in tubes)
    w.undo_edit()
    tubes = [a for a in w.renderer.dynamic if a.IsA('vtkActor')
             and a.GetMapper().GetInputConnection(0, 0) is not None
             and a.GetMapper().GetInputConnection(0, 0).GetProducer().IsA('vtkTubeFilter')]
    assert all(a.GetProperty().GetOpacity() == 1 for a in tubes)


def test_boundary_panel_repeats_whole_cells_without_changing_source(gui):
    frame = Frame(['Si'], [[0, 0, 0]], np.eye(3) * 2.2, (True,) * 3)
    gui.attach(frame)
    w = gui.window
    w.boundary_panel.enabled.setChecked(True)
    w.boundary_panel.spins[0][1].setValue(2)
    w.boundary_panel.spins[1][1].setValue(2)
    w.boundary_panel.apply.click()
    view = w.renderer.boundary_display
    assert len(view.source_indices) == 18
    assert len(view.tiles) == 4
    np.testing.assert_allclose(view.frame.cell, frame.cell)
    np.testing.assert_allclose(view.frame.positions[:4], [[0, 0, 0], [0, 2.2, 0], [2.2, 0, 0], [2.2, 2.2, 0]])
    assert set(view.source_indices) == {0}
    assert np.max(view.frame.positions[:,2]) == 2.2
    assert w.atom_table.rowCount() == 1 and w.doc.frames[0] is frame
    assert '4 cells' in w.boundary_panel.count.text()
