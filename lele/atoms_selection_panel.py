"""Select atoms by element ordinal, global index or selection expression."""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)


def element_indices(frame):
    """Element → site indices, matching the existing Atoms browser order.

    Mixed-occupancy components share their site index. Their original CIF
    row order determines both element order and element-local numbering.
    """
    if frame is None:
        return {}
    groups = {}
    if 'site_occupancies' not in frame.info and 'cif_row_order' not in frame.info:
        # Ordinary structures do not need one temporary species dictionary
        # per atom just to recover the same symbol list.
        rows = enumerate(frame.symbols)
    else:
        from .site_occupancy import component_rows
        rows = component_rows(frame)
    for index, symbol in rows:
        groups.setdefault(symbol, []).append(index)
    return groups


def parse_atom_indices(text, count, *, base=1):
    """Parse bounded ranges in an explicit numbering base to zero-based rows."""
    if base not in (0, 1):
        raise ValueError("Atom numbering base must be 0 or 1.")
    text = str(text).strip().replace('，', ',')
    if not text:
        return []
    indices = set()
    for part in text.split(','):
        match = re.fullmatch(r'\s*([0-9]+)\s*(?:-\s*([0-9]+)\s*)?', part)
        if match is None:
            raise ValueError('Use numbers or ranges separated by commas, for example 1, 2-10, 24.')
        try:
            first = int(match[1])
            last = int(match[2]) if match[2] is not None else first
        except ValueError:
            raise ValueError(f'Enter numbers from {base} to {count + base - 1}.') from None
        if first < base or last < base or first >= count + base or last >= count + base:
            raise ValueError(f'Enter numbers from {base} to {count + base - 1}.')
        if last < first:
            raise ValueError('A range must start with the smaller number, for example 2-10.')
        # Validate before expanding; even an enormous invalid range is cheap.
        indices.update(range(first - base, last - base + 1))
    return sorted(indices)


def parse_element_indices(text, count):
    """One-based element-local numbers; retained for existing callers."""
    return parse_atom_indices(text, count, base=1)


