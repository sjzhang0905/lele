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
    QSplitter, QTreeWidget, QTreeWidgetItem, QLabel,
    QSlider, QCheckBox, QDoubleSpinBox, QPushButton, QSpinBox,
    QGroupBox, QFormLayout, QTabWidget, QTableWidget, QTableWidgetItem,
    QScrollArea, QPlainTextEdit, QAbstractItemView,
    QLineEdit, QTextEdit, QAbstractSpinBox, QStackedWidget, QHeaderView, QMenu, QMenuBar, QSizePolicy,
)
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QColor, QIcon, QPalette
from .dialog_policy import QDialog, QMessageBox, QFileDialog, QInputDialog, QColorDialog, configure_dialog, show_dialog

from .render_options import RenderOptions
from .backend_loader import get_backend_loader
from .operations import run_data_task,ui_operation,gui_operation,ui_checkpoint,ui_busy
from .progress_dialog import LeleProgressDialog
from .output_text import LoadCancelled
from .atom_panel import AtomPanel
from .atom_appearance import DEFAULT_APPEARANCE, LABEL_MODES, appearance
from .numeric_controls import IsovalueSpinBox
from .color_controls import set_color_swatch
from .panel_controls import (
    PanelComboBox, SIDEBAR_MIN_WIDTH, compact_panel_sliders, compact_panel_editors,
)
from .vibration_controls import VibrationControls
from .style_presets import (BUILTIN_PRESETS, CUSTOM_KEY, STYLE_KEYS, STYLE_MODES,
                            ATOM_PALETTES, BOND_PALETTES, SURFACE_FINISHES,
                            apply_preset, snapshot, validate_preset)
from .welcome import WelcomePage
from .restored_actions import RestoredActions
from .trajectory_actions import TrajectoryAnalysisActions
from .document_view import DocumentViewActions
from .crystal_actions import CrystalActions
from .element_rule_actions import ElementRuleActions
from .project_actions import ProjectActions
from .file_loading import FileLoadActions
from .field_actions import FieldActions
from .selection_actions import SelectionActions
from .coordinate_update_actions import CoordinateUpdateActions
from .annotation_actions import AnnotationActions
from .batch_export import BatchExportActions
from .loaded_documents import LoadedDocumentActions

if TYPE_CHECKING:
    from .core import Document, Frame

ICON_PATH = Path(__file__).with_name('assets') / 'lele.ico'


