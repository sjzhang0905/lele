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
from typing import TYPE_CHECKING

from . import APP_NAME, APP_FULL_NAME, APP_TITLE, __version__
from .settings import read_style_presets

from PySide6.QtCore import Qt, QTimer, QSignalBlocker, QStandardPaths, QEvent, QElapsedTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QLabel, QFileDialog,
    QComboBox, QSlider, QCheckBox, QDoubleSpinBox, QPushButton, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QMessageBox, QScrollArea, QPlainTextEdit, QAbstractItemView, QColorDialog,
    QInputDialog, QDialog, QLineEdit, QTextEdit, QAbstractSpinBox, QStackedWidget, QHeaderView, QProgressDialog, QMenu,
)
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QColor, QIcon, QPalette

from .render_options import RenderOptions
from .backend_loader import get_backend_loader
from .atom_panel import AtomPanel
from .atom_appearance import DEFAULT_APPEARANCE, LABEL_MODES, appearance
from .numeric_controls import IsovalueSpinBox
from .vibration_controls import VibrationControls
from .style_presets import (BUILTIN_PRESETS, CUSTOM_KEY, STYLE_KEYS,
                            ATOM_PALETTES, BOND_PALETTES, SURFACE_FINISHES,
                            apply_preset, snapshot, validate_preset)
from .welcome import WelcomePage
from .restored_actions import RestoredActions
from .trajectory_actions import TrajectoryAnalysisActions
from .document_view import DocumentViewActions

if TYPE_CHECKING:
    from .core import Document, Frame

ICON_PATH = Path(__file__).with_name('assets') / 'lele.ico'


