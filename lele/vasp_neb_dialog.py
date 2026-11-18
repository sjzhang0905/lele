"""Build a VASP NEB path from loaded outputs and inspect its final images.

All scientific data are snapshots. Building or viewing a path never changes
the loaded documents, their atom order, coordinates or energies.
"""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QComboBox, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
from .dialog_policy import QDialog, QFileDialog, QMessageBox
from .operations import gui_operation, run_data_task, ui_operation
from .output_text import LoadCancelled


def _button(text, callback, layout):
    button = QPushButton(text)
    button.clicked.connect(callback)
    layout.addWidget(button)
    return button


class VaspNebInputDialog(QDialog):
    """One selection gesture chooses many files; list order is path order."""
    def __init__(self, documents, parent=None):
        super().__init__(parent)
        from .vasp_neb import is_vasp_output, natural_path_key
        self.documents = sorted((d for d in documents if is_vasp_output(d)), key=natural_path_key)
        self.path = None
        self.setWindowTitle('VASP NEB — choose loaded outputs')
        self.resize(820, 510)
        layout = QVBoxLayout(self)
        note = QLabel('Check the initial state, intermediate images and final state. '
            'Checked files are read from top to bottom; each contributes its final printed geometry. '
            'Use Ctrl / Shift and “Use selected only” to choose several files at once. '
            'Highlight rows and use Up / Down to change their order without changing the checked files.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.files = QListWidget()
        self.files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for i, document in enumerate(self.documents):
            item = QListWidgetItem(str(document.path))
            item.setToolTip(str(document.path))
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.files.addItem(item)
        layout.addWidget(self.files, 1)
        order = QHBoxLayout()
        layout.addLayout(order)
        _button('Up', lambda: self.move_rows(-1), order)
        _button('Down', lambda: self.move_rows(1), order)
        _button('Sort by path number', self.sort_paths, order)
        _button('Use selected only', self.use_selected_only, order)
        order.addStretch(1)
        form = QFormLayout()
        layout.addLayout(form)
        self.energy = QComboBox()
        self.energy.addItem('E0 (σ→0), eV', 'E0')
        self.energy.addItem('Free energy TOTEN, eV', 'TOTEN')
        self.energy.setToolTip('Every image must contain the selected energy. Energy types are never mixed.')
        form.addRow('Energy for every image', self.energy)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setStyleSheet('color:#a32626')
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Build NEB path')
        buttons.accepted.connect(self.build)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_documents(self):
        return [self.documents[self.files.item(row).data(Qt.ItemDataRole.UserRole)]
                for row in range(self.files.count())
                if self.files.item(row).checkState() == Qt.CheckState.Checked]

    def use_selected_only(self):
        if not self.files.selectedItems():
            self.error.setText('Highlight the files to include, using Ctrl / Shift for multiple files.')
            return
        for row in range(self.files.count()):
            item = self.files.item(row)
            item.setCheckState(Qt.CheckState.Checked if item.isSelected() else Qt.CheckState.Unchecked)
        self.error.clear()

    def move_rows(self, direction):
        rows = [i for i in range(self.files.count()) if self.files.item(i).isSelected()]
        if direction > 0:
            rows.reverse()
        for row in rows:
            other = row + direction
            if 0 <= other < self.files.count() and not self.files.item(other).isSelected():
                item = self.files.takeItem(row)
                self.files.insertItem(other, item)
                item.setSelected(True)

    def sort_paths(self):
        from .vasp_neb import natural_path_key
        selected = {id(document) for document in self.selected_documents()}
        self.documents.sort(key=natural_path_key)
        self.files.clear()
        for i, document in enumerate(self.documents):
            item = QListWidgetItem(str(document.path))
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if id(document) in selected else Qt.CheckState.Unchecked)
            self.files.addItem(item)

    def build(self):
        from .dialog_policy import ensure_source_current
        if not ensure_source_current(self):return
        from .vasp_neb import build_neb_path
        documents = self.selected_documents()
        energy = self.energy.currentData()
        try:
            self.path = run_data_task(self, 'Preparing VASP NEB path',
                lambda: build_neb_path(documents, energy=energy), cancellable=True)
        except LoadCancelled:
            return
        except (ValueError, TypeError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class VaspNebDialog(QDialog):
    def __init__(self, path, source_window, parent=None):
        super().__init__(parent or source_window)
        self.path = path
        self.source_window = source_window
        self._initialized = False
        self._finalized = False
        self._has_scene = False
        self.setWindowTitle('VASP NEB — path and caterpillar')
        self.resize(1040, 830)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self._build_curve_tab()
        self._build_caterpillar_tab()
        self.redraw_curve()
        self.rebuild_caterpillar()
        self.tabs.currentChanged.connect(self._tab_changed)
        self.finished.connect(self._shutdown)

    def _build_curve_tab(self):
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from .figure_export import FigureExportToolbar as NavigationToolbar2QT
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.coordinate = QComboBox()
        self.coordinate.addItems(['Path distance (Å)', 'Image number'])
        row.addWidget(QLabel('Horizontal axis'))
        row.addWidget(self.coordinate)
        row.addStretch(1)
        _button('Export path CSV…', self.export_csv, row)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.figure = Figure(figsize=(8, 4), tight_layout=True)
        self.plot = FigureCanvasQTAgg(self.figure)
        layout.addWidget(NavigationToolbar2QT(self.plot, self))
        layout.addWidget(self.plot, 1)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Image', 'Distance (Å)', 'Energy (eV)', 'ΔE (eV)', 'Source'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().hide()
        self.table.setMaximumHeight(240)
        layout.addWidget(self.table)
        note = QLabel('Energies are relative to image 0. Lines join the calculated images; they are not a fitted transition-state calculation. '
            'Path distance is the cumulative Cartesian displacement norm of all atoms, using minimum-image steps. '
            'Use files from the same path with the same atom order, including within each element. '
            'A set of loaded outputs does not establish NEB convergence.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs.addTab(page, 'Energy path')
        self.coordinate.currentIndexChanged.connect(self.redraw_curve)

    def redraw_curve(self, *_):
        import numpy as np
        path = self.path
        self.figure.clear()
        axes = self.figure.add_subplot(111)
        x = path.distances if self.coordinate.currentIndex() == 0 else np.arange(len(path.frames))
        axes.plot(x, path.relative_energies, 'o-', color='#2876ad', linewidth=1.4, markersize=6)
        highest = int(np.argmax(path.energies))
        axes.plot([x[highest]], [path.relative_energies[highest]], '*', color='#c43b32', markersize=13,
                  label=f'Highest sampled image {highest}')
        for i, (a, b) in enumerate(zip(x, path.relative_energies)):
            axes.annotate(str(i), (a, b), xytext=(4, 6), textcoords='offset points', fontsize=8)
        axes.set_xlabel(self.coordinate.currentText())
        axes.set_ylabel(f'Relative {path.energy_label} (eV)')
        axes.axhline(0., color='0.7', linewidth=.6)
        axes.grid(True, alpha=.2)
        axes.legend(fontsize=9)
        self.summary.setText(f'{len(path.frames)} images · {path.energy_label} throughout · '
            f'Forward sampled barrier {path.forward_barrier:.6g} eV · '
            f'Reverse sampled barrier {path.reverse_barrier:.6g} eV · '
            f'Final − initial {path.relative_energies[-1]:.6g} eV')
        self.table.setRowCount(len(path.frames))
        for i, source in enumerate(path.sources):
            values = (i, f'{path.distances[i]:.7g}', f'{path.energies[i]:.10g}',
                      f'{path.relative_energies[i]:.7g}', source)
            for j, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()
        self.plot.draw_idle()

    def _build_caterpillar_tab(self):
        from .vasp_neb import suggested_atom_indices
        from .vasp_neb_canvas import NebCanvas
        from vtkmodules.vtkRenderingCore import vtkRenderer
        from .renderer import MoleculeRenderer
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        layout.addLayout(form)
        current = tuple(getattr(self.source_window, 'selection', ()))
        current_doc = getattr(self.source_window, 'doc', None)
        # A selection from an unrelated document must not silently select atoms.
        if (current_doc is None or str(current_doc.path) not in self.path.sources
                or any(i < 0 or i >= len(self.path.frames[0].symbols) for i in current)):
            current = ()
        indices = current or suggested_atom_indices(self.path)
        self.atoms = QLineEdit(', '.join(str(i + 1) for i in indices))
        self.atoms.setPlaceholderText('1, 2, 5-8')
        form.addRow('Migrating atom indices (1-based)', self.atoms)
        self.reference = QComboBox()
        for i, source in enumerate(self.path.sources):
            self.reference.addItem(f'Image {i} — {Path(source).parent.name}/{Path(source).name}')
        form.addRow('Fixed surrounding structure', self.reference)
        row = QHBoxLayout()
        layout.addLayout(row)
        self.path_lines = QCheckBox('Connect trajectory positions')
        self.path_lines.setChecked(True)
        self.image_colors = QCheckBox('Color by image')
        self.image_colors.setChecked(True)
        self.image_labels = QCheckBox('Label image numbers')
        for widget in (self.path_lines, self.image_colors, self.image_labels):
            row.addWidget(widget)
        row.addStretch(1)
        _button('Apply', self.rebuild_caterpillar, row)
        self.scene_note = QLabel()
        self.scene_note.setWordWrap(True)
        layout.addWidget(self.scene_note)
        self.canvas = NebCanvas(self)
        self.canvas.setMinimumSize(500, 300)
        layout.addWidget(self.canvas, 1)
        self.scene = vtkRenderer()
        self.canvas.scene = self.scene
        self.canvas.GetRenderWindow().AddRenderer(self.scene)
        self.drawing = MoleculeRenderer(self.scene)
        # Draw the surroundings and the path independently. This keeps all
        # main-canvas styles (including Boundary) on the reference structure,
        # without replicating or bonding the moving atoms between images.
        self.track_drawing = MoleculeRenderer(self.scene)
        for light in self.track_drawing._lights:
            self.scene.RemoveLight(light)
        from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
        self.axes_widget = vtkOrientationMarkerWidget()
        self.axes_widget.SetInteractor(self.canvas.interactor)
        self.axes_widget.SetViewport(.015, .015, .225, .225)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        _button('Fit view', self.fit_view, buttons)
        _button('Use current main view', self.use_main_view, buttons)
        buttons.addStretch(1)
        _button('Save caterpillar PNG…', self.save_caterpillar, buttons)
        note = QLabel('Only the selected atoms are repeated through the path. All other atoms remain at the chosen reference image. '
            'Apply and export refresh the surroundings from the current main-canvas appearance; moving atoms keep the path style. '
            'Thin trajectory lines are visual guides, not chemical bonds. Left drag rotates; right drag rolls; wheel zooms. '
            'Periodic paths follow the nearest image at each step; a jump exceeding half a cell may need additional images.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.tabs.addTab(page, 'Caterpillar')

    @gui_operation('Preparing NEB caterpillar')
    def rebuild_caterpillar(self, *_):
        from .vasp_neb import parse_atom_indices, caterpillar_frame
        from .atom_appearance import AtomAppearance
        from matplotlib import colormaps
        from matplotlib.colors import to_hex
        try:
            indices = parse_atom_indices(self.atoms.text(), len(self.path.frames[0].symbols))
            reference = self.reference.currentIndex()
            self.options = deepcopy(self.source_window.render_options)
            self.drawing.options = self.options
            source = deepcopy(self.path.frames[reference])
            current_doc = getattr(self.source_window, 'doc', None)
            current_frame = getattr(self.source_window, 'frame', None)
            if (current_doc is not None and str(current_doc.path) in self.path.sources
                    and current_frame is not None and current_frame.symbols == source.symbols):
                source.atom_appearance = deepcopy(current_frame.atom_appearance)
            source.info['bond_model'] = self.options.bond_model
            from .element_rules import install_rules
            install_rules(source, self.options.element_pair_rules, self.options.pair_rules_only)
            # Appearance changes never alter the immutable path snapshots.
            scene_path = replace(self.path, frames=tuple(
                source if i == reference else f for i, f in enumerate(self.path.frames)))
            frame = caterpillar_frame(scene_path, indices, reference=reference,
                                      bond_cutoff=self.options.bond_cutoff)
        except (ValueError, TypeError) as exc:
            self.scene_note.setText(str(exc))
            return False
        colors = [to_hex(colormaps['viridis'](i / max(1, len(self.path.frames) - 1)))
                  for i in range(len(self.path.frames))]
        for atom in frame.info['neb_caterpillar_atoms']:
            old = frame.atom_appearance.get(atom['index'], AtomAppearance())
            frame.atom_appearance[atom['index']] = AtomAppearance(
                color=colors[atom['image']] if self.image_colors.isChecked() else old.color,
                opacity=old.opacity, representation='Ball and stick', size_scale=old.size_scale,
                label_mode='Custom' if self.image_labels.isChecked() else 'None',
                label_text=f'{atom["source_atom"] + 1}:{atom["image"]}' if self.image_labels.isChecked() else '')
        surroundings = source.clone()
        for index in indices:
            old = surroundings.atom_appearance.get(index, AtomAppearance())
            surroundings.atom_appearance[index] = replace(old, visible=False)
        main_drawing = getattr(self.source_window, 'renderer', None)
        self.drawing.alignment = deepcopy(getattr(main_drawing, 'alignment', None))
        self.drawing.fitted_plane = deepcopy(getattr(main_drawing, 'fitted_plane', None))
        self.drawing.set_scene(surroundings, reset_camera=False)
        tracks = frame.clone()
        moving = {atom['index'] for atom in frame.info['neb_caterpillar_atoms']}
        for index in range(len(tracks.symbols)):
            if index not in moving:
                old = tracks.atom_appearance.get(index, AtomAppearance())
                tracks.atom_appearance[index] = replace(old, visible=False)
        tracks.positions = (tracks.positions @ self.drawing.display_rotation
                            + self.drawing.display_translation)
        tracks.cell = tracks.cell @ self.drawing.display_rotation
        tracks.pbc = (False, False, False)
        tracks.bond_snapshot = frozenset()
        tracks.periodic_bond_snapshot = ()
        track_options = deepcopy(self.options)
        track_options.boundary_enabled = False
        track_options.unit_cell = False
        track_options.axes_position = 'Off'
        track_options.labels = 'None'
        track_options.style = 'Ball and stick'
        track_options.hydrogen_bonds = False
        track_options.lattice_planes = []
        track_options.dipole_mode = 'Off'
        self.track_drawing.options = track_options
        self.track_drawing.set_scene(tracks, reset_camera=False)
        self._sync_corner_axes(self.drawing.frame)
        if self.path_lines.isChecked():
            segments = []
            for atom_index in indices:
                records = [record for record in frame.info['neb_caterpillar_atoms']
                           if record['source_atom'] == atom_index]
                records.sort(key=lambda record: record['image'])
                for a, b in zip(records[:-1], records[1:]):
                    segments.append((tracks.positions[a['index']], tracks.positions[b['index']], '#546577'))
            if segments:
                self.track_drawing._tube_segments(segments, .015, .65).PickableOff()
        main_scene = getattr(self.source_window, 'scene', None)
        if not self._has_scene:
            if main_scene is not None:
                self._copy_main_camera()
            else:
                self.scene.ResetCamera()
        elif main_scene is not None:
            # Preserve deliberate NEB rotation/zoom, while updating projection.
            camera = self.scene.GetActiveCamera()
            main_camera = main_scene.GetActiveCamera()
            camera.SetParallelProjection(main_camera.GetParallelProjection())
            camera.SetViewAngle(main_camera.GetViewAngle())
        self._has_scene = True
        self.caterpillar_frame = frame
        self.scene.ResetCameraClippingRange()
        self.scene_note.setText(f'{len(indices)} migrating atom(s) × {len(self.path.frames)} images; '
            f'surroundings from image {reference}. Atom labels: index (1-based) : image. '
            + ('Image colors: dark purple → yellow (initial → final).' if self.image_colors.isChecked() else 'Element colors.'))
        if self._initialized:
            self.canvas.render()
        return True

    def fit_view(self):
        self.scene.ResetCamera()
        self.scene.ResetCameraClippingRange()
        self.canvas.render()

    def use_main_view(self):
        if self.rebuild_caterpillar():
            self._copy_main_camera()
            self.canvas.render()

    def _copy_main_camera(self):
        source = getattr(self.source_window, 'scene', None)
        if source is None:
            return
        camera = self.scene.GetActiveCamera()
        camera.DeepCopy(source.GetActiveCamera())
        camera.Modified()
        self.scene.ResetCameraClippingRange()

    def _sync_corner_axes(self, frame):
        self.drawing.detach_corner_labels()
        if self.axes_widget.GetEnabled():
            self.axes_widget.SetEnabled(0)
        if self.options.axes_position == 'Corner':
            self.axes_widget.SetOrientationMarker(self.drawing.make_corner_marker(frame))
            self.axes_widget.SetEnabled(1)
            self.drawing.attach_corner_labels(self.axes_widget.GetRenderer())
            self.axes_widget.InteractiveOff()

    def _tab_changed(self, index):
        if index == 1:
            self._initialize()

    def _initialize(self):
        if self._finalized:
            return
        if not self._initialized:
            self._initialized = True
            self.canvas.Initialize()
        self.canvas.render()

    def export_csv(self):
        from .vasp_neb import export_path_csv
        default = Path(self.path.sources[0]).with_name('vasp_neb_path.csv')
        filename, _ = QFileDialog.getSaveFileName(self, 'Export VASP NEB path', str(default), 'CSV (*.csv)')
        if filename:
            try:
                run_data_task(self, 'Exporting VASP NEB path',
                    lambda: export_path_csv(self.path, filename), cancellable=True)
            except LoadCancelled:
                return
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Could not export path', str(exc))

    def save_caterpillar(self):
        default = Path(self.path.sources[0]).with_name('vasp_neb_caterpillar.png')
        filename, _ = QFileDialog.getSaveFileName(self, 'Save caterpillar', str(default), 'PNG (*.png)')
        if not filename:
            return
        from .png_dialog import PngExportDialog
        dialog = PngExportDialog(self, view_size=self.canvas.GetRenderWindow().GetSize())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        filename = Path(filename)
        if filename.suffix.lower() != '.png':
            filename = filename.with_name(filename.name + '.png')
        try:
            self.write_caterpillar_png(filename, dialog.settings())
        except Exception as exc:
            QMessageBox.warning(self, 'Could not export caterpillar', str(exc))

    def write_caterpillar_png(self, filename, settings=None):
        from .png_export import export_png, PngSettings
        from .operations import ui_operation, ui_checkpoint
        if not self.rebuild_caterpillar():
            raise ValueError(self.scene_note.text())
        self._initialize()
        ratio = max(.1, self.canvas.height() / max(1, self.canvas.width()))
        if settings is None:
            settings = PngSettings(2400, min(8192, max(1, round(2400 * ratio))))
        with ui_operation(self, 'Exporting caterpillar PNG'):
            export_png(filename, self.canvas.GetRenderWindow(), settings,
                mesh_items=self.drawing._keepalive + self.track_drawing._keepalive,
                progress=ui_checkpoint)
        self.canvas.render()

    def _shutdown(self, *_):
        if not self._finalized:
            self._finalized = True
            if self.axes_widget.GetEnabled():
                self.axes_widget.SetEnabled(0)
            self.drawing.detach_corner_labels()
            self.canvas.shutdown()

    def closeEvent(self, event):
        self._shutdown()
        super().closeEvent(event)


def show_vasp_neb(window):
    """Lazy entry point for Analysis → VASP NEB from loaded outputs."""
    chooser = VaspNebInputDialog(window.documents, window)
    if len(chooser.documents) < 2:
        QMessageBox.information(window, 'VASP NEB', 'Load at least two VASP output files with final structures first. '
            'Include both endpoints and all available intermediate images.')
        chooser.deleteLater()
        return None
    try:
        if chooser.exec() != QDialog.DialogCode.Accepted:
            return None
        with ui_operation(window, 'Preparing VASP NEB display'):
            dialog = VaspNebDialog(chooser.path, window)
        return window._show_analysis_window(dialog)
    finally:
        chooser.deleteLater()