class ResultsText(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setToolTip('Ctrl+C copies the selection, or the entire result if no text is selected.')

    def event(self, event):
        if event.type() == QEvent.Type.ShortcutOverride and any(
            event.matches(key) for key in (QKeySequence.StandardKey.Copy, QKeySequence.StandardKey.SelectAll)
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy) and not self.textCursor().hasSelection():
            QApplication.clipboard().setText(self.toPlainText())
            event.accept()
            return
        super().keyPressEvent(event)


class LELEWindow(LoadedDocumentActions, BatchExportActions, AnnotationActions, SelectionActions, CoordinateUpdateActions, FieldActions, RestoredActions, TrajectoryAnalysisActions, DocumentViewActions, CrystalActions, ElementRuleActions, ProjectActions, FileLoadActions, QMainWindow):
    def menuBar(self):
        """Keep menu actions in the sidebar without reserving a full-width row."""
        if not hasattr(self, '_sidebar_menu_bar'):
            self._sidebar_menu_bar = QMenuBar(self)
            self._sidebar_menu_bar.setNativeMenuBar(False)
        return self._sidebar_menu_bar

    def __init__(self, initial_files=()):
        super().__init__()
        from .wheel_guard import install_wheel_guard
        install_wheel_guard()
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
        from .window_caption import install_caption
        self._caption = install_caption(self)
        self.playback = QTimer(self)
        self.playback.timeout.connect(self._step_next)
        self._closing = False
        self._backend_state = 'waiting'
        self._backend_loader = None
        from .import_paths import ImportBatch
        self._pending_open_paths = [ImportBatch(tuple(initial_files))] if initial_files else []
        self._startup_painted = False
        self._backend_start_timer = QTimer(self)
        self._backend_start_timer.setSingleShot(True)
        self._backend_start_timer.timeout.connect(self._start_backend_loading)
        # Wait for all visible welcome sections, not just its first heading.
        # The zero-delay callback runs only after this paint pass completes.
        self._startup_paint_seen = set()
        self._startup_paint_targets = [
            self.welcome_page.title_label, self.welcome_page.full_name_label,
            self.welcome_page.version_label, self.welcome_page.parrot_walk,
            *self.welcome_page.shortcut_groups,
        ]
        for widget in self._startup_paint_targets:
            widget.installEventFilter(self)
        self.statusBar().showMessage('Open a calculation input/output file or a structure.')

    def eventFilter(self, watched, event):
        if watched is getattr(self,'tabs',None) and event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.Show):
            self._queue_summary_alignment()
        if (watched in (getattr(self,'footer_row',None),getattr(self,'status_message_label',None),getattr(self,'_summary_status_bar',None))
                and event.type() in (QEvent.Type.Move,QEvent.Type.Resize,QEvent.Type.Show,QEvent.Type.LayoutRequest)):
            self._queue_summary_alignment()
        measurement=getattr(self,'measurement_value',None)
        if (measurement is not None and watched in (measurement,measurement.lineEdit())
                and event.type()==QEvent.Type.FocusIn and hasattr(self,'playback')):
            self.playback.stop();self.play_btn.setText('Play')
        targets = getattr(self, '_startup_paint_targets', ())
        if watched in targets and event.type() == QEvent.Type.Paint:
            self._startup_paint_seen.add(watched)
            visible = [widget for widget in targets if not widget.visibleRegion().isEmpty()]
            if visible and all(widget in self._startup_paint_seen for widget in visible):
                for widget in targets:
                    widget.removeEventFilter(self)
                self._startup_paint_targets = []
                self._startup_painted = True
                self._backend_start_timer.start(0)
        return super().eventFilter(watched, event)

    def _pause_selection_playback(self):
        """Keep element-local indices stable while an expression is entered."""
        if hasattr(self, 'playback'):
            self.playback.stop()
            self.play_btn.setText('Play')

    def _start_backend_loading(self):
        if self._closing or self._backend_state in ('loading', 'initializing', 'ready'):
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
                self._backend_state = 'initializing'
                self.statusBar().showMessage('Preparing the 3D view…')
                self._ensure_3d_view()
                self._warm_up_3d_view()
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
            self._open_or_queue_file(filename)

    def _warm_up_3d_view(self):
        """Prepare the native context and common pipelines before the first file.

        This runs on the GUI thread after the welcome page has painted and the
        import worker has finished. The tiny temporary scene never becomes a
        document or replaces the visible welcome page or the user's settings.
        """
        if not self._vtk_initialized:
            self.vtk.Initialize()
            self._vtk_initialized = True
        import numpy as np
        from .core import Frame, Volume
        from .render_options import RenderOptions
        from .renderer import rgb
        options = self.renderer.options
        try:
            self.renderer.options = RenderOptions(labels='Element', axes_position='Origin',
                                                  volume_iso=.25, volume_opacity=.5)
            frame = Frame(['O', 'H', 'H'], [[2., 2., 2.], [2.96, 2., 2.], [1.76, 2.92, 2.]],
                          np.eye(3)*6., (True, True, True))
            grid = np.indices((5, 5, 5), dtype=float) - 2.
            density = np.exp(-np.sum(grid*grid, axis=0))
            volume = Volume(density, np.zeros(3), np.eye(3))
            self.renderer.set_scene(frame, volume, reset_camera=True)
            self.axes_widget.SetOrientationMarker(self.renderer.make_corner_marker(frame))
            self.axes_widget.SetEnabled(1)
            self.renderer.attach_corner_labels(self.axes_widget.GetRenderer())
            self.axes_widget.InteractiveOff()
            self.vtk.GetRenderWindow().Render()
        finally:
            self.renderer.detach_corner_labels()
            if self.axes_widget.GetEnabled():
                self.axes_widget.SetEnabled(0)
            self.renderer.clear()
            self.renderer.frame = self.renderer.source_frame = None
            self.renderer.volume = None
            self.renderer.boundary_display = None
            self.renderer._boundary_cache = None
            self.renderer.options = options
            self.renderer.apply_lighting()
            self.scene.SetBackground(rgb(options.background))
            # Do not leave the temporary warmup pixels in a hidden framebuffer
            # that could flash when the first real document reveals the canvas.
            self.vtk.GetRenderWindow().Render()

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
        self._png_exporting = False
        self._batch_exporting = False
        self._batch_progress = None
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
        self.convert_all_action = self._action(self.file_menu, 'Convert all…', self.convert_all_dialog)
        self.export_png_all_action = self._action(self.file_menu, 'Export PNG all…', self.export_png_all_dialog)
        self.convert_all_action.setEnabled(False)
        self.export_png_all_action.setEnabled(False)
        self.apply_coordinates_action = self._action(self.file_menu, 'Apply new coordinates…', self.apply_new_coordinates_dialog)
        self.apply_coordinates_action.setEnabled(False)
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
        self.reorient_action=self._action(self.edit_menu,'Reorient complete structure / crystal…',self.configure_coordinate_reorientation)
        self.reorient_action.setEnabled(False)
        self.rotate_axis_action = self._action(self.edit_menu, 'Rotate about selected axis…', self.rotate_about_selected_axis)
        self.rotate_axis_action.setEnabled(False)
        self.dihedral_action = self._action(self.edit_menu, 'Set selected dihedral…', self.set_selected_dihedral)
        self.dihedral_action.setEnabled(False)
        self.vacuum_action=self._action(self.edit_menu,'Modify slab vacuum…',self.configure_vacuum)
        self.vacuum_action.setEnabled(False)
        self.edit_menu.addSeparator()
        self.fit_plane_action = self._action(
            self.edit_menu, 'Fit selected plane', self.fit_selected_plane)
        self.fit_plane_action.setEnabled(False)
        self.align_plane_action = self._action(
            self.edit_menu, 'Align fitted plane to XY', self.align_selected_plane)
        self.align_plane_action.setEnabled(False)

        self.view_menu = self.menuBar().addMenu('&View')
        lighting_menu = self.view_menu.addMenu('Lighting')
        self.light_actions = []
        from .lighting import LIGHT_NAMES
        for i, label in enumerate(LIGHT_NAMES):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(self.render_options.light_enabled[i])
            action.toggled.connect(lambda checked, index=i: self._set_light_enabled(index, checked))
            lighting_menu.addAction(action)
            self.light_actions.append(action)
        self.atom_legend_action=self._action(self.view_menu,'Atom legend…',self.show_atom_legend)
        self._action(self.view_menu, 'Fit to window', lambda: self.reset_camera())
        self._action(self.view_menu, 'Isometry', self.isometric_view)
        self.view_menu.addSeparator()
        self.axis_actions = {}
        for axis in ('X', 'Y', 'Z'):
            action = self._action(
                self.view_menu, axis, lambda _checked=False, axis=axis: self.align_camera(axis))
            action.setStatusTip(f'View from +{axis} toward the structure along the {axis} axis')
            self.axis_actions[axis] = action
        for axis in ('a', 'b', 'c'):
            action = self._action(
                self.view_menu, axis, lambda _checked=False, axis=axis: self.align_camera(axis))
            action.setStatusTip(f'View from +{axis} along the displayed lattice vector')
            action.setEnabled(False)
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
        self.nmr_action=self._action(self.analysis_menu,'NMR spectrum / shielding table…',self.show_nmr_results)
        self.nmr_action.setEnabled(False)
        self.energy_curve_action=self._action(self.analysis_menu, 'Energy / maximum-RMS convergence curves…', self.show_energy_curve)
        self.energy_curve_action.setEnabled(False)
        self.scan_action = self._action(self.analysis_menu, 'ORCA scan curve…', self.show_scan_curve)
        self.scan_action.setEnabled(False)
        self._action(self.analysis_menu, 'Vibrational frequencies', self.show_frequencies)
        self.qe_reference_action=self._action(self.analysis_menu,'Assign QE phonon reference…',self.assign_qe_phonon_reference)
        self.neb_action=self._action(self.analysis_menu,'NEB / NEB-TS paths…',self.show_neb_results)
        self.vasp_neb_action=self._action(self.analysis_menu,'VASP NEB from loaded outputs…',self.show_vasp_neb)
        self.stm_action = self._action(self.analysis_menu, 'STM from VASP PARCHG…', self.show_stm)
        self.xrd_action = self._action(self.analysis_menu, 'Simulate powder XRD…', self.show_xrd)
        self.stm_action.setEnabled(False)
        self.xrd_action.setEnabled(False)
        self.goat_action=self._action(self.analysis_menu,'GOAT conformer ensemble…',self.show_goat_results)
        self.soc_action=self._action(self.analysis_menu,'Spin–orbit coupling (SOC)…',self.show_soc_results)
        self.hessian_action=self._action(self.analysis_menu,'Hessian history…',self.show_hessian_results)
        self.help_menu = self.menuBar().addMenu('&Help')
        self._action(self.help_menu, 'Help and shortcuts…', self.help_dialog)
        self._action(self.help_menu, 'Atom selection syntax…', self.show_selection_expression_help)

        root = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(root)

        # All settings live in a single tabbed sidebar; the 3D canvas remains wide.
        sidebar_tabs = QTabWidget()
        self.sidebar_tabs = sidebar_tabs
        sidebar_tabs.setDocumentMode(True)
        sidebar_tabs.setMinimumWidth(SIDEBAR_MIN_WIDTH)
        sidebar_tabs.setMaximumWidth(475)
        sidebar_tabs.tabBar().setUsesScrollButtons(True)
        self.sidebar_column = QWidget()
        self.sidebar_column.setMinimumWidth(SIDEBAR_MIN_WIDTH)
        self.sidebar_column.setMaximumWidth(475)
        sidebar_layout = QVBoxLayout(self.sidebar_column)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addWidget(self.menuBar())
        sidebar_layout.addWidget(sidebar_tabs, 1)
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
        self.files_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.files_tree.customContextMenuRequested.connect(self._loaded_file_context_menu)
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
        self.scan_curve_button = QPushButton('Scan curve…')
        self.scan_curve_button.setToolTip('Plot one final energy per scan point; inspect all scanned coordinates.')
        self.scan_curve_button.clicked.connect(self.show_scan_curve)
        self.scan_curve_button.setEnabled(False)
        left.addWidget(self.scan_curve_button)
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
        root.addWidget(self.sidebar_column)

        # Centre: a white startup canvas, then the 3D canvas + data inspector.
        centre = QStackedWidget()
        self.canvas_stack = centre
        self.welcome_page = WelcomePage()
        centre.addWidget(self.welcome_page)
        self.structure_page = QSplitter(Qt.Orientation.Vertical)
        centre.addWidget(self.structure_page)
        self.results_only_page=QWidget()
        results_layout=QVBoxLayout(self.results_only_page);results_layout.setContentsMargins(28,24,28,24)
        self.results_only_title=QLabel('Calculation results')
        title_font=self.results_only_title.font();title_font.setPointSize(20);title_font.setBold(True)
        self.results_only_title.setFont(title_font);results_layout.addWidget(self.results_only_title)
        results_notice=QLabel('No coordinates for this result. Available calculation data can be viewed independently.')
        results_notice.setWordWrap(True);results_layout.addWidget(results_notice)
        result_buttons=QHBoxLayout();results_layout.addLayout(result_buttons)
        self.results_energy_button=QPushButton('Energy curve…');self.results_energy_button.clicked.connect(self.show_energy_curve)
        self.results_orbital_button=QPushButton('HOMO / LUMO…');self.results_orbital_button.clicked.connect(self.show_orbital_energies)
        overview_button=QPushButton('Calculation overview…');overview_button.clicked.connect(self.show_calculation_overview)
        for button in (self.results_energy_button,self.results_orbital_button,overview_button):result_buttons.addWidget(button)
        property_buttons=QHBoxLayout();results_layout.addLayout(property_buttons)
        self.results_spectrum_button=QPushButton('UV-Vis spectrum…');self.results_spectrum_button.clicked.connect(lambda:self.show_spectrum('UV-Vis'))
        self.results_transition_button=QPushButton('Export transitions CSV…');self.results_transition_button.clicked.connect(self.export_transition_data)
        self.results_nmr_button=QPushButton('NMR spectrum / table…');self.results_nmr_button.clicked.connect(self.show_nmr_results)
        for button in (self.results_spectrum_button,self.results_transition_button,self.results_nmr_button):property_buttons.addWidget(button)
        self.results_only_info = ResultsText()
        results_layout.addWidget(self.results_only_info, 1)
        centre.addWidget(self.results_only_page)
        self.tabs = QTabWidget()
        self.tabs.installEventFilter(self)
        self.atom_table = QTableWidget(0, 4)
        self.atom_table.setHorizontalHeaderLabels(['Atom', 'X (Å)', 'Y (Å)', 'Z (Å)'])
        self.atom_table.horizontalHeaderItem(0).setToolTip('* marks a mixed / partial-occupancy site. Hover a row for all element fractions and vacancy.')
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
        self.atom_table.itemDoubleClicked.connect(self._coordinate_atom_activated)
        self.tabs.addTab(self.atom_table, 'Coordinates (editable)')
        self.info_view = ResultsText()
        self.tabs.addTab(self.info_view, 'Results / info')
        lower_panel = QWidget()
        lower_layout = QVBoxLayout(lower_panel)
        lower_layout.setContentsMargins(0, 0, 0, 0)
        lower_layout.setSpacing(4)
        self.lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.lower_splitter.setChildrenCollapsible(False)
        self.bottom_control_tabs = QTabWidget()
        self.bottom_control_tabs.setDocumentMode(True)
        self.bottom_control_tabs.setMinimumWidth(270)
        self.bottom_control_tabs.tabBar().setUsesScrollButtons(True)
        self.lower_splitter.addWidget(self.bottom_control_tabs)
        self.lower_splitter.addWidget(self.tabs)
        from .selection_panel import SelectionPanel, FragmentPanel
        from .atoms_selection_panel import AtomsSelectionPanel
        self.selection_tabs = QTabWidget()
        self.selection_tabs.setDocumentMode(True)
        self.selection_tabs.setMinimumWidth(230)
        self.selection_tabs.tabBar().setUsesScrollButtons(True)
        self.selection_panel = SelectionPanel()
        self.fragment_panel = FragmentPanel()
        self.atoms_selection_panel = AtomsSelectionPanel()
        self.selection_tabs.addTab(self.selection_panel, 'Current selection')
        self.selection_tabs.addTab(self.fragment_panel, 'Fragment')
        self.selection_tabs.addTab(self.atoms_selection_panel, 'Atoms selection')
        self.atoms_selection_panel.selectionRequested.connect(self.select_named_fragment)
        self.atoms_selection_panel.expressionRequested.connect(self.select_by_expression)
        self.atoms_selection_panel.syntaxHelpRequested.connect(self.show_selection_expression_help)
        self.atoms_selection_panel.editingStarted.connect(self._pause_selection_playback)
        self.fragment_panel.saveRequested.connect(self.save_named_fragment)
        self.fragment_panel.deleteRequested.connect(self.delete_named_fragment)
        self.fragment_panel.selectRequested.connect(self.select_named_fragment)
        self.fragment_panel.moveRequested.connect(self.move_named_fragment)
        self.lower_splitter.addWidget(self.selection_tabs)
        self.lower_splitter.setStretchFactor(0, 1)
        self.lower_splitter.setStretchFactor(1, 1)
        self.lower_splitter.setStretchFactor(2, 1)
        self.lower_splitter.setSizes([300, 380, 350])
        lower_layout.addWidget(self.lower_splitter, 1)
        self.summary_label = QLabel('Atoms 0  |  Formula -  |  electrons -  |')
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_label.setWordWrap(False)
        self.summary_label.setContentsMargins(0, 0, 6, 0)
        self.summary_label.setToolTip(
            'Total atoms and composition in the active frame. Electron parity uses the net charge; '
            'neutral is assumed when charge is unknown. Short contacts use the periodic minimum image.')
        summary_row = QHBoxLayout()
        summary_row.setSpacing(0)
        summary_row.addWidget(self.summary_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.short_contacts_button = QPushButton('Short contacts -')
        self.short_contacts_button.setFlat(True)
        self.short_contacts_button.setEnabled(False)
        self.short_contacts_button.setCursor(Qt.CursorShape.PointingHandCursor)
        contact_font = self.short_contacts_button.font(); contact_font.setUnderline(True)
        self.short_contacts_button.setFont(contact_font)
        self.short_contacts_button.setStyleSheet('QPushButton { color: palette(link); padding: 1px 2px; border: none; }')
        self.short_contacts_button.setToolTip('Click to inspect atom pairs and distances.')
        self.short_contacts_button.clicked.connect(self.show_short_contacts)
        summary_row.addWidget(self.short_contacts_button)
        summary_row.addStretch(1)
        self.measurement_label = QLabel()
        self.measurement_label.setObjectName('selectionMeasurement')
        self.measurement_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.measurement_label.setWordWrap(False)
        self.measurement_label.setContentsMargins(8, 0, 2, 0)
        self.measurement_label.setStyleSheet('font-weight: 600;')
        self.measurement_label.setToolTip(
            'Measurement in selection order: two atoms give a bond length, three a bond angle, '
            'and four a dihedral. Uses the active frame coordinates, including the frequency reference.')
        summary_row.addWidget(self.measurement_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.measurement_value = QDoubleSpinBox()
        self.measurement_value.setDecimals(4)
        self.measurement_value.setKeyboardTracking(False)
        self.measurement_value.installEventFilter(self)
        self.measurement_value.lineEdit().installEventFilter(self)
        self.measurement_value.setFixedWidth(118)
        self.measurement_value.setToolTip('Enter a target value and press Enter or Set. Move the last selected atom and its bonded terminal fragment.')
        self.measurement_value.valueChanged.connect(self._measurement_value_changed)
        self.measurement_value.editingFinished.connect(self._apply_measurement_value)
        self.measurement_set = QPushButton('Set')
        self.measurement_set.setFixedWidth(36)
        self.measurement_set.clicked.connect(self._apply_measurement_value)
        self.measurement_value.hide();self.measurement_set.hide()
        self._measurement_context = None
        self._measurement_pending = False
        summary_row.addWidget(self.measurement_value)
        summary_row.addWidget(self.measurement_set)
        self.footer_row = QWidget()
        self.footer_row.setLayout(summary_row)
        summary_row.setContentsMargins(0, 0, 4, 0)
        # Keep space for the native editor height even when it is hidden.
        # Showing a bond length/angle must not resize QStatusBar and the canvas.
        footer_widgets = (self.summary_label, self.short_contacts_button,
                          self.measurement_label, self.measurement_value, self.measurement_set)
        for widget in footer_widgets:
            widget.ensurePolished()
        self.footer_row.setFixedHeight(max(widget.sizeHint().height() for widget in footer_widgets))
        self.footer_row.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        self.footer_row.hide()
        # One bottom row replaces the former summary row plus separate status
        # strip. Keep full status text available on hover in its compact cell.
        self.status_message_label = QLabel()
        self.status_message_label.setFixedWidth(235)
        self.status_message_label.setContentsMargins(5,0,5,0)
        bar=self.statusBar();bar.setSizeGripEnabled(False)
        self._summary_status_bar=bar
        bar.addPermanentWidget(self.status_message_label)
        bar.addPermanentWidget(self.footer_row,1)
        bar.messageChanged.connect(self._status_message_changed)
        bar.layout().setContentsMargins(0,0,0,0)
        self._footer_alignment_timer=QTimer(self);self._footer_alignment_timer.setSingleShot(True)
        self._footer_alignment_timer.setInterval(0);self._footer_alignment_timer.timeout.connect(self._align_summary_footer)
        for watched in (bar,self.footer_row,self.status_message_label):watched.installEventFilter(self)
        self.structure_page.addWidget(lower_panel)
        self.structure_page.setSizes([660, 190])
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
            target = self.bottom_control_tabs if title in ('Axes', 'Labels') else sidebar_tabs
            target.addTab(scroll, title)
            return layout

        display_outer = control_page('Style')
        group = QGroupBox('3D drawing')
        form = QFormLayout(group)
        self._custom_style_state = snapshot(self.render_options)
        self.preset_combo = PanelComboBox()
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
        preset_help = QLabel('Presets change appearance only; coordinates, bond '
                             'cutoff, labels and cell settings stay unchanged.')
        preset_help.setWordWrap(True)
        form.addRow(preset_help)
        self.style_combo = PanelComboBox()
        self.style_combo.addItems(STYLE_MODES)
        self.style_combo.currentTextChanged.connect(lambda s: self._set_option('style', s))
        form.addRow('Style', self.style_combo)
        from .numeric_controls import CenteredScaleSlider
        self.atom_slider = CenteredScaleSlider(20, 45, 180)
        self.atom_slider.setValue(round(self.render_options.atom_scale * 100))
        self.atom_slider.valueChanged.connect(lambda v: self._set_option(
            'space_filling_scale' if self.render_options.style == 'Space filling' else 'atom_scale', v / 100))
        form.addRow('Atom size', self.atom_slider)
        self.sf_radii_combo = PanelComboBox()
        self.sf_radii_combo.addItems(['Atomic', 'Ionic', 'van der Waals'])
        self.sf_radii_combo.setToolTip('VESTA 3.5.8 radius table. Space filling uses 100% at Atom size 100%; ionic values represent preset oxidation/coordination states.')
        self.sf_radii_combo.setEnabled(False)
        self.sf_radii_combo.currentTextChanged.connect(lambda v: self._set_option('space_filling_radii', v))
        form.addRow('VESTA radii', self.sf_radii_combo)
        self.bond_slider = CenteredScaleSlider(3, 5, 35, decimals=1)
        self.bond_slider.setValue(round(self.render_options.bond_scale * 100))
        self.bond_slider.valueChanged.connect(lambda v: self._set_option('bond_scale', v / 100))
        form.addRow('Bond thickness', self.bond_slider)
        self.atom_palette_combo = PanelComboBox()
        self.atom_palette_combo.addItems(ATOM_PALETTES)
        self.atom_palette_combo.setToolTip('Default separates common metals by hue. Select another palette or edit individual element colors.')
        self.atom_palette_combo.currentTextChanged.connect(
            lambda val: self._set_option('atom_palette', val))
        form.addRow('Atom colors', self.atom_palette_combo)
        self.bond_palette_combo = PanelComboBox()
        self.bond_palette_combo.addItems(BOND_PALETTES)
        self.bond_palette_combo.currentTextChanged.connect(
            lambda val: self._set_option('bond_palette', val))
        form.addRow('Bond colors', self.bond_palette_combo)
        self.finish_combo = PanelComboBox()
        self.finish_combo.addItems(SURFACE_FINISHES)
        self.finish_combo.setCurrentText(self.render_options.surface_finish)
        self.finish_combo.currentTextChanged.connect(
            lambda val: self._set_option('surface_finish', val))
        form.addRow('Lighting', self.finish_combo)
        self.bond_model_combo = PanelComboBox()
        self.bond_model_combo.addItems(['Chemcraft pair ranges', 'Covalent radii'])
        self.bond_model_combo.setToolTip('Ordinary-bond limits from Chemcraft b816bt. Explicit element-pair rules override these limits. Hydrogen bonds are controlled separately.')
        self.bond_model_combo.currentTextChanged.connect(lambda v: self._set_option('bond_model', v))
        form.addRow('Bond search', self.bond_model_combo)
        self.cutoff_slider = CenteredScaleSlider(10, 88, 500)
        self.cutoff_slider.setValue(round(self.render_options.bond_cutoff * 100))
        self.cutoff_slider.valueChanged.connect(lambda v: self._set_option('bond_cutoff', v / 100))
        self.cutoff_slider.setToolTip('Distance multiplier, 0.10–5.00. LELE defaults to ×0.88 of Chemcraft’s tabulated ordinary-bond limits. Changing this rebuilds automatic bonds; manual bonds and element-pair rules remain.')
        self.cutoff_spin=QDoubleSpinBox()
        self.cutoff_spin.setRange(.10,5.)
        self.cutoff_spin.setDecimals(2);self.cutoff_spin.setSingleStep(.05)
        self.cutoff_spin.setValue(self.render_options.bond_cutoff);self.cutoff_spin.setKeyboardTracking(False)
        self.cutoff_spin.setToolTip(self.cutoff_slider.toolTip())
        self.cutoff_spin.valueChanged.connect(lambda v:self._set_option('bond_cutoff',v))
        cutoff_row=QHBoxLayout();cutoff_row.addWidget(self.cutoff_slider,1);cutoff_row.addWidget(self.cutoff_spin)
        form.addRow('Bond cutoff ×',cutoff_row)
        self.bond_check = QCheckBox('Display bonds')
        self.bond_check.setChecked(True)
        self.bond_check.toggled.connect(lambda v: self._set_option('bonds', v))
        form.addRow(self.bond_check)
        self.hbond_check = QCheckBox('Automatic hydrogen bonds (dashed)')
        self.hbond_check.setChecked(False)
        self.hbond_check.toggled.connect(lambda v: self._set_option('hydrogen_bonds', v))
        form.addRow(self.hbond_check)
        bond_help = QLabel('Geometric N/O/F-H...N/O/F candidates only; '
                           'not part of the covalent fragment graph.')
        bond_help.setWordWrap(True)
        form.addRow(bond_help)
        manual_bond_help = QLabel('Ctrl+H draws/removes a manual dashed link '
                                  'between two selected atoms.')
        manual_bond_help.setWordWrap(True)
        form.addRow(manual_bond_help)
        self.cell_check = QCheckBox('Show unit cell')
        self.cell_check.setChecked(True)
        self.cell_check.toggled.connect(lambda v: self._set_option('unit_cell', v))
        form.addRow(self.cell_check)
        self.element_combo = PanelComboBox()
        self.element_combo.currentTextChanged.connect(self._sync_color_controls)
        form.addRow('Element', self.element_combo)
        self.element_color_btn = QPushButton('Edit element color…')
        self.element_color_btn.clicked.connect(self.pick_element_colour)
        form.addRow('Element color', self.element_color_btn)
        self.bg_btn = QPushButton('Background color…')
        self.bg_btn.clicked.connect(self.pick_background)
        form.addRow('Background color', self.bg_btn)
        dark_btn = QPushButton('Dark background')
        dark_btn.clicked.connect(lambda: self._set_option('background', '#131824'))
        form.addRow(dark_btn)
        light_btn = QPushButton('Light background')
        light_btn.clicked.connect(lambda: self._set_option('background', '#FFFFFF'))
        form.addRow(light_btn)
        display_outer.addWidget(group)
        display_outer.addStretch(1)

        axes_outer = control_page('Axes')
        axis_group = QGroupBox('Coordinate axes')
        axis_form = QFormLayout(axis_group)
        self.axes_position_combo = PanelComboBox()
        self.axes_position_combo.addItem('Hidden', 'Off')
        self.axes_position_combo.addItem('Bottom-left (VESTA style)', 'Corner')
        self.axes_position_combo.addItem('World origin (0, 0, 0)', 'Origin')
        self.axes_position_combo.setCurrentIndex(1)
        self.axes_position_combo.currentIndexChanged.connect(
            lambda _: self._set_option('axes_position', self.axes_position_combo.currentData()))
        axis_form.addRow('Position', self.axes_position_combo)
        self.axes_basis_combo = PanelComboBox()
        self.axes_basis_combo.addItem('Automatic (periodic abc / molecular XYZ)', 'Auto')
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
        self.label_combo = PanelComboBox()
        self.label_combo.addItems(LABEL_MODES)
        self.label_combo.currentTextChanged.connect(lambda v: self._set_option('labels', v))
        labels_form.addRow('Atom labels', self.label_combo)
        self.label_font_combo = PanelComboBox()
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
        self.label_color_btn = QPushButton('Label text color…')
        self.label_color_btn.clicked.connect(self.pick_label_colour)
        labels_form.addRow('Label text color', self.label_color_btn)

        labels_outer.addWidget(labels_group)
        labels_outer.addStretch(1)

        field_outer = control_page('Field')
        volume_group = QGroupBox('Volumetric fields / orbitals')
        volume_form = QFormLayout(volume_group)
        self._build_field_controls(volume_form)
        self.volume_check = QCheckBox('Show isosurfaces')
        self.volume_check.setChecked(True)
        self.volume_check.toggled.connect(lambda v: self._set_option('show_volume', v))
        self.surface_form.insertRow(0, self.volume_check)
        self.iso_spin = IsovalueSpinBox()
        self.iso_spin.setValue(.035)
        self.iso_spin.valueChanged.connect(lambda v: self._set_option('volume_iso', v))
        iso_row = QHBoxLayout()
        iso_row.addWidget(self.iso_spin)
        self.iso_apply_button = QPushButton('Apply')
        self.iso_apply_button.setFixedWidth(60)
        self.iso_apply_button.clicked.connect(self.iso_spin.interpretText)
        iso_row.addWidget(self.iso_apply_button)
        iso_row.addStretch(1)
        self.surface_form.insertRow(1, 'Positive / shared |isovalue|', iso_row)
        iso_hint = QLabel('Type a value (e.g. 1.25e-5), then Enter or Apply.')
        iso_hint.setWordWrap(True)
        self.surface_form.insertRow(2, iso_hint)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(round(self.render_options.volume_opacity * 100))
        self.opacity_slider.valueChanged.connect(lambda v: self._set_option('volume_opacity', v / 100))
        self.surface_form.insertRow(3, 'Positive / shared opacity', self.opacity_slider)
        field_outer.addWidget(volume_group)

        field_outer.addStretch(1)
        # Field now lives in the narrow sidebar: stack form labels above
        # editors, keeping scientific-number input and Apply fully visible.
        field_body = field_outer.parentWidget()
        compact_panel_editors(field_body)
        for field_form in field_body.findChildren(QFormLayout):
            field_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        for field_label in field_body.findChildren(QLabel):
            field_label.setWordWrap(True)

        edit_outer = control_page('Edit')
        measurements = QGroupBox('Geometry / atom selection')
        m_layout = QVBoxLayout(measurements)
        selection_help = QLabel('Click atoms to select; right-click an atom to edit its element, occupancy or index.\n'
                                'Ctrl+B toggles selected bonds.\n'
                                'Ctrl+H toggles a selected hydrogen bond (dashed).\n'
                                'Ctrl+G selects complete connected fragment(s).\n'
                                'Canvas: Ctrl+1–9 saves/replaces a fragment; 1–9 selects it; Shift+1–9 adds atoms.\n'
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
        self.rotate_axis_btn = QPushButton('Rotate about selected axis…')
        self.rotate_axis_btn.clicked.connect(self.rotate_about_selected_axis)
        self.rotate_axis_btn.setToolTip('Select axis atoms first, then optional moving fragment seeds, in that order.')
        m_layout.addWidget(self.rotate_axis_btn)
        self.dihedral_btn = QPushButton('Set selected dihedral…')
        self.dihedral_btn.clicked.connect(self.set_selected_dihedral)
        self.dihedral_btn.setToolTip('Select four atoms in order; rotate the last-side fragment around the middle bond.')
        m_layout.addWidget(self.dihedral_btn)
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
        self.align_combo = PanelComboBox()
        for axis in ('X', 'Y', 'Z', 'a', 'b', 'c'):
            self.align_combo.addItem(axis)
        self.align_btn = QPushButton('Align 1st → 2nd')
        self.align_btn.clicked.connect(self.align_selected_pair)
        alignment_row.addWidget(self.align_combo)
        alignment_row.addWidget(self.align_btn)
        m_layout.addLayout(alignment_row)
        alignment_help = QLabel('XYZ: periodic coordinates and cell rotate together.\n'
                                'a/b/c: rotate atoms within the fixed cell (changes crystal geometry).\n'
                                'The first selected atom remains fixed. Use Origin + X/Z to define both axes at once.')
        alignment_help.setWordWrap(True)
        m_layout.addWidget(alignment_help)
        self.reorient_btn=QPushButton('Set origin + X/Z axes…')
        self.reorient_btn.setToolTip('Select origin, X hint, Z in order, or enter atom indices. Uses a proper rotation of the complete crystal; also accepts a rotation matrix from the analyzer script.')
        self.reorient_btn.clicked.connect(self.configure_coordinate_reorientation)
        m_layout.addWidget(self.reorient_btn)
        self.vacuum_btn=QPushButton('Modify slab vacuum…');self.vacuum_btn.setEnabled(False)
        self.vacuum_btn.clicked.connect(self.configure_vacuum);m_layout.addWidget(self.vacuum_btn)
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
        from .plane_field_controls import PlaneFieldControls
        self.fitted_plane_controls = PlaneFieldControls(include_opacity=True)
        self.fitted_plane_controls.set_values(self.render_options.fitted_plane_style)
        self.fitted_plane_controls.valuesChanged.connect(self._set_fitted_plane_style)
        plane_layout.addWidget(self.fitted_plane_controls)
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

        self._set_frame_controls_enabled(False)
        self.toggle_bonds_btn.setEnabled(False)
        self.toggle_hbond_btn.setEnabled(False)
        self.toggle_hbond_action.setEnabled(False)
        self.fragment_btn.setEnabled(False)
        self.origin_btn.setEnabled(False)
        self.align_btn.setEnabled(False)
        self.reorient_btn.setEnabled(False)
        self.invert_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self._install_restored_controls()
        self._install_crystal_controls()
        self._init_document_views()
        self._install_project_actions()
        self._install_annotation_actions()
        self._sync_color_controls()
        compact_panel_sliders(sidebar_tabs, self.bottom_control_tabs)
        compact_panel_editors(self.bottom_control_tabs)
        root.setStretchFactor(0, 0)
        root.setStretchFactor(1, 1)
        root.setSizes([SIDEBAR_MIN_WIDTH, max(1, self.width() - SIDEBAR_MIN_WIDTH - root.handleWidth())])

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
        if hasattr(self.vtk,'atomContextClick'):self.vtk.atomContextClick.connect(self._atom_context_from_canvas)
        if hasattr(self.vtk,'rectangleSelected'):
            self.vtk.rectangleSelected.connect(self._rectangle_selected)
            self.vtk.set_box_selection(self.box_select_action.isChecked() or self.surface_hide_check.isChecked())
        self.vtk.clearSelectionClick.connect(self._right_click_clear)
        self.vtk.fragmentGestureBegin.connect(self._fragment_begin)
        self.vtk.fragmentGestureMove.connect(self._fragment_move)
        self.vtk.fragmentGestureEnd.connect(self._fragment_end)
        if hasattr(self.vtk, 'fragmentSlotRequested'):
            self.vtk.fragmentSlotRequested.connect(self.fragment_slot_shortcut)
        self.axes_widget = vtkOrientationMarkerWidget()
        self.axes_widget.SetInteractor(self.vtk.GetRenderWindow().GetInteractor())
        self.axes_widget.SetViewport(0.015, 0.015, 0.225, 0.225)
        self.structure_page.insertWidget(0, self.vtk)
        self.structure_page.setSizes([660, 190])

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
        filenames, _ = QFileDialog.getOpenFileNames(self, 'Open calculation or structure files', '',
            'All files (*);;XCrySDen structures and scalar grids (*.xsf *.XSF);;CP2K input / restart (*.inp *.restart *.restart.bak-*);;CP2K output (*.out *.log *.xyz *.mol)')
        self.open_paths(filenames)

    def open_paths(self, filenames):
        """Queue a whole request so discovery and sorting precede imports."""
        from .import_paths import ImportBatch
        if filenames:
            self.open_path(ImportBatch(tuple(filenames)))

    def assign_qe_phonon_reference(self):
        if self.doc is None or not getattr(self.doc.calculation_results,'phonon_sets',None):
            QMessageBox.information(self,'QE phonons','Open a QE PHONON output or normalized .modes file first.');return
        from .qe_reference_dialog import QeReferenceDialog
        from .qe_phonons import bind_qe_phonons
        dialog=QeReferenceDialog(self,self.doc)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if dialog.reference() is None:return
        try:
            document=bind_qe_phonons(self.doc,dialog.reference(),dialog.alat.value(),dialog.reference_name())
        except ValueError as exc:
            QMessageBox.warning(self,'QE reference mismatch',str(exc));return
        self._attach_loaded_document(document)

    def open_path(self, filename):
        if self._closing:
            return
        if getattr(self, '_batch_exporting', False):
            self.statusBar().showMessage('Finish or cancel the batch export before opening files.', 5000)
            return
        if self._backend_state != 'ready':
            self._pending_open_paths.append(filename)
            if self._backend_state == 'failed':
                self._start_backend_loading()
            elif self._startup_painted and self._backend_state == 'waiting':
                self._backend_start_timer.start(0)
            self.statusBar().showMessage('Loading components… The selected file will open when ready.')
            return
        self._open_or_queue_file(filename)

    def _open_path_now(self, filename):
        if Path(filename).suffix.lower() == '.lele':
            return self._load_project_path(filename)
        try:
            from .formats import load_document
            new_doc = run_data_task(self,'Loading '+Path(filename).name,lambda:load_document(filename),cancellable=True)
            if not self._closing:
                self._attach_loaded_document(new_doc)
        except LoadCancelled:return
        except Exception as ex:
            self._show_file_load_error(filename, str(ex))
            return

    @gui_operation('Preparing structure view')
    def _attach_loaded_document(self, new_doc):
        index = len(self.documents)
        self.documents.append(new_doc)
        self._add_document_tree(index, new_doc)
        self.change_frame(max(0, len(new_doc.frames) - 1), switch_doc=index, reset_camera=True)
        modes = sum(len(a.modes) for a in new_doc.vibrations)
        suffix = f' • {modes} vibrational modes' if modes else ''
        detail=(f'{len(new_doc.frames)} frame(s) • {len(new_doc.frames[0].symbols)} atoms' if new_doc.frames else 'calculation results • no structure')
        self.statusBar().showMessage(f'Opened {new_doc.path.name} • {detail}{suffix}')

    @gui_operation('Preparing file tree')
    def _add_document_tree(self, index, new_doc):
        from .energy_units import display_energy
        head = QTreeWidgetItem([self._document_heading(new_doc)])
        head.setToolTip(0, str(new_doc.path))
        head.setData(0, Qt.ItemDataRole.UserRole, (index, max(0, len(new_doc.frames) - 1)))
        self.files_tree.addTopLevelItem(head)
        if not getattr(self,'_lazy_tree_connected',False):
            from .workflow_ui import expand_tree_item
            self.files_tree.itemExpanded.connect(expand_tree_item)
            self.files_tree.setUniformRowHeights(True)
            self._lazy_tree_connected=True
        from .workflow_ui import populate_tree, populate_energy_steps
        populate_energy_steps(self, index, new_doc, head)
        if not new_doc.frames:
            head.setExpanded(True)
            return
        if populate_tree(self,index,new_doc,head):return
        geometry_parent = head
        if new_doc.vibrations:
            label = ('Frequency calculation structures' if new_doc.calculation_results is not None
                     and new_doc.calculation_results.program == 'VASP' else 'Geometry / optimization')
            geometry_parent = QTreeWidgetItem([f'{label} ({len(new_doc.frames)} frames)'])
            geometry_parent.setData(0, Qt.ItemDataRole.UserRole, (index, len(new_doc.frames) - 1))
            head.addChild(geometry_parent)
        if len(new_doc.frames) > 1 or new_doc.vibrations:
            from .workflow_ui import add_frame_items
            add_frame_items(self,index,new_doc,geometry_parent,range(len(new_doc.frames)))
        else:
            self._frame_tree_items[index, 0] = head
        for analysis_index, analysis in enumerate(new_doc.vibrations):
            imaginary = sum(mode.imaginary for mode in analysis.modes)
            title = analysis.purpose or ('Frequencies' if len(new_doc.vibrations) == 1 else f'Frequencies {analysis_index + 1}')
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
                    details.append(f'IR intensity: {mode.ir_intensity:.4f} {mode.ir_intensity_unit}')
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
                self._show_results_only()
                with QSignalBlocker(self.files_tree): self.files_tree.setCurrentItem(item)
                return
            if len(data)>1 and data[1]=='series':
                doc_index,_,indices,position,label=data
                indices=self._tree_sequences[indices]
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
            if item.parent() is None:
                # The file heading returns to its last viewed frame. A child
                # geometry node still requests that explicit frame.
                state = self._document_views.get(id(self.documents[doc_index]))
                if doc_index == self.current_doc:
                    frame_index = self.frame_index
                elif state is not None:
                    frame_index = state.frame_index
            self.change_frame(frame_index, switch_doc=doc_index)

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

    @gui_operation('Preparing structure frame')
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
            from .workflow_ui import frame_tree_item
            target=frame_tree_item(self,self.current_doc,sequence,self.frame_index,head)
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
        self.axes_basis_combo.model().item(self.axes_basis_combo.findData('abc')).setEnabled(has_cell)
        if not has_cell and self.axes_basis_combo.currentData() == 'abc':
            self.axes_basis_combo.setCurrentIndex(self.axes_basis_combo.findData('XYZ'))
        self._set_frame_controls_enabled(len(sequence) > 1)
        self.play_btn.setEnabled(len(sequence) > 1)
        self.refresh_scene(reset_camera=reset_camera)
        self._refresh_coordinates()
        self._sync_selection_to_table()
        self._refresh_info()
        self._update_gif_action()
        self._refresh_frame_tree_label()

    def show_frequencies(self):
        if self.doc is not None and not self.doc.vibrations and getattr(self.doc.calculation_results,'phonon_sets',None):
            self.assign_qe_phonon_reference();return
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
            reference_line=source_analysis.reference.info.get('vasp_reference_source_line')
            matches=[i for i,f in enumerate(source_doc.frames) if f.symbols==source_analysis.reference.symbols
                     and (f.info.get('source_line')==reference_line if reference_line is not None else
                          np.allclose(f.positions,source_analysis.reference.positions,atol=2.e-6,rtol=0))]
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
        if hasattr(mode,'qpoint'):description+='\n'+analysis.purpose
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
        if ui_busy():return
        if self._active_vibration is None:
            return
        from math import tau
        elapsed = self._vibration_clock.restart() / 1000.
        self._vibration_phase = (self._vibration_phase + elapsed * tau
                                 * self.vibration_controls.speed.value()) % tau
        self._render_vibration()

    def _vibration_preview(self):
        _, analysis, mode = self._active_vibration
        return self.doc.vibrations[analysis].modes[mode].preview_frame(
            self.frame,self._vibration_phase,self.vibration_controls.amplitude.value(),self.render_options.bond_cutoff)

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
        from .operations import ui_operation
        with ui_operation(self,'Updating coordinate table'):
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
                        from .operations import ui_checkpoint
                        ui_checkpoint('Building coordinate table',i,len(rows))
                        for j, value in enumerate(row):
                            item = self.atom_table.item(i, j)
                            if item is None:
                                item = QTableWidgetItem()
                                self.atom_table.setItem(i, j, item)
                            item.setText(value)
                            from .site_occupancy import description,site_is_disordered
                            item.setToolTip(f'Site #{i+1} · Occupancy: '+description(frame,i)+
                                            ('\n* Mixed / partial occupancy; X/Y/Z locate this site.' if site_is_disordered(frame,i) else ''))
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
            from .site_occupancy import occupied_elements
            choices = occupied_elements(frame)
            self.element_combo.addItems(choices)
            if choices:
                self.element_combo.setCurrentText(previously if previously in choices else choices[0])
        self._sync_color_controls()

    def _refresh_after_geometry_edit(self,*,preserve_results=False):
        """Publish new coordinates, selection, rendering and document details."""
        if getattr(self, 'renderer', None) is not None:
            self.renderer.periodic_preview = None
        if getattr(self,'undo_stack',None) and not preserve_results:
            old=self.undo_stack[-1]
            if old[0:2]==(self.current_doc,self.frame_index):
                from .energy_units import rigid_equivalent
                if not rigid_equivalent(old[2],self.frame):
                    self.frame.energy_ev=None;self.frame.info.pop('energy_source',None)
                    self.frame.info.pop('optimization_converged',None)
                    if str(self.frame.info.get('source_kind','')).startswith('qe'):
                        for key in ('qe_total_energy_ry','qe_energy_source_line','qe_forces_ev_ang',
                                    'cartesian_max_force_ev_ang','cartesian_rms_force_ev_ang'):
                            self.frame.info.pop(key,None)
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

    @gui_operation('Analyzing structure')
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
                from .energy_units import program_energy_unit
                step = doc.calculation_results.steps[self._energy_only_context[1]]
                cycle = step.cycle if step.cycle is not None else self._energy_only_context[1]+1
                if doc.calculation_results.program == 'VASP':
                    from .vasp_results import energy_lines
                    energy_text = '\n'.join(energy_lines(step.info))+'\n'
                elif program_energy_unit(doc.calculation_results.program) == 'eV':
                    energy_text = f'Energy: {step.energy_ev:.9f} eV\n'
                else:
                    energy_text = (f'Energy: {step.energy_ev/Hartree:.12f} Eh\n'
                                   f'        {step.energy_ev:.9f} eV\n'
                                   f'        {step.energy_ev*23.0605478306:.8f} kcal/mol\n')
                text = (f'Selected energy step: {cycle}\n'+energy_text+
                        f'Source line: {step.source_line}\nNo structure for this energy record.\n\n' + text)
            self.results_only_title.setText(doc.path.name+' · calculation results')
            self.results_only_info.setPlainText(text);self.info_view.setPlainText(text)
            self.summary_label.setText('No structure in this file')
            return
        from .site_occupancy import composition,is_disordered
        from .chemical_analysis import electron_parity
        from .periodic_geometry import short_contacts
        lines = [f'File: {doc.path}', f'Reader: {doc.format_name}',
                 ('View: frequency reference geometry' if self._active_vibration is not None
                  else f'Frame: {self.frame_index + 1} of {len(doc.frames)}'),
                 f'Atoms: {len(frame.symbols)}', f'Periodic flags: {frame.pbc}']
        if doc.nmr_results:
            lines.append(f'NMR: {len(doc.nmr_results)} dataset(s) · Analysis → NMR spectrum / shielding table')
        if is_disordered(frame):
            lines.append('Occupancy-weighted composition: '+composition(frame))
            lines.append('Fractional occupancies describe average sites; bonding uses the representative species, not a uniquely ordered microscopic configuration.')
        if frame.info.get('composition_edited'):
            lines.append('Elements / occupancies edited. Source calculation results refer to the original composition.')
        if frame.info.get('vacuum_adjustment'):
            data=frame.info['vacuum_adjustment'];lines.append(f'Last vacuum spacing: {data["gap"]:.6f} → {data["new_gap"]:.6f} Å (atomic-plane convention; Cartesian coordinates unchanged)')
        if doc.trajectory_link:
            if 'linked_step' in frame.info:
                lines.append(f'Calculation step: {frame.info["linked_step"]}')
            if 'trajectory_frame' in frame.info:
                lines.append(f'Position trajectory: {Path(doc.trajectory_link["path"]).name}, frame {frame.info["trajectory_frame"]}')
            for key, label in (('time_fs', 'Time (fs)'), ('cp2k_md_temperature_K', 'Temperature (K)'),
                               ('cp2k_md_kinetic_hartree', 'Kinetic energy (Eh)'),
                               ('cp2k_md_conserved_hartree', 'Conserved quantity (Eh)'),
                               ('xtb_trajectory_gnorm', 'Trajectory gradient norm (Eh/bohr)')):
                if key in frame.info:
                    lines.append(f'{label}: {frame.info[key]:.10g}')
        if frame.info.get('series_label'):lines.insert(2,'Result series: '+frame.info['series_label'])
        if frame.info.get('optimization_converged'):lines.append('Geometry optimization: converged')
        if doc.calculation_results is not None and doc.calculation_results.program == 'CP2K':
            from .cp2k_results import summary_lines
            job_index = frame.info.get('calculation_index', 0)
            if isinstance(job_index, int) and 0 <= job_index < len(doc.calculation_results.jobs):
                job = doc.calculation_results.jobs[job_index]
                lines.extend(['Source calculation (CP2K):',
                              'Task: ' + (' / '.join(sorted(job.tasks)) or 'Not printed'),
                              'Method: ' + (job.method or 'Not printed'),
                              'Basis: ' + (job.basis or 'Not printed'),
                              'Charge: ' + (str(job.charge) if job.charge is not None else 'Not printed'),
                              'Multiplicity: ' + (str(job.multiplicity) if job.multiplicity is not None else 'Not printed'),
                              'Termination: ' + (job.termination or 'Not printed')])
                lines.extend(summary_lines(doc.calculation_results, job.index))
                if job.scf_cycles is not None:
                    lines.append(f'Last SCF cycles: {job.scf_cycles}')
        if 'stage_index' in frame.info and doc.calculation_results is not None:
            stages=getattr(doc.calculation_results,'stages',[])
            stage_index=frame.info['stage_index']
            if isinstance(stage_index,int) and 0<=stage_index<len(stages):
                stage=stages[stage_index]
                lines.insert(2,'Stage: '+stage.name+' · '+stage.status)
        from .energy_units import display_energy
        energy,unit=display_energy(frame,doc.format_name)
        if energy is not None:
            if doc.calculation_results is not None and doc.calculation_results.program == 'VASP':
                lines.append(f'E0 (σ→0): {energy:.9f} {unit}')
            else:lines.append(f"Energy: {energy:.8f} {unit} ({frame.info.get('energy_source','reader result')})")
            if 'qe_total_energy_ry' in frame.info:lines.append(f'QE source total energy: {frame.info["qe_total_energy_ry"]:.10f} Ry')
        if frame.info.get('source_kind') in ('vasp_out', 'vasp_xdatcar'):
            if 'vasp_nelect' in frame.info:lines.append(f'Valence electrons (NELECT): {frame.info["vasp_nelect"]:g}')
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
                lines.append(f'  {n}: '+(analysis.purpose+' · ' if analysis.purpose else '')+f'{len(analysis.modes)} modes, '
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
        reorientation=frame.info.get('coordinate_reorientation')
        if reorientation is not None:
            lines.append('\nLast coordinate reorientation: r_new = (r_old + image_shift @ cell_old) @ Q + t')
            lines.append('Q (row vectors; cell_new = cell_old @ Q):')
            lines.extend('  '+' '.join(f'{v: .12f}' for v in row) for row in reorientation['row_rotation'])
            lines.append('Translation (Å): '+', '.join(f'{v:.12f}' for v in reorientation['translation']))
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
            f'{system} {composition(frame)}  |  '
            f'electrons {parity.split()[0].lower()}  |')
        self.summary_label.setToolTip(
            f'Electron parity: {parity}\nComposition and counts refer to the active source geometry.')
        count, _ = short_contacts(frame)
        self.short_contacts_button.setText(f'Short contacts {count}')
        self.short_contacts_button.setEnabled(True)
        self._align_summary_footer()

    def _align_summary_footer(self):
        from shiboken6 import isValid
        if not isValid(self):return
        if not hasattr(self,'footer_row') or self.footer_row.isHidden():return
        from PySide6.QtCore import QPoint
        # A resize can deliver several events before QStatusBar applies its
        # pending layout. Never accumulate a correction against stale geometry.
        self._summary_status_bar.layout().activate()
        target=self.lower_splitter.mapToGlobal(QPoint(0,0)).x()
        current=self.footer_row.mapToGlobal(QPoint(0,0)).x()
        if abs(target-current)>1:
            self.status_message_label.setFixedWidth(max(0,self.status_message_label.width()+target-current))
            self._summary_status_bar.layout().activate()

    def _queue_summary_alignment(self):
        timer=getattr(self,'_footer_alignment_timer',None)
        if timer is not None and not timer.isActive():timer.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._queue_summary_alignment()

    def show_short_contacts(self):
        if self.frame is None:
            return
        from .short_contacts_dialog import ShortContactsDialog
        context = f'{self.doc.path.name} · Frame {self.frame_index+1}'
        if self._active_vibration is not None:
            context = f'{self.doc.path.name} · Frequency reference {self._active_vibration[1]+1}'
        return self._show_analysis_window(ShortContactsDialog(self.frame, context, self))

    @gui_operation('Updating structure view')
    def refresh_scene(self, reset_camera=False):
        available = any(document.frames for document in self.documents)
        self.convert_all_action.setEnabled(available and not self._batch_exporting)
        self.export_png_all_action.setEnabled(available and not self._batch_exporting)
        from .camera_views import refresh_crystal_view_actions
        refresh_crystal_view_actions(self)
        from .stm import can_simulate_stm
        from .core import valid_lattice
        self.stm_action.setEnabled(self.doc is not None and can_simulate_stm(self.doc))
        self.xrd_action.setEnabled(self.frame is not None and bool(self.frame.symbols)
                                   and all(self.frame.pbc) and valid_lattice(self.frame))
        self.save_project_action.setEnabled(bool(self.documents));self.save_project_as_action.setEnabled(bool(self.documents))
        self._refresh_trajectory_controls()
        self._refresh_field_controls()
        self._prepare_analysis_scene()
        self._update_fitted_plane()
        self.orbital_btn.setEnabled(bool(self.doc is not None and self.doc.calculation_results
                                        and self.doc.calculation_results.orbitals))
        self.results_orbital_button.setEnabled(self.orbital_btn.isEnabled())
        self.results_spectrum_button.setEnabled(bool(self.doc is not None and self.doc.electronic_spectra))
        self.results_transition_button.setEnabled(self.results_spectrum_button.isEnabled())
        self.nmr_action.setEnabled(bool(self.doc is not None and self.doc.nmr_results))
        self.results_nmr_button.setEnabled(self.nmr_action.isEnabled())
        from .result_availability import has_curve_data
        available=has_curve_data(self.doc)
        self.energy_curve_action.setEnabled(available);self.results_energy_button.setEnabled(available)
        doc=self.doc
        scan_available = bool(doc is not None and doc.calculation_results is not None
                              and getattr(doc.calculation_results, 'scans', []))
        self.scan_action.setEnabled(scan_available)
        self.scan_curve_button.setEnabled(scan_available)
        for action,available in ((self.neb_action,doc is not None and bool(doc.neb_runs)),
                                 (self.goat_action,doc is not None and bool(doc.conformer_ensembles)),
                                 (self.soc_action,doc is not None and bool(doc.soc_results)),
                                 (self.hessian_action,doc is not None and doc.calculation_results is not None and bool(doc.calculation_results.hessians))):
            action.setEnabled(bool(available))
        self.orca_results_btn.setEnabled(any(a.isEnabled() for a in (self.neb_action,self.goat_action,self.soc_action,self.hessian_action)))
        if self.frame is None:
            self.supercell_action.setEnabled(False)
            self._refresh_atom_panel()
            self._refresh_crystal_controls()
            self._sync_annotations()
            return
        from .core import valid_lattice
        self.supercell_action.setEnabled(bool(self.frame.symbols) and any(self.frame.pbc)
            and valid_lattice(self.frame) and self._active_vibration is None)
        self.render_options.show_volume = bool(self.volume_check.isChecked())
        self._refresh_properties()
        self.renderer.selected = list(self.selection)
        from .boundary_selection import selected_images
        images = selected_images(self)
        self.renderer.selected_image_positions = (
            [(item.index, item.position(self.frame)) for item in images]
            if getattr(self, '_selected_atom_images', None) is not None else None)
        if self._active_vibration is not None:
            from .core import visible_bonds
            self.renderer.fixed_bonds = visible_bonds(self.frame, self.render_options.bond_cutoff)
            self.renderer.set_scene(self._vibration_preview(), None, reset_camera=False)
        else:
            self.renderer.fixed_bonds = None
            scene_frame = self.frame
            preview = getattr(self, '_rotation_preview', None)
            if preview is not None:
                scene_frame = preview.frame_for_scene(scene_frame)
            try:self.renderer.set_scene(scene_frame, self.doc.volume, reset_camera=False, volumes=self.doc.volumes)
            except ValueError as ex:
                if not self.render_options.boundary_enabled:raise
                self.render_options.boundary_enabled=False
                self.boundary_panel.set_values(False,self.render_options.boundary_bounds)
                self.renderer.set_scene(scene_frame,self.doc.volume,reset_camera=False,volumes=self.doc.volumes)
                self.statusBar().showMessage('Boundary disabled for this frame: '+str(ex),7000)
        self._refresh_isosurface_style_controls()
        if self.renderer.field_warnings:
            self.field_note.setText(self.field_note.text()+'\n'+'\n'.join(dict.fromkeys(self.renderer.field_warnings)))
        self._sync_annotations()
        self._apply_document_camera(reset_camera)
        self._refresh_crystal_controls()
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
        from .site_occupancy import site_species
        from .atom_appearance import appearance
        component_colors={(i,symbol):appearance(self.frame,i).color or self.renderer._display_color(symbol)
                          for i in range(len(self.frame.symbols)) for symbol in site_species(self.frame,i)}
        self.atom_panel.set_frame(self.frame, colors, self.selection, component_colors=component_colors,document_key=id(self.doc))

    def _atom_panel_selected(self, indices):
        if self.frame is None:
            return
        self._selected_atom_images = None
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

    def _set_fitted_plane_style(self, values):
        from .plane_field import validate_plane_style
        try:
            style = validate_plane_style(values)
        except (ValueError, TypeError) as exc:
            self.statusBar().showMessage(str(exc), 6000)
            return
        self.render_options.fitted_plane_style = style
        if self.frame is not None:self.refresh_scene()

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
        self.custom_font_btn.setToolTip('Choose a TTF/OTF font file')
        self._set_option('label_font', text)

    def _select_label_font_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Select font file (not bundled into EXE)', '',
            'Font files (*.ttf *.otf);;All files (*)')
        if path:
            self.render_options.label_font_file = path
            self.custom_font_btn.setText('Font file: ' + Path(path).name)
            self.custom_font_btn.setToolTip(path)
            self.refresh_scene()

    def pick_label_colour(self):
        picked = QColorDialog.getColor(QColor(self.render_options.label_color),
                                       self, 'Atom label text color')
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
                    self.finish_combo, self.bond_check, self.sf_radii_combo]
        blockers = [QSignalBlocker(widget) for widget in controls]
        try:
            self.style_combo.setCurrentText(opts.style)
            self.atom_slider.setCenter(100 if opts.style == 'Space filling' else 45)
            self.atom_slider.setValue(round((opts.space_filling_scale if opts.style == 'Space filling' else opts.atom_scale) * 100))
            self.sf_radii_combo.setCurrentText(opts.space_filling_radii)
            self.sf_radii_combo.setEnabled(opts.style == 'Space filling')
            self.bond_slider.setValue(opts.bond_scale * 100)
            self.atom_palette_combo.setCurrentText(opts.atom_palette)
            self.bond_palette_combo.setCurrentText(opts.bond_palette)
            self.finish_combo.setCurrentText(opts.surface_finish)
            self.bond_check.setChecked(opts.bonds)
        finally:
            del blockers
        self._sync_color_controls()

    def _sync_color_controls(self, *_):
        opts = self.render_options
        if hasattr(self, 'bg_btn'):
            set_color_swatch(self.bg_btn, opts.background, 'Background color')
        if hasattr(self, 'label_color_btn'):
            set_color_swatch(self.label_color_btn, opts.label_color, 'Label text color')
        if hasattr(self, 'element_color_btn'):
            from .style_presets import element_palette_color
            symbol = self.element_combo.currentText()
            set_color_swatch(self.element_color_btn,
                             element_palette_color(opts, symbol) if symbol else None,
                             (symbol + ' color') if symbol else 'Element color')
            self.element_color_btn.setEnabled(bool(symbol))

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
        previous=getattr(self.render_options,option)
        setattr(self.render_options, option, value)
        if option == 'style':
            self._sync_style_widgets()
        if option in STYLE_KEYS:
            self._custom_style_state = snapshot(self.render_options)
            with QSignalBlocker(self.preset_combo):
                self.preset_combo.setCurrentIndex(self.preset_combo.findData(CUSTOM_KEY))
        if option in ('background', 'label_color', 'element_colors', 'atom_palette'):
            self._sync_color_controls()
        if option in ('bond_cutoff', 'bond_model'):
            if option == 'bond_model':
                value = RenderOptions().bond_cutoff if value == 'Chemcraft pair ranges' else 1.18
                self.render_options.bond_cutoff = value
            with QSignalBlocker(self.cutoff_slider):
                self.cutoff_slider.setCenter(118 if self.render_options.bond_model == 'Covalent radii' else 88)
                self.cutoff_slider.setValue(round(value * 100))
            with QSignalBlocker(self.cutoff_spin):self.cutoff_spin.setValue(value)
            if (value!=previous or option == 'bond_model') and self.doc is not None:
                # An explicit cutoff change is an explicit graph rebuild.
                # Ordinary geometry edits continue to preserve frozen bonds.
                frames = [*self.doc.frames,*[a.reference for a in self.doc.vibrations],
                          *[f for (di,_),f in self._vibration_references.items() if di==self.current_doc]]
                with ui_operation(self, 'Rebuilding automatic bonds'):
                    for index, frame in enumerate(frames):
                        frame.info['bond_model'] = self.render_options.bond_model
                        frame.bond_snapshot=frame.periodic_bond_snapshot=None
                        if index % 256 == 0:ui_checkpoint('Rebuilding automatic bonds', value=index, total=len(frames))
                note='Automatic bonds rebuilt for the new cutoff; manual bonds retained.'
                if self.render_options.element_pair_rules:
                    note+=' Explicit element-pair rules keep their own distance ranges.'
                self.statusBar().showMessage(note,6500)
            if self.renderer is not None:
                self.renderer.periodic_preview = None;self.renderer.fixed_bonds=None
        if self.frame is not None:
            self.refresh_scene()

    def pick_element_colour(self):
        symbol = self.element_combo.currentText()
        if not symbol:
            return
        colors = self.render_options.element_colors
        from .style_presets import element_palette_color
        picked = QColorDialog.getColor(QColor(element_palette_color(self.render_options,symbol)),
                                       self, f'{symbol} color')
        if picked.isValid():
            self._set_option('element_colors', {**colors, symbol: picked.name()})

    def pick_background(self):
        current = QColor(self.render_options.background)
        picked = QColorDialog.getColor(current, self, 'Background color')
        if picked.isValid():
            self._set_option('background', picked.name())

    def _pick_from_canvas(self, x: float, y: float):
        """Handle a *native Qt* click. Convert logical pixels for high-DPI VTK."""
        if self.frame is None:
            return
        if self._pick_annotation_from_canvas(x, y):return
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
        from .boundary_selection import toggle_atom_image, image_label
        image = toggle_atom_image(self, picked, getattr(self.renderer, 'last_pick_position', None))
        self._sync_selection_to_table(preserve_images=True)
        self.refresh_scene()
        self.statusBar().showMessage(f'Atom {image_label(self.frame, image)}', 2500)

    def _sync_selection_to_table(self, *, preserve_images=False):
        if not preserve_images:
            self._selected_atom_images = None
            self._selected_atom_image_frame = None
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

    def _coordinate_atom_activated(self,item):
        if self.frame is None or item.column()!=0:return
        index=item.row()
        if not 0<=index<len(self.frame.symbols):return
        self.selection=[index]
        self.renderer.periodic_preview=None
        self._sync_selection_to_table();self.refresh_scene()
        self.sidebar_tabs.setCurrentWidget(self.atom_panel)
        self.atom_panel.reveal_atom(index)

    def _create_settings_window(self,panel,title,width=600,height=600):
        dialog=QDialog(self);dialog.setWindowTitle(title);dialog.resize(width,height)
        layout=QVBoxLayout(dialog)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel)
        layout.addWidget(scroll)
        # Enter commits a numeric edit; it must not activate an export/apply button.
        for button in panel.findChildren(QPushButton):button.setAutoDefault(False);button.setDefault(False)
        return dialog

    @staticmethod
    def _show_settings_window(dialog):
        show_dialog(dialog)

    def _table_selected(self):
        if self._ignore_table or self.frame is None:
            return
        self._selected_atom_images = None
        rows = [x.row() for x in self.atom_table.selectionModel().selectedRows()]
        # QTableWidget selection is unordered; retain prior click order where
        # possible so the first->second alignment direction stays predictable.
        self.selection = [i for i in self.selection if i in rows] + [i for i in rows if i not in self.selection]
        self.renderer.periodic_preview = None
        self.refresh_scene()

    def _refresh_measurement(self):
        self._refresh_selection_panels()
        frame = self.frame
        n = len(self.selection)
        editable = frame is not None and self._active_vibration is None and not self._alignment_enabled()
        self.toggle_bonds_btn.setEnabled(editable and n >= 2)
        self.toggle_hbond_btn.setEnabled(editable and n == 2)
        self.toggle_hbond_action.setEnabled(editable and n == 2)
        self.fragment_btn.setEnabled(frame is not None and n > 0)
        self.origin_btn.setEnabled(editable and n == 1)
        self.align_btn.setEnabled(editable and n == 2)
        self.reorient_btn.setEnabled(editable and bool(frame.symbols))
        self.reorient_action.setEnabled(self.reorient_btn.isEnabled())
        self.rotate_axis_action.setEnabled(editable and n >= 2)
        self.rotate_axis_btn.setEnabled(self.rotate_axis_action.isEnabled())
        self.dihedral_action.setEnabled(editable and n == 4)
        self.dihedral_btn.setEnabled(self.dihedral_action.isEnabled())
        from .core import valid_lattice
        vacuum_ok=editable and any(frame.pbc) and valid_lattice(frame) if frame is not None else False
        self.vacuum_action.setEnabled(vacuum_ok);self.vacuum_btn.setEnabled(vacuum_ok)
        self.invert_btn.setEnabled(frame is not None and bool(frame.symbols))
        self.delete_btn.setEnabled(editable and n > 0)
        self.measurement_label.clear()
        self.measurement_value.hide();self.measurement_set.hide()
        self._measurement_context=None;self._measurement_pending=False
        self.footer_row.setVisible(frame is not None)
        self._status_message_changed(self.statusBar().currentMessage())
        if frame is None or not self.selection:
            self.selected_label.setText('No atoms selected')
            return
        from .boundary_selection import selected_images, image_label, image_measurement, image_editable
        images = selected_images(self)
        atoms = [image_label(frame, item) for item in images]
        measurement_count = len(images)
        measurement_editable = editable and image_editable(images)
        label = f'{measurement_count} selected: ' + ' — '.join(atoms[:12])
        if measurement_count > 12:
            label += f' … (+{measurement_count - 12} more)'
        if 2 <= measurement_count <= 4:
            try:
                quantity, value = image_measurement(frame, images)
                units = 'Å' if quantity == 'distance' else '°'
                label += f'\n{quantity}: {value:.4f} {units}'
                name = {'distance': 'Bond length', 'angle': 'Bond angle', 'dihedral': 'Dihedral'}[quantity]
                self.measurement_label.setText(f'{name}  {"—".join(atoms)}')
                self.measurement_label.setToolTip('Index (1-based), [a,b,c] lattice image: ' + ' — '.join(atoms))
                with QSignalBlocker(self.measurement_value):
                    self.measurement_value.setRange(0., max(10000.,value*2) if quantity=='distance' else 180.)
                    if quantity=='angle':self.measurement_value.setRange(0.,180.)
                    elif quantity=='dihedral':self.measurement_value.setRange(-180.,180.)
                    self.measurement_value.setSuffix(' '+units)
                    self.measurement_value.setValue(value)
                    self.measurement_value.setSingleStep(.01 if quantity=='distance' else 1.)
                self.measurement_value.setEnabled(editable)
                self.measurement_value.setReadOnly(not measurement_editable)
                self.measurement_value.setButtonSymbols(
                    QDoubleSpinBox.ButtonSymbols.UpDownArrows if measurement_editable else QDoubleSpinBox.ButtonSymbols.NoButtons)
                self.measurement_set.setEnabled(measurement_editable)
                self.measurement_value.show();self.measurement_set.setVisible(measurement_editable)
                self._measurement_context=(id(self.doc),self.frame_index,tuple(self.selection))
            except (ValueError, IndexError):
                self.measurement_label.setText('Selected geometry undefined')
        self.selected_label.setText(label)

    def _status_message_changed(self,text):
        label=self.status_message_label
        label.setVisible(not self.footer_row.isHidden())
        label.setText(label.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,label.width()-10))
        label.setToolTip(text)

    def _measurement_value_changed(self,_value):
        self._measurement_pending=True

    def _apply_measurement_value(self):
        if not self._measurement_pending:return
        self._measurement_pending=False
        context=(id(self.doc),self.frame_index,tuple(self.selection))
        if context!=self._measurement_context or self.frame is None or not self._geometry_edit_allowed():
            self._refresh_measurement();return
        from .boundary_selection import selected_images, image_editable
        if not image_editable(selected_images(self)):
            self._refresh_measurement();return
        from .core import measure
        from .internal_coordinates import plan_internal_edit
        value=self.measurement_value.value()
        try:
            quantity,current=measure(self.frame,self.selection)
            if abs(value-current)<.00005:return
            edit=plan_internal_edit(self.frame,self.selection,value,self.render_options.bond_cutoff)
        except (ValueError,IndexError) as exc:
            QMessageBox.warning(self,'Cannot change selected geometry',str(exc))
            self._refresh_measurement();return
        self.playback.stop();self.play_btn.setText('Play')
        self._record_undo()
        self.frame.positions[:]=edit.positions
        if edit.periodic_edges is not None:self.frame.periodic_bond_snapshot=edit.periodic_edges
        self.frame.hbond_added=edit.hbond_added
        self.doc.modified=True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(f'Set {quantity} to {value:.4f}; moved {len(edit.moving)} atom(s). Ctrl+Z to undo.',6000)

    def _right_click_clear(self):
        if self.selection or self._selected_annotation is not None:
            self.clear_selection()
            self.statusBar().showMessage('Atom selection cleared', 2500)

    def clear_selection(self):
        if hasattr(self, '_selected_annotation'):
            self._clear_annotation_selection()
        self.selection.clear()
        self._selected_atom_images = None
        self._selected_atom_image_frame = None
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
        if self.delete_canvas_text():
            return
        if self.surface_hide_check.isChecked():
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
        old = self._fragment_gesture
        if old is not None and old.get('preview') is not None:
            old['preview'].close()
        self._fragment_gesture = None
        if self._begin_annotation_gesture(kind, _x, _y):return
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
        if self._move_annotation_gesture(kind, dx, dy):return
        state = self._fragment_gesture
        if state is None or kind != state['kind'] or (abs(dx) + abs(dy)) < 1e-10:
            return
        if kind == 'roll' and abs(dx) < 1e-10:
            return
        from .fragment import (screen_translation, apply_fragment_translation,
                               screen_rotation, apply_fragment_rotation)
        if not state['edited']:
            self._record_undo()
            state['edited'] = True
            self.selection = list(state['indices'])
            if kind == 'pan':
                self._sync_selection_to_table()
                from .fragment_preview import start_fragment_pan_preview
                state['preview'] = start_fragment_pan_preview(self.renderer, self.frame, state['indices'])
            else:
                from .fragment_preview import start_fragment_rotation_preview
                state['preview'] = start_fragment_rotation_preview(self.renderer, self.frame, state['indices'])
            self.renderer.periodic_preview = None
        camera = self.scene.GetActiveCamera()
        if kind == 'pan':
            offset = screen_translation(camera, dx, dy, self.vtk.height(), state['pivot'])
            apply_fragment_translation(self.frame, state['indices'], offset)
            state['pivot'] += offset
            if state.get('preview') is not None and not state['preview'].closed:
                state['preview'].translate(offset)
        else:
            R = screen_rotation(camera, kind, dx, dy)
            apply_fragment_rotation(self.frame, state['indices'], R, state['pivot'])
        self.doc.modified = True
        if kind != 'pan':
            from .fragment_preview import queue_fragment_rotation
            queue_fragment_rotation(self, state)
        elif state.get('preview') is not None and not state['preview'].closed:
            self.scene.ResetCameraClippingRange()
            self.vtk.GetRenderWindow().Render()
        else:
            self.refresh_scene()

    def _fragment_end(self, kind):
        if self._end_annotation_gesture(kind):return
        state = self._fragment_gesture
        self._fragment_gesture = None
        if state is not None and state.get('preview') is not None:
            state['preview'].close()
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
            from .workflow_ui import FRAME_LABEL_ROLE, frame_tree_label
            data = item.data(0, Qt.ItemDataRole.UserRole)
            series_step = data[3] + 1 if data and len(data) > 3 and data[1] == 'series' else None
            item.setText(0, frame_tree_label(
                self.frame, self.frame_index, self.doc.format_name,
                title=item.data(0, FRAME_LABEL_ROLE), series_step=series_step))

    def build_supercell(self):
        if self.frame is None or not self._geometry_edit_allowed():
            return
        from .supercell_dialog import SupercellDialog
        dialog = SupercellDialog(self.frame, has_volume=self.doc.volume is not None, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_supercell(dialog.repeats(), wrap=dialog.wrap.isChecked(), growth=dialog.growth())

    def apply_supercell(self, repeats, *, wrap=None, growth='forward'):
        if self.frame is None or not self._geometry_edit_allowed():
            return False
        from .supercell import make_supercell
        try:
            frame=self.frame;cutoff=self.render_options.bond_cutoff
            expanded = run_data_task(self,'Building supercell',lambda:make_supercell(frame,repeats,wrap=wrap,growth=growth,bond_cutoff=cutoff))
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
        self.change_frame(self.frame_index, reset_camera=growth != 'alternating')
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
        if self.doc.volume is not None and axis.lower() in ('a','b','c'):
            QMessageBox.warning(self, 'Volume attached',
                'Aligning to a/b/c keeps the lattice and volumetric grid fixed '
                'while rotating atoms only. This would invalidate the geometry-to-grid '
                'relationship, so alignment is disabled for files with attached volume data.')
            return
        self._record_undo()
        try:
            rotation,pivot,cell_rotated=align_pair_to_axis(self.frame, self.selection[0], self.selection[1], axis)
        except (ValueError, IndexError) as ex:
            old=self.undo_stack.pop();self.doc.frames[self.frame_index]=old[2]
            QMessageBox.warning(self, 'Alignment unavailable', str(ex))
            return
        if self.doc.volume is not None:
            self.doc.volume.origin=(self.doc.volume.origin-pivot)@rotation.T+pivot
            self.doc.volume.voxel_vectors=self.doc.volume.voxel_vectors@rotation.T
        self.doc.modified = True
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage(
            f'Pair aligned to {axis}; '+('complete periodic structure and cell rotated.' if cell_rotated else 'atomic positions rotated within the fixed cell.'), 6000)

    def configure_coordinate_reorientation(self):
        if not self._geometry_edit_allowed() or self.frame is None or not self.frame.symbols:return
        from .reorientation_dialog import ReorientationDialog
        dialog=ReorientationDialog(self.frame,self.selection,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        try:rotation,translation,center,details=dialog.plan()
        except ValueError as exc:QMessageBox.warning(self,'Orientation unavailable',str(exc));return
        self.apply_coordinate_reorientation(rotation,translation,nearest_origin=center,details=details)

    def apply_coordinate_reorientation(self,rotation,translation,*,nearest_origin=None,details=None):
        if not self._geometry_edit_allowed() or self.frame is None:return
        from .coordinate_reorientation import transform_complete_frame
        from .operations import run_data_task
        self._record_undo()
        source=self.frame.clone()
        def calculate():
            transform_complete_frame(source,rotation,translation,nearest_origin=nearest_origin,details=details)
            return source
        try:transformed=run_data_task(self,'Reorienting complete crystal',calculate)
        except (ValueError,IndexError) as exc:
            old=self.undo_stack.pop();self.doc.frames[self.frame_index]=old[2]
            QMessageBox.warning(self,'Orientation unavailable',str(exc));return
        self.doc.frames[self.frame_index]=transformed
        if self.doc.volume is not None:
            import numpy as np
            self.doc.volume.origin=self.doc.volume.origin@np.asarray(rotation).T+translation
            self.doc.volume.voxel_vectors=self.doc.volume.voxel_vectors@np.asarray(rotation).T
        self.doc.modified=True;self._fragment_gesture=None
        self._refresh_after_geometry_edit()
        self.statusBar().showMessage('Origin and axes reset with a proper rotation; coordinates, cell and grid transformed together. Ctrl+Z to undo.',7000)

    def _atom_context_from_canvas(self,x,y):
        if self.frame is None:return
        if self._annotation_context_from_canvas(x, y):return
        from .interaction import vtk_display_from_qt
        rw=self.vtk.GetRenderWindow();width,height=rw.GetSize()
        try:dx,dy=vtk_display_from_qt(x,y,self.vtk.width(),self.vtk.height(),width,height)
        except ValueError:return
        atom=self.renderer.pick_index(dx,dy,width,height)
        if atom is None:self._right_click_clear();return
        if atom not in self.selection:
            self.selection=[atom];self._sync_selection_to_table();self.refresh_scene()
        from .structure_edit_dialogs import AtomIndexDialog
        editable=self._active_vibration is None and not self._alignment_enabled()
        dialog=AtomIndexDialog(self.frame,atom,self.selection,editable=editable,parent=self)
        if dialog.exec()==QDialog.DialogCode.Accepted and editable:
            if dialog.operation=='species':self.apply_atom_species(atom,dialog.species.requested_rows())
            else:self.apply_atom_index(atom,dialog.index.value()-1,swap=dialog.swap if dialog.operation=='swap' else None)

    def apply_atom_species(self,atom,rows):
        if not self._geometry_edit_allowed() or self.frame is None:return False
        from .site_occupancy import change_site_species,description
        candidate=self.frame.clone()
        try:changed=change_site_species(candidate,atom,rows)
        except ValueError as exc:
            QMessageBox.warning(self,'Invalid element / occupancy',str(exc));return False
        if not changed:return False
        self._record_undo()
        candidate.bond_snapshot=self.frame.bond_snapshot
        candidate.periodic_bond_snapshot=self.frame.periodic_bond_snapshot
        self.doc.frames[self.frame_index]=candidate
        # A grid calculated for the old nuclear species is no longer attached
        # to this edited structure; undo restores the original grid and frame.
        self.doc.volume=None;self.doc.modified=True
        self._refresh_after_geometry_edit()
        self._refresh_frame_tree_label()
        self.statusBar().showMessage(f'Atom #{atom+1}: {description(candidate,atom)}. Current frame updated; Ctrl+Z to undo.',7000)
        return True

    def apply_atom_index(self,atom,target,*,swap=None):
        if not self._geometry_edit_allowed() or self.frame is None:return
        from .atom_indices import index_order,reorder_atoms
        try:order=index_order(len(self.frame.symbols),atom,target,swap=swap)
        except ValueError as exc:QMessageBox.warning(self,'Invalid atom index',str(exc));return
        if order==list(range(len(order))):return
        self._record_undo();mapping=reorder_atoms(self.frame,order)
        self.selection=[mapping[i] for i in self.selection]
        self.doc.modified=True;self._refresh_after_geometry_edit(preserve_results=True)
        self.statusBar().showMessage('Atom indices updated; positions and properties follow their atoms. Ctrl+Z to undo.',5000)

    def configure_vacuum(self):
        if not self._geometry_edit_allowed() or self.frame is None:return
        if self.doc.volume is not None:
            QMessageBox.warning(self,'Volume grid attached','Open a structure without a fixed volumetric grid to change the periodic cell.');return
        from .structure_edit_dialogs import VacuumDialog
        dialog=VacuumDialog(self.frame,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.apply_vacuum(dialog.requested_gap(),dialog.selected_axis())

    def apply_vacuum(self,gap,axis=None):
        if not self._geometry_edit_allowed() or self.frame is None or self.doc.volume is not None:return
        from .vacuum import change_vacuum
        candidate=self.frame.clone()
        try:result=change_vacuum(candidate,gap,axis)
        except ValueError as exc:QMessageBox.warning(self,'Vacuum adjustment unavailable',str(exc));return
        if not result['changed']:
            self.statusBar().showMessage('Vacuum is unchanged; calculation results preserved.',5000);return
        self._record_undo();candidate.bond_snapshot=self.frame.bond_snapshot;candidate.periodic_bond_snapshot=self.frame.periodic_bond_snapshot
        self.doc.frames[self.frame_index]=candidate;self.doc.modified=True;self._refresh_after_geometry_edit()
        self._refresh_frame_tree_label()
        self.statusBar().showMessage(f'Vacuum {result["gap"]:.6f} → {gap:.6f} Å; Cartesian coordinates unchanged. Ctrl+Z to undo.',6000)

    def _coordinate_edited(self, item):
        if self._ignore_table or item.column() not in (1, 2, 3) or self.frame is None:
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
        if self.surface_hide_check.isChecked():
            if not self._text_editor_active():self._undo_surface_hide()
            return
        if not self.undo_stack:
            return
        item = self.undo_stack.pop()
        if self._undo_annotation_item(item):return
        if item[0] == 'pair_rules':
            self._undo_element_pair_rules(item)
            return
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

    def show_vasp_neb(self):
        from .vasp_neb_dialog import show_vasp_neb
        return show_vasp_neb(self)

    def _step_previous(self):
        sequence=self._navigation_indices()
        if sequence:self.change_frame(sequence[max(0,sequence.index(self.frame_index)-1)])

    def _step_next(self):
        if ui_busy():return
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
        if index is None or not any(doc is document for doc in self.documents):return
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
    def show_scan_curve(self):
        doc = self.doc
        if doc is None or doc.calculation_results is None or not getattr(doc.calculation_results, 'scans', []):
            return
        from .orca_scan_dialog import ScanDialog
        return self._show_analysis_window(ScanDialog(doc, lambda index: self._jump_to_scan_frame(doc, index), self))

    def _jump_to_scan_frame(self, doc, index):
        for run in getattr(doc.calculation_results, 'scans', []):
            selected = next((point for point in run.points if point.frame_index == index), None)
            if selected is not None:
                sequence = [point.frame_index for point in run.points
                            if point.frame_index is not None and point.converged == selected.converged]
                label = f'Scan {run.index + 1} · ' + ('converged endpoints' if selected.converged else 'incomplete points')
                return self._jump_to_result_sequence(doc, index, sequence, label)
        return self._jump_to_result_frame(doc, index)

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
        if axis in ('a', 'b', 'c'):
            from .camera_views import align_window_camera
            return align_window_camera(self, axis, fit=True)
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
        dialog._lele_document = self.doc
        self._analysis_windows.append(dialog)
        dialog.finished.connect(lambda _=0: self._analysis_windows.remove(dialog)
                                if dialog in self._analysis_windows else None)
        show_dialog(dialog)
        return dialog

    def show_atom_legend(self):
        if self.frame is None or self.renderer is None:
            self.statusBar().showMessage('Open a structure before showing its atom legend.',5000);return
        from .atom_legend_dialog import AtomLegendDialog
        return self._show_analysis_window(AtomLegendDialog(self))

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

    def show_nmr_results(self):
        if self.doc is None or not self.doc.nmr_results:return
        from .nmr_dialog import NMRDialog
        doc=self.doc;dialog=NMRDialog(doc,self)
        dialog.atomRequested.connect(lambda result,number:self._locate_nmr_atom(doc,result,number))
        return self._show_analysis_window(dialog)

    def _locate_nmr_atom(self,document,result_index,number):
        import numpy as np
        if not any(doc is document for doc in self.documents):return
        result=document.nmr_results[result_index];index=result.frame_index;reference=result.reference
        if index is None or reference is None or not 0<=index<len(document.frames):
            self.statusBar().showMessage('No matching source structure for this NMR dataset.',7000);return
        frame=document.frames[index]
        from .atom_indices import atom_mapping
        mapping = atom_mapping(reference, frame)
        if (mapping is None or frame.positions.shape!=reference.positions.shape
                or not np.allclose(frame.positions[list(mapping)],reference.positions,rtol=0,atol=1.e-8)):
            self.statusBar().showMessage('The source structure has been edited; NMR atom locations refer to the original output.',7000);return
        if not 1<=number<=len(frame.symbols):return
        self._jump_to_result_frame(document,index)
        selected = mapping[number-1]
        self.selection=[selected];self.renderer.periodic_preview=None;self._sync_selection_to_table();self.refresh_scene()
        self.sidebar_tabs.setCurrentWidget(self.atom_panel);self.atom_panel.reveal_atom(selected)

    def _jump_to_result_frame(self, document, frame_index):
        index = next((i for i, doc in enumerate(self.documents) if doc is document), None)
        if index is None or not 0 <= frame_index < len(document.frames):
            return
        self.playback.stop()
        self.play_btn.setText('Play')
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
        if self.frame is None or self._png_exporting:
            return
        self._png_exporting = True
        source_document, source_frame = self.doc, self.frame
        source_index, source_vibration = self.frame_index, self._active_vibration
        timers = [timer for timer in (self.playback, self.vibration_timer) if timer.isActive()]
        for timer in timers:
            timer.stop()
        try:
            path, _ = QFileDialog.getSaveFileName(self, 'Save rendering', self._save_path(suffix if isinstance(suffix,str) else '_view.png'), 'PNG image (*.png)')
            if not path:
                return
            from .png_dialog import PngExportDialog
            from .png_export import export_png
            window = self.vtk.GetRenderWindow()
            dialog = PngExportDialog(self, view_size=window.GetSize())
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            settings = dialog.settings()
            with ui_operation(self, 'Saving high-resolution PNG'):
                export_png(path, window, settings, mesh_items=self.renderer._keepalive, progress=ui_checkpoint)
            self.statusBar().showMessage(f'Saved image: {path} · {settings.width} × {settings.height} px', 5000)
        except Exception as ex:
            QMessageBox.warning(self, 'Export failed', str(ex))
        finally:
            self._png_exporting = False
            if (not self._closing and self.doc is source_document and self.frame is source_frame
                    and self.frame_index == source_index and self._active_vibration == source_vibration):
                for timer in timers:
                    timer.start()

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
                export_document=Document(self.doc.path,self.doc.format_name,[self.doc.frames[i] for i in sequence],self.doc.volume,volumes=self.doc.volumes)
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
        progress = LeleProgressDialog('Preparing GIF…', 'Cancel', 0, count, self)
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
        from .site_occupancy import is_disordered
        occupancy_policy='error'
        if target!='cif' and is_disordered(self.frame):
            from .structure_edit_dialogs import confirm_maximum_occupancy_export
            if not confirm_maximum_occupancy_export(self):return
            occupancy_policy='maximum'
        extension = {'xyz': '.xyz', 'gjf': '.gjf', 'cif': '.cif'}.get(target, '')
        from .export_paths import structure_export_path
        name = str(structure_export_path(self._save_path('_edited' + extension), target))
        path, _ = QFileDialog.getSaveFileName(self, 'Export selected frame', name)
        if not path:
            return
        normalized = str(structure_export_path(path, target))
        if normalized != path and Path(normalized).exists():
            answer = QMessageBox.question(self, 'Replace file?',
                f'{Path(normalized).name} already exists. Replace it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        path = normalized
        export_options = {'occupancy_policy': occupancy_policy}
        if target in ('poscar-direct', 'poscar-cartesian'):
            answer = QMessageBox.question(self, 'Merge same elements?',
                'Group atoms of the same element together in the exported POSCAR?\n\n'
                'Yes: one block per element, in first-appearance order.\n'
                'No: preserve the current atom order and existing element blocks.\n'
                'Only the exported copy is reordered.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes)
            if answer not in (QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No):
                return
            export_options['merge_same_elements'] = answer == QMessageBox.StandardButton.Yes
        try:
            from .formats import export_frame
            frame=self.frame
            notices = run_data_task(self,'Exporting structure',lambda:export_frame(frame,path,target,**export_options))
            self.statusBar().showMessage('Exported ' + path + (' | ' + '; '.join(notices) if notices else ''), 10000)
        except Exception as ex:
            QMessageBox.warning(self, 'Export failed', str(ex))

    def _set_light_enabled(self, index, enabled):
        values = list(self.render_options.light_enabled)
        values[index] = bool(enabled)
        self.render_options.light_enabled = tuple(values)
        if self.renderer is not None:
            self.renderer.apply_lighting()
            self.vtk.GetRenderWindow().Render()

    def show_stm(self):
        from .stm import can_simulate_stm
        if self.doc is None or not can_simulate_stm(self.doc):
            return
        from .stm_dialog import STMDialog
        dialog = STMDialog(self.doc, self)
        return self._show_analysis_window(dialog)

    def show_xrd(self):
        from .core import valid_lattice
        if self.frame is None or not all(self.frame.pbc) or not valid_lattice(self.frame):
            return
        from .xrd_dialog import XrdDialog
        dialog = XrdDialog(self.frame.clone(), source_path=self.doc.path, parent=self)
        return self._show_analysis_window(dialog)

    def help_dialog(self):
        existing = getattr(self, '_help_window', None)
        if existing is not None:
            show_dialog(existing)
            return existing
        text = (
            APP_FULL_NAME + '\n\n'
            'Open files: Ctrl+O; save PNG: Ctrl+S; export structure: Ctrl+Shift+S.\n\n'
            'File > Export animation GIF saves a trajectory or the selected vibration mode.\n'
            'Atoms selection accepts expressions; see Help > Atom selection syntax for examples.\n'
            'Drag files into the window. Left-drag: rotate; right-drag: roll clockwise/counterclockwise; mouse wheel: zoom.\n'
            'Click atoms to select; right-click an atom to edit element / occupancy / index, empty space to clear; right-drag to roll.\n'
            'Ctrl+B toggles selected internal bonds; two atoms toggle regardless of distance.\n'
            'Ctrl+H draws/removes a dashed hydrogen bond between two selected atoms; Ctrl+Z undoes it.\n'
            'Switching files restores each file\'s camera, colors and display settings for this session.\n'
            'Ctrl+Shift+B toggles box selection; drag its unfilled dashed outline; Esc exits.\n'
            'One atom -> Move to origin; two ordered atoms -> Align to XYZ or lattice abc.\n'
            'Use Up/Down in frame tree to change frames.\n'
            'Expand Frequencies in Files and select a mode to animate it; negative frequencies are imaginary.\n'
            'Pause or reset vibration, and adjust its visual amplitude and speed below the file tree.\n'
            'Select 2/3/4 atoms to measure distance/angle/dihedral.\n'
            'View > X/Y/Z looks from the positive coordinate axis toward the structure.\n'
            'View > a/b/c looks along the displayed direct lattice vectors of a periodic structure.\n'
            'Select 3+ atoms, then click Fit selected plane in Edit to show a plane.\n'
            'Align plane to XY rotates all atoms and the cell; optional Z translation.\n'
            'Ctrl+A selects all atoms; box selection always adds atoms and Ctrl+Z undoes the last addition.\n'
            'Ctrl+I inverts selection; Delete removes selected atoms; Ctrl+Z restores them.\n'
            'Edit > Build supercell repeats the current periodic frame and enlarges the unit cell.\n'
            'Axes default to periodic abc or molecular XYZ; explicit XYZ/abc and hidden/corner/world-origin modes remain available.\n'
            'Labels are centred on their atoms with global (1-based), ORCA (0-based) or POSCAR-group numbering.\n'
            'Double-click X/Y/Z cells to edit atomic coordinates; Ctrl+Z to undo.\n\n'
            'This version does not calculate chemical bonds, wavefunctions, spectra, or DFT results.\n'
            'Ordinary bonds use Chemcraft pair limits by default. Default uses slightly lighter element colors, with Glossy lighting.\n'
            'Space filling uses VESTA radii (Atomic by default). Manual bond overrides are visualization-only and are not saved in XYZ/POSCAR/CIF.')
        dialog = QDialog(self)
        dialog.setWindowTitle('Help and shortcuts — ' + APP_TITLE)
        dialog.resize(680, 520)
        layout = QVBoxLayout(dialog)
        browser = QPlainTextEdit(dialog)
        browser.setReadOnly(True)
        browser.setPlainText(text)
        layout.addWidget(browser)
        close = QPushButton('Close', dialog)
        close.clicked.connect(dialog.close)
        layout.addWidget(close)
        self._help_window = dialog
        dialog.finished.connect(lambda _=0: setattr(self, '_help_window', None))
        return self._show_analysis_window(dialog)

    def dragEnterEvent(self, event):
        if (not self._closing and event.possibleActions() & Qt.DropAction.CopyAction
                and any(url.isLocalFile() for url in event.mimeData().urls())):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        # Windows keeps the source application's native drag call active until
        # this callback returns. Never parse, render, stat network paths or enter
        # a progress/error dialog's nested event loop while handling the drop.
        paths = tuple(url.toLocalFile() for url in event.mimeData().urls()
                      if url.isLocalFile() and url.toLocalFile())
        if self._closing or not paths or not event.possibleActions() & Qt.DropAction.CopyAction:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        QTimer.singleShot(0, self, lambda: self._open_dropped_paths(paths))

    def _open_dropped_paths(self, paths):
        if not self._closing:
            self.open_paths(paths)

    def closeEvent(self, event):
        if getattr(self, '_batch_exporting', False):
            if self._batch_progress is not None:
                self._batch_progress.cancel()
            event.ignore()
            return
        if self._png_exporting:
            event.ignore()
            return
        if self._gif_exporting:
            self._gif_close_requested = True
            if self._gif_progress is not None:
                self._gif_progress.cancel()
            event.ignore()
            return
        self._closing = True
        self._cancel_file_imports()
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
    window.showMaximized()
    return app.exec()