class AtomsSelectionPanel(QWidget):
    selectionRequested = Signal(list)
    expressionRequested = Signal(str)
    editingStarted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._source_refs = ()
        self._atom_count = None
        self.groups = {}
        self.inputs = {}
        self.errors = {}
        self.element_labels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.expression_input = QLineEdit()
        self.expression_input.setMinimumWidth(0)
        self.expression_input.setPlaceholderText('element O and within 3.5 of selected')
        self.expression_input.setAccessibleName('Atom selection expression')
        self.expression_input.setToolTip('Distances are in Å from the nearest selected atom. See Help → Atom selection syntax for examples.')
        self.expression_input.returnPressed.connect(self.submit_expression)
        self.expression_input.textEdited.connect(lambda _text: self.set_expression_error(''))
        self.expression_input.installEventFilter(self)
        self.expression_apply = QPushButton('Apply expression')
        self.expression_apply.clicked.connect(self.submit_expression)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self.expression_input, 1)
        row.addWidget(self.expression_apply)
        layout.addLayout(row)
        self.expression_error = QLabel()
        self.expression_error.setWordWrap(True)
        self.expression_error.setStyleSheet('color: #b42318;')
        self.expression_error.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.expression_error.hide()
        layout.addWidget(self.expression_error)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setMinimumWidth(0)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(self.scroll, 1)
        self.set_frame(None)

    def set_frame(self, frame, *, force=False, options=None):
        """Refresh chemistry/order only; ordinary scene refreshes are O(1).

        LELE chemistry edits, deletion and reordering replace the affected
        lists. Pasting extends symbols in place, so the count is checked too.
        Keep references rather than bare IDs to avoid reuse after collection.
        A caller that directly mutates same-length lists outside these edit
        APIs can request a rebuild with force=True.
        """
        self.expression_input.setEnabled(frame is not None)
        self.expression_apply.setEnabled(frame is not None)
        if frame is not self._frame:
            self.set_expression_error('')
        source_refs = () if frame is None else (
            frame.symbols, frame.info.get('site_occupancies'),
            frame.info.get('cif_row_order'), frame.info.get('atom_source_order'),
        )
        atom_count = None if frame is None else len(frame.symbols)
        if (not force and frame is self._frame and atom_count == self._atom_count
                and len(source_refs) == len(self._source_refs)
                and all(new is old for new, old in zip(source_refs, self._source_refs))
                and self.scroll.widget() is not None):
            self._update_swatches(options)
            return
        groups = element_indices(frame)
        self._frame = frame
        self._source_refs = source_refs
        self._atom_count = atom_count
        self.groups = groups
        self.inputs = {}
        self.errors = {}
        self.element_labels = {}
        self._swatches = {}
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 2, 2, 2)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(1, 1)
        self.index_inputs = {}
        self.index_errors = {}
        if frame is not None:
            for row, (key, label, base, example) in enumerate((
                    ('global', 'Global index', 1, '1, 2-10, 24'),)):
                editor = QLineEdit()
                editor.setMinimumWidth(0)
                editor.setPlaceholderText(example)
                editor.setAccessibleName(label)
                editor.setToolTip(f'{label}: {base}…{len(frame.symbols) + base - 1} in the current structure order.\n'
                                  'Combined with every other filled row; duplicate atoms are selected once.')
                editor.returnPressed.connect(self.submit)
                editor.textEdited.connect(lambda _text, name=key: self._clear_index_error(name))
                editor.installEventFilter(self)
                error = QLabel()
                error.setWordWrap(True)
                error.setStyleSheet('color: #b42318;')
                error.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                error.hide()
                self.index_inputs[key] = editor
                self.index_errors[key] = error
                grid.addWidget(QLabel(label), row * 2, 0)
                grid.addWidget(editor, row * 2, 1)
                grid.addWidget(error, row * 2 + 1, 0, 1, 2)
        self.global_input = self.index_inputs.get('global')
        for row, (symbol, indices) in enumerate(groups.items()):
            label_container = QWidget()
            label_layout = QHBoxLayout(label_container)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(5)
            swatch = QLabel()
            swatch.setFixedSize(10, 10)
            self._swatches[symbol] = swatch
            label_layout.addWidget(swatch)
            label = QLabel(f'{symbol} ({len(indices)})')
            label_layout.addWidget(label)
            label_layout.addStretch()
            self.element_labels[symbol] = label
            editor = QLineEdit()
            editor.setMinimumWidth(0)
            editor.setPlaceholderText('1, 2-10, 24')
            editor.setAccessibleName(f'{symbol} atom numbers')
            editor.setToolTip(
                f'{symbol}: 1…{len(indices)} within this element, as numbered in the Atoms tab.\n'
                'All filled rows are combined. Clear every row and press Enter to clear the selection.\n'
                'Mixed-occupancy components select the same shared atomic site.')
            editor.returnPressed.connect(self.submit)
            editor.textEdited.connect(lambda _text, name=symbol: self._clear_error(name))
            editor.installEventFilter(self)
            self.inputs[symbol] = editor
            grid.addWidget(label_container, row * 2 + 2, 0)
            grid.addWidget(editor, row * 2 + 2, 1)
            error = QLabel()
            error.setWordWrap(True)
            error.setStyleSheet('color: #b42318;')
            error.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            error.hide()
            self.errors[symbol] = error
            grid.addWidget(error, row * 2 + 3, 0, 1, 2)
        if not groups:
            grid.addWidget(QLabel('No structure loaded'), 0, 0, 1, 2)
        grid.setRowStretch(len(groups) * 2 + 3, 1)
        old = self.scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll.setWidget(content)
        self._update_swatches(options)

    def _update_swatches(self, options):
        if not self._swatches:
            return
        from .render_options import RenderOptions
        from .style_presets import element_palette_color
        if options is None:
            options = RenderOptions()
        for symbol, swatch in self._swatches.items():
            color = element_palette_color(options, symbol)
            if color != swatch.property('elementColor'):
                swatch.setProperty('elementColor', color)
                swatch.setStyleSheet(f'background: {color}; border: 1px solid #64748b;')

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.FocusIn:
            self.editingStarted.emit()
        return super().eventFilter(watched, event)

    def set_expression_error(self, message):
        self.expression_error.setText(str(message))
        self.expression_error.setVisible(bool(message))
        self.expression_input.setStyleSheet('QLineEdit { border: 1px solid #b42318; }' if message else '')

    def submit_expression(self):
        if self._frame is None:
            self.set_expression_error('Open a structure before selecting atoms.')
            return False
        text = self.expression_input.text().strip()
        if not text:
            self.set_expression_error("Enter an expression; use 'none' to clear the selection.")
            return False
        self.set_expression_error('')
        self.expressionRequested.emit(text)
        return True

    def _clear_error(self, symbol):
        self.errors[symbol].clear()
        self.errors[symbol].hide()
        self.inputs[symbol].setStyleSheet('')

    def _clear_index_error(self, key):
        self.index_errors[key].clear()
        self.index_errors[key].hide()
        self.index_inputs[key].setStyleSheet('')

    def submit(self):
        if self._frame is None:
            return False
        selected = set()
        invalid = []
        for key, base in (('global', 1),):
            self._clear_index_error(key)
            try:
                selected.update(parse_atom_indices(self.index_inputs[key].text(), len(self._frame.symbols), base=base))
            except ValueError as exc:
                self.index_errors[key].setText(str(exc))
                self.index_errors[key].show()
                self.index_inputs[key].setStyleSheet('QLineEdit { border: 1px solid #b42318; }')
                invalid.append(self.index_inputs[key])
        for symbol, indices in self.groups.items():
            self._clear_error(symbol)
            try:
                ordinals = parse_element_indices(self.inputs[symbol].text(), len(indices))
            except ValueError as exc:
                self.errors[symbol].setText(str(exc))
                self.errors[symbol].show()
                self.inputs[symbol].setStyleSheet('QLineEdit { border: 1px solid #b42318; }')
                invalid.append(self.inputs[symbol])
            else:
                selected.update(indices[ordinal] for ordinal in ordinals)
        if invalid:
            invalid[0].setFocus()
            self.scroll.ensureWidgetVisible(invalid[0])
            return False
        self.selectionRequested.emit(sorted(selected))
        return True
