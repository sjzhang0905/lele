"""Element-grouped atom browser and per-atom appearance editor."""
from collections import defaultdict

from PySide6.QtCore import Qt, Signal, QSignalBlocker, QItemSelectionModel
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QAbstractItemView, QHeaderView, QGroupBox, QFormLayout,
    QPushButton, QColorDialog, QLineEdit, QSpinBox, QSlider,
)

from .panel_controls import PanelComboBox
from .atom_appearance import LABEL_MODES, ATOM_REPRESENTATIONS, appearance

COMPONENT_ROLE = int(Qt.ItemDataRole.UserRole) + 1


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
        self._component_items = {}
        self._component_colors = {}
        self._groups = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Atom / show', 'Colour', 'T %', 'Occupancy %'])
        self.tree.headerItem().setToolTip(3,'占据百分比 · Element occupancy at this site; 100% is fully occupied.')
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setIndentation(14)
        self.tree.setMinimumHeight(130)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            self.tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemChanged.connect(self._visibility_changed)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.setToolTip('Each element component has its own row. Components of a mixed site share coordinates and selection.\n'
                             'Checkbox / labels / transparency affect the shared site. Occupancy % is separate from transparency T %.')
        layout.addWidget(self.tree, 1)

        self.editor = QGroupBox('Atom appearance')
        form = QFormLayout(self.editor)
        form.setContentsMargins(8, 9, 8, 9)
        form.setSpacing(6)
        self.target_label = QLabel('Select one or more atoms')
        self.target_label.setWordWrap(True)
        form.addRow(self.target_label)
        self.representation_combo = PanelComboBox()
        for mode in ATOM_REPRESENTATIONS:
            self.representation_combo.addItem('Use global style' if mode=='Global' else mode,mode)
        self.representation_combo.setPlaceholderText('Mixed')
        self.representation_combo.currentIndexChanged.connect(self._representation_changed)
        self.representation_combo.setToolTip('Display style for selected atoms only. Each bond half follows its endpoint; Space filling hides that half. Use global style clears this override.')
        form.addRow('Selected style',self.representation_combo)
        label_actions = QGridLayout()
        for position, (attr, text, mode) in enumerate((
            ('show_labels_button', 'Labels', 'Element'),
            ('show_indices_button', 'Indices', 'Index (1..N)'),
            ('show_both_button', 'Both', 'Element + index (global)'),
            ('hide_labels_button', 'Hide', 'None'),
        )):
            button = QPushButton(text)
            button.setToolTip('Apply only to the selected atoms. Other atoms keep their label settings.')
            button.clicked.connect(lambda checked=False, value=mode: self._emit_patch({'label_mode': value}))
            setattr(self, attr, button)
            label_actions.addWidget(button, position//2, position%2)
        form.addRow('Selected labels', label_actions)
        self.label_combo = PanelComboBox()
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

    def set_frame(self, frame, colors=(), selection=(), *, component_colors=None, document_key=None):
        from .site_occupancy import site_species,description,component_rows
        from .core import colour
        expanded={symbol for symbol,item in self._groups.items() if item.isExpanded()}
        if document_key is not None and document_key != getattr(self,'_document_key',None):
            expanded=set()
        self._document_key=document_key
        current=self.tree.currentItem()
        current_data=current.data(0,Qt.ItemDataRole.UserRole) if current is not None else None
        current_symbol=current.data(0,COMPONENT_ROLE) if current is not None else None
        current_key=(current_data,current_symbol) if isinstance(current_data,int) else None
        current_group=current_symbol if current is not None and current.parent() is None else None
        sites=[] if frame is None else [site_species(frame,i) for i in range(len(frame.symbols))]
        self._frame,self._colors=frame,list(colors)
        if frame is not None and len(self._colors)!=len(frame.symbols):
            self._colors=[appearance(frame,i).color or colour(s) for i,s in enumerate(frame.symbols)]
        signature=None if frame is None else (id(frame),tuple(frame.symbols),tuple(tuple(s) for s in sites),tuple(component_rows(frame)))
        supplied=component_colors or {}
        self._component_colors={}
        with QSignalBlocker(self.tree):
            if signature!=self._signature:
                self.tree.clear();self._items.clear();self._component_items.clear();self._groups.clear()
                self._signature=signature
                groups=defaultdict(list)
                for i,symbol in component_rows(frame) if frame is not None else ():
                    groups[symbol].append(i)
                for symbol,indices in groups.items():
                    parent=QTreeWidgetItem([f'{symbol} ({len(indices)})','','',''])
                    parent.setToolTip(0,'Element components at source sites; mixed-site components share coordinates and source index.')
                    parent.setData(0,Qt.ItemDataRole.UserRole,tuple(indices))
                    parent.setData(0,COMPONENT_ROLE,symbol)
                    parent.setFlags(parent.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    self.tree.addTopLevelItem(parent);self._groups[symbol]=parent
                    for ordinal,i in enumerate(indices,1):
                        item=QTreeWidgetItem([f'{symbol}{ordinal}  ·  #{i+1}','','',''])
                        item.setData(0,Qt.ItemDataRole.UserRole,i)
                        item.setData(0,COMPONENT_ROLE,symbol)
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        parent.addChild(item);self._component_items[i,symbol]=item
                        self._items.setdefault(i,item)
                        if symbol==frame.symbols[i]:self._items[i]=item
                    parent.setExpanded(symbol in expanded)
            if frame is not None:
                for (i,symbol),item in self._component_items.items():
                    style=appearance(frame,i)
                    percent=f'{sites[i][symbol]*100:.10g}%'
                    coordinates=', '.join(f'{v:.8f}' for v in frame.positions[i])
                    tooltip=(f'Atom #{i+1}: {symbol}; coordinate-table site index\n'
                             f'Occupancy: {percent}\nCartesian / Å: {coordinates}\n'
                             'Site occupancy: '+description(frame,i))
                    if len(sites[i])>1:
                        tooltip+='\nComponents at this site share coordinates, selection and per-site appearance controls.'
                    item.setToolTip(0,tooltip);item.setToolTip(3,tooltip)
                    item.setCheckState(0,Qt.CheckState.Checked if style.visible else Qt.CheckState.Unchecked)
                    item.setForeground(0,QBrush(QColor('#303343' if style.visible else '#999999')))
                    default=self._colors[i] if symbol==frame.symbols[i] else style.color or colour(symbol)
                    value=supplied.get((i,symbol),default);self._component_colors[i,symbol]=value
                    color=QColor(value);item.setText(1,color.name());item.setBackground(1,QBrush(color))
                    item.setForeground(1,QBrush(QColor('#ffffff' if color.lightness()<135 else '#202020')))
                    item.setText(2,str(round((1-style.opacity)*100)))
                    item.setTextAlignment(2,Qt.AlignmentFlag.AlignCenter)
                    item.setText(3,percent);item.setTextAlignment(3,Qt.AlignmentFlag.AlignCenter)
                for parent in self._groups.values():
                    visible=[appearance(frame,i).visible for i in self._item_indices(parent)]
                    parent.setCheckState(0,Qt.CheckState.Checked if all(visible) else
                                         Qt.CheckState.Unchecked if not any(visible) else Qt.CheckState.PartiallyChecked)
            self.tree.clearSelection();selected_set=set(selection)
            for parent in self._groups.values():
                indices=set(self._item_indices(parent))
                if indices and indices<=selected_set and not parent.isExpanded():parent.setSelected(True)
            for (i,symbol),item in self._component_items.items():
                if i in selected_set:item.setSelected(True)
            item=None
            if current_group in self._groups and set(self._item_indices(self._groups[current_group]))<=selected_set:
                item=self._groups[current_group]
            elif current_key in self._component_items and current_key[0] in selected_set:
                item=self._component_items[current_key]
            elif selection:item=self._items.get(selection[-1])
            if item is not None:
                if item.parent() is not None and not item.parent().isExpanded():item=item.parent()
                self.tree.setCurrentItem(item,0,QItemSelectionModel.SelectionFlag.NoUpdate)
            for symbol,item in self._groups.items():item.setExpanded(symbol in expanded)
        self._sync_editor()

    def reveal_atom(self,index):
        """Explicit coordinate-row navigation expands only the matching element."""
        item=self._items.get(index)
        if item is None:return
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            item.parent().setExpanded(True)
            self.tree.setCurrentItem(item)
            item.setSelected(True)
            self.tree.scrollToItem(item)
        self._sync_editor()

    def _representation_changed(self,_):
        value=self.representation_combo.currentData()
        if value is not None:self._emit_patch({'representation':value})

    def _current_component(self,indices):
        item=self.tree.currentItem()
        if item is None:return None
        symbol=item.data(0,COMPONENT_ROLE)
        return next(((i,symbol) for i in self._item_indices(item)
                     if i in indices and (i,symbol) in self._component_items),None)

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
        component=self._current_component(indices)
        initial=self._component_colors.get(component,self._colors[indices[0]])
        color = QColorDialog.getColor(QColor(initial), self, 'Atom colour')
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
        component=self._current_component(indices)
        symbol=component[1] if component is not None else self._frame.symbols[indices[0]]
        self.target_label.setText(
            f'Atom #{indices[0] + 1} · {symbol}' if len(indices) == 1
            else f'{len(indices)} atoms selected')
        if len(indices)==1:
            from .site_occupancy import description,site_is_disordered
            if site_is_disordered(self._frame,indices[0]):
                self.target_label.setText(self.target_label.text()+'\nOccupancy: '+description(self._frame,indices[0]))
        styles = [appearance(self._frame, i) for i in indices]
        modes = {style.label_mode for style in styles}
        texts = {style.label_text for style in styles}
        values = {round((1 - style.opacity) * 100) for style in styles}
        active_symbol=component[1] if component is not None else None
        colors = {self._component_colors.get((i,active_symbol),self._colors[i]) for i in indices}
        blockers = [QSignalBlocker(widget) for widget in
                    (self.label_combo, self.label_text, self.transparency_spin, self.transparency_slider,self.representation_combo)]
        try:
            representations={style.representation for style in styles}
            self.representation_combo.setCurrentIndex(self.representation_combo.findData(styles[0].representation)
                if len(representations)==1 else -1)
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
