#!/usr/bin/env python3
"""Windows desktop GUI: PySide6 + embedded VTK.

The application does not run chemistry simulations. It visualizes structures,
frames, and optional volumetric grids from existing calculation files.
"""
from __future__ import annotations

import sys
import traceback
import json
from pathlib import Path

from . import APP_NAME, APP_FULL_NAME, APP_TITLE, __version__
from .settings import read_style_presets

from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QStandardPaths
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QLabel, QToolBar, QFileDialog,
    QComboBox, QSlider, QCheckBox, QDoubleSpinBox, QPushButton, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QMessageBox, QScrollArea, QPlainTextEdit, QAbstractItemView, QColorDialog,
    QInputDialog, QDialog, QLineEdit, QTextEdit, QAbstractSpinBox,
)
from PySide6.QtGui import QAction, QKeySequence, QColor

# Pin the chosen Qt binding before importing VTK's Qt adapter.
import vtkmodules.qt
vtkmodules.qt.PyQtImpl = 'PySide6'
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkWindowToImageFilter
from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
from vtkmodules.vtkIOImage import vtkPNGWriter

from .core import (Document, Frame, measure, colour,
                   toggle_selected_bonds, move_atom_to_origin, align_pair_to_axis)
from .formats import load_document, export_frame
from .structure_summary import molecular_formula
from .chemical_analysis import electron_parity, short_contact_summary
from .periodic_geometry import periodic_fragment, periodic_basis
from .renderer import MoleculeRenderer, set_isometric_view
from .style_presets import (BUILTIN_PRESETS, CUSTOM_KEY, STYLE_KEYS,
                            ATOM_PALETTES, BOND_PALETTES, SURFACE_FINISHES,
                            apply_preset, snapshot, validate_preset)
from .interaction import InteractiveVTKView, vtk_display_from_qt
from .fragment import (selected_fragments, apply_fragment_rotation, apply_fragment_translation,
                       screen_rotation, screen_translation)
from .selection_geometry import (fit_selection_plane, align_plane_to_xy,
                                 delete_selected_atoms as remove_atoms)


