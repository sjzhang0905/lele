"""Panel layout, public entry points and compatibility of saved display choices."""
from math import log10
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QComboBox, QLabel, QScrollArea, QWidget,
)

from lele.app import LELEWindow
from lele.atom_appearance import AtomAppearance, LEGACY_ORCA_LABEL
from lele.core import Frame
from lele.lattice_tiles import ONE_CELL
from lele.render_options import RenderOptions
from test_display_and_order_v2130 import crystal, project_roundtrip
from test_independent_results_v1111 import ENERGY, attach
from test_periodic_fragment_ui_v171 import gui


def show_page(app, tabs, name):
    index = next(i for i in range(tabs.count()) if tabs.tabText(i) == name)
    tabs.setCurrentIndex(index)
    app.processEvents()
    return tabs.currentWidget()


def check_row(page, widgets):
    viewport = page.viewport() if isinstance(page, QScrollArea) else page
    if isinstance(page, QScrollArea):
        assert page.horizontalScrollBar().maximum() == 0
    previous_right = 0
    centers = []
    for widget in widgets:
        assert widget.isVisible()
        top_left = widget.mapTo(viewport, QPoint())
        assert previous_right <= top_left.x()
        previous_right = top_left.x() + widget.width()
        assert previous_right <= viewport.width()
        centers.append(top_left.y() + widget.height() // 2)
    assert max(centers) - min(centers) <= 1


@pytest.mark.parametrize('style', ['Windows', 'Fusion'])
def test_compact_rows_fit_their_visible_panels(style):
    app = QApplication.instance() or QApplication([])
    old_style = app.style().objectName()
    app.setStyle(style)
    with patch.object(LELEWindow, '_start_backend_loading', lambda self: None):
        w = LELEWindow()
    try:
        w.structure_page.insertWidget(0, QWidget())
        w.canvas_stack.setCurrentWidget(w.structure_page)
        w.resize(1366, 768)
        w.show()
        w.structure_page.setSizes([420, 280])
        w.lower_splitter.setSizes([270, 410, 320])
        axes = show_page(app, w.bottom_control_tabs, 'Axes')
        rotation = w.rotation_controls
        check_row(axes, [rotation.findChild(QLabel), rotation.axis, *rotation.findChildren(QAbstractButton)])
        for group in (w.coordinate_axes.position, w.coordinate_axes.basis):
            assert len(group.buttons) == 3 and not group.findChildren(QComboBox)
            check_row(axes, group.buttons.values())
        check_row(axes, [w.coordinate_axes.length, w.coordinate_axes.slider])
        labels = show_page(app, w.bottom_control_tabs, 'Labels')
        check_row(labels, [w.label_size_spin, w.label_bold_check, w.label_color_btn])
        boundary = show_page(app, w.bottom_control_tabs, 'Boundary')
        panel = w.boundary_panel
        check_row(boundary, [panel.growth, *panel.repeat_spins])
        check_row(boundary, [panel.apply, panel.reset])
        style_page = show_page(app, w.sidebar_tabs, 'Style')
        save = next(b for b in style_page.findChildren(QAbstractButton) if 'Save current' in b.toolTip())
        check_row(style_page, [w.preset_combo, save, w.delete_style_button])
        fragment = show_page(app, w.selection_tabs, 'Fragment')
        check_row(fragment, [fragment.save_button, fragment.delete_button, fragment.front_button, fragment.back_button])
        selection = show_page(app, w.selection_tabs, 'Atoms selection')
        check_row(selection, [selection.expression_input, selection.expression_apply])
        assert selection.expression_input.width() > selection.expression_apply.width()
        w.resize(800, 700)
        axes = show_page(app, w.bottom_control_tabs, 'Axes')
        assert w.width() == 800
        assert w.bottom_control_tabs.geometry().right() < w.tabs.x()
        assert w.tabs.geometry().right() < w.selection_tabs.x()
        scrollbar = axes.horizontalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        last = rotation.findChildren(QAbstractButton)[-1]
        left = last.mapTo(axes.viewport(), QPoint()).x()
        assert 0 <= left <= axes.viewport().width() - last.width()
    finally:
        w.close()
        w.deleteLater()
        app.processEvents()
        app.setStyle(old_style)


def test_edit_buttons_and_analysis_entry_points(gui):
    w, _ = attach(gui, ENERGY)
    files = show_page(gui.app, w.sidebar_tabs, 'Files')
    curve_buttons = (w.geometry_curve_button, w.scan_curve_button, w.energy_curve_button)
    assert all(files.isAncestorOf(button) for button in curve_buttons)
    analysis = w.analysis_menu.actions()
    assert all(action in analysis for action in
               (w.vibration_analysis_action, w.orbital_action, w.neb_action, w.goat_action, w.soc_action))
    assert all('Energy /' not in action.text() for action in analysis)
    assert all(not any(term in b.text() for term in ('Find vibrations', 'HOMO', 'NEB', 'GOAT', 'SOC'))
               for b in files.findChildren(QAbstractButton))
    w.energy_curve_button.click()
    dialog = w._analysis_windows[-1]
    assert len(dialog.points()) == 3 and dialog.isVisible()
    edit = w.mirror_btn.parentWidget().layout()
    assert edit.itemAt(0).widget() is w.mirror_btn
    assert edit.itemAt(edit.indexOf(w.origin_btn) - 1).layout().indexOf(w.charge_spin) >= 0


def test_axis_buttons_and_slider_update_the_display_and_survive_reopen(gui, tmp_path):
    w = gui.window
    axes = w.coordinate_axes
    for value in ('Off', 'Origin', 'Corner'):
        axes.position.buttons[value].click()
        assert w.render_options.axes_position == value
        assert [k for k, b in axes.position.buttons.items() if b.isChecked()] == [value]
    axes.basis.buttons['abc'].click()
    assert w.render_options.axes_basis == 'abc'
    for tick, length in [(-100, .1), (100, 10.), (300, 1000.)]:
        axes.slider.setValue(tick)
        assert axes.length.value() == w.render_options.axes_length == length
    axes.length.setValue(4.25)
    assert axes.slider.value() == round(100 * log10(4.25))
    path = tmp_path/'axes.lele'
    assert w.save_project_to(path)
    axes.basis.buttons['XYZ'].click()
    axes.slider.setValue(0)
    assert w._load_project_path(path)
    assert axes.basis.buttons['abc'].isChecked()
    assert axes.length.value() == w.renderer.options.axes_length == 4.25


def test_open_old_visual_choices_and_select_new_labels(gui, tmp_path):
    frame = crystal()
    frame.atom_appearance[0] = AtomAppearance(label_mode=LEGACY_ORCA_LABEL)
    options = RenderOptions(boundary_enabled=False, boundary_bounds=((0, 4),) * 3,
                            labels=LEGACY_ORCA_LABEL, label_font_file='old-project-font.ttf')
    _, path = project_roundtrip(tmp_path, frame, options)
    w = gui.window
    assert w._load_project_path(path)
    assert w.render_options.boundary_enabled and w.render_options.boundary_bounds == ONE_CELL
    assert w.boundary_panel.bounds() == ONE_CELL
    assert w.label_combo.findText(LEGACY_ORCA_LABEL) < 0 and w.label_combo.currentIndex() == -1
    gui.select([0])
    atom_combo = w.atom_panel.label_combo
    assert atom_combo.findData(LEGACY_ORCA_LABEL) < 0 and atom_combo.currentIndex() == -1
    assert w.label_font_combo.currentIndex() == -1 and w.render_options.label_font_file == 'old-project-font.ttf'
    assert 'O0' in [actor.GetInput() for actor in w.renderer._label_actors]
    w.label_font_combo.setCurrentText('Times')
    assert w.render_options.label_font == 'Times' and not w.render_options.label_font_file
    atom_combo.setCurrentIndex(atom_combo.findData('ORCA index (0..N-1)'))
    w.label_combo.setCurrentText('Element')
    assert w.frame.atom_appearance[0].label_mode == 'ORCA index (0..N-1)' and w.render_options.labels == 'Element'


def test_boundary_uses_source_when_face_images_exceed_budget_and_retries_on_next_frame(gui, monkeypatch):
    monkeypatch.setattr('lele.boundary.MAX_DISPLAY_ATOMS', 2)
    corner = Frame(['Si'], [[0, 0, 0]], np.eye(3)*4, (True,)*3)
    interior = Frame(['Si'], [[1, 1, 1]], corner.cell.copy(), corner.pbc)
    gui.attach(corner, second_frame=interior)
    w = gui.window
    assert w.render_options.boundary_enabled and w.render_options.unit_cell
    assert w.renderer.boundary_display is None and len(w.renderer.displayed_atoms()) == 1
    w.boundary_panel.reset.click()
    assert w.render_options.boundary_bounds == ONE_CELL
    w.change_frame(1)
    assert w.render_options.boundary_enabled and w.renderer.boundary_display is not None
    assert len(w.renderer.displayed_atoms()) == 1
    w.boundary_panel.repeat_spins[0].setValue(2)
    w.boundary_panel.apply.click()
    assert len(w.renderer.displayed_atoms()) == 2
    w.change_frame(0)
    assert w.render_options.boundary_enabled and w.boundary_panel.bounds() == ONE_CELL
    assert len(w.renderer.displayed_atoms()) == 1