class LELEWindow(RestoredActions, TrajectoryAnalysisActions, DocumentViewActions, QMainWindow):
    def __init__(self, initial_files=()):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowIcon(QIcon(str(ICON_PATH)))
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
        self._closing = False
        self._backend_state = 'waiting'
        self._backend_loader = None
        self._pending_open_paths = list(initial_files)
        self._startup_painted = False
        self._backend_start_timer = QTimer(self)
        self._backend_start_timer.setSingleShot(True)
        self._backend_start_timer.timeout.connect(self._start_backend_loading)
        # A show event or a zero-delay timer alone can run before the first
        # paint. Start imports on the next event turn after the welcome header.
        self.welcome_page.title_label.installEventFilter(self)
        self.statusBar().showMessage('Open a calculation input/output file or a structure.')

    def eventFilter(self, watched, event):
        if (watched is self.welcome_page.title_label
                and event.type() == QEvent.Type.Paint):
            watched.removeEventFilter(self)
            self._startup_painted = True
            self._backend_start_timer.start(0)
        return super().eventFilter(watched, event)

    def _start_backend_loading(self):
        if self._closing or self._backend_state in ('loading', 'ready'):
            return
        self._backend_state = 'loading'
        self.statusBar().showMessage('Loading components… You can choose a file while loading.')
        loader = get_backend_loader()
        if self._backend_loader is not loader:
            self._backend_loader = loader
            loader.finished.connect(self._backend_loaded, Qt.ConnectionType.QueuedConnection)
        if loader.loaded:
            self._backend_loaded()
        else:
            loader.ensure_started()

    def _backend_loaded(self):
        if self._closing or self._backend_state == 'ready':
            return
        error = self._backend_loader.error
        if not error:
            try:
                # Cached imports are now cheap; all QWidget/VTK construction
                # happens here, on the GUI thread.
                self._ensure_3d_view()
            except Exception:
                error = traceback.format_exc()
        if error:
            self._backend_state = 'failed'
            self.statusBar().showMessage('Loading failed. Open a file to retry.')
            if self._pending_open_paths:
                self._pending_open_paths.clear()
                QMessageBox.warning(self, 'Could not load components', error)
            return
        self._backend_state = 'ready'
        self.statusBar().showMessage('Ready. Open a calculation input/output file or a structure.')
        pending, self._pending_open_paths = self._pending_open_paths, []
        for filename in pending:
            if self._closing:
                break
            self._open_path_now(filename)

    def _action(self, menu, title, handler, shortcut=None):
        act = QAction(title, self)
        act.triggered.connect(handler)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        menu.addAction(act)
        return act

    def _build_ui(self):
        # The welcome page and settings do not need scientific libraries or VTK.
        self.render_options = RenderOptions()
        self._analysis_windows = []
        self.vtk = self.scene = self.renderer = self.axes_widget = None
        self._vtk_initialized = False
        self._plane_fit = None
        self._plane_context = None
        self._active_vibration = None
        self._vibration_reference = None
        self._vibration_references = {}
        self._gif_exporting = False
        self._gif_progress = None
        self._gif_close_requested = False
        self._vibration_phase = 0.
        self._frame_tree_items = {}
        self._vibration_tree_items = {}
        self.vibration_timer = QTimer(self)
        self.vibration_timer.setInterval(33)
        self.vibration_timer.timeout.connect(self._advance_vibration)
        self._vibration_clock = QElapsedTimer()
        self.file_menu = self.menuBar().addMenu('&File')
        self._action(self.file_menu, 'Open…', self.open_dialog, 'Ctrl+O')
        self._action(self.file_menu, 'Export structure…', self.export_dialog, 'Ctrl+Shift+S')
        self._action(self.file_menu, 'Save PNG…', self.save_png, 'Ctrl+S')
        self.gif_action = self._action(self.file_menu, 'Export animation GIF…', self.save_gif)
        self.gif_action.setEnabled(False)

        self.edit_menu = self.menuBar().addMenu('&Edit')
        self._action(self.edit_menu, 'Undo edit', self.undo_edit, 'Ctrl+Z')
        self.edit_menu.addSeparator()
        self._action(self.edit_menu, 'Select connected fragment(s)', self.select_connected_fragment, 'Ctrl+G')
        self.select_all_action = self._action(self.edit_menu, 'Select all atoms', self.select_all_atoms, 'Ctrl+A')
        self.invert_action = self._action(
            self.edit_menu, 'Invert atom selection', self.invert_selection, 'Ctrl+I')
        self._action(self.edit_menu, 'Clear selection', self.clear_selection)
        self.delete_action = self._action(
            self.edit_menu, 'Delete selected atoms', self._delete_shortcut, 'Delete')
        self.edit_menu.addSeparator()
        self._action(self.edit_menu, 'Toggle selected bonds', self.toggle_bonds, 'Ctrl+B')
        self.toggle_hbond_action = self._action(self.edit_menu, 'Toggle selected hydrogen bond',
                                               self.toggle_hydrogen_bonds, 'Ctrl+H')
        self._action(self.edit_menu, 'Rebuild bonds from distances', self.rebuild_bonds)
        self.edit_menu.addSeparator()
        self.supercell_action = self._action(self.edit_menu, 'Build supercell…', self.build_supercell)
        self.supercell_action.setEnabled(False)
        self.edit_menu.addSeparator()
        self.fit_plane_action = self._action(
            self.edit_menu, 'Fit selected plane', self.fit_selected_plane)
        self.fit_plane_action.setEnabled(False)
        self.align_plane_action = self._action(
            self.edit_menu, 'Align fitted plane to XY', self.align_selected_plane)
        self.align_plane_action.setEnabled(False)

        self.view_menu = self.menuBar().addMenu('&View')
        self._action(self.view_menu, 'Fit to window', lambda: self.reset_camera())
        self._action(self.view_menu, 'Isometry', self.isometric_view)
        self.view_menu.addSeparator()
        self.axis_actions = {}
        for axis in ('X', 'Y', 'Z'):
            action = self._action(
                self.view_menu, axis, lambda _checked=False, axis=axis: self.align_camera(axis))
            action.setStatusTip(f'View from +{axis} toward the structure along the {axis} axis')
            self.axis_actions[axis] = action
        self.view_menu.addSeparator()
        projection_menu = self.view_menu.addMenu('Projection')
        self.projection_group = QActionGroup(self)
        self.projection_actions = {}
        for mode in ('Orthographic', 'Perspective'):
            action = self._action(
                projection_menu, mode, lambda _checked=False, mode=mode: self.set_projection(mode))
            action.setCheckable(True)
            self.projection_group.addAction(action)
            self.projection_actions[mode] = action
        self.projection_actions['Orthographic'].setChecked(True)

        self.analysis_menu = self.menuBar().addMenu('&Analysis')
        self._action(self.analysis_menu, 'Calculation overview…', self.show_calculation_overview)
        self._action(self.analysis_menu, 'HOMO / LUMO and orbital energies…', self.show_orbital_energies)
        self._action(self.analysis_menu, 'Excited-state transitions…', self.show_transition_results)
        self.energy_curve_action=self._action(self.analysis_menu, 'Energy / maximum-RMS convergence curves…', self.show_energy_curve)
        self.energy_curve_action.setEnabled(False)
        self._action(self.analysis_menu, 'Vibrational frequencies', self.show_frequencies)
        self.neb_action=self._action(self.analysis_menu,'NEB / NEB-TS paths…',self.show_neb_results)
        self.goat_action=self._action(self.analysis_menu,'GOAT conformer ensemble…',self.show_goat_results)
        self.soc_action=self._action(self.analysis_menu,'Spin–orbit coupling (SOC)…',self.show_soc_results)
        self.hessian_action=self._action(self.analysis_menu,'Hessian history…',self.show_hessian_results)
        self.help_menu = self.menuBar().addMenu('&Help')
        self._action(self.help_menu, 'Help and shortcuts…', self.help_dialog)

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
        self.files_page = files_page
        left = QVBoxLayout(files_page)
        left.setContentsMargins(8, 8, 8, 8)
        left.addWidget(QLabel('<b>Files and calculation steps</b>'))
        self.files_tree = QTreeWidget()
        self.files_tree.setHeaderHidden(True)
        self.files_tree.setUniformRowHeights(True)
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
        self.frame_spin.valueChanged.connect(self._frame_number_changed)
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
        self._install_trajectory_controls(left)
        self.orbital_btn = QPushButton('HOMO / LUMO…')
        self.orbital_btn.setToolTip('Open the printed orbital energies and HOMO–LUMO gaps.')
        self.orbital_btn.setEnabled(False)
        self.orbital_btn.clicked.connect(self.show_orbital_energies)
        left.addWidget(self.orbital_btn)
        self.orca_results_btn=QPushButton('NEB / GOAT / SOC…')
        result_menu=QMenu(self.orca_results_btn)
        for action in (self.neb_action,self.goat_action,self.soc_action,self.hessian_action):result_menu.addAction(action)
        self.orca_results_btn.setMenu(result_menu);self.orca_results_btn.setEnabled(False);left.addWidget(self.orca_results_btn)
        self.vibration_controls = VibrationControls()
        self.vibration_controls.playRequested.connect(self.toggle_vibration)
        self.vibration_controls.stopRequested.connect(self.stop_vibration)
        self.vibration_controls.amplitudeChanged.connect(self._render_vibration)
        self.vibration_controls.arrows_check.toggled.connect(lambda _: self.refresh_scene())
        self.vibration_controls.selected_arrows_check.toggled.connect(lambda _: self.refresh_scene())
        self.vibration_controls.arrow_length.valueChanged.connect(lambda _: self.refresh_scene())
        left.addWidget(self.vibration_controls)
        sidebar_tabs.addTab(files_page, 'Files')
        self.atom_panel = AtomPanel()
        self.atom_panel.selectionChanged.connect(self._atom_panel_selected)
        self.atom_panel.appearanceChanged.connect(self._change_atom_appearance)
        self.atom_panel.resetRequested.connect(self._reset_atom_appearance)
        sidebar_tabs.addTab(self.atom_panel, 'Atoms')
        root.addWidget(sidebar_tabs)

        # Centre: a white startup canvas, then the 3D canvas + data inspector.
        centre = QStackedWidget()
        self.canvas_stack = centre
        self.welcome_page = WelcomePage()
        self.welcome_page.openRequested.connect(self.open_dialog)
        centre.addWidget(self.welcome_page)
        self.structure_page = QSplitter(Qt.Orientation.Vertical)
        centre.addWidget(self.structure_page)
        self.results_only_page=QWidget()
        results_layout=QVBoxLayout(self.results_only_page);results_layout.setContentsMargins(28,24,28,24)
        self.results_only_title=QLabel('Calculation results')
        title_font=self.results_only_title.font();title_font.setPointSize(20);title_font.setBold(True)
        self.results_only_title.setFont(title_font);results_layout.addWidget(self.results_only_title)
        results_notice=QLabel('No coordinates in this file. Available energies and orbital results can be viewed independently.')
        results_notice.setWordWrap(True);results_layout.addWidget(results_notice)
        result_buttons=QHBoxLayout();results_layout.addLayout(result_buttons)
        self.results_energy_button=QPushButton('Energy curve…');self.results_energy_button.clicked.connect(self.show_energy_curve)
        self.results_orbital_button=QPushButton('HOMO / LUMO…');self.results_orbital_button.clicked.connect(self.show_orbital_energies)
        overview_button=QPushButton('Calculation overview…');overview_button.clicked.connect(self.show_calculation_overview)
        for button in (self.results_energy_button,self.results_orbital_button,overview_button):result_buttons.addWidget(button)
        results_tabs=QTabWidget();results_layout.addWidget(results_tabs,1)
        self.results_only_info=QPlainTextEdit();self.results_only_info.setReadOnly(True);results_tabs.addTab(self.results_only_info,'Results')
        self.results_only_source=QPlainTextEdit();self.results_only_source.setReadOnly(True);results_tabs.addTab(self.results_only_source,'Input / output text')
        centre.addWidget(self.results_only_page)
        self.tabs = QTabWidget()
        self.atom_table = QTableWidget(0, 4)
        self.atom_table.setHorizontalHeaderLabels(['Atom', 'X (Å)', 'Y (Å)', 'Z (Å)'])
        coordinate_font = self.atom_table.font()
        coordinate_font.setPointSizeF(max(8.0, coordinate_font.pointSizeF() - 1))
        self.atom_table.setFont(coordinate_font)
        metrics = self.atom_table.fontMetrics()
        row_height = max(20, metrics.height() + 4)
        self.atom_table.verticalHeader().hide()
        self.atom_table.verticalHeader().setMinimumSectionSize(row_height)
        self.atom_table.verticalHeader().setDefaultSectionSize(row_height)
        self.atom_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.atom_table.horizontalHeader().setStretchLastSection(False)
        self.atom_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.atom_table.horizontalHeader().setMinimumSectionSize(48)
        self.atom_table.setColumnWidth(0, max(68, metrics.horizontalAdvance('9999 Og') + 12))
        for column in (1, 2, 3):
            self.atom_table.setColumnWidth(column, metrics.horizontalAdvance('-1234.123456') + 14)
        self.atom_table.setStyleSheet(
            'QTableView::item { padding: 0px 3px; } '
            'QHeaderView::section { padding: 2px 4px; }')
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
        self.lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lower_splitter.setChildrenCollapsible(False)
        self.lower_splitter.addWidget(self.tabs)
        self.future_panel = QWidget()
        self.future_panel.setObjectName('futurePanel')
        self.future_panel.setAutoFillBackground(True)
        blank_palette = self.future_panel.palette()
        blank_palette.setColor(QPalette.ColorRole.Window, blank_palette.color(QPalette.ColorRole.Base))
        self.future_panel.setPalette(blank_palette)
        self.lower_splitter.addWidget(self.future_panel)
        self.lower_splitter.setStretchFactor(0, 1)
        self.lower_splitter.setStretchFactor(1, 1)
        self.lower_splitter.setSizes([500, 500])
        lower_layout.addWidget(self.lower_splitter, 1)
        self.summary_label = QLabel('Atoms 0  |  Formula -  |  electrons -  |')
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_label.setWordWrap(False)
        self.summary_label.setContentsMargins(8, 4, 8, 5)
        self.summary_label.setToolTip(
            'Total atoms and composition in the active frame. Electron parity uses the net charge; '
            'neutral is assumed when charge is unknown. Short contacts use the periodic minimum image.')
        summary_row = QHBoxLayout()
        summary_row.setSpacing(0)
        summary_row.addWidget(self.summary_label)
        self.short_contacts_button = QPushButton('Short contacts -')
        self.short_contacts_button.setFlat(True)
        self.short_contacts_button.setEnabled(False)
        self.short_contacts_button.setCursor(Qt.CursorShape.PointingHandCursor)
        contact_font = self.short_contacts_button.font(); contact_font.setUnderline(True)
        self.short_contacts_button.setFont(contact_font)
        self.short_contacts_button.setStyleSheet('QPushButton { color: palette(link); padding: 4px 2px; border: none; }')
        self.short_contacts_button.setToolTip('Click to inspect atom pairs and distances.')
        self.short_contacts_button.clicked.connect(self.show_short_contacts)
        summary_row.addWidget(self.short_contacts_button)
        summary_row.addStretch(1)
        self.measurement_label = QLabel()
        self.measurement_label.setObjectName('selectionMeasurement')
        self.measurement_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.measurement_label.setWordWrap(False)
        self.measurement_label.setContentsMargins(8, 4, 8, 5)
        self.measurement_label.setStyleSheet('font-weight: 600;')
        self.measurement_label.setToolTip(
            'Measurement in selection order: two atoms give a bond length, three a bond angle, '
            'and four a dihedral. Uses the active frame coordinates, including the frequency reference.')
        summary_row.addWidget(self.measurement_label)
        lower_layout.addLayout(summary_row)
        self.structure_page.addWidget(lower_panel)
        self.structure_page.setSizes([630, 220])
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
        self._custom_style_state = snapshot(self.render_options)
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
        self.cutoff_slider.setToolTip('Used for initial bonds and Edit → Rebuild bonds from distances. '
                                     'Moving or editing atoms preserves their existing connections.')
        form.addRow('Bond cutoff ×', self.cutoff_slider)
        self.bond_check = QCheckBox('Display bonds')
        self.bond_check.setChecked(True)
        self.bond_check.toggled.connect(lambda v: self._set_option('bonds', v))
        form.addRow(self.bond_check)
        self.hbond_check = QCheckBox('Automatic hydrogen bonds (dashed)')
        self.hbond_check.setChecked(False)
        self.hbond_check.toggled.connect(lambda v: self._set_option('hydrogen_bonds', v))
        form.addRow(self.hbond_check)
        form.addRow(QLabel('Geometric N/O/F-H...N/O/F candidates only;\nnot part of the covalent fragment graph.'))
        form.addRow(QLabel('Ctrl+H draws/removes a manual dashed link\nbetween two selected atoms.'))
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
        self.label_combo.addItems(LABEL_MODES)
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
        self.iso_spin = IsovalueSpinBox()
        self.iso_spin.setValue(.035)
        self.iso_spin.valueChanged.connect(lambda v: self._set_option('volume_iso', v))
        iso_row = QHBoxLayout()
        iso_row.addWidget(self.iso_spin, 1)
        self.iso_apply_button = QPushButton('Apply')
        self.iso_apply_button.clicked.connect(self.iso_spin.interpretText)
        iso_row.addWidget(self.iso_apply_button)
        volume_form.addRow('|Isovalue|', iso_row)
        iso_hint = QLabel('Type a value (e.g. 1.25e-5), then Enter or Apply.')
        iso_hint.setWordWrap(True)
        volume_form.addRow(iso_hint)
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
        selection_help = QLabel('Click atoms to select; right-click clears.\n'
                                'Ctrl+B toggles selected bonds.\n'
                                'Ctrl+H toggles a selected hydrogen bond (dashed).\n'
                                'Ctrl+G selects complete connected fragment(s).\n'
                                'Alt+left drag: rotate fragment in 3D.\n'
                                'Alt+right drag: roll fragment.\n'
                                'Alt+middle drag: move fragment in screen plane.\n'
                                'Without Alt, mouse gestures control the camera.')
        selection_help.setWordWrap(True)
        m_layout.addWidget(selection_help)
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
        self.charge_spin.setEnabled(False)
        self.charge_spin.setToolTip(
            'Used for electron parity. Defaults to the file charge; otherwise assumes neutral.')
        self.charge_spin.valueChanged.connect(self._set_net_charge)
        charge_row.addWidget(self.charge_spin)
        m_layout.addLayout(charge_row)
        fragment_help = QLabel('Cross-cell fragments automatically build a real supercell.\n'
                               'Coordinates and Ctrl+I include all new atoms; Ctrl+Z restores the original.\n'
                               'Infinite crystal networks cannot be fully selected.')
        fragment_help.setWordWrap(True)
        m_layout.addWidget(fragment_help)
        self.toggle_bonds_btn = QPushButton('Toggle bonds within selection  (Ctrl+B)')
        self.toggle_bonds_btn.clicked.connect(self.toggle_bonds)
        m_layout.addWidget(self.toggle_bonds_btn)
        self.toggle_hbond_btn = QPushButton('Toggle hydrogen bond  (Ctrl+H)')
        self.toggle_hbond_btn.setToolTip('Select two atoms, usually H and its acceptor. '
                                        'Dashed links are independent of ordinary bonds; Ctrl+Z undoes changes.')
        self.toggle_hbond_btn.clicked.connect(self.toggle_hydrogen_bonds)
        m_layout.addWidget(self.toggle_hbond_btn)
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
        alignment_help = QLabel('All axes (XYZ/abc): rotate atomic coordinates only.\n'
                                'The lattice and camera remain unchanged.\n'
                                'The first selected atom remains fixed.')
        alignment_help.setWordWrap(True)
        m_layout.addWidget(alignment_help)
        edit_outer.addWidget(measurements)
        plane_group = QGroupBox('Best-fit selection plane')
        plane_layout = QVBoxLayout(plane_group)
        self.fit_plane_btn = QPushButton('Fit selected plane')
        self.fit_plane_btn.setEnabled(False)
        self.fit_plane_btn.clicked.connect(self.fit_selected_plane)
        plane_layout.addWidget(self.fit_plane_btn)
        self.show_plane_check = QCheckBox('Show fitted plane')
        self.show_plane_check.setChecked(True)
        self.show_plane_check.toggled.connect(lambda _checked: self.refresh_scene())
        self.show_plane_check.setEnabled(False)
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
        plane_help = QLabel(
            'Rotate the complete structure, cell and attached grid.\n'
            'Atomic deviations from the plane are preserved. Ctrl+Z to undo.')
        plane_help.setWordWrap(True)
        plane_layout.addWidget(plane_help)
        edit_outer.addWidget(plane_group)
        edit_outer.addStretch(1)

        root.setSizes([355, 1025])
        self._set_frame_controls_enabled(False)
        self.toggle_bonds_btn.setEnabled(False)
        self.toggle_hbond_btn.setEnabled(False)
        self.toggle_hbond_action.setEnabled(False)
        self.fragment_btn.setEnabled(False)
        self.origin_btn.setEnabled(False)
        self.align_btn.setEnabled(False)
        self.invert_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self._install_restored_controls()
        self._init_document_views()

    def _ensure_3d_view(self):
        """Create the native canvas once on the GUI thread after preloading."""
        if self.vtk is not None:
            return
        # Pin the chosen Qt binding before importing VTK's Qt adapter.
        import vtkmodules.qt
        vtkmodules.qt.PyQtImpl = 'PySide6'
        from vtkmodules.vtkRenderingCore import vtkRenderer
        from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
        from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
        from .interaction import InteractiveVTKView
        from .renderer import MoleculeRenderer

        self.vtk = InteractiveVTKView()
        self.scene = vtkRenderer()
        self.scene.SetBackground(1.0, 1.0, 1.0)
        self.vtk.GetRenderWindow().AddRenderer(self.scene)
        self.renderer = MoleculeRenderer(self.scene)
        self.renderer.options = self.render_options
        self.vtk.GetRenderWindow().GetInteractor().SetInteractorStyle(vtkInteractorStyleTrackballCamera())
        self.vtk.scene_renderer = self.scene
        self.vtk.atomClick.connect(self._pick_from_canvas)
        if hasattr(self.vtk,'rectangleSelected'):
            self.vtk.rectangleSelected.connect(self._rectangle_selected)
            self.vtk.set_box_selection(self.box_select_action.isChecked())
        self.vtk.clearSelectionClick.connect(self._right_click_clear)
        self.vtk.fragmentGestureBegin.connect(self._fragment_begin)
        self.vtk.fragmentGestureMove.connect(self._fragment_move)
        self.vtk.fragmentGestureEnd.connect(self._fragment_end)
        self.axes_widget = vtkOrientationMarkerWidget()
        self.axes_widget.SetInteractor(self.vtk.GetRenderWindow().GetInteractor())
        self.axes_widget.SetViewport(0.015, 0.015, 0.225, 0.225)
        self.structure_page.insertWidget(0, self.vtk)
        self.structure_page.setSizes([630, 220])

    @property
    def doc(self) -> Document | None:
        return self.documents[self.current_doc] if 0 <= self.current_doc < len(self.documents) else None

    @property
    def frame(self) -> Frame | None:
        if self._active_vibration is not None:
            return self._vibration_reference
        if self._energy_only_context is not None and self._energy_only_context[0] == self.current_doc:
            return None
        doc = self.doc
        return doc.frames[self.frame_index] if doc is not None and doc.frames else None

    def _set_frame_controls_enabled(self, value):
        for widget in (self.prev_btn, self.next_btn, self.play_btn, self.frame_spin):
            widget.setEnabled(value)

    def open_dialog(self):
        filenames, _ = QFileDialog.getOpenFileNames(self, 'Open calculation or structure files', '', 'All files (*)')
        for name in filenames:
            self.open_path(name)

    def open_path(self, filename):
        if self._closing:
            return
        if self._backend_state != 'ready':
            self._pending_open_paths.append(filename)
            if self._backend_state == 'failed':
                self._start_backend_loading()
            elif self._startup_painted and self._backend_state == 'waiting':
                self._backend_start_timer.start(0)
            self.statusBar().showMessage('Loading components… The selected file will open when ready.')
            return
        self._open_path_now(filename)

    def _open_path_now(self, filename):
        try:
            from .formats import load_document
            new_doc = load_document(filename)
        except Exception as ex:
            QMessageBox.warning(self, 'Could not open file', f'{Path(filename).name}\n\n{ex}')
            return
        index = len(self.documents)
        self.documents.append(new_doc)
        self._add_document_tree(index, new_doc)
        self.change_frame(0, switch_doc=index, reset_camera=True)
        self._update_source_view()
        modes = sum(len(a.modes) for a in new_doc.vibrations)
        suffix = f' • {modes} vibrational modes' if modes else ''
        detail=(f'{len(new_doc.frames)} frame(s) • {len(new_doc.frames[0].symbols)} atoms' if new_doc.frames else 'calculation results • no structure')
        self.statusBar().showMessage(f'Opened {new_doc.path.name} • {detail}{suffix}')

    def _add_document_tree(self, index, new_doc):
        from .energy_units import display_energy
        label=new_doc.format_name+(' · results only' if not new_doc.frames else '')
        head = QTreeWidgetItem([f'{new_doc.path.name}  ({label})'])
        head.setData(0, Qt.ItemDataRole.UserRole, (index, 0))
        self.files_tree.addTopLevelItem(head)
        from .workflow_ui import populate_tree, populate_energy_steps
        populate_energy_steps(self, index, new_doc, head)
        if not new_doc.frames:
            head.setExpanded(True)
            return
        if populate_tree(self,index,new_doc,head):return
        geometry_parent = head
        if new_doc.vibrations:
            geometry_parent = QTreeWidgetItem([f'Geometry / optimization ({len(new_doc.frames)} frames)'])
            geometry_parent.setData(0, Qt.ItemDataRole.UserRole, (index, 0))
            head.addChild(geometry_parent)
        if len(new_doc.frames) > 1 or new_doc.vibrations:
            for i, frame in enumerate(new_doc.frames):
                energy,unit=display_energy(frame,new_doc.format_name)
                suffix = f' • {energy:.5f} {unit}' if energy is not None else ''
                child = QTreeWidgetItem([f'Frame {i + 1}{suffix}'])
                child.setData(0, Qt.ItemDataRole.UserRole, (index, i))
                geometry_parent.addChild(child)
                self._frame_tree_items[index, i] = child
        else:
            self._frame_tree_items[index, 0] = head
        for analysis_index, analysis in enumerate(new_doc.vibrations):
            imaginary = sum(mode.imaginary for mode in analysis.modes)
            title = 'Frequencies' if len(new_doc.vibrations) == 1 else f'Frequencies {analysis_index + 1}'
            group = QTreeWidgetItem([f'{title} ({len(analysis.modes)} modes · {imaginary} imaginary)'])
            group.setData(0, Qt.ItemDataRole.UserRole, (index, 'frequencies', analysis_index))
            head.addChild(group)
            for mode_index, mode in enumerate(analysis.modes):
                suffix = ' · imaginary' if mode.imaginary else ''
                if not mode.can_animate:
                    suffix += ' · no displacement data'
                item = QTreeWidgetItem([f'{mode.number}   {mode.frequency_cm1:.4f} cm⁻¹{suffix}'])
                strength=[]
                if mode.ir_intensity is not None:strength.append(f'IR {mode.ir_intensity:.3f}')
                if mode.raman_activity is not None:strength.append(f'Raman {mode.raman_activity:.3f}')
                if strength:item.setText(0,item.text(0)+' · '+' · '.join(strength))
                item.setData(0, Qt.ItemDataRole.UserRole, (index, 'mode', analysis_index, mode_index))
                details = [f'Mode {mode.number}: {mode.frequency_cm1:.4f} cm⁻¹']
                if mode.ir_intensity is not None:
                    details.append(f'IR intensity: {mode.ir_intensity:.4f} km/mol')
                if mode.symmetry:
                    details.append(f'Symmetry: {mode.symmetry}')
                item.setToolTip(0, '\n'.join(details))
                if mode.imaginary:
                    item.setForeground(0, QColor('#c43b35'))
                group.addChild(item)
                self._vibration_tree_items[index, analysis_index, mode_index] = item
            group.setExpanded(True)
        head.setExpanded(index == 0 or bool(new_doc.vibrations))

    def _tree_current_changed(self, item, _previous):
        # Both a mouse click and Up/Down/Left/Right navigation change the
        # tree's current item. itemClicked only covered the first case.
        if item is None or self._ignore_tree:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            if len(data) > 1 and data[1] == 'energy':
                doc_index, _, step_index = data
                self._activate_document(doc_index)
                self._leave_vibration()
                self._energy_only_context = (doc_index, step_index)
                self._update_source_view(doc_index)
                self._show_results_only()
                with QSignalBlocker(self.files_tree): self.files_tree.setCurrentItem(item)
                return
            if len(data)>1 and data[1]=='series':
                doc_index,_,indices,position,label=data
                self._jump_to_result_sequence(self.documents[doc_index],indices[position],indices,label)
                return
            if len(data)>1 and data[1]=='analysis':
                doc_index,_,kind=data
                if doc_index!=self.current_doc:self.change_frame(0,switch_doc=doc_index)
                {'neb':self.show_neb_results,'goat':self.show_goat_results,'soc':self.show_soc_results,'hessian':self.show_hessian_results}[kind]()
                return
            if len(data) >= 3:
                doc_index, kind, analysis_index, *rest = data
                self.select_vibration(doc_index, analysis_index, rest[0] if rest else 0)
                return
            doc_index, frame_index = data
            if doc_index != self.current_doc:
                self._update_source_view(doc_index)
            self.change_frame(frame_index, switch_doc=doc_index)

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
            from .output_text import output_encoding, decode_output
            if b'\x00' in raw[:4000] and not output_encoding(raw).startswith('utf-16'):
                self.source_view.setPlainText('[Binary file: text preview not available]')
            else:
                decoded = decode_output(raw)
                self.source_view.setPlainText(decoded + ('\n\n[Text preview truncated at 180 KB]' if remaining else ''))
        except Exception as ex:
            self.source_view.setPlainText(str(ex))
        self.results_only_source.setPlainText(self.source_view.toPlainText())

    def _show_results_only(self):
        self.frame_index=0;self.selection.clear();self.playback.stop();self.play_btn.setText('Play')
        self._set_frame_controls_enabled(False);self.fps_spin.setEnabled(False)
        with QSignalBlocker(self.frame_spin):self.frame_spin.setRange(0,0)
        self.frame_count_label.setText('No structure')
        self.charge_spin.setEnabled(False)
        self.canvas_stack.setCurrentWidget(self.results_only_page)
        head=self.files_tree.topLevelItem(self.current_doc)
        if head is not None:
            with QSignalBlocker(self.files_tree):self.files_tree.setCurrentItem(head)
        self._refresh_coordinates();self._refresh_element_choices();self._refresh_measurement()
        self.refresh_scene();self._refresh_info();self._update_gif_action()

    def change_frame(self, index, *, switch_doc=None, reset_camera=False):
        self._pending_paste=None
        self._energy_only_context = None
        target = self.current_doc if switch_doc is None else switch_doc
        if target >= 0:
            self._activate_document(target)
        self._leave_vibration()
        doc = self.doc
        if doc is None:
            return
        if not doc.frames:
            self._show_results_only()
            return
        from .chemical_analysis import known_net_charge
        self._ensure_3d_view()
        self.canvas_stack.setCurrentWidget(self.structure_page)
        if not self._vtk_initialized:
            self.vtk.Initialize()
            self._vtk_initialized = True
        self.frame_index = max(0, min(int(index), len(doc.frames) - 1))
        self.renderer.periodic_preview = None
        # Keep keyboard navigation, playback, spinbox and mouse clicks in sync.
        head = self.files_tree.topLevelItem(self.current_doc)
        if head is not None:
            sequence=self._navigation_indices()
            target=getattr(self,'_series_tree_items',{}).get((self.current_doc,tuple(sequence),self.frame_index))
            if target is None:target = self._frame_tree_items.get((self.current_doc, self.frame_index), head)
            if target is not None and self.files_tree.currentItem() is not target:
                self._ignore_tree = True
                try:
                    self.files_tree.setCurrentItem(target)
                finally:
                    self._ignore_tree = False
        frame = self.frame
        with QSignalBlocker(self.charge_spin):
            self.charge_spin.setValue(known_net_charge(frame) or 0)
        self.charge_spin.setEnabled(True)
        self.selection = [i for i in self.selection if i < len(frame.symbols)]
        self.frame_spin.blockSignals(True)
        sequence=self._navigation_indices()
        self.frame_spin.setRange(1, len(sequence))
        self.frame_spin.setValue(sequence.index(self.frame_index)+1)
        self.frame_spin.blockSignals(False)
        self.frame_count_label.setText(f'{sequence.index(self.frame_index)+1} / {len(sequence)}')
        self.frame_count_label.setToolTip(self.frame.info.get('series_label','Current stage / trajectory'))
        self._refresh_element_choices()
        from .core import valid_lattice
        has_cell = valid_lattice(frame)
        self.axes_basis_combo.model().item(1).setEnabled(has_cell)
        if not has_cell and self.axes_basis_combo.currentData() == 'abc':
            self.axes_basis_combo.setCurrentIndex(0)
        self._set_frame_controls_enabled(len(sequence) > 1)
        self.play_btn.setEnabled(len(sequence) > 1)
        self.refresh_scene(reset_camera=reset_camera)
        self._refresh_coordinates()
        self._sync_selection_to_table()
        self._refresh_info()
        self._update_gif_action()
        self._refresh_frame_tree_label()

    def show_frequencies(self):
        if self.doc is None or not self.doc.vibrations:
            self.statusBar().showMessage('No supported harmonic frequencies in the current file.', 5000)
            return
        self.sidebar_tabs.setCurrentWidget(self.files_page)
        preferred=next((i for i,a in reversed(list(enumerate(self.doc.vibrations))) if a.purpose=='Final frequency verification'),0)
        self.select_vibration(self.current_doc, preferred, 0)

    def select_vibration(self, doc_index, analysis_index, mode_index, *, autoplay=True):
        previous = self._active_vibration
        reference = self._vibration_references.get((doc_index, analysis_index))
        entering_reference = previous is None or previous[:2] != (doc_index, analysis_index)
        switching_doc = doc_index != self.current_doc
        restoring_view = switching_doc and self._has_document_camera(self.documents[doc_index])
        self.playback.stop()
        self.play_btn.setText('Play')
        source_doc=self.documents[doc_index]
        source_analysis=source_doc.vibrations[analysis_index]
        reference_index=len(source_doc.frames)-1
        if source_analysis.stage_index is not None:
            import numpy as np
            matches=[i for i,f in enumerate(source_doc.frames) if f.symbols==source_analysis.reference.symbols and np.allclose(f.positions,source_analysis.reference.positions,atol=2.e-6,rtol=0)]
            if matches:reference_index=matches[-1]
        self.change_frame(reference_index, switch_doc=doc_index)
        self._active_vibration = (doc_index, analysis_index, mode_index)
        analysis = self.doc.vibrations[analysis_index]
        mode = analysis.modes[mode_index]
        self._vibration_reference = reference if reference is not None else analysis.reference.clone()
        self._vibration_references[doc_index, analysis_index] = self._vibration_reference
        self.selection = [i for i in self.selection if i < len(self.frame.symbols)]
        from .chemical_analysis import known_net_charge
        with QSignalBlocker(self.charge_spin):
            self.charge_spin.setValue(known_net_charge(self.frame) or 0)
        self._vibration_phase = 0.
        self._plane_fit = self._plane_context = None
        self.renderer.periodic_preview = None
        self.vibration_controls.show()
        self.tabs.setTabText(self.tabs.indexOf(self.atom_table), 'Coordinates (reference)')
        suffix = ' · imaginary' if mode.imaginary else ''
        description = f'Mode {mode.number} · {mode.frequency_cm1:.4f} cm⁻¹{suffix}'
        if mode.ir_intensity is not None:
            description += f'\nIR: {mode.ir_intensity:.4f} {mode.ir_intensity_unit}'
        if mode.raman_activity is not None:
            description += f'\nRaman activity: {mode.raman_activity:.4f} Å⁴/amu'
        if not mode.can_animate:
            description += '\nNo complete, nonzero displacement data; animation unavailable.'
        self.vibration_controls.description.setText(description)
        self.vibration_controls.play_button.setEnabled(mode.can_animate)
        self.vibration_controls.play_button.setText('Play')
        self._set_frame_controls_enabled(False)
        self.fps_spin.setEnabled(False)
        self.frame_count_label.setText('Frequency reference')
        self._refresh_coordinates()
        self._sync_selection_to_table()
        self.refresh_scene(reset_camera=(switching_doc or entering_reference) and not restoring_view)
        self._refresh_info()
        self._update_gif_action()
        target = self._vibration_tree_items.get(self._active_vibration)
        if target is not None:
            with QSignalBlocker(self.files_tree):
                self.files_tree.setCurrentItem(target)
                self.files_tree.scrollToItem(target)
        if autoplay and mode.can_animate:
            self.toggle_vibration()
        self.statusBar().showMessage(description.replace('\n', ' • '))

    def _leave_vibration(self):
        self.vibration_timer.stop()
        self._active_vibration = self._vibration_reference = None
        self._vibration_phase = 0.
        self.vibration_controls.hide()
        self.tabs.setTabText(self.tabs.indexOf(self.atom_table), 'Coordinates (editable)')
        self.fps_spin.setEnabled(True)
        if self.renderer is not None:
            self.renderer.fixed_bonds = None
            self.renderer.mode_vectors = None

    def toggle_vibration(self):
        if self._active_vibration is None:
            return
        if self.vibration_timer.isActive():
            self.vibration_timer.stop()
            self.vibration_controls.play_button.setText('Play')
        else:
            _, analysis, mode = self._active_vibration
            if not self.doc.vibrations[analysis].modes[mode].can_animate:
                return
            self._vibration_clock.start()
            self.vibration_timer.start()
            self.vibration_controls.play_button.setText('Pause')

    def stop_vibration(self):
        self.vibration_timer.stop()
        self._vibration_phase = 0.
        self.vibration_controls.play_button.setText('Play')
        self._render_vibration()

    def _advance_vibration(self):
        if self._active_vibration is None:
            return
        from math import tau
        elapsed = self._vibration_clock.restart() / 1000.
        self._vibration_phase = (self._vibration_phase + elapsed * tau
                                 * self.vibration_controls.speed.value()) % tau
        self._render_vibration()

    def _vibration_preview(self):
        _, analysis, mode = self._active_vibration
        preview = self.frame.clone()
        preview.positions = self.doc.vibrations[analysis].modes[mode].positions_at(
            self.frame, self._vibration_phase, self.vibration_controls.amplitude.value())
        return preview

    def _render_vibration(self):
        if self._active_vibration is None:
            return
        self._prepare_analysis_scene()
        self.renderer.set_scene(self._vibration_preview(), None)
        self.scene.ResetCameraClippingRange()
        self.vtk.GetRenderWindow().Render()

    def _geometry_edit_allowed(self):
        if self._alignment_enabled():
            self.statusBar().showMessage('Turn off trajectory display alignment before editing coordinates or bonds.', 5000)
            return False
        if self._active_vibration is None:
            return True
        self.statusBar().showMessage('Select a geometry / optimization frame to edit coordinates or bonds.', 5000)
        return False

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
                        if j == 0 or self._active_vibration is not None or self._alignment_enabled():
                            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                        else:
                            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        finally:
            self._ignore_table = False
            self.atom_table.setUpdatesEnabled(True)
            self.atom_table.viewport().update()

    def _refresh_element_choices(self):
        """Synchronize the Edit-page element selector with the active frame."""
        frame = self.frame
        previously = self.element_combo.currentText()
        with QSignalBlocker(self.element_combo):
            self.element_combo.clear()
            if frame is None:
                return
            choices = sorted(set(frame.symbols))
            self.element_combo.addItems(choices)
            if choices:
                self.element_combo.setCurrentText(previously if previously in choices else choices[0])

    def _refresh_after_geometry_edit(self):
        """Publish new coordinates, selection, rendering and document details."""
        if getattr(self, 'renderer', None) is not None:
            self.renderer.periodic_preview = None
        if getattr(self,'undo_stack',None):
            old=self.undo_stack[-1]
            if old[0:2]==(self.current_doc,self.frame_index):
                from .energy_units import rigid_equivalent
                if not rigid_equivalent(old[2],self.frame):
                    self.frame.energy_ev=None;self.frame.info.pop('energy_source',None)
                    self._refresh_frame_tree_label()
        self._refresh_element_choices()
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
        """Update the active frame's net charge for electron parity reporting."""
        if self.frame is None:
            return
        self.frame.info['charge_override'] = int(new_charge)
        self._refresh_info()

    def _refresh_info(self):
        doc, frame = self.doc, self.frame
        if doc is None:
            return
        if frame is None:
            self.short_contacts_button.setEnabled(False)
            self.short_contacts_button.setText('Short contacts -')
            from .result_availability import results_text
            text=results_text(doc)
            if self._energy_only_context is not None:
                from ase.units import Hartree
                step = doc.calculation_results.steps[self._energy_only_context[1]]
                cycle = step.cycle if step.cycle is not None else self._energy_only_context[1]+1
                text = (f'Selected energy step: {cycle}\n'
                        f'Energy: {step.energy_ev/Hartree:.12f} Eh\n'
                        f'        {step.energy_ev:.9f} eV\n'
                        f'        {step.energy_ev*23.0605478306:.8f} kcal/mol\n'
                        f'Source line: {step.source_line}\nNo structure for this energy record.\n\n' + text)
            self.results_only_title.setText(doc.path.name+' · calculation results')
            self.results_only_info.setPlainText(text);self.info_view.setPlainText(text)
            self.summary_label.setText('No structure in this file')
            return
        from .structure_summary import molecular_formula
        from .chemical_analysis import electron_parity
        from .periodic_geometry import short_contacts
        lines = [f'File: {doc.path}', f'Reader: {doc.format_name}',
                 ('View: frequency reference geometry' if self._active_vibration is not None
                  else f'Frame: {self.frame_index + 1} of {len(doc.frames)}'),
                 f'Atoms: {len(frame.symbols)}', f'Periodic flags: {frame.pbc}']
        if frame.info.get('series_label'):lines.insert(2,'Result series: '+frame.info['series_label'])
        if 'stage_index' in frame.info and doc.calculation_results is not None:
            stage=doc.calculation_results.stages[frame.info['stage_index']]
            lines.insert(2,'Stage: '+stage.name+' · '+stage.status)
        from .energy_units import display_energy
        energy,unit=display_energy(frame,doc.format_name)
        if energy is not None:lines.append(f"Energy: {energy:.8f} {unit} ({frame.info.get('energy_source','reader result')})")
        supercell = frame.info.get('supercell')
        if supercell is not None:
            repeats = ' × '.join(str(n) for n in supercell['repeats'])
            lines.append(f'Supercell: {repeats} from {supercell["source_atoms"]} source atoms')
            lines.append(frame.info['energy_note'])
        cell_volume = abs(float(__import__('numpy').linalg.det(frame.cell)))
        if cell_volume > 1e-10:
            lines.append('Unit cell (Å):')
            lines.extend('  ' + '  '.join(f'{v:12.6f}' for v in a) for a in frame.cell)
            if any(frame.pbc):
                lines.append(f'Cell volume: {cell_volume:.6f} Å³')
        if doc.volume is not None:
            lines.append(f'Volumetric grid: {doc.volume.data.shape}')
        if doc.vibrations:
            lines.append(f'Frequency calculations: {len(doc.vibrations)}')
            for n, analysis in enumerate(doc.vibrations, 1):
                lines.append(f'  {n}: {len(analysis.modes)} modes, '
                             f'{sum(m.imaginary for m in analysis.modes)} imaginary')
                if analysis.note:
                    lines.append(analysis.note)
        if self._active_vibration is not None:
            _, analysis_index, mode_index = self._active_vibration
            mode = doc.vibrations[analysis_index].modes[mode_index]
            lines.append(f'\nSelected mode: {mode.number} · {mode.frequency_cm1:.4f} cm⁻¹'
                         + (' (imaginary)' if mode.imaginary else ''))
            for name, value, unit in [('IR intensity', mode.ir_intensity, mode.ir_intensity_unit),
                                      ('Raman activity', mode.raman_activity, 'Å⁴/amu'),
                                      ('Reduced mass', mode.reduced_mass, 'amu'),
                                      ('Force constant', mode.force_constant, 'mDyne/Å')]:
                if value is not None:
                    lines.append(f'{name}: {value:.4f} {unit}')
            lines.append('Coordinates, measurements and structure exports use the frequency reference geometry. '
                         'Animation amplitude and speed are visual controls, not molecular dynamics.')
        alignment = frame.info.get('plane_alignment')
        if alignment is not None:
            lines.append('\nLast plane alignment: r_new = r_old @ R.T + translation')
            lines.extend('  ' + '  '.join(f'{v: .9f}' for v in row)
                         for row in alignment['rotation'])
            lines.append('Translation (Å): ' + ', '.join(f'{v:.9f}' for v in alignment['translation']))
        if doc.note:
            lines.append('\nReader note: ' + doc.note)
        if self._alignment_enabled():
            spec = self._trajectory_alignments.get(id(doc))
            lines.append(f'\nDisplay alignment: reference frame {spec.reference_index+1}, {len(spec.indices)} fitting atoms. '
                         'Coordinates and structure exports retain the source frame.')
            if self.renderer is not None and self.renderer.alignment_note:
                lines.append(self.renderer.alignment_note)
        if doc.modified:
            lines.append('\nThis document has unsaved coordinate edits.')
        lines.append('\nAvailable geometry and energies are read from the file; Gaussian/ORCA harmonic modes '
                     'include printed frequencies, intensities and Cartesian displacements. '
                     'Spectra are broadened simulations from printed data, not new electronic calculations.')
        self.info_view.setPlainText('\n'.join(lines))
        system = 'Composition' if any(frame.pbc) else 'Formula'
        parity = electron_parity(frame)
        self.summary_label.setText(
            f'Atoms {len(frame.symbols)}  |  '
            f'{system} {molecular_formula(frame.symbols)}  |  '
            f'electrons {parity.split()[0].lower()}  |')
        self.summary_label.setToolTip(
            f'Electron parity: {parity}\nComposition and counts refer to the active source geometry.')
        count, _ = short_contacts(frame)
        self.short_contacts_button.setText(f'Short contacts {count}')
        self.short_contacts_button.setEnabled(True)

    def show_short_contacts(self):
        if self.frame is None:
            return
        from .short_contacts_dialog import ShortContactsDialog
        context = f'{self.doc.path.name} · Frame {self.frame_index+1}'
        if self._active_vibration is not None:
            context = f'{self.doc.path.name} · Frequency reference {self._active_vibration[1]+1}'
        return self._show_analysis_window(ShortContactsDialog(self.frame, context, self))

    def refresh_scene(self, reset_camera=False):
        self._refresh_trajectory_controls()
        self._prepare_analysis_scene()
        self._update_fitted_plane()
        self.orbital_btn.setEnabled(bool(self.doc is not None and self.doc.calculation_results
                                        and self.doc.calculation_results.orbitals))
        self.results_orbital_button.setEnabled(self.orbital_btn.isEnabled())
        from .result_availability import has_curve_data
        available=has_curve_data(self.doc)
        self.energy_curve_action.setEnabled(available);self.results_energy_button.setEnabled(available)
        doc=self.doc
        for action,available in ((self.neb_action,doc is not None and bool(doc.neb_runs)),
                                 (self.goat_action,doc is not None and bool(doc.conformer_ensembles)),
                                 (self.soc_action,doc is not None and bool(doc.soc_results)),
                                 (self.hessian_action,doc is not None and doc.calculation_results is not None and bool(doc.calculation_results.hessians))):
            action.setEnabled(bool(available))
        self.orca_results_btn.setEnabled(any(a.isEnabled() for a in (self.neb_action,self.goat_action,self.soc_action,self.hessian_action)))
        if self.frame is None:
            self.supercell_action.setEnabled(False)
            self._refresh_atom_panel()
            return
        from .core import valid_lattice
        self.supercell_action.setEnabled(bool(self.frame.symbols) and any(self.frame.pbc)
            and valid_lattice(self.frame) and self._active_vibration is None)
        self.render_options.show_volume = bool(self.volume_check.isChecked())
        self._refresh_properties()
        self.renderer.selected = list(self.selection)
        if self._active_vibration is not None:
            from .core import visible_bonds
            self.renderer.fixed_bonds = visible_bonds(self.frame, self.render_options.bond_cutoff)
            self.renderer.set_scene(self._vibration_preview(), None, reset_camera=False)
        else:
            self.renderer.fixed_bonds = None
            try:self.renderer.set_scene(self.frame, self.doc.volume, reset_camera=False)
            except ValueError as ex:
                if not self.render_options.boundary_enabled:raise
                self.render_options.boundary_enabled=False
                self.boundary_panel.set_values(False,self.render_options.boundary_bounds)
                self.renderer.set_scene(self.frame,self.doc.volume,reset_camera=False)
                self.statusBar().showMessage('Boundary disabled for this frame: '+str(ex),7000)
        self._apply_document_camera(reset_camera)
        self._sync_corner_axes()
        self.vtk.GetRenderWindow().Render()
        self._refresh_measurement()
        self._refresh_atom_panel()
        display=self.renderer.boundary_display
        self.boundary_panel.count.setText(f'{len(display.tiles)} cells · {len(display.source_indices)} displayed atoms · {len(self.frame.symbols)} source atoms' if display is not None else f'{len(self.frame.symbols)} source atoms')

    def _refresh_atom_panel(self):
        if self.frame is None or self.renderer is None:
            self.atom_panel.set_frame(None)
            return
        colors = [self.renderer.atom_color(self.frame, i) for i in range(len(self.frame.symbols))]
        self.atom_panel.set_frame(self.frame, colors, self.selection)

    def _atom_panel_selected(self, indices):
        if self.frame is None:
            return
        self.selection = [i for i in self.selection if i in indices] + [i for i in indices if i not in self.selection]
        self.renderer.periodic_preview = None
        self._sync_selection_to_table()
        self.refresh_scene()

    def _change_atom_appearance(self, indices, values, *, reset=False):
        if self.frame is None:
            return
        from .appearance_workflow import apply_appearance
        if apply_appearance(self, indices, values, reset):
            self.refresh_scene()
            self.statusBar().showMessage('Display settings applied across matching frames in this file. Ctrl+Z to undo.',5000)

    def _reset_atom_appearance(self, indices):
        self._change_atom_appearance(indices, {}, reset=True)

    def _update_fitted_plane(self):
        """Keep an explicitly fitted plane only while its input remains current."""
        frame = self.frame
        has_periodic_cell = False
        if frame is not None:
            from .periodic_geometry import periodic_basis
            has_periodic_cell = periodic_basis(frame) is not None
        self.plane_images_check.setEnabled(has_periodic_cell)
        can_fit = frame is not None and len(self.selection) >= 3 and self._active_vibration is None
        self.fit_plane_btn.setEnabled(can_fit)
        self.fit_plane_action.setEnabled(can_fit)
        if self._plane_fit is not None:
            import numpy as np
            old_frame, positions, cell, nearest_images = self._plane_context
            if (frame is not old_frame or tuple(self.selection) != self._plane_fit.indices
                    or nearest_images != self.plane_images_check.isChecked()
                    or not np.array_equal(frame.positions[self.selection], positions)
                    or not np.array_equal(frame.cell, cell)):
                self._plane_fit = None
                self._plane_context = None
        text = 'Select at least three non-collinear atoms.'
        if can_fit:
            text = 'Click Fit selected plane to create a plane.'
        if self._plane_fit is not None:
            plane = self._plane_fit
            nx, ny, nz = plane.normal
            offset = -float(plane.normal @ plane.center)
            text = (f'{len(plane.indices)} atoms; least-squares plane\n'
                    f'{nx:+.5f} x {ny:+.5f} y {nz:+.5f} z {offset:+.5f} = 0\n'
                    f'RMS distance: {plane.rms:.5f} Å; max: {plane.max_distance:.5f} Å')
        self.plane_label.setText(text)
        self.plane_align_btn.setEnabled(self._plane_fit is not None)
        self.align_plane_action.setEnabled(self._plane_fit is not None)
        self.show_plane_check.setEnabled(self._plane_fit is not None)
        if self.renderer is not None:
            self.renderer.fitted_plane = self._plane_fit if self.show_plane_check.isChecked() else None

    def _fit_selected_plane(self):
        """Calculate a plane only as part of an explicit fit/alignment command."""
        from .selection_geometry import fit_selection_plane
        frame = self.frame
        self._plane_fit = fit_selection_plane(
            frame, self.selection, nearest_images=self.plane_images_check.isChecked())
        self._plane_context = (frame, frame.positions[self.selection].copy(),
                               frame.cell.copy(), self.plane_images_check.isChecked())

    def fit_selected_plane(self):
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or len(self.selection) < 3:
            return
        self._plane_fit = None
        self._plane_context = None
        try:
            self._fit_selected_plane()
        except ValueError as exc:
            self.refresh_scene()
            self.plane_label.setText(str(exc))
            return
        with QSignalBlocker(self.show_plane_check):
            self.show_plane_check.setChecked(True)
        self.refresh_scene()

    def align_selected_plane(self):
        if not self._geometry_edit_allowed():
            return
        self._update_fitted_plane()
        if self._plane_fit is None:
            return
        from .selection_geometry import align_plane_to_xy
        self._record_undo()
        align_plane_to_xy(self.frame, self._plane_fit,
                          place_at_zero=self.plane_zero_check.isChecked(), volume=self.doc.volume)
        self._fit_selected_plane()
        self._fragment_gesture = None
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(
            'Fitted plane aligned to XY; complete structure and cell rotated. Ctrl+Z to undo.', 6000)

    def _sync_corner_axes(self):
        """Switch between camera-following overlay and true world-origin axes."""
        if self.frame is None:
            return
        enabled = self.render_options.axes_position == 'Corner'
        self.renderer.detach_corner_labels()
        if self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        if enabled:
            marker = self.renderer.make_corner_marker(self.renderer.frame or self.frame)
            self.axes_widget.SetOrientationMarker(marker)
            self.axes_widget.SetEnabled(1)
            self.renderer.attach_corner_labels(self.axes_widget.GetRenderer())
            self.axes_widget.InteractiveOff()

    def _set_standard_label_font(self, text):
        self.render_options.label_font_file = ''
        self.custom_font_btn.setText('Choose TTF/OTF font file…')
        self._set_option('label_font', text)

    def _select_label_font_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select font file (not bundled into EXE)', '',
            'Font files (*.ttf *.otf);;All files (*)')
        if path:
            self.render_options.label_font_file = path
            self.custom_font_btn.setText('Font file: ' + Path(path).name)
            self.refresh_scene()

    def pick_label_colour(self):
        picked = QColorDialog.getColor(QColor(self.render_options.label_color),
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
        opts = self.render_options
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
        apply_preset(self.render_options, values)
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
        self._user_style_presets[name] = snapshot(self.render_options)
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
        setattr(self.render_options, option, value)
        if option in STYLE_KEYS:
            self._custom_style_state = snapshot(self.render_options)
            with QSignalBlocker(self.preset_combo):
                self.preset_combo.setCurrentIndex(self.preset_combo.findData(CUSTOM_KEY))
            if option == 'background':
                self.bg_btn.setText('Background colour… (' + value + ')')
        if option == 'bond_cutoff' and self.renderer is not None:
            self.renderer.periodic_preview = None
        if self.frame is not None:
            self.refresh_scene()

    def pick_element_colour(self):
        symbol = self.element_combo.currentText()
        if not symbol:
            return
        from .core import colour
        colors = self.render_options.element_colors
        picked = QColorDialog.getColor(QColor(colors.get(symbol, colour(symbol))),
                                       self, f'{symbol} colour')
        if picked.isValid():
            self._set_option('element_colors', {**colors, symbol: picked.name()})

    def pick_background(self):
        current = QColor(self.render_options.background)
        picked = QColorDialog.getColor(current, self, 'Background colour')
        if picked.isValid():
            self._set_option('background', picked.name())

    def _pick_from_canvas(self, x: float, y: float):
        """Handle a *native Qt* click. Convert logical pixels for high-DPI VTK."""
        if self.frame is None:
            return
        if self._paste_at_click(x,y):return
        from .interaction import vtk_display_from_qt
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
        editable = frame is not None and self._active_vibration is None and not self._alignment_enabled()
        self.toggle_bonds_btn.setEnabled(editable and n >= 2)
        self.toggle_hbond_btn.setEnabled(editable and n == 2)
        self.toggle_hbond_action.setEnabled(editable and n == 2)
        self.fragment_btn.setEnabled(frame is not None and n > 0)
        self.origin_btn.setEnabled(editable and n == 1)
        self.align_btn.setEnabled(editable and n == 2)
        self.invert_btn.setEnabled(frame is not None and bool(frame.symbols))
        self.delete_btn.setEnabled(editable and n > 0)
        self.measurement_label.clear()
        if frame is None or not self.selection:
            self.selected_label.setText('No atoms selected')
            return
        atoms = [f'{frame.symbols[i]}{i + 1}' for i in self.selection]
        label = f'{n} selected: ' + ' — '.join(atoms[:12])
        if n > 12:
            label += f' … (+{n - 12} more)'
        if 2 <= n <= 4:
            try:
                from .core import measure
                quantity, value = measure(frame, self.selection)
                units = 'Å' if quantity == 'distance' else '°'
                label += f'\n{quantity}: {value:.4f} {units}'
                name = {'distance': 'Bond length', 'angle': 'Bond angle', 'dihedral': 'Dihedral'}[quantity]
                self.measurement_label.setText(f'{name}  {"—".join(atoms)}  {value:.4f} {units}')
            except (ValueError, IndexError):
                self.measurement_label.setText('Selected geometry undefined')
        self.selected_label.setText(label)

    def _right_click_clear(self):
        if self.selection:
            self.clear_selection()
            self.statusBar().showMessage('Atom selection cleared', 2500)

    def clear_selection(self):
        self.selection.clear()
        if self.renderer is not None:
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

    def select_all_atoms(self):
        if self.frame is None or self._text_editor_active():
            return
        selected = list(range(len(self.frame.symbols)))
        if self.selection != selected:
            self._record_selection_undo()
            self.selection = selected
            self._sync_selection_to_table()
            self.refresh_scene()

    def _record_selection_undo(self):
        self.undo_stack.append(('selection', self.current_doc, self.frame_index,
                                list(self.selection), self._active_vibration))
        self.undo_stack = self.undo_stack[-50:]

    def _delete_shortcut(self):
        """Keep Delete available to text and numeric editors while typing."""
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
            return
        self.delete_selected_atoms()

    def delete_selected_atoms(self):
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or not self.selection:
            return
        from .selection_geometry import delete_selected_atoms as remove_atoms
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
        """Select a complete fragment, building editable periodic images if needed."""
        if self.frame is None or not self.selection:
            self.statusBar().showMessage('Select an atom before selecting its fragment.', 3500)
            return
        from .periodic_geometry import periodic_basis, periodic_fragment
        from .fragment import selected_fragments
        if periodic_basis(self.frame) is not None:
            try:
                preview = periodic_fragment(self.frame, self.selection,
                                            self.renderer.options.bond_cutoff)
                if preview.extra_tiles:
                    if not self._geometry_edit_allowed():
                        return
                    from .supercell import make_fragment_supercell
                    expanded, selection = make_fragment_supercell(
                        self.frame, preview, bond_cutoff=self.renderer.options.bond_cutoff)
            except ValueError as exc:
                self.renderer.periodic_preview = None
                QMessageBox.information(self, 'Periodic fragment', str(exc))
                return
            if preview.extra_tiles:
                self.playback.stop()
                self.play_btn.setText('Play')
                self._record_undo()
                self.doc.frames[self.frame_index] = expanded
                self.doc.volume = None
                self.doc.modified = True
                self.selection = selection
                self._fragment_gesture = None
                self.change_frame(self.frame_index, reset_camera=True)
                repeats = ' × '.join(str(n) for n in preview.supercell_extent)
                self.statusBar().showMessage(
                    f'Built {repeats} supercell: {len(expanded.symbols)} atoms; '
                    f'selected {len(selection)} connected atoms. '
                    'Coordinates and Ctrl+I include all new atoms. Ctrl+Z to undo.', 8000)
                return
            self.selection = preview.indices
            self.renderer.periodic_preview = None
            self._sync_selection_to_table()
            self.refresh_scene()
            self.statusBar().showMessage(
                f'Selected {len(preview.indices)} connected atoms.', 6000)
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
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or not self.selection:
            self.statusBar().showMessage('Select an atom before Alt+dragging its fragment.', 3500)
            return
        from .fragment import selected_fragments
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
        from .fragment import (screen_translation, apply_fragment_translation,
                               screen_rotation, apply_fragment_rotation)
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
                                frame.clone(), volume_geometry, list(self.selection), volume,
                                self._active_vibration))
        self.undo_stack = self.undo_stack[-50:]
        from .core import freeze_bonds
        freeze_bonds(frame, self.render_options.bond_cutoff)

    def _refresh_frame_tree_label(self):
        item = self._frame_tree_items.get((self.current_doc, self.frame_index))
        if item is not None and item.parent() is not None and self.frame is not None:
            from .energy_units import display_energy
            energy,unit=display_energy(self.frame,self.doc.format_name)
            suffix = f' • {energy:.5f} {unit}' if energy is not None else ''
            info=self.frame.info
            label=(f'Conformer {info["goat_conformer"]}' if 'goat_conformer' in info else
                   f'Image {info["neb_image"]}' if 'neb_image' in info else
                   f'Step {info["optimization_cycle"]}' if info.get('optimization_cycle') is not None else
                   f'Frame {self.frame_index+1}')
            item.setText(0,label+suffix)

    def build_supercell(self):
        if self.frame is None or not self._geometry_edit_allowed():
            return
        from .supercell_dialog import SupercellDialog
        dialog = SupercellDialog(self.frame, has_volume=self.doc.volume is not None, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_supercell(dialog.repeats(), wrap=dialog.wrap.isChecked())

    def apply_supercell(self, repeats, *, wrap=True):
        if self.frame is None or not self._geometry_edit_allowed():
            return False
        from .supercell import make_supercell
        try:
            expanded = make_supercell(self.frame, repeats, wrap=wrap,
                                      bond_cutoff=self.render_options.bond_cutoff)
        except (ValueError, TypeError) as ex:
            QMessageBox.warning(self, 'Could not build supercell', str(ex))
            return False
        if tuple(repeats) == (1, 1, 1):
            return False
        self.playback.stop(); self.play_btn.setText('Play')
        self._record_undo()
        self.doc.frames[self.frame_index] = expanded
        self.doc.volume = None
        self.doc.modified = True
        self.selection.clear()
        self.change_frame(self.frame_index, reset_camera=True)
        self.statusBar().showMessage(
            f'Supercell {" × ".join(str(n) for n in repeats)}: {len(expanded.symbols):,} atoms. '
            'Use Export structure to save; Ctrl+Z to undo.', 10000)
        return True

    def rebuild_bonds(self):
        if self.frame is None or not self._geometry_edit_allowed(): return
        from .core import freeze_bonds
        self._record_undo()
        self.frame.bond_snapshot = self.frame.periodic_bond_snapshot = None
        freeze_bonds(self.frame, self.render_options.bond_cutoff)
        self.doc.modified = True
        self.renderer.periodic_preview = None
        self.refresh_scene(); self._refresh_info()
        self.statusBar().showMessage('Bonds explicitly rebuilt from current distances. Ctrl+Z to undo.', 5000)

    def toggle_bonds(self):
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or len(self.selection) < 2:
            self.statusBar().showMessage('Select at least two atoms to edit bonds', 3000)
            return
        from .core import toggle_selected_bonds
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

    def toggle_hydrogen_bonds(self):
        if self._text_editor_active() or not self._geometry_edit_allowed():
            return
        if self.frame is None or len(self.selection) != 2:
            self.statusBar().showMessage('Select exactly two atoms for a hydrogen bond (Ctrl+H).', 4000)
            return
        from .hydrogen_bonds import toggle_hydrogen_bond
        self._record_undo()
        action = toggle_hydrogen_bond(self.frame, self.selection, self.render_options.hydrogen_bonds)
        self.doc.modified = True
        self.refresh_scene()
        self.statusBar().showMessage('Hydrogen bond ' + action + ' (dashed). Ctrl+Z to undo.', 5000)

    def move_selected_to_origin(self):
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or len(self.selection) != 1:
            return
        from .core import move_atom_to_origin
        self._record_undo()
        displacement = move_atom_to_origin(self.frame, self.selection[0])
        if self.doc.volume is not None:
            self.doc.volume.origin += displacement
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage('Translated geometry so selected atom is at (0,0,0).', 4000)

    def align_selected_pair(self):
        if not self._geometry_edit_allowed():
            return
        if self.frame is None or len(self.selection) != 2:
            return
        from .core import align_pair_to_axis
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
        if not self._geometry_edit_allowed():
            self._refresh_coordinates()
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
        item = self.undo_stack.pop()
        if item[0] in ('selection', 'appearance'):
            kind, doc_idx, frame_idx, old_selection, vibration = item[:5]
            if kind == 'appearance':
                from .appearance_workflow import restore_appearance
                restore_appearance(self, doc_idx, item[5])
            if vibration is not None:
                self.select_vibration(*vibration, autoplay=False)
            else:
                self.change_frame(frame_idx, switch_doc=doc_idx)
            self.selection = old_selection
            self._sync_selection_to_table()
            self.refresh_scene()
            return
        doc_idx, frame_idx, old_frame, old_volume_geometry, old_selection, old_volume, vibration = item
        if vibration is not None:
            self.select_vibration(*vibration, autoplay=False)
            self._vibration_reference = old_frame
            self._vibration_references[vibration[:2]] = old_frame
            self.selection = old_selection
            self._refresh_coordinates()
            self._sync_selection_to_table()
            self.refresh_scene()
            return
        self.documents[doc_idx].frames[frame_idx] = old_frame
        self.documents[doc_idx].volume = old_volume
        volume = old_volume
        if volume is not None and old_volume_geometry is not None:
            volume.origin = old_volume_geometry[0]
            volume.voxel_vectors = old_volume_geometry[1]
        self.selection = old_selection
        self.change_frame(frame_idx, switch_doc=doc_idx)

    def _step_previous(self):
        sequence=self._navigation_indices()
        if sequence:self.change_frame(sequence[max(0,sequence.index(self.frame_index)-1)])

    def _step_next(self):
        doc = self.doc
        if doc is not None:
            sequence=self._navigation_indices()
            if sequence:self.change_frame(sequence[(sequence.index(self.frame_index)+1)%len(sequence)])

    def _navigation_indices(self):
        from .workflow_ui import sequence_for
        return sequence_for(self)

    def _frame_number_changed(self,n):
        sequence=self._navigation_indices()
        if sequence:self.change_frame(sequence[max(0,min(n-1,len(sequence)-1))])

    def _jump_to_result_sequence(self,document,index,sequence=(),label=''):
        if index is None:return
        self._result_sequence=(document,tuple(sequence),label) if sequence else None
        self._jump_to_result_frame(document,index)

    def _orca_dialog(self,kind):
        if self.doc is None:return
        from .orca_analysis_dialogs import NebDialog,GoatDialog,SocDialog,HessianDialog
        doc=self.doc
        jump=lambda i,seq,label:self._jump_to_result_sequence(doc,i,seq,label)
        if kind=='neb':
            if not doc.neb_runs:return
            dialog=NebDialog(doc,jump,self)
        elif kind=='goat':
            if not doc.conformer_ensembles:return
            dialog=GoatDialog(doc,jump,self)
        elif kind=='soc':
            if not doc.soc_results:return
            dialog=SocDialog(doc,self)
        else:
            dialog=HessianDialog(doc,jump,lambda ai:self.select_vibration(next(i for i,d in enumerate(self.documents) if d is doc),ai,0),self)
        return self._show_analysis_window(dialog)

    def show_neb_results(self):return self._orca_dialog('neb')
    def show_goat_results(self):return self._orca_dialog('goat')
    def show_soc_results(self):return self._orca_dialog('soc')
    def show_hessian_results(self):return self._orca_dialog('hessian')

    def _update_play_rate(self):
        if self.playback.isActive():
            self.playback.start(1000 // self.fps_spin.value())

    def toggle_play(self):
        if self.frame is None:return
        if self._active_vibration is not None:
            return
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
            from .renderer import set_isometric_view
            set_isometric_view(self.scene)
        else:
            cam = self.scene.GetActiveCamera()
            cam.SetParallelProjection(mode == 'Orthographic')
            self.scene.ResetCamera()
            self.scene.ResetCameraClippingRange()
        projection = ('Orthographic' if self.scene.GetActiveCamera().GetParallelProjection()
                      else 'Perspective')
        self.projection_actions[projection].setChecked(True)

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
        if self.frame is None:
            return
        self.scene.ResetCamera()
        self.scene.ResetCameraClippingRange()
        self.vtk.GetRenderWindow().Render()

    def align_camera(self, axis):
        if self.frame is None or not self.frame.symbols:
            return
        import numpy as np
        directions = {
            'X': ((1, 0, 0), (0, 0, 1)),
            'Y': ((0, 1, 0), (0, 0, 1)),
            'Z': ((0, 0, 1), (0, 1, 0)),
        }
        direction, up = directions[axis]
        camera = self.scene.GetActiveCamera()
        centre = self.frame.positions.mean(axis=0)
        spread = max(2.0, float(np.ptp(self.frame.positions, axis=0).max()) * 3)
        camera.SetFocalPoint(*[float(x) for x in centre])
        camera.SetPosition(*[float(centre[i] + direction[i] * spread) for i in range(3)])
        camera.SetViewUp(*up)
        camera.SetParallelProjection(True)
        self.projection_actions['Orthographic'].setChecked(True)
        self.reset_camera()

    def _show_analysis_window(self, dialog):
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._analysis_windows.append(dialog)
        dialog.finished.connect(lambda _=0: self._analysis_windows.remove(dialog)
                                if dialog in self._analysis_windows else None)
        dialog.show()
        return dialog

    def show_calculation_overview(self):
        if self.doc is None:
            return
        from .results_dialog import CalculationOverview
        return self._show_analysis_window(CalculationOverview(self.doc, self))

    def show_orbital_energies(self, checked=False, *, document=None):
        doc = document if document is not None else self.doc
        if doc is None:
            return
        from .orbital_dialog import OrbitalDialog
        return self._show_analysis_window(OrbitalDialog(doc, self))

    def show_transition_results(self):
        if self.doc is None:
            return
        from .transition_dialog import TransitionDialog
        return self._show_analysis_window(TransitionDialog(self.doc, self))

    def _jump_to_result_frame(self, document, frame_index):
        index = next((i for i, doc in enumerate(self.documents) if doc is document), None)
        if index is None or not 0 <= frame_index < len(document.frames):
            return
        self.playback.stop()
        self.play_btn.setText('Play')
        if self.current_doc!=index:self._update_source_view(index)
        self.change_frame(frame_index, switch_doc=index)

    def show_energy_curve(self):
        from .result_availability import has_curve_data
        if not has_curve_data(self.doc):
            return
        from .convergence_dialog import ConvergenceDialog
        doc = self.doc
        return self._show_analysis_window(ConvergenceDialog(doc,
            lambda index: self._jump_to_result_frame(doc, index), self))

    def save_png(self,suffix=None):
        if self.frame is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save rendering', self._save_path(suffix if isinstance(suffix,str) else '_view.png'), 'PNG image (*.png)')
        if not path:
            return
        try:
            from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
            from vtkmodules.vtkIOImage import vtkPNGWriter
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

    def _update_gif_action(self):
        available = self.doc is not None and len(self._navigation_indices()) > 1
        if self._active_vibration is not None:
            _, analysis, mode = self._active_vibration
            available = available or self.doc.vibrations[analysis].modes[mode].can_animate
        self.gif_action.setEnabled(available and not self._gif_exporting)

    def save_gif(self):
        if self.frame is None or self._gif_exporting:
            return
        from .gif_dialog import GifExportDialog
        mode = None
        if self._active_vibration is not None:
            _, analysis_index, mode_index = self._active_vibration
            candidate = self.doc.vibrations[analysis_index].modes[mode_index]
            mode = candidate if candidate.can_animate else None
        dialog = GifExportDialog(self, total_frames=len(self._navigation_indices()),
            mode_label=f'Mode {mode.number} · {mode.frequency_cm1:.4f} cm⁻¹' if mode is not None else '',
            view_size=self.vtk.GetRenderWindow().GetSize(), trajectory_fps=self.fps_spin.value(),
            amplitude=self.vibration_controls.amplitude.value(),
            cycle_seconds=1. / self.vibration_controls.speed.value())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dialog.settings()
        suffix = f'_mode_{mode.number:03d}' if settings.source == 'vibration' else '_trajectory'
        path, _ = QFileDialog.getSaveFileName(self, 'Save animation GIF',
            self._save_path(suffix + '.gif'), 'GIF animation (*.gif)')
        if not path:
            return
        if not path.lower().endswith('.gif'):
            path += '.gif'
        self._save_gif_file(path, settings)

    def _save_gif_file(self, path, settings):
        from copy import deepcopy
        from .animation_export import export_animation_gif, ExportCancelled
        if self._gif_exporting:
            return False
        export_document=self.doc
        if settings.source=='trajectory':
            from .core import Document
            sequence=self._navigation_indices()
            if sequence!=list(range(len(self.doc.frames))):
                export_document=Document(self.doc.path,self.doc.format_name,[self.doc.frames[i] for i in sequence],self.doc.volume)
        reference = mode = None
        if settings.source == 'vibration':
            if self._active_vibration is None:
                return False
            _, analysis, index = self._active_vibration
            reference = self.frame.clone()
            mode = deepcopy(self.doc.vibrations[analysis].modes[index])
            count = settings.vibration_frame_count()
        else:
            count = len(settings.trajectory_indices(len(export_document.frames)))
        was_playing, was_vibrating = self.playback.isActive(), self.vibration_timer.isActive()
        vibration = self._active_vibration
        self.playback.stop()
        self.vibration_timer.stop()
        self.play_btn.setText('Play')
        self.vibration_controls.play_button.setText('Play')
        self._gif_close_requested = False
        progress = QProgressDialog('Preparing GIF…', 'Cancel', 0, count, self)
        progress.setWindowTitle('Export animation GIF')
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        self._gif_progress = progress
        self._gif_exporting = True
        self._update_gif_action()
        progress.show()
        error = None
        completed = False

        def cancelled():
            QApplication.processEvents()
            return progress.wasCanceled() or self._gif_close_requested

        def update(value, total):
            progress.setLabelText(f'Rendering frame {value} / {total}…')
            progress.setValue(value)

        try:
            export_animation_gif(path, export_document, settings, self.render_options,
                camera=self.scene.GetActiveCamera(), selected=self.selection,
                source_size=self.vtk.GetRenderWindow().GetSize(), reference=reference,
                mode=mode, progress=update, cancelled=cancelled,
                alignment=self._trajectory_alignments.get(id(self.doc)) if self._alignment_enabled() else None,
                mode_arrows=self.vibration_controls.arrows_check.isChecked(),
                mode_arrow_length=self.vibration_controls.arrow_length.value(),
                mode_arrow_indices=tuple(self.selection) if self.vibration_controls.selected_arrows_check.isChecked() else None)
            completed = True
        except ExportCancelled:
            self.statusBar().showMessage('GIF export cancelled.', 5000)
        except Exception as ex:
            error = str(ex)
        finally:
            progress.close()
            progress.deleteLater()
            self._gif_progress = None
            self._gif_exporting = False
            self._update_gif_action()
            if not self._gif_close_requested and not getattr(self, '_closing', False):
                if was_playing:
                    self.playback.start(1000 // self.fps_spin.value())
                    self.play_btn.setText('Pause')
                if was_vibrating and self._active_vibration == vibration:
                    self._vibration_clock.start()
                    self.vibration_timer.start()
                    self.vibration_controls.play_button.setText('Pause')
            if self._gif_close_requested:
                QTimer.singleShot(0, self.close)
        if completed:
            self.statusBar().showMessage(f'Saved GIF: {path} • {count} frames', 10000)
        elif error is not None:
            QMessageBox.warning(self, 'GIF export failed', error)
        return completed

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
        name = self._save_path('_edited' + extension)
        path, _ = QFileDialog.getSaveFileName(self, 'Export selected frame', name)
        if not path:
            return
        try:
            from .formats import export_frame
            notices = export_frame(self.frame, path, target)
            self.statusBar().showMessage('Exported ' + path + (' | ' + '; '.join(notices) if notices else ''), 10000)
        except Exception as ex:
            QMessageBox.warning(self, 'Export failed', str(ex))

    def help_dialog(self):
        QMessageBox.information(self, APP_TITLE,
            APP_FULL_NAME + '\n\n'
            'Open files: Ctrl+O; save PNG: Ctrl+S; export structure: Ctrl+Shift+S.\n\n'
            'File > Export animation GIF saves a trajectory or the selected vibration mode.\n'
            'Drag files into the window. Left-drag: rotate; right-drag: roll clockwise/counterclockwise; mouse wheel: zoom.\n'
            'Click atoms to add/remove from selection; right-click to clear, right-drag to roll.\n'
            'Ctrl+B toggles selected internal bonds; two atoms toggle regardless of distance.\n'
            'Ctrl+H draws/removes a dashed hydrogen bond between two selected atoms; Ctrl+Z undoes it.\n'
            'Switching files restores each file\'s camera, colours and display settings for this session.\n'
            'Ctrl+Shift+B toggles box selection; drag its unfilled dashed outline; Esc exits.\n'
            'One atom -> Move to origin; two ordered atoms -> Align to XYZ or lattice abc.\n'
            'Use Up/Down in frame tree to change frames.\n'
            'Expand Frequencies in Files and select a mode to animate it; negative frequencies are imaginary.\n'
            'Pause or reset vibration, and adjust its visual amplitude and speed below the file tree.\n'
            'Select 2/3/4 atoms to measure distance/angle/dihedral.\n'
            'View > X/Y/Z looks from the positive coordinate axis toward the structure.\n'
            'Select 3+ atoms, then click Fit selected plane in Edit to show a plane.\n'
            'Align plane to XY rotates all atoms and the cell; optional Z translation.\n'
            'Ctrl+A selects all atoms; box selection always adds atoms and Ctrl+Z undoes the last addition.\n'
            'Ctrl+I inverts selection; Delete removes selected atoms; Ctrl+Z restores them.\n'
            'Edit > Build supercell repeats the current periodic frame and enlarges the unit cell.\n'
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
        if self._gif_exporting:
            self._gif_close_requested = True
            if self._gif_progress is not None:
                self._gif_progress.cancel()
            event.ignore()
            return
        self._closing = True
        self._backend_start_timer.stop()
        self._pending_open_paths.clear()
        self.playback.stop()
        self.vibration_timer.stop()
        if self.axes_widget is not None and self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        if self.vtk is not None:
            self.vtk.GetRenderWindow().Finalize()
            self.vtk.TerminateApp()
        super().closeEvent(event)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LELE.Explorer')
    app = QApplication([sys.argv[0], *argv])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_FULL_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle('Fusion')
    window = LELEWindow(argv)
    window.show()
    return app.exec()
