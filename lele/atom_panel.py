"""Element-grouped atom browser and per-atom appearance editor."""
from collections import defaultdict

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QItemSelectionModel
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QHeaderView, QGroupBox, QFormLayout, QComboBox,
    QPushButton, QColorDialog, QLineEdit, QSpinBox, QSlider,
)

from .atom_appearance import LABEL_MODES, appearance


class AtomPanel(QWidget):
    selectionChanged = Signal(list)
    appearanceChanged = Signal(list, dict)
    resetRequested = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._signature = None
        self._colors = []
        self._items = {}
        self._groups = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Atom / show', 'Colour', 'T %'])
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setIndentation(14)
        self.tree.setMinimumHeight(130)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._visibility_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setToolTip('Checkbox: show atom. Ctrl/Shift: select multiple atoms. T %: transparency.')
        layout.addWidget(self.tree, 1)

        self.editor = QGroupBox('Atom appearance')
        form = QFormLayout(self.editor)
        form.setContentsMargins(8, 9, 8, 9)
        form.setSpacing(6)
        self.target_label = QLabel('Select one or more atoms')
        self.target_label.setWordWrap(True)
        form.addRow(self.target_label)
        self.label_combo = QComboBox()
        self.label_combo.addItem('Use global label setting', 'Global')
        for mode in LABEL_MODES:
            self.label_combo.addItem(mode, mode)
        self.label_combo.addItem('Custom text', 'Custom')
        self.label_combo.setPlaceholderText('Mixed')
        self.label_combo.currentIndexChanged.connect(self._label_mode_changed)
        form.addRow('Label', self.label_combo)
        self.label_text = QLineEdit()
        self.label_text.setPlaceholderText('Custom atom label')
        self.label_text.editingFinished.connect(self._custom_label_changed)
        form.addRow('Text', self.label_text)
        color_row = QHBoxLayout()
        self.color_button = QPushButton('Colour…')
        self.color_button.clicked.connect(self.choose_color)
        self.element_color_button = QPushButton('Use element colour')
        self.element_color_button.clicked.connect(lambda: self._emit_patch({'color': None}))
        color_row.addWidget(self.color_button)
        color_row.addWidget(self.element_color_button)
        form.addRow(color_row)
        transparency_row = QHBoxLayout()
        self.transparency_slider = QSlider(Qt.Orientation.Horizontal)
        self.transparency_slider.setRange(0, 100)
        self.transparency_slider.setTracking(False)
        self.transparency_spin = QSpinBox()
        self.transparency_spin.setRange(0, 100)
        self.transparency_spin.setSuffix(' %')
        self.transparency_spin.setKeyboardTracking(False)
        self.transparency_spin.lineEdit().setPlaceholderText('Mixed')
        self.transparency_slider.valueChanged.connect(self.transparency_spin.setValue)
        self.transparency_spin.valueChanged.connect(self._transparency_changed)
        transparency_row.addWidget(self.transparency_slider, 1)
        transparency_row.addWidget(self.transparency_spin)
        form.addRow('Transparency', transparency_row)
        self.transparency_spin.setToolTip('0%: opaque. 100%: fully transparent. Bonds fade faster: 50% atom transparency gives 75% bond transparency. Display settings apply to matching frames in this file.')
        self.reset_button = QPushButton('Reset atom display')
        self.reset_button.clicked.connect(lambda: self.resetRequested.emit(self.selected_indices()))
        form.addRow(self.reset_button)
        layout.addWidget(self.editor)
        note = QLabel('Current frame · display only · Ctrl+Z to undo')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.editor.setEnabled(False)

    @staticmethod
    def _item_indices(item):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        return [value] if isinstance(value, int) else list(value or ())

    def selected_indices(self):
        return sorted({i for item in self.tree.selectedItems() for i in self._item_indices(item)})

    def set_frame(self, frame, colors=(), selection=()):
        expanded={symbol for symbol,item in self._groups.items() if item.isExpanded()}
        self._frame, self._colors = frame, list(colors)
        signature = None if frame is None else (id(frame), tuple(frame.symbols))
        with QSignalBlocker(self.tree):
            if signature != self._signature:
                self.tree.clear()
                self._items.clear()
                self._groups.clear()
                self._signature = signature
                if frame is not None:
                    groups = defaultdict(list)
                    for i, symbol in enumerate(frame.symbols):
                        groups[symbol].append(i)
                    for symbol in sorted(groups):
                        indices = groups[symbol]
                        parent = QTreeWidgetItem([f'{symbol} ({len(indices)})'])
                        parent.setData(0, Qt.ItemDataRole.UserRole, tuple(indices))
                        parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        self.tree.addTopLevelItem(parent)
                        self._groups[symbol] = parent
                        for ordinal, i in enumerate(indices, 1):
                            item = QTreeWidgetItem([f'{symbol}{ordinal}  ·  #{i + 1}'])
                            item.setData(0, Qt.ItemDataRole.UserRole, i)
                            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                            from .site_occupancy import description
                            item.setToolTip(0, f'Atom #{i + 1}: {symbol}; coordinate-table index\nOccupancy: '+description(frame,i))
                            parent.addChild(item)
                            self._items[i] = item
                        parent.setExpanded(symbol in expanded)
            if frame is not None:
                for i, item in self._items.items():
                    from .site_occupancy import description
                    item.setToolTip(0,f'Atom #{i+1}: {frame.symbols[i]}; coordinate-table index\nOccupancy: '+description(frame,i))
                    style = appearance(frame, i)
                    item.setCheckState(0, Qt.CheckState.Checked if style.visible else Qt.CheckState.Unchecked)
                    item.setForeground(0, QBrush(QColor('#303343' if style.visible else '#999999')))
                    color = QColor(self._colors[i])
                    item.setText(1, color.name())
                    item.setBackground(1, QBrush(color))
                    item.setForeground(1, QBrush(QColor('#ffffff' if color.lightness() < 135 else '#202020')))
                    item.setText(2, str(round((1 - style.opacity) * 100)))
                    item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)
                for parent in self._groups.values():
                    visible = [appearance(frame, i).visible for i in self._item_indices(parent)]
                    state = (Qt.CheckState.Checked if all(visible) else
                             Qt.CheckState.Unchecked if not any(visible) else Qt.CheckState.PartiallyChecked)
                    parent.setCheckState(0, state)
            self.tree.clearSelection()
            selected_set=set(selection)
            for parent in self._groups.values():
                indices=set(self._item_indices(parent))
                if indices and indices<=selected_set and not parent.isExpanded():parent.setSelected(True)
            for i in selection:
                if i in self._items:
                    self._items[i].setSelected(True)
            if selection and selection[-1] in self._items:
                item=self._items[selection[-1]]
                if not item.parent().isExpanded():item=item.parent()
                self.tree.setCurrentItem(item, 0,
                                         QItemSelectionModel.SelectionFlag.NoUpdate)
            for symbol,item in self._groups.items():item.setExpanded(symbol in expanded)
        self._sync_editor()

    def _selection_changed(self):
        self._sync_editor()
        self.selectionChanged.emit(self.selected_indices())

    def _visibility_changed(self, item, column):
        if column == 0 and self._frame is not None:
            self.appearanceChanged.emit(self._item_indices(item),
                                        {'visible': item.checkState(0) != Qt.CheckState.Unchecked})

    def _emit_patch(self, values):
        indices = self.selected_indices()
        if indices:
            self.appearanceChanged.emit(indices, values)

    def _label_mode_changed(self, _index):
        mode = self.label_combo.currentData()
        self.label_text.setEnabled(mode == 'Custom')
        if mode is not None:
            self._emit_patch({'label_mode': mode})

    def _custom_label_changed(self):
        if self.label_combo.currentData() == 'Custom':
            self._emit_patch({'label_text': self.label_text.text()})

    def _transparency_changed(self, value):
        with QSignalBlocker(self.transparency_slider):
            self.transparency_slider.setValue(value)
        self._emit_patch({'opacity': 1 - value / 100})

    def choose_color(self):
        indices = self.selected_indices()
        if not indices:
            return
        color = QColorDialog.getColor(QColor(self._colors[indices[0]]), self, 'Atom colour')
        if color.isValid():
            self._emit_patch({'color': color.name()})

    def _double_clicked(self, _item, column):
        if column == 1:
            self.choose_color()
        elif column == 2:
            self.transparency_spin.setFocus()

    def _sync_editor(self):
        indices = self.selected_indices()
        self.editor.setEnabled(bool(indices))
        if not indices or self._frame is None:
            self.target_label.setText('Select one or more atoms')
            return
        self.target_label.setText(
            f'Atom #{indices[0] + 1} · {self._frame.symbols[indices[0]]}' if len(indices) == 1
            else f'{len(indices)} atoms selected')
        styles = [appearance(self._frame, i) for i in indices]
        modes = {style.label_mode for style in styles}
        texts = {style.label_text for style in styles}
        values = {round((1 - style.opacity) * 100) for style in styles}
        colors = {self._colors[i] for i in indices}
        blockers = [QSignalBlocker(widget) for widget in
                    (self.label_combo, self.label_text, self.transparency_spin, self.transparency_slider)]
        try:
            self.label_combo.setCurrentIndex(self.label_combo.findData(styles[0].label_mode) if len(modes) == 1 else -1)
            self.label_text.setEnabled(modes == {'Custom'})
            self.label_text.setText(next(iter(texts)) if len(texts) == 1 else '')
            self.label_text.setPlaceholderText('Custom atom label' if len(texts) == 1 else 'Mixed')
            value = round((1 - styles[0].opacity) * 100)
            self.transparency_spin.setValue(value)
            self.transparency_slider.setValue(value)
            if len(values) > 1:
                self.transparency_spin.lineEdit().clear()
            self.color_button.setText('Colour… ' + (next(iter(colors)) if len(colors) == 1 else 'Mixed'))
        finally:
            del blockers