class LELEWindow(QMainWindow):
    def __init__(self, initial_files=()):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1380, 850)
        self.setAcceptDrops(True)
        self.documents: list[Document] = []
        self.current_doc = -1
        self.frame_index = 0
        self.selection: list[int] = []
        self.undo_stack: list[tuple] = []
        self._ignore_table = False
        self._ignore_tree = False
        self._fragment_gesture = None
        self._user_style_presets = self._read_user_style_presets()
        self._build_ui()
        self.playback = QTimer(self)
        self.playback.timeout.connect(self._step_next)
        self.statusBar().showMessage('Open a calculation input/output file or a structure.')
        self.vtk.Initialize()
        self.axes_widget = vtkOrientationMarkerWidget()
        self.axes_widget.SetInteractor(self.vtk.GetRenderWindow().GetInteractor())
        self.axes_widget.SetViewport(0.015, 0.015, 0.225, 0.225)
        self.vtk.GetRenderWindow().Render()
        for filename in initial_files:
            self.open_path(filename)

    def _action(self, toolbar, title, handler, shortcut=None):
        act = QAction(title, self)
        act.triggered.connect(handler)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        toolbar.addAction(act)
        return act

    def _build_ui(self):
        toolbar = QToolBar('File and view')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self._action(toolbar, 'Open…', self.open_dialog, 'Ctrl+O')
        self._action(toolbar, 'Export structure…', self.export_dialog, 'Ctrl+Shift+S')
        self._action(toolbar, 'Save PNG…', self.save_png, 'Ctrl+S')
        self._action(toolbar, 'Undo edit', self.undo_edit, 'Ctrl+Z')
        self.invert_action = QAction('Invert atom selection', self)
        self.invert_action.setShortcut(QKeySequence('Ctrl+I'))
        self.invert_action.triggered.connect(self.invert_selection)
        self.addAction(self.invert_action)
        self.delete_action = QAction('Delete selected atoms', self)
        self.delete_action.setShortcut(QKeySequence('Delete'))
        self.delete_action.triggered.connect(self._delete_shortcut)
        self.addAction(self.delete_action)
        self._action(toolbar, 'Toggle selected bonds', self.toggle_bonds, 'Ctrl+B')
        self._action(toolbar, 'Select fragment', self.select_connected_fragment, 'Ctrl+G')
        self._action(toolbar, 'Energy curve', self.show_energy_curve)
        toolbar.addSeparator()
        self._action(toolbar, 'Fit', lambda: self.reset_camera())
        self._action(toolbar, 'Isometry', self.isometric_view)
        self.projection_combo = QComboBox()
        self.projection_combo.addItems(['Isometry', 'Perspective'])
        self.projection_combo.setToolTip('Isometry: orthographic XYZ isometric view; Perspective: perspective projection')
        self.projection_combo.currentTextChanged.connect(self.set_projection)
        toolbar.addWidget(self.projection_combo)
        self._action(toolbar, 'Front', lambda: self.align_camera('front'))
        self._action(toolbar, 'Top', lambda: self.align_camera('top'))
        self._action(toolbar, 'Side', lambda: self.align_camera('side'))
        toolbar.addSeparator()
        self._action(toolbar, 'Help', self.help_dialog)

        root = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(root)

        # All settings live in a single tabbed sidebar; the 3D canvas remains wide.
        sidebar_tabs = QTabWidget()
        self.sidebar_tabs = sidebar_tabs
        sidebar_tabs.setDocumentMode(True)
        sidebar_tabs.setMinimumWidth(295)
        sidebar_tabs.setMaximumWidth(475)
        sidebar_tabs.tabBar().setUsesScrollButtons(True)
        # Left: Chemcraft-inspired data/frame hierarchy.
        files_page = QWidget()
        left = QVBoxLayout(files_page)
        left.setContentsMargins(8, 8, 8, 8)
        left.addWidget(QLabel('<b>Files and calculation steps</b>'))
        self.files_tree = QTreeWidget()
        self.files_tree.setHeaderHidden(True)
        self.files_tree.currentItemChanged.connect(self._tree_current_changed)
        left.addWidget(self.files_tree, 1)
        left.addWidget(QLabel('Frame'))
        control = QHBoxLayout()
        self.prev_btn = QPushButton('◀')
        self.prev_btn.clicked.connect(self._step_previous)
        control.addWidget(self.prev_btn)
        self.frame_spin = QSpinBox()
        self.frame_spin.setMinimum(1)
        self.frame_spin.setMaximum(1)
        self.frame_spin.valueChanged.connect(lambda n: self.change_frame(n - 1))
        control.addWidget(self.frame_spin, 1)
        self.next_btn = QPushButton('▶')
        self.next_btn.clicked.connect(self._step_next)
        control.addWidget(self.next_btn)
        self.play_btn = QPushButton('Play')
        self.play_btn.clicked.connect(self.toggle_play)
        control.addWidget(self.play_btn)
        left.addLayout(control)
        fps_line = QHBoxLayout()
        fps_line.addWidget(QLabel('FPS'))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(1, 30)
        self.fps_spin.setValue(6)
        self.fps_spin.valueChanged.connect(self._update_play_rate)
        fps_line.addWidget(self.fps_spin)
        self.frame_count_label = QLabel('0 frames')
        fps_line.addWidget(self.frame_count_label, 1)
        left.addLayout(fps_line)
        sidebar_tabs.addTab(files_page, 'Files')
        root.addWidget(sidebar_tabs)

        # Centre: embedded native 3D VTK canvas + data inspector.
        centre = QSplitter(Qt.Orientation.Vertical)
        self.vtk = InteractiveVTKView()
        self.scene = vtkRenderer()
        self.vtk.GetRenderWindow().AddRenderer(self.scene)
        self.renderer = MoleculeRenderer(self.scene)
        self.vtk.GetRenderWindow().GetInteractor().SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.vtk.scene_renderer = self.scene
        self.vtk.atomClick.connect(self._pick_from_canvas)
        self.vtk.clearSelectionClick.connect(self._right_click_clear)
        self.vtk.fragmentGestureBegin.connect(self._fragment_begin)
        self.vtk.fragmentGestureMove.connect(self._fragment_move)
        self.vtk.fragmentGestureEnd.connect(self._fragment_end)
        centre.addWidget(self.vtk)

        self.tabs = QTabWidget()
        self.atom_table = QTableWidget(0, 4)
        self.atom_table.setHorizontalHeaderLabels(['Atom', 'X (Å)', 'Y (Å)', 'Z (Å)'])
        self.atom_table.horizontalHeader().setStretchLastSection(True)
        self.atom_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.atom_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.atom_table.itemChanged.connect(self._coordinate_edited)
        self.atom_table.itemSelectionChanged.connect(self._table_selected)
        self.tabs.addTab(self.atom_table, 'Coordinates (editable)')
        self.source_view = QPlainTextEdit()
        self.source_view.setReadOnly(True)
        self.tabs.addTab(self.source_view, 'Input / output text')
        self.info_view = QPlainTextEdit()
        self.info_view.setReadOnly(True)
        self.tabs.addTab(self.info_view, 'Results / info')
        lower_panel = QWidget()
        lower_layout = QVBoxLayout(lower_panel)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(4)
        lower_layout.addWidget(self.tabs, 1)
        self.summary_label = QLabel('Formula: - | Electrons: - | Short contacts: -')
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        self.summary_label.setContentsMargins(8, 4, 8, 5)
        self.summary_label.setToolTip('Electron count uses total charge when known; otherwise assumes neutral. Short contacts use the periodic minimum image.')
        lower_layout.addWidget(self.summary_label)
        centre.addWidget(lower_panel)
        centre.setSizes([630, 220])
        root.addWidget(centre)

        def control_page(title):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            body = QWidget()
            layout = QVBoxLayout(body)
            layout.setContentsMargins(10, 12, 10, 10)
            layout.setSpacing(10)
            scroll.setWidget(body)
            sidebar_tabs.addTab(scroll, title)
            return layout

        display_outer = control_page('Style')
        group = QGroupBox('3D drawing')
        form = QFormLayout(group)
        self._custom_style_state = snapshot(self.renderer.options)
        self.preset_combo = QComboBox()
        self.preset_combo.setToolTip('Choose a complete appearance profile. Structure data and bond cutoffs are unchanged.')
        self.preset_combo.addItem('Custom (manual)', CUSTOM_KEY)
        for name in BUILTIN_PRESETS:
            self.preset_combo.addItem(name, name)
        for name in self._user_style_presets:
            self.preset_combo.addItem(f'My style: {name}', name)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData('Classic ball and stick'))
        self.preset_combo.currentIndexChanged.connect(self._choose_style_preset)
        form.addRow('Preset', self.preset_combo)
        save_style = QPushButton('Save current appearance as preset…')
        save_style.clicked.connect(self._save_style_preset)
        form.addRow(save_style)
        form.addRow(QLabel('Presets change appearance only; coordinates, bond\n'
                               'cutoff, labels and cell settings stay unchanged.'))
        self.style_combo = QComboBox()
        self.style_combo.addItems(['Ball and stick', 'Space filling', 'Sticks', 'Wireframe'])
        self.style_combo.currentTextChanged.connect(lambda s: self._set_option('style', s))
        form.addRow('Style', self.style_combo)
        self.atom_slider = QSlider(Qt.Orientation.Horizontal)
        self.atom_slider.setRange(20, 180)
        self.atom_slider.setValue(60)
        self.atom_slider.valueChanged.connect(lambda v: self._set_option('atom_scale', v / 100))
        form.addRow('Atom size', self.atom_slider)
        self.bond_slider = QSlider(Qt.Orientation.Horizontal)
        self.bond_slider.setRange(3, 35)
        self.bond_slider.setValue(11)
        self.bond_slider.valueChanged.connect(lambda v: self._set_option('bond_scale', v / 100))
        form.addRow('Bond thickness', self.bond_slider)
        self.atom_palette_combo = QComboBox()
        self.atom_palette_combo.addItems(ATOM_PALETTES)
        self.atom_palette_combo.currentTextChanged.connect(
            lambda val: self._set_option('atom_palette', val))
        form.addRow('Atom colours', self.atom_palette_combo)
        self.bond_palette_combo = QComboBox()
        self.bond_palette_combo.addItems(BOND_PALETTES)
        self.bond_palette_combo.currentTextChanged.connect(
            lambda val: self._set_option('bond_palette', val))
        form.addRow('Bond colours', self.bond_palette_combo)
        self.finish_combo = QComboBox()
        self.finish_combo.addItems(SURFACE_FINISHES)
        self.finish_combo.currentTextChanged.connect(
            lambda val: self._set_option('surface_finish', val))
        form.addRow('Lighting', self.finish_combo)
        self.cutoff_slider = QSlider(Qt.Orientation.Horizontal)
        self.cutoff_slider.setRange(100, 160)
        self.cutoff_slider.setValue(118)
        self.cutoff_slider.valueChanged.connect(lambda v: self._set_option('bond_cutoff', v / 100))
        form.addRow('Bond cutoff ×', self.cutoff_slider)
        self.bond_check = QCheckBox('Display bonds')
        self.bond_check.setChecked(True)
        self.bond_check.toggled.connect(lambda v: self._set_option('bonds', v))
        form.addRow(self.bond_check)
        self.hbond_check = QCheckBox('Show hydrogen bonds (dashed)')
        self.hbond_check.setChecked(False)
        self.hbond_check.toggled.connect(lambda v: self._set_option('hydrogen_bonds', v))
        form.addRow(self.hbond_check)
        form.addRow(QLabel('Geometric N/O/F-H...N/O/F candidates only;\nnot part of the covalent fragment graph.'))
        self.cell_check = QCheckBox('Show unit cell')
        self.cell_check.setChecked(True)
        self.cell_check.toggled.connect(lambda v: self._set_option('unit_cell', v))
        form.addRow(self.cell_check)
        self.element_combo = QComboBox()
        form.addRow('Element', self.element_combo)
        self.element_color_btn = QPushButton('Edit element colour…')
        self.element_color_btn.clicked.connect(self.pick_element_colour)
        form.addRow(self.element_color_btn)
        self.bg_btn = QPushButton('Background colour…')
        self.bg_btn.clicked.connect(self.pick_background)
        form.addRow(self.bg_btn)
        dark_btn = QPushButton('Dark background')
        dark_btn.clicked.connect(lambda: self._set_option('background', '#131824'))
        form.addRow(dark_btn)
        light_btn = QPushButton('Light background')
        light_btn.clicked.connect(lambda: self._set_option('background', '#F7F8FA'))
        form.addRow(light_btn)
        display_outer.addWidget(group)
        display_outer.addStretch(1)

        axes_outer = control_page('Axes')
        axis_group = QGroupBox('Coordinate axes')
        axis_form = QFormLayout(axis_group)
        self.axes_position_combo = QComboBox()
        self.axes_position_combo.addItem('Hidden', 'Off')
        self.axes_position_combo.addItem('Bottom-left (VESTA style)', 'Corner')
        self.axes_position_combo.addItem('World origin (0, 0, 0)', 'Origin')
        self.axes_position_combo.setCurrentIndex(1)
        self.axes_position_combo.currentIndexChanged.connect(
            lambda _: self._set_option('axes_position', self.axes_position_combo.currentData()))
        axis_form.addRow('Position', self.axes_position_combo)
        self.axes_basis_combo = QComboBox()
        self.axes_basis_combo.addItem('XYZ (Cartesian)', 'XYZ')
        self.axes_basis_combo.addItem('abc (cell vectors)', 'abc')
        self.axes_basis_combo.currentIndexChanged.connect(
            lambda _: self._set_option('axes_basis', self.axes_basis_combo.currentData()))
        axis_form.addRow('Axes type', self.axes_basis_combo)
        self.axes_length_spin = QDoubleSpinBox()
        self.axes_length_spin.setRange(.1, 1000.)
        self.axes_length_spin.setDecimals(2)
        self.axes_length_spin.setValue(2.5)
        self.axes_length_spin.setSingleStep(.5)
        self.axes_length_spin.valueChanged.connect(lambda v: self._set_option('axes_length', v))
        axis_form.addRow('XYZ length (Å)', self.axes_length_spin)
        axis_form.addRow(QLabel('abc uses true lattice vectors at the origin.\n'
                                'Bottom-left arrows retain directions, not lengths.'))
        axes_outer.addWidget(axis_group)
        axes_outer.addStretch(1)

        labels_outer = control_page('Labels')
        labels_group = QGroupBox('Atom labels')
        labels_form = QFormLayout(labels_group)
        self.label_combo = QComboBox()
        self.label_combo.addItems(['None', 'Element', 'Index (1..N)',
                                   'Element + index (global)', 'VESTA (POSCAR groups)'])
        self.label_combo.currentTextChanged.connect(lambda v: self._set_option('labels', v))
        labels_form.addRow('Atom labels', self.label_combo)
        self.label_font_combo = QComboBox()
        self.label_font_combo.addItems(['Arial', 'Courier', 'Times'])
        self.label_font_combo.currentTextChanged.connect(self._set_standard_label_font)
        labels_form.addRow('Label font', self.label_font_combo)
        self.custom_font_btn = QPushButton('Choose TTF/OTF font file…')
        self.custom_font_btn.clicked.connect(self._select_label_font_file)
        labels_form.addRow(self.custom_font_btn)
        self.label_size_spin = QSpinBox()
        self.label_size_spin.setRange(8, 72)
        self.label_size_spin.setValue(15)
        self.label_size_spin.valueChanged.connect(lambda n: self._set_option('label_font_size', n))
        labels_form.addRow('Label size (pt)', self.label_size_spin)
        self.label_bold_check = QCheckBox('Bold text')
        self.label_bold_check.setChecked(True)
        self.label_bold_check.toggled.connect(lambda v: self._set_option('label_bold', v))
        labels_form.addRow(self.label_bold_check)
        self.label_color_btn = QPushButton('Label text colour…')
        self.label_color_btn.clicked.connect(self.pick_label_colour)
        labels_form.addRow(self.label_color_btn)

        labels_outer.addWidget(labels_group)
        labels_outer.addStretch(1)

        field_outer = control_page('Field')
        volume_group = QGroupBox('CUBE scalar field')
        volume_form = QFormLayout(volume_group)
        self.volume_check = QCheckBox('Show isosurfaces')
        self.volume_check.setChecked(True)
        self.volume_check.toggled.connect(lambda v: self._set_option('show_volume', v))
        volume_form.addRow(self.volume_check)
        self.iso_spin = QDoubleSpinBox()
        self.iso_spin.setDecimals(4)
        self.iso_spin.setRange(.0001, 10000)
        self.iso_spin.setSingleStep(.005)
        self.iso_spin.setValue(.035)
        self.iso_spin.valueChanged.connect(lambda v: self._set_option('volume_iso', v))
        volume_form.addRow('|Isovalue|', self.iso_spin)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(65)
        self.opacity_slider.valueChanged.connect(lambda v: self._set_option('volume_opacity', v / 100))
        volume_form.addRow('Opacity', self.opacity_slider)
        field_outer.addWidget(volume_group)

        field_outer.addStretch(1)

        edit_outer = control_page('Edit')
        measurements = QGroupBox('Geometry / atom selection')
        m_layout = QVBoxLayout(measurements)
        m_layout.addWidget(QLabel('Click atoms to select; right-click clears.\n'
                                  'Ctrl+B toggles selected bonds.\n'
                                  'Ctrl+G selects complete connected fragment(s).\n'
                                  'Alt+left drag: rotate fragment in 3D.\n'
                                  'Alt+right drag: roll fragment.\n'
                                  'Alt+middle drag: move fragment in screen plane.\n'
                                  'Without Alt, mouse gestures control the camera.'))
        self.selected_label = QLabel('No atoms selected')
        self.selected_label.setWordWrap(True)
        m_layout.addWidget(self.selected_label)
        clear_btn = QPushButton('Clear selection')
        clear_btn.clicked.connect(self.clear_selection)
        m_layout.addWidget(clear_btn)
        self.invert_btn = QPushButton('Invert selection  (Ctrl+I)')
        self.invert_btn.clicked.connect(self.invert_selection)
        m_layout.addWidget(self.invert_btn)
        self.delete_btn = QPushButton('Delete selected atoms  (Delete)')
        self.delete_btn.clicked.connect(self.delete_selected_atoms)
        m_layout.addWidget(self.delete_btn)
        self.fragment_btn = QPushButton('Select connected fragment(s)  (Ctrl+G)')
        self.fragment_btn.clicked.connect(self.select_connected_fragment)
        m_layout.addWidget(self.fragment_btn)
        charge_row = QHBoxLayout()
        charge_row.addWidget(QLabel('Net charge (electron parity)'))
        self.charge_spin = QSpinBox()
        self.charge_spin.setRange(-999, 999)
        self.charge_spin.setToolTip('Used to count total electrons. Defaults to file charge, or neutral when unknown.')
        self.charge_spin.valueChanged.connect(self._set_net_charge)
        charge_row.addWidget(self.charge_spin)
        m_layout.addLayout(charge_row)
        m_layout.addWidget(QLabel('Periodic fragments are unwrapped into adjacent-cell replicas.\n'
                                  'Infinite crystal networks cannot be fully selected.\n'
                                  'Preview changes only the display; source coordinates stay fixed.'))
        self.toggle_bonds_btn = QPushButton('Toggle bonds within selection  (Ctrl+B)')
        self.toggle_bonds_btn.clicked.connect(self.toggle_bonds)
        m_layout.addWidget(self.toggle_bonds_btn)
        self.origin_btn = QPushButton('Move selected atom to (0, 0, 0)')
        self.origin_btn.clicked.connect(self.move_selected_to_origin)
        m_layout.addWidget(self.origin_btn)
        alignment_row = QHBoxLayout()
        self.align_combo = QComboBox()
        for axis in ('X', 'Y', 'Z', 'a', 'b', 'c'):
            self.align_combo.addItem(axis)
        self.align_btn = QPushButton('Align 1st → 2nd')
        self.align_btn.clicked.connect(self.align_selected_pair)
        alignment_row.addWidget(self.align_combo)
        alignment_row.addWidget(self.align_btn)
        m_layout.addLayout(alignment_row)
        m_layout.addWidget(QLabel('All axes (XYZ/abc): rotate atomic coordinates only.\n'
                                  'The lattice and camera remain unchanged.\n'
                                  'The first selected atom remains fixed.'))
        edit_outer.addWidget(measurements)
        plane_group = QGroupBox('Best-fit selection plane')
        plane_layout = QVBoxLayout(plane_group)
        self.show_plane_check = QCheckBox('Show plane for 3+ selected atoms')
        self.show_plane_check.setChecked(True)
        self.show_plane_check.toggled.connect(lambda _checked: self.refresh_scene())
        plane_layout.addWidget(self.show_plane_check)
        self.plane_images_check = QCheckBox('Use nearest periodic images')
        self.plane_images_check.setChecked(True)
        self.plane_images_check.setToolTip(
            'Fit nearest images around the first selected atom. Uncheck to use the displayed coordinates.')
        self.plane_images_check.toggled.connect(lambda _checked: self.refresh_scene())
        plane_layout.addWidget(self.plane_images_check)
        self.plane_label = QLabel('Select at least three non-collinear atoms.')
        self.plane_label.setWordWrap(True)
        self.plane_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        plane_layout.addWidget(self.plane_label)
        self.plane_zero_check = QCheckBox('Place fitted plane at z = 0')
        self.plane_zero_check.setChecked(True)
        plane_layout.addWidget(self.plane_zero_check)
        self.plane_align_btn = QPushButton('Align fitted plane to XY')
        self.plane_align_btn.setEnabled(False)
        self.plane_align_btn.clicked.connect(self.align_selected_plane)
        plane_layout.addWidget(self.plane_align_btn)
        plane_layout.addWidget(QLabel(
            'Rotate the complete structure, cell and attached grid.\n'
            'Atomic deviations from the plane are preserved. Ctrl+Z to undo.'))
        edit_outer.addWidget(plane_group)
        edit_outer.addStretch(1)

        root.setSizes([355, 1025])
        self._set_frame_controls_enabled(False)
        self.toggle_bonds_btn.setEnabled(False)
        self.fragment_btn.setEnabled(False)
        self.origin_btn.setEnabled(False)
        self.align_btn.setEnabled(False)
        self.invert_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)

    @property
    def doc(self) -> Document | None:
        return self.documents[self.current_doc] if 0 <= self.current_doc < len(self.documents) else None

    @property
    def frame(self) -> Frame | None:
        doc = self.doc
        return doc.frames[self.frame_index] if doc is not None else None

    def _set_frame_controls_enabled(self, value):
        for widget in (self.prev_btn, self.next_btn, self.play_btn, self.frame_spin):
            widget.setEnabled(value)

    def open_dialog(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, 'Open calculation or structure files', '', 'All files (*)')
        for name in filenames:
            self.open_path(name)

    def open_path(self, filename):
        try:
            new_doc = load_document(filename)
        except Exception as ex:
            QMessageBox.warning(self, 'Could not open file', f'{Path(filename).name}\n\n{ex}')
            return
        index = len(self.documents)
        self.documents.append(new_doc)
        head = QTreeWidgetItem([f'{new_doc.path.name}  ({new_doc.format_name})'])
        head.setData(0, Qt.ItemDataRole.UserRole, (index, 0))
        self.files_tree.addTopLevelItem(head)
        if len(new_doc.frames) > 1:
            for i, frame in enumerate(new_doc.frames):
                suffix = f' • {frame.energy_ev:.5f} eV' if frame.energy_ev is not None else ''
                child = QTreeWidgetItem([f'Frame {i + 1}{suffix}'])
                child.setData(0, Qt.ItemDataRole.UserRole, (index, i))
                head.addChild(child)
            head.setExpanded(index == 0)
        self.current_doc = index
        self.frame_index = 0
        self.selection.clear()
        self.change_frame(0, switch_doc=index, reset_camera=True)
        self._update_source_view()
        self.statusBar().showMessage(f'Opened {new_doc.path.name} • {len(new_doc.frames)} frame(s) • {len(new_doc.frames[0].symbols)} atoms')

    def _tree_current_changed(self, item, _previous):
        # Both a mouse click and Up/Down/Left/Right navigation change the
        # tree's current item. itemClicked only covered the first case.
        if item is None or self._ignore_tree:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            doc_index, frame_index = data
            if doc_index != self.current_doc:
                self._update_source_view(doc_index)
            self.change_frame(frame_index, switch_doc=doc_index, reset_camera=(doc_index != self.current_doc))

    def _update_source_view(self, doc_index=None):
        idx = self.current_doc if doc_index is None else doc_index
        if idx < 0:
            return
        path = self.documents[idx].path
        try:
            with path.open('rb') as f:
                raw = f.read(180_000)
                remaining = bool(f.read(1))
            # Binary ASE trajectories and similar formats aren't printable.
            if b'\x00' in raw[:4000]:
                self.source_view.setPlainText('[Binary file: text preview not available]')
            else:
                decoded = raw.decode('utf-8', errors='replace')
                self.source_view.setPlainText(decoded + ('\n\n[Text preview truncated at 180 KB]' if remaining else ''))
        except Exception as ex:
            self.source_view.setPlainText(str(ex))

    def change_frame(self, index, *, switch_doc=None, reset_camera=False):
        if switch_doc is not None:
            self.current_doc = switch_doc
        doc = self.doc
        if doc is None:
            return
        self.frame_index = max(0, min(int(index), len(doc.frames) - 1))
        self.renderer.periodic_preview = None
        # Keep keyboard navigation, playback, spinbox and mouse clicks in sync.
        head = self.files_tree.topLevelItem(self.current_doc)
        if head is not None:
            target = (head.child(self.frame_index) if head.childCount() else head)
            if target is not None and self.files_tree.currentItem() is not target:
                self._ignore_tree = True
                try:
                    self.files_tree.setCurrentItem(target)
                finally:
                    self._ignore_tree = False
        frame = self.frame
        self.charge_spin.blockSignals(True)
        from .chemical_analysis import known_net_charge
        self.charge_spin.setValue(known_net_charge(frame) or 0)
        self.charge_spin.blockSignals(False)
        self.selection = [i for i in self.selection if i < len(frame.symbols)]
        self.frame_spin.blockSignals(True)
        self.frame_spin.setRange(1, len(doc.frames))
        self.frame_spin.setValue(self.frame_index + 1)
        self.frame_spin.blockSignals(False)
        self.frame_count_label.setText(f'{self.frame_index + 1} / {len(doc.frames)}')
        previously = self.element_combo.currentText()
        self.element_combo.blockSignals(True)
        self.element_combo.clear()
        self.element_combo.addItems(sorted(set(frame.symbols)))
        if frame.symbols:
            self.element_combo.setCurrentText(previously if previously in frame.symbols else frame.symbols[0])
        self.element_combo.blockSignals(False)
        from .core import valid_lattice
        has_cell = valid_lattice(frame)
        self.axes_basis_combo.model().item(1).setEnabled(has_cell)
        if not has_cell and self.axes_basis_combo.currentData() == 'abc':
            self.axes_basis_combo.setCurrentIndex(0)
        self._set_frame_controls_enabled(len(doc.frames) > 1)
        self.play_btn.setEnabled(len(doc.frames) > 1)
        self.refresh_scene(reset_camera=reset_camera)
        self._refresh_coordinates()
        self._sync_selection_to_table()
        self._refresh_info()

    def _refresh_coordinates(self):
        """Rebuild the table from the active Frame; never from source-file text.

        Blocking both itemChanged and selectionChanged prevents a structural
        transform from feeding its own formatted values back into the model.
        """
        frame = self.frame
        self._ignore_table = True
        self.atom_table.setUpdatesEnabled(False)
        try:
            with QSignalBlocker(self.atom_table):
                if frame is None:
                    self.atom_table.setRowCount(0)
                    return
                from .core import coordinate_table_rows
                rows = coordinate_table_rows(frame)
                self.atom_table.setRowCount(len(rows))
                for i, row in enumerate(rows):
                    for j, value in enumerate(row):
                        item = self.atom_table.item(i, j)
                        if item is None:
                            item = QTableWidgetItem()
                            self.atom_table.setItem(i, j, item)
                        item.setText(value)
                        if j == 0:
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        finally:
            self._ignore_table = False
            self.atom_table.setUpdatesEnabled(True)
            self.atom_table.viewport().update()

    def _refresh_after_geometry_edit(self):
        """Publish new coordinates, selection, rendering and document details."""
        if hasattr(self, "renderer"):
            self.renderer.periodic_preview = None
        self._refresh_coordinates()
        self._sync_selection_to_table()
        self.tabs.setCurrentWidget(self.atom_table)
        if self.selection:
            first = self.atom_table.item(self.selection[0], 0)
            if first is not None:
                self.atom_table.scrollToItem(first)
        self.refresh_scene()
        self._refresh_info()

    def _set_net_charge(self, new_charge):
        """Update frame-level total charge used by electron parity diagnostics."""
        if self.frame is None:
            return
        self.frame.info['charge_override'] = int(new_charge)
        self._refresh_info()

    def _refresh_info(self):
        doc, frame = self.doc, self.frame
        if doc is None:
            return
        lines = [f'File: {doc.path}', f'Reader: {doc.format_name}',
                 f'Frame: {self.frame_index + 1} of {len(doc.frames)}',
                 f'Atoms: {len(frame.symbols)}', f'Periodic flags: {frame.pbc}']
        if frame.energy_ev is not None:
            lines.append(f"Energy: {frame.energy_ev:.8f} eV ({frame.info.get('energy_source', 'reader result')})")
        if abs(float(__import__('numpy').linalg.det(frame.cell))) > 1e-10:
            lines.append('Unit cell (Å):')
            lines.extend('  ' + '  '.join(f'{v:12.6f}' for v in a) for a in frame.cell)
        if doc.volume is not None:
            lines.append(f'Volumetric grid: {doc.volume.data.shape}')
        alignment = frame.info.get('plane_alignment')
        if alignment is not None:
            lines.append('\nLast plane alignment: r_new = r_old @ R.T + translation')
            lines.extend('  ' + '  '.join(f'{v: .9f}' for v in row)
                         for row in alignment['rotation'])
            lines.append('Translation (Å): ' + ', '.join(f'{v:.9f}' for v in alignment['translation']))
        if doc.note:
            lines.append('\nReader note: ' + doc.note)
        if doc.modified:
            lines.append('\nThis document has unsaved coordinate edits.')
        lines.append('\nInput/output parser only extracts available geometry and associated ASE energy.\nSpectra, frequency modes and MO coefficients require future analysis readers.')
        self.info_view.setPlainText('\n'.join(lines))
        system = 'Cell composition' if any(frame.pbc) else 'Formula'
        self.summary_label.setText(
            f'{system}: {molecular_formula(frame.symbols)}    |    '
            f'Electrons: {electron_parity(frame)}    |    {short_contact_summary(frame)}')

    def refresh_scene(self, reset_camera=False):
        self._update_fitted_plane()
        if self.frame is None:
            return
        self.renderer.options.show_volume = bool(self.volume_check.isChecked())
        self.renderer.selected = list(self.selection)
        self.renderer.set_scene(self.frame, self.doc.volume, reset_camera=False)
        if reset_camera:
            self._set_projection_mode('Isometry')
        self._sync_corner_axes()
        self.vtk.GetRenderWindow().Render()
        self._refresh_measurement()

    def _update_fitted_plane(self):
        """Refit after every selection or geometry change, without editing atoms."""
        self._plane_fit = None
        frame = self.frame
        self.plane_images_check.setEnabled(frame is not None and periodic_basis(frame) is not None)
        text = 'Select at least three non-collinear atoms.'
        if frame is not None and len(self.selection) >= 3:
            try:
                self._plane_fit = fit_selection_plane(
                    frame, self.selection, nearest_images=self.plane_images_check.isChecked())
                plane = self._plane_fit
                nx, ny, nz = plane.normal
                offset = -float(plane.normal @ plane.center)
                text = (f'{len(plane.indices)} atoms; least-squares plane\n'
                        f'{nx:+.5f} x {ny:+.5f} y {nz:+.5f} z {offset:+.5f} = 0\n'
                        f'RMS distance: {plane.rms:.5f} Å; max: {plane.max_distance:.5f} Å')
            except ValueError as exc:
                text = str(exc)
        self.plane_label.setText(text)
        self.plane_align_btn.setEnabled(self._plane_fit is not None)
        self.renderer.fitted_plane = self._plane_fit if self.show_plane_check.isChecked() else None

    def align_selected_plane(self):
        self._update_fitted_plane()
        if self._plane_fit is None:
            return
        self._record_undo()
        align_plane_to_xy(self.frame, self._plane_fit,
                          place_at_zero=self.plane_zero_check.isChecked(), volume=self.doc.volume)
        self._fragment_gesture = None
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(
            'Fitted plane aligned to XY; complete structure and cell rotated. Ctrl+Z to undo.', 6000)

    def _sync_corner_axes(self):
        """Switch between camera-following overlay and true world-origin axes."""
        if self.frame is None:
            return
        enabled = self.renderer.options.axes_position == 'Corner'
        if self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        if enabled:
            marker = self.renderer.make_corner_marker(self.frame)
            self.axes_widget.SetOrientationMarker(marker)
            self.axes_widget.SetEnabled(1)
            self.axes_widget.InteractiveOff()

    def _set_standard_label_font(self, text):
        self.renderer.options.label_font_file = ''
        self.custom_font_btn.setText('Choose TTF/OTF font file…')
        self._set_option('label_font', text)

    def _select_label_font_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select font file (not bundled into EXE)', '',
            'Font files (*.ttf *.otf);;All files (*)')
        if path:
            self.renderer.options.label_font_file = path
            self.custom_font_btn.setText('Font file: ' + Path(path).name)
            self.refresh_scene()

    def pick_label_colour(self):
        picked = QColorDialog.getColor(QColor(self.renderer.options.label_color),
                                       self, 'Atom label text colour')
        if picked.isValid():
            self._set_option('label_color', picked.name())

    @staticmethod
    def _style_storage_path():
        base = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation)
        return Path(base) / 'style_presets.json'

    def _read_user_style_presets(self):
        return read_style_presets(self._style_storage_path())

    def _sync_style_widgets(self):
        opts = self.renderer.options
        controls = [self.style_combo, self.atom_slider, self.bond_slider,
                    self.atom_palette_combo, self.bond_palette_combo,
                    self.finish_combo, self.bond_check]
        blockers = [QSignalBlocker(widget) for widget in controls]
        try:
            self.style_combo.setCurrentText(opts.style)
            self.atom_slider.setValue(round(opts.atom_scale * 100))
            self.bond_slider.setValue(round(opts.bond_scale * 100))
            self.atom_palette_combo.setCurrentText(opts.atom_palette)
            self.bond_palette_combo.setCurrentText(opts.bond_palette)
            self.finish_combo.setCurrentText(opts.surface_finish)
            self.bond_check.setChecked(opts.bonds)
        finally:
            del blockers
        self.bg_btn.setText('Background colour… (' + opts.background + ')')

    def _choose_style_preset(self, _index):
        key = self.preset_combo.currentData()
        if key == CUSTOM_KEY:
            values = self._custom_style_state
        elif key in BUILTIN_PRESETS:
            values = BUILTIN_PRESETS[key]
        else:
            values = self._user_style_presets.get(key)
        if values is None:
            return
        apply_preset(self.renderer.options, values)
        self._sync_style_widgets()
        if self.frame is not None:
            self.refresh_scene()

    def _save_style_preset(self):
        name, ok = QInputDialog.getText(self, 'Save display preset', 'Preset name:')
        name = name.strip()
        if not ok or not name:
            return
        if name == CUSTOM_KEY or name in BUILTIN_PRESETS:
            QMessageBox.warning(self, 'Reserved name', 'Please choose a different preset name.')
            return
        if name in self._user_style_presets:
            result = QMessageBox.question(self, 'Overwrite preset',
                                          f'Replace saved preset "{name}"?')
            if result != QMessageBox.StandardButton.Yes:
                return
        self._user_style_presets[name] = snapshot(self.renderer.options)
        try:
            path = self._style_storage_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._user_style_presets, indent=2), encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, 'Save failed', str(exc))
            return
        index = self.preset_combo.findData(name)
        if index < 0:
            self.preset_combo.addItem(f'My style: {name}', name)
            index = self.preset_combo.findData(name)
        self.preset_combo.setCurrentIndex(index)
        self.statusBar().showMessage(f'Saved display preset: {name}', 3500)

    def _set_option(self, option, value):
        setattr(self.renderer.options, option, value)
        if option in STYLE_KEYS:
            self._custom_style_state = snapshot(self.renderer.options)
            with QSignalBlocker(self.preset_combo):
                self.preset_combo.setCurrentIndex(self.preset_combo.findData(CUSTOM_KEY))
            if option == 'background':
                self.bg_btn.setText('Background colour… (' + value + ')')
        if option == 'bond_cutoff':
            self.renderer.periodic_preview = None
        if self.frame is not None:
            self.refresh_scene()

    def pick_element_colour(self):
        symbol = self.element_combo.currentText()
        if not symbol:
            return
        colors = self.renderer.options.element_colors
        picked = QColorDialog.getColor(QColor(colors.get(symbol, colour(symbol))),
                                       self, f'{symbol} colour')
        if picked.isValid():
            self._set_option('element_colors', {**colors, symbol: picked.name()})

    def pick_background(self):
        current = QColor(self.renderer.options.background)
        picked = QColorDialog.getColor(current, self, 'Background colour')
        if picked.isValid():
            self._set_option('background', picked.name())

    def _pick_from_canvas(self, x: float, y: float):
        """Handle a *native Qt* click. Convert logical pixels for high-DPI VTK."""
        if self.frame is None:
            return
        rw = self.vtk.GetRenderWindow()
        vw, vh = rw.GetSize()
        try:
            dx, dy = vtk_display_from_qt(
                x, y, self.vtk.width(), self.vtk.height(), vw, vh)
        except ValueError:
            return
        picked = self.renderer.pick_index(dx, dy, vw, vh)
        if picked is None:
            self.statusBar().showMessage('No atom at cursor (drag to rotate; click directly on an atom).', 3000)
            return
        self.renderer.periodic_preview = None
        if picked in self.selection:
            self.selection.remove(picked)
        else:
            self.selection.append(picked)
        self._sync_selection_to_table()
        self.refresh_scene()
        self.statusBar().showMessage(f'Selected atom {picked + 1}: {self.frame.symbols[picked]}', 2500)

    def _sync_selection_to_table(self):
        if self.frame is None:
            return
        self._ignore_table = True
        self.atom_table.blockSignals(True)
        self.atom_table.clearSelection()
        if len(self.selection) == 1:
            self.atom_table.selectRow(self.selection[0])
        elif len(self.selection) > 1:
            from PySide6.QtCore import QItemSelectionModel
            model = self.atom_table.selectionModel()
            for idx in self.selection:
                index = self.atom_table.model().index(idx, 0)
                model.select(index, QItemSelectionModel.SelectionFlag.Select |
                             QItemSelectionModel.SelectionFlag.Rows)
        self.atom_table.blockSignals(False)
        self._ignore_table = False

    def _table_selected(self):
        if self._ignore_table or self.frame is None:
            return
        rows = [x.row() for x in self.atom_table.selectionModel().selectedRows()]
        # QTableWidget selection is unordered; retain prior click order where
        # possible so the first->second alignment direction stays predictable.
        self.selection = [i for i in self.selection if i in rows] + [i for i in rows if i not in self.selection]
        self.renderer.periodic_preview = None
        self.refresh_scene()

    def _refresh_measurement(self):
        frame = self.frame
        n = len(self.selection)
        self.toggle_bonds_btn.setEnabled(frame is not None and n >= 2)
        self.fragment_btn.setEnabled(frame is not None and n > 0)
        self.origin_btn.setEnabled(frame is not None and n == 1)
        self.align_btn.setEnabled(frame is not None and n == 2)
        self.invert_btn.setEnabled(frame is not None and bool(frame.symbols))
        self.delete_btn.setEnabled(frame is not None and n > 0)
        if frame is None or not self.selection:
            self.selected_label.setText('No atoms selected')
            return
        atoms = [f'{frame.symbols[i]}{i + 1}' for i in self.selection]
        label = f'{n} selected: ' + ' — '.join(atoms[:12])
        if n > 12:
            label += f' … (+{n - 12} more)'
        if 2 <= n <= 4:
            try:
                quantity, value = measure(frame, self.selection)
                units = 'Å' if quantity == 'distance' else '°'
                label += f'\n{quantity}: {value:.4f} {units}'
            except (ValueError, IndexError):
                pass
        self.selected_label.setText(label)

    def _right_click_clear(self):
        if self.selection:
            self.clear_selection()
            self.statusBar().showMessage('Atom selection cleared', 2500)

    def clear_selection(self):
        self.selection.clear()
        self.renderer.periodic_preview = None
        self._ignore_table = True
        self.atom_table.clearSelection()
        self._ignore_table = False
        if self.frame is not None:
            self.refresh_scene()

    def invert_selection(self):
        if self.frame is None:
            return
        selected = set(self.selection)
        self.selection = [i for i in range(len(self.frame.symbols)) if i not in selected]
        self.renderer.periodic_preview = None
        self._sync_selection_to_table()
        self.refresh_scene()

    def _delete_shortcut(self):
        """Keep Delete available to text and numeric editors while typing."""
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return
        self.delete_selected_atoms()

    def delete_selected_atoms(self):
        if self.frame is None or not self.selection:
            return
        self._record_undo()
        count = remove_atoms(self.frame, self.selection)
        had_volume = self.doc.volume is not None
        # A field computed for the input structure no longer belongs to this model.
        self.doc.volume = None
        self.doc.modified = True
        self.selection = []
        self._fragment_gesture = None
        self.change_frame(self.frame_index)
        message = f'Deleted {count} atom(s) in the current frame. Ctrl+Z to restore.'
        if had_volume:
            message += ' The input volumetric field was detached.'
        self.statusBar().showMessage(message, 6000)

    def select_connected_fragment(self):
        """Select the connected fragment, showing periodic replicas if needed."""
        from .periodic_geometry import periodic_basis, periodic_fragment
        if self.frame is None or not self.selection:
            self.statusBar().showMessage('Select an atom before selecting its fragment.', 3500)
            return
        if periodic_basis(self.frame) is not None:
            try:
                preview = periodic_fragment(self.frame, self.selection,
                                            self.renderer.options.bond_cutoff)
            except ValueError as exc:
                self.renderer.periodic_preview = None
                QMessageBox.information(self, 'Periodic fragment', str(exc))
                return
            self.selection = preview.indices
            self.renderer.periodic_preview = preview
            self._sync_selection_to_table()
            self.refresh_scene()
            if preview.extra_tiles:
                self.scene.ResetCamera()
                self.scene.ResetCameraClippingRange()
                self.vtk.GetRenderWindow().Render()
            self.statusBar().showMessage(
                f'Selected {len(preview.indices)} connected atoms; '
                f'{len(preview.extra_tiles)} extra cell(s) shown (visualization only).', 6000)
        else:
            fragment = selected_fragments(self.frame, self.selection,
                                          self.renderer.options.bond_cutoff)
            self.selection = fragment
            self.renderer.periodic_preview = None
            self._sync_selection_to_table()
            self.refresh_scene()
            self.statusBar().showMessage(
                f'Selected {len(fragment)} atoms in connected fragment(s).', 3500)

    def _fragment_begin(self, kind, _x, _y):
        """Freeze the graph component for this gesture; never grow it mid-drag."""
        self._fragment_gesture = None
        if self.frame is None or not self.selection:
            self.statusBar().showMessage('Select an atom before Alt+dragging its fragment.', 3500)
            return
        indices = (list(self.renderer.periodic_preview.indices)
                   if getattr(self.renderer, "periodic_preview", None) is not None else
                   selected_fragments(self.frame, self.selection,
                                      self.renderer.options.bond_cutoff))
        if not indices:
            return
        import numpy as np
        pivot = np.mean(self.frame.positions[indices], axis=0)
        self._fragment_gesture = {'kind': kind, 'indices': indices,
                                  'pivot': pivot, 'edited': False}

    def _fragment_move(self, kind, dx, dy):
        state = self._fragment_gesture
        if state is None or kind != state['kind'] or (abs(dx) + abs(dy)) < 1e-10:
            return
        if not state['edited']:
            self.renderer.periodic_preview = None
            self._record_undo()
            state['edited'] = True
            self.selection = list(state['indices'])
            self._sync_selection_to_table()
        camera = self.scene.GetActiveCamera()
        if kind == 'pan':
            offset = screen_translation(camera, dx, dy, self.vtk.height(), state['pivot'])
            apply_fragment_translation(self.frame, state['indices'], offset)
            state['pivot'] += offset
        else:
            R = screen_rotation(camera, kind, dx, dy)
            apply_fragment_rotation(self.frame, state['indices'], R, state['pivot'])
        self.doc.modified = True
        self.refresh_scene()

    def _fragment_end(self, kind):
        state = self._fragment_gesture
        self._fragment_gesture = None
        if state is None or not state['edited']:
            return
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(
            f'Alt+{kind}: changed {len(state["indices"])} fragment atoms; '
            'other atoms and cell were not moved. Ctrl+Z to undo.', 5000)

    def _record_undo(self):
        frame = self.frame
        if frame is None:
            return
        volume = self.doc.volume
        volume_geometry = None if volume is None else (
            volume.origin.copy(), volume.voxel_vectors.copy())
        self.undo_stack.append((self.current_doc, self.frame_index,
                                frame.clone(), volume_geometry, list(self.selection), volume))
        self.undo_stack = self.undo_stack[-50:]

    def toggle_bonds(self):
        if self.frame is None or len(self.selection) < 2:
            self.statusBar().showMessage('Select at least two atoms to edit bonds', 3000)
            return
        self._record_undo()
        try:
            action, count = toggle_selected_bonds(
                self.frame, self.selection, self.renderer.options.bond_cutoff)
        except (ValueError, IndexError) as ex:
            self.undo_stack.pop()
            QMessageBox.warning(self, 'Bond edit failed', str(ex))
            return
        self.doc.modified = True
        self.renderer.periodic_preview = None
        self.refresh_scene()
        self._refresh_info()
        self.statusBar().showMessage(
            f'Bonds {action}: {count} internal bond(s). Changes affect visualization only.', 5000)

    def move_selected_to_origin(self):
        if self.frame is None or len(self.selection) != 1:
            return
        self._record_undo()
        displacement = move_atom_to_origin(self.frame, self.selection[0])
        if self.doc.volume is not None:
            self.doc.volume.origin += displacement
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage('Translated geometry so selected atom is at (0,0,0).', 4000)

    def align_selected_pair(self):
        if self.frame is None or len(self.selection) != 2:
            return
        axis = self.align_combo.currentText()
        if self.doc.volume is not None:
            QMessageBox.warning(self, 'Volume attached',
                'Aligning to any axis now keeps the lattice and volumetric grid fixed '
                'while rotating atoms only. This would invalidate the geometry-to-grid '
                'relationship, so alignment is disabled for files with attached volume data.')
            return
        self._record_undo()
        try:
            align_pair_to_axis(self.frame, self.selection[0], self.selection[1], axis)
        except (ValueError, IndexError) as ex:
            self.undo_stack.pop()
            QMessageBox.warning(self, 'Alignment unavailable', str(ex))
            return
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(
            f'Pair aligned to {axis}; atomic positions updated, cell and camera unchanged.', 6000)

    def _coordinate_edited(self, item):
        if self._ignore_table or item.column() == 0 or self.frame is None:
            return
        try:
            number = float(item.text())
            if not __import__('math').isfinite(number):
                raise ValueError('Not finite')
        except ValueError:
            QMessageBox.warning(self, 'Invalid coordinate', 'Use a finite number in Angstrom.')
            self._refresh_coordinates()
            return
        frame = self.frame
        self._record_undo()
        frame.positions[item.row(), item.column() - 1] = number
        self.doc.modified = True
        self._refresh_after_geometry_edit()

    def undo_edit(self):
        if not self.undo_stack:
            return
        doc_idx, frame_idx, old_frame, old_volume_geometry, old_selection, old_volume = self.undo_stack.pop()
        self.documents[doc_idx].frames[frame_idx] = old_frame
        self.documents[doc_idx].volume = old_volume
        volume = old_volume
        if volume is not None and old_volume_geometry is not None:
            volume.origin = old_volume_geometry[0]
            volume.voxel_vectors = old_volume_geometry[1]
        self.selection = old_selection
        self.change_frame(frame_idx, switch_doc=doc_idx)

    def _step_previous(self):
        self.change_frame(self.frame_index - 1)

    def _step_next(self):
        doc = self.doc
        if doc is not None:
            self.change_frame((self.frame_index + 1) % len(doc.frames))

    def _update_play_rate(self):
        if self.playback.isActive():
            self.playback.start(1000 // self.fps_spin.value())

    def toggle_play(self):
        if self.playback.isActive():
            self.playback.stop()
            self.play_btn.setText('Play')
        else:
            self.playback.start(1000 // self.fps_spin.value())
            self.play_btn.setText('Pause')

    def _set_projection_mode(self, mode):
        if self.frame is None:
            return
        if mode == 'Isometry':
            set_isometric_view(self.scene)
        else:
            cam = self.scene.GetActiveCamera()
            cam.SetParallelProjection(False)
            self.scene.ResetCamera()
            self.scene.ResetCameraClippingRange()
        self.projection_combo.blockSignals(True)
        self.projection_combo.setCurrentText(mode)
        self.projection_combo.blockSignals(False)

    def set_projection(self, mode):
        self._set_projection_mode(mode)
        if self.frame is not None:
            self.vtk.GetRenderWindow().Render()

    def isometric_view(self):
        if self.frame is None:
            return
        self._set_projection_mode('Isometry')
        self.vtk.GetRenderWindow().Render()

    def reset_camera(self):
        self.scene.ResetCamera()
        self.scene.ResetCameraClippingRange()
        self.vtk.GetRenderWindow().Render()

    def align_camera(self, name):
        if self.frame is None or not self.frame.symbols:
            return
        camera = self.scene.GetActiveCamera()
        centre = self.frame.positions.mean(axis=0)
        spread = max(2.0, float(__import__('numpy').ptp(self.frame.positions, axis=0).max()) * 3)
        if name == 'front':
            direction, up = (0, 0, 1), (0, 1, 0)
        elif name == 'top':
            direction, up = (0, -1, 0), (0, 0, 1)
        else:
            direction, up = (1, 0, 0), (0, 0, 1)
        camera.SetFocalPoint(*[float(x) for x in centre])
        camera.SetPosition(*[float(centre[i] + direction[i] * spread) for i in range(3)])
        camera.SetViewUp(*up)
        camera.SetParallelProjection(True)
        self.reset_camera()

    def show_energy_curve(self):
        doc = self.doc
        if doc is None:
            return
        available = [(i+1, f.energy_ev) for i, f in enumerate(doc.frames) if f.energy_ev is not None]
        if len(available) < 2:
            QMessageBox.information(self, 'Energy curve',
                'This reader did not expose energies for at least two frames.\n'
                'The structure trajectory can still be viewed.')
            return
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
        from matplotlib.figure import Figure
        fig = Figure(figsize=(6.5, 4.0), tight_layout=True)
        ax = fig.add_subplot(111)
        x = [p[0] for p in available]
        baseline = min(p[1] for p in available)
        y = [p[1] - baseline for p in available]
        ax.plot(x, y, '.-', linewidth=1.4, markersize=4)
        ax.set_xlabel('Structure / optimization step')
        ax.set_ylabel('Energy relative to minimum (eV)')
        ax.grid(True, alpha=.22)
        canvas = FigureCanvasQTAgg(fig)
        dialog = QDialog(self)
        dialog.setWindowTitle('Energy trajectory — ' + doc.path.name)
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(NavigationToolbar2QT(canvas, dialog))
        layout.addWidget(canvas)
        canvas.draw()
        dialog.exec()

    def save_png(self):
        if self.frame is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save rendering', 'lele.png', 'PNG image (*.png)')
        if not path:
            return
        try:
            image = vtkWindowToImageFilter()
            image.SetInput(self.vtk.GetRenderWindow())
            image.SetScale(2)
            image.ReadFrontBufferOff()
            image.Update()
            writer = vtkPNGWriter()
            writer.SetFileName(path)
            writer.SetInputConnection(image.GetOutputPort())
            writer.Write()
            self.statusBar().showMessage(f'Saved image: {path}', 5000)
        except Exception as ex:
            QMessageBox.warning(self, 'Export failed', str(ex))

    def export_dialog(self):
        if self.frame is None:
            return
        if not self.frame.symbols:
            self.statusBar().showMessage('No atoms to export. Use Ctrl+Z to restore the deleted atoms.', 5000)
            return
        targets = ['XYZ (.xyz)', 'Gaussian GJF (.gjf)', 'CIF (.cif)',
                   'POSCAR Direct (POSCAR)', 'POSCAR Cartesian (POSCAR)']
        choice, ok = QInputDialog.getItem(self, 'Structure export', 'Output format:', targets, 0, False)
        if not ok:
            return
        target = ['xyz', 'gjf', 'cif', 'poscar-direct', 'poscar-cartesian'][targets.index(choice)]
        extension = {'xyz': '.xyz', 'gjf': '.gjf', 'cif': '.cif'}.get(target, '')
        name = self.doc.path.stem + '_edited' + extension
        path, _ = QFileDialog.getSaveFileName(self, 'Export selected frame', name)
        if not path:
            return
        try:
            notices = export_frame(self.frame, path, target)
            self.statusBar().showMessage('Exported ' + path + (' | ' + '; '.join(notices) if notices else ''), 10000)
        except Exception as ex:
            QMessageBox.warning(self, 'Export failed', str(ex))

    def help_dialog(self):
        QMessageBox.information(self, APP_TITLE,
            APP_FULL_NAME + '\n\n'
            'Open files: Ctrl+O; save PNG: Ctrl+S; export structure: Ctrl+Shift+S.\n\n'
            'Drag files into the window. Left-drag: rotate; right-drag: roll clockwise/counterclockwise; mouse wheel: zoom.\n'
            'Click atoms to add/remove from selection; right-click to clear, right-drag to roll.\n'
            'Ctrl+B toggles selected internal bonds; two atoms toggle regardless of distance.\n'
            'One atom -> Move to origin; two ordered atoms -> Align to XYZ or lattice abc.\n'
            'Use Up/Down in frame tree to change frames.\n'
            'Select 2/3/4 atoms to measure distance/angle/dihedral.\n'
            'Select 3+ atoms to show a least-squares plane in Edit.\n'
            'Align plane to XY rotates all atoms and the cell; optional Z translation.\n'
            'Ctrl+I inverts selection; Delete removes selected atoms; Ctrl+Z restores them.\n'
            'Choose hidden/corner/world-origin axes and XYZ or periodic abc.\n'
            'Labels are centred on their atoms with global or POSCAR-group numbering.\n'
            'Double-click X/Y/Z cells to edit atomic coordinates; Ctrl+Z to undo.\n\n'
            'This version does not calculate chemical bonds, wavefunctions, spectra, or DFT results.\n'
            'The default bonds are covalent-radius estimates; manual bond overrides are visualization-only and are not saved in XYZ/POSCAR/CIF.')

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file():
                    self.open_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event):
        self.playback.stop()
        if self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        self.vtk.GetRenderWindow().Finalize()
        self.vtk.TerminateApp()
        super().closeEvent(event)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    app = QApplication([sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_FULL_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle('Fusion')
    window = LELEWindow(argv)
    window.show()
    return app.exec()
