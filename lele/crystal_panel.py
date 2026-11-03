"""Crystal display controls; no scientific imports before the first paint."""
from copy import deepcopy
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QColorDialog,
    QTabWidget, QScrollArea)
from .crystal_settings import PLANE_MODES, POLYHEDRA_KEYS, default_plane


def decimal(value, minimum, maximum, step=.05):
    widget = QDoubleSpinBox();widget.setRange(minimum, maximum)
    widget.setDecimals(4);widget.setSingleStep(step);widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


class LatticePlanePanel(QWidget):
    applyRequested = Signal(object)
    normalRequested = Signal(object)
    centerRequested = Signal()
    previewChanged = Signal()

    def __init__(self):
        super().__init__();layout = QVBoxLayout(self)
        title = QLabel('Miller planes / display cuts');title.setStyleSheet('font-weight:600');layout.addWidget(title)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['(h k l)', 'Position', 'Cut'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(115);self.table.setMaximumHeight(170)
        self.table.verticalHeader().hide();layout.addWidget(self.table)
        buttons = QHBoxLayout();layout.addLayout(buttons)
        self.add = QPushButton('New');self.remove = QPushButton('Remove');self.clear = QPushButton('Clear all')
        for button in (self.add, self.remove, self.clear):buttons.addWidget(button)
        self.editor = QWidget();form = QFormLayout(self.editor);form.setContentsMargins(0, 0, 0, 0)
        self.enabled = QCheckBox('Enable this plane');form.addRow(self.enabled)
        row = QHBoxLayout();self.hkl = []
        for name in ('h', 'k', 'l'):
            row.addWidget(QLabel(name));spin = QSpinBox();spin.setRange(-99, 99);spin.setKeyboardTracking(False)
            row.addWidget(spin);self.hkl.append(spin)
        form.addRow(row)
        self.offset = decimal(.5, -100000., 100000.)
        self.unit = QComboBox();self.unit.addItems(['d', 'Å'])
        row = QHBoxLayout();row.addWidget(self.offset);row.addWidget(self.unit);form.addRow('Position', row)
        self.mode = QComboBox();self.mode.addItems(PLANE_MODES);form.addRow('Keep region', self.mode)
        self.thickness = decimal(.5, .0001, 100000.);form.addRow('Slab thickness', self.thickness)
        self.show = QCheckBox('Show plane surface / edges');form.addRow(self.show)
        self.opacity = decimal(.2, 0., 1.);form.addRow('Plane opacity', self.opacity)
        self.color = QPushButton('Plane colour…');form.addRow(self.color);layout.addWidget(self.editor)
        self.center = QPushButton('Center plane in shown cells');layout.addWidget(self.center)
        self.view_normal = QPushButton('View normal to (hkl)');layout.addWidget(self.view_normal)
        self.apply = QPushButton('Apply planes');layout.addWidget(self.apply)
        self.info = QLabel('Open a periodic structure to define Miller planes.');self.info.setWordWrap(True);layout.addWidget(self.info)
        note = QLabel('Position is the signed distance from the cell origin, in d or Å.\n'
            'Below / above follows the (hkl) normal; slab thickness uses the selected unit.\n'
            'Multiple cuts intersect. Up to six cutting faces; each slab uses two.\n'
            'Cuts affect the 3D display and images. Structure export keeps the complete source structure.')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch()
        self.records = [];self._loading = False;self._color = '#36A8D8'
        self.table.itemSelectionChanged.connect(self._load_row)
        self.add.clicked.connect(self.add_plane);self.remove.clicked.connect(self.remove_plane)
        self.clear.clicked.connect(self.clear_planes)
        self.apply.clicked.connect(lambda:self.applyRequested.emit(deepcopy(self.records)))
        self.view_normal.clicked.connect(lambda:self.normalRequested.emit(self.selected_plane()))
        self.center.clicked.connect(lambda:self.centerRequested.emit())
        self.color.clicked.connect(self.choose_color)
        for widget in self.hkl+[self.offset, self.thickness, self.opacity]:widget.valueChanged.connect(self._edited)
        for widget in (self.enabled, self.show):widget.toggled.connect(self._edited)
        for widget in (self.unit, self.mode):widget.currentTextChanged.connect(self._edited)
        self.set_values([]);self.setEnabled(False)

    def selected_plane(self):
        row = self.table.currentRow()
        return deepcopy(self.records[row]) if 0 <= row < len(self.records) else None

    def _row(self, index):
        p = self.records[index]
        values = [' '.join(str(x) for x in p['hkl']), f'{p["offset"]:g} {p["unit"]}',
                  p['mode'] if p['enabled'] else 'Disabled']
        for column, value in enumerate(values):self.table.setItem(index, column, QTableWidgetItem(value))

    def set_values(self, records):
        self._loading = True;self.records = deepcopy(records)
        self.table.setRowCount(len(records))
        for i in range(len(records)):self._row(i)
        self._loading = False
        if records:self.table.selectRow(0)
        self._load_row()

    def _load_row(self):
        if self._loading:return
        p = self.selected_plane();self.editor.setEnabled(p is not None)
        self.remove.setEnabled(p is not None);self.view_normal.setEnabled(p is not None);self.center.setEnabled(p is not None)
        if p is None:self.previewChanged.emit();return
        self._loading = True
        for spin, value in zip(self.hkl, p['hkl']):spin.setValue(value)
        self.offset.setValue(p['offset']);self.unit.setCurrentText(p['unit']);self.mode.setCurrentText(p['mode'])
        self.enabled.setChecked(p['enabled']);self.show.setChecked(p['show'])
        self.thickness.setValue(p['thickness']);self.opacity.setValue(p['opacity'])
        self._color = p['color'];self.color.setText('Plane colour… ('+self._color+')')
        self.thickness.setEnabled(p['mode'] == 'Slab');self._loading = False
        self.previewChanged.emit()

    def _edited(self, *_):
        if self._loading:return
        index = self.table.currentRow()
        if not 0 <= index < len(self.records):return
        self.records[index].update(enabled=self.enabled.isChecked(), hkl=tuple(spin.value() for spin in self.hkl),
            offset=self.offset.value(), unit=self.unit.currentText(), mode=self.mode.currentText(),
            thickness=self.thickness.value(), show=self.show.isChecked(), color=self._color, opacity=self.opacity.value())
        self._row(index);self.thickness.setEnabled(self.mode.currentText() == 'Slab');self.previewChanged.emit()

    def add_plane(self):
        self.records.append(default_plane());self.table.setRowCount(len(self.records))
        self._row(len(self.records)-1);self.table.selectRow(len(self.records)-1);self._load_row()

    def remove_plane(self):
        index = self.table.currentRow()
        if 0 <= index < len(self.records):
            records = deepcopy(self.records);records.pop(index);self.set_values(records)

    def clear_planes(self):
        self.set_values([]);self.applyRequested.emit([])

    def choose_color(self):
        value = QColorDialog.getColor(QColor(self._color), self, 'Plane colour')
        if value.isValid():self._color = value.name();self.color.setText('Plane colour… ('+self._color+')');self._edited()


class PolyhedraPanel(QWidget):
    applyRequested = Signal(object)

    def __init__(self):
        super().__init__();layout = QVBoxLayout(self);form = QFormLayout();layout.addLayout(form)
        self.centers = QLineEdit('Auto');self.ligands = QLineEdit('Auto')
        form.addRow('Center elements', self.centers);form.addRow('Ligand elements', self.ligands)
        self.search = QComboBox();self.search.addItems(['Covalent radii', 'Distance range']);form.addRow('Neighbors', self.search)
        self.minimum = decimal(0., 0., 20.);self.maximum = decimal(3., .0001, 20.)
        form.addRow('Min. distance (Å)', self.minimum);form.addRow('Max. distance (Å)', self.maximum)
        self.opacity = decimal(.35, 0., 1.);form.addRow('Face opacity', self.opacity)
        self.edges = QCheckBox('Show polyhedron edges');form.addRow(self.edges)
        self.edge_color = QPushButton('Edge colour…');form.addRow(self.edge_color)
        self.atoms = QCheckBox('Show atoms');self.vertices = QCheckBox('Complete ligand atoms across cells')
        form.addRow(self.atoms);form.addRow(self.vertices)
        self.apply = QPushButton('Apply Polyhedral style');layout.addWidget(self.apply)
        self.analyze = QPushButton('Analyze coordination / polyhedra…');layout.addWidget(self.analyze)
        self.info = QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        note = QLabel('Enter elements such as Ti Fe / O N, Auto, or * for all.\n'
            'Auto uses common ligand elements and the remaining non-H centers.\n'
            'Covalent radii also uses Style → Bond cutoff; Distance range uses only the distances above.\n'
            'Polyhedra complete periodic ligand shells. Three coplanar ligands form a polygon; collinear shells have no face.\n'
            'Faces follow center-atom colours. Style → Bonds uses the existing ordinary bonds, including manual edits.')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch()
        self._edge_color = '#334155';self.edge_color.clicked.connect(self.choose_edge_color)
        self.apply.clicked.connect(lambda:self.applyRequested.emit(self.values()))
        self.setEnabled(False)

    def values(self):
        return dict(polyhedra_centers=self.centers.text().strip() or 'Auto',
            polyhedra_ligands=self.ligands.text().strip() or 'Auto', polyhedra_search=self.search.currentText(),
            polyhedra_min_distance=self.minimum.value(), polyhedra_max_distance=self.maximum.value(),
            polyhedra_opacity=self.opacity.value(), polyhedra_edges=self.edges.isChecked(),
            polyhedra_edge_color=self._edge_color, polyhedra_show_atoms=self.atoms.isChecked(),
            polyhedra_show_vertices=self.vertices.isChecked())

    def set_values(self, options):
        self.centers.setText(options.polyhedra_centers);self.ligands.setText(options.polyhedra_ligands)
        self.search.setCurrentText(options.polyhedra_search);self.minimum.setValue(options.polyhedra_min_distance)
        self.maximum.setValue(options.polyhedra_max_distance);self.opacity.setValue(options.polyhedra_opacity)
        self.edges.setChecked(options.polyhedra_edges);self.atoms.setChecked(options.polyhedra_show_atoms)
        self.vertices.setChecked(options.polyhedra_show_vertices);self._edge_color = options.polyhedra_edge_color
        self.edge_color.setText('Edge colour… ('+self._edge_color+')')

    def choose_edge_color(self):
        value = QColorDialog.getColor(QColor(self._edge_color), self, 'Polyhedron edge colour')
        if value.isValid():self._edge_color = value.name();self.edge_color.setText('Edge colour… ('+self._edge_color+')')


class CrystalPanel(QWidget):
    def __init__(self):
        super().__init__();layout = QVBoxLayout(self);layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget();layout.addWidget(self.tabs)
        self.planes = LatticePlanePanel();self.polyhedra = PolyhedraPanel()
        from .element_rules_panel import ElementRulesPanel
        self.rules = ElementRulesPanel()
        for widget, title in ((self.planes, 'HKL planes'), (self.polyhedra, 'Polyhedra'), (self.rules, 'Pair rules')):
            scroll = QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setWidget(widget);self.tabs.addTab(scroll, title)

    def set_values(self, options):
        self.planes.set_values(options.lattice_planes);self.polyhedra.set_values(options)
        self.rules.set_values(options.element_pair_rules, options.pair_rules_only)
