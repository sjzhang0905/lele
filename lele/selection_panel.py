"""Compact selection details and reusable named-fragment controls."""
from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal, QSignalBlocker, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPlainTextEdit, QPushButton, QToolButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .saved_fragments import fragments, index_summary, selected_indices


def _fixed_axes(frame):
    if frame is None:
        return None, ''
    values = frame.info.get('fixed_axes', frame.info.get('vasp_fixed_axes'))
    if values is None:
        return None, ''
    # Do not materialize an N×3 object array on every selection refresh. The
    # readers validate records once; only visible cells need scalar access.
    try:
        valid = len(values) == len(frame.symbols)
        shape = getattr(values, 'shape', None)
        if shape is not None:
            valid = valid and tuple(shape) == (len(frame.symbols), 3)
    except TypeError:
        valid = False
    if not valid:
        return None, 'Fixed-atom information has an incompatible atom count.'
    basis = frame.info.get('fixed_axes_basis', 'direct' if 'vasp_fixed_axes' in frame.info else 'cartesian')
    return values, str(basis)


class SelectionTableModel(QAbstractTableModel):
    """Lazy text formatting keeps full selections usable for large structures."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.rows = []
        self.indices = []
        self.direct = None
        self.fixed_axes = None
        self.fixed_basis = ''
        self.headers = []
        self.column_kinds = []
        self._row_source = None
        self.set_frame(None, [])

    def set_frame(self, frame, selection):
        indices = selected_indices(frame, selection) if frame is not None else []
        species = frame.info.get('site_occupancies') if frame is not None else None
        source = (frame.symbols if frame is not None else None, species)
        same_rows = (self._row_source is not None and source[0] is self._row_source[0]
                     and source[1] is self._row_source[1] and indices == self.indices)
        if same_rows:
            rows = self.rows
        elif species is None:
            rows = [(index, frame.symbols[index], 1., position) for position, index in enumerate(indices)]
        else:
            from .site_occupancy import site_species
            rows = [(index, symbol, occupancy, position) for position, index in enumerate(indices)
                    for symbol, occupancy in site_species(frame, index).items()]
        direct = None
        if frame is not None and any(frame.pbc):
            import numpy as np
            try:
                # Preserve unwrapped coordinates, matching Cartesian values.
                inverse = np.linalg.inv(frame.cell)
                direct = frame.positions[indices] @ inverse
            except np.linalg.LinAlgError:
                pass
        fixed_axes, fixed_basis = _fixed_axes(frame)
        headers = ['Index', 'Element', 'Occ. %', 'Cartesian X', 'Cartesian Y', 'Cartesian Z']
        kinds = [('index', 0), ('element', 0), ('occupancy', 0), *[('cartesian', i) for i in range(3)]]
        if direct is not None:
            headers.extend(['Direct X', 'Direct Y', 'Direct Z'])
            kinds.extend(('direct', i) for i in range(3))
        if fixed_axes is not None:
            headers.extend(['Fixed X', 'Fixed Y', 'Fixed Z'])
            kinds.extend(('fixed', i) for i in range(3))
        reset = len(rows) != len(self.rows) or headers != self.headers
        if reset:
            self.beginResetModel()
        self.frame, self.rows, self.indices = frame, rows, indices
        self._row_source = source
        self.direct, self.fixed_axes, self.fixed_basis = direct, fixed_axes, fixed_basis
        self.headers, self.column_kinds = headers, kinds
        if reset:
            self.endResetModel()
        elif rows:
            # A trajectory or in-place coordinate edit changes values, not
            # the table layout; retain column widths, scroll and row focus.
            self.dataChanged.emit(self.index(0, 0), self.index(len(rows) - 1, len(headers) - 1))

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            kind, axis = self.column_kinds[section]
            if role == Qt.ItemDataRole.DisplayRole:
                return self.headers[section]
            if role == Qt.ItemDataRole.ToolTipRole:
                if kind == 'cartesian':
                    return 'Cartesian coordinates in Å.'
                if kind == 'direct':
                    return 'Fractional coordinates along the cell vectors; values are not wrapped into 0…1.'
                if kind == 'fixed':
                    return f'T = fixed; F = free; — = unknown. Axis basis: {self.fixed_basis}.'
                if kind == 'occupancy':
                    return 'Occupancy of this element at the selected site, in percent.'
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows) or index.column() >= len(self.headers):
            return None
        atom, symbol, occupancy, selected_row = self.rows[index.row()]
        kind, axis = self.column_kinds[index.column()]
        if role == Qt.ItemDataRole.UserRole:
            return atom
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) if kind == 'element' else int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.headerData(index.column(), Qt.Orientation.Horizontal, role)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self.cell_text(index.row(), index.column())

    def cell_text(self, row, column):
        """Format one plain-text cell without constructing Qt model indices."""
        atom, symbol, occupancy, selected_row = self.rows[row]
        kind, axis = self.column_kinds[column]
        if kind == 'index':
            return str(atom + 1)
        if kind == 'element':
            return symbol
        if kind == 'occupancy':
            return f'{100 * occupancy:.8g}'
        if kind == 'cartesian':
            return f'{self.frame.positions[atom, axis]:.8f}'
        if kind == 'direct':
            return f'{self.direct[selected_row, axis]:.8f}'
        if kind == 'fixed':
            try:
                values = self.fixed_axes[atom]
                value = values[axis] if len(values) == 3 else None
            except (IndexError, TypeError):
                value = None
            return '—' if value is None else ('T' if bool(value) else 'F')
        return None


def _selection_plain_text_chunks(model, budget=.010):
    """Yield control between bounded chunks, returning complete aligned text.

    Two passes avoid retaining a second, potentially enormous collection of
    individual cell strings for all atoms while calculating the column widths.
    """
    if not model.rows:
        return ''
    deadline = monotonic() + budget
    widths = [len(header) for header in model.headers]
    for row in range(len(model.rows)):
        for column in range(len(widths)):
            widths[column] = max(widths[column], len(model.cell_text(row, column)))
        if monotonic() >= deadline:
            yield
            deadline = monotonic() + budget

    def line(values):
        return '  '.join(value.ljust(width) if kind[0] == 'element' else value.rjust(width)
                         for value, width, kind in zip(values, widths, model.column_kinds)).rstrip()

    lines = [line(model.headers)]
    for row in range(len(model.rows)):
        lines.append(line([model.cell_text(row, column) for column in range(len(widths))]))
        if monotonic() >= deadline:
            yield
            deadline = monotonic() + budget

    return '\n'.join(lines)


def selection_plain_text(model):
    """Immediate formatter for small selections and scientific export tests."""
    job = _selection_plain_text_chunks(model, budget=float('inf'))
    try:
        next(job)
    except StopIteration as finished:
        return finished.value


class SelectionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.summary_label = QLabel('No atoms selected')
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary_label.setWordWrap(True)
        self.summary_label.setMaximumHeight(45)
        self.summary_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        summary_row = QHBoxLayout()
        summary_row.addWidget(self.summary_label, 1)
        self.copy_coordinates_button = QPushButton('Copy coordinates')
        self.copy_coordinates_button.setToolTip(
            'Copy selected atoms as Element X Y Z in Å, in structure order.\n'
            'No XYZ header, atom numbers or coordinate recentering.\n'
            'Mixed sites use the representative element, as in XYZ export.')
        self.copy_coordinates_button.clicked.connect(self.copy_coordinates)
        summary_row.addWidget(self.copy_coordinates_button)
        layout.addLayout(summary_row)
        self.model = SelectionTableModel(self)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.text.setFont(font)
        self.text.setMinimumWidth(0)
        self.text.setPlaceholderText('No atoms selected')
        self.text.setToolTip('Select text and press Ctrl+C to copy. Cartesian coordinates are in Å.\n'
                             'Direct coordinates are fractional and are not wrapped into 0…1.\n'
                             'Occ. % is site occupancy. Fixed: T = fixed, F = free, — = unknown.')
        layout.addWidget(self.text, 1)
        self.note_label = QLabel()
        self.note_label.setWordWrap(True)
        self.note_label.setMaximumHeight(65)
        self.note_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.note_label)
        self._summary_indices = None
        self._text_dirty = False
        self._last_text = ''
        self._text_job = None
        self._text_generation = 0
        self._pending_view_state = None
        self._text_timer = QTimer(self)
        self._text_timer.setSingleShot(True)
        self._text_timer.timeout.connect(self._format_text_chunk)
        self.set_frame(None, [])

    def set_frame(self, frame, selection):
        self._cancel_text_job()
        self.model.set_frame(frame, selection)
        self.copy_coordinates_button.setEnabled(bool(self.model.indices))
        if self.model.indices != self._summary_indices:
            summary = index_summary(self.model.indices)
            self.summary_label.setText(f'Atoms {summary}' if summary else 'No atoms selected')
            self.summary_label.setToolTip('Index (1-based): ' + summary)
            self._summary_indices = self.model.indices
        notes = []
        if self.model.fixed_axes is not None:
            basis = 'Direct' if self.model.fixed_basis == 'direct' else 'Cartesian'
            notes.append(f'Fixed: T = fixed, F = free ({basis} axes).')
        if frame is not None and any(frame.pbc) and self.model.direct is None:
            notes.append('Direct coordinates unavailable: the cell is singular.')
        if frame is not None:
            constraint_notes = frame.info.get('constraint_notes', [])
            if isinstance(constraint_notes, str):
                constraint_notes = [constraint_notes]
            notes.extend(str(note) for note in constraint_notes if note)
        self.note_label.setText(' '.join(notes))
        self.note_label.setToolTip('\n'.join(notes))
        self.note_label.setVisible(bool(notes))
        self._text_dirty = True
        if self.isVisible():
            self._refresh_text()

    def copy_coordinates(self):
        if self.model.frame is None or not self.model.indices:
            return
        from .atom_clipboard import coordinate_text
        QApplication.clipboard().setText(coordinate_text(self.model.frame, self.model.indices))

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_text()

    def hideEvent(self, event):
        self._cancel_text_job()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._cancel_text_job()
        super().closeEvent(event)

    def _cancel_text_job(self):
        self._text_timer.stop()
        self._text_generation += 1
        if self._text_job is not None:
            self._text_job.close()
            self._text_job = None

    def _refresh_text(self):
        if not self._text_dirty:
            return
        self._cancel_text_job()
        if len(self.model.rows) < 2000:
            self._text_dirty = False
            self._apply_text(selection_plain_text(self.model))
            return
        if self._pending_view_state is None:
            self._pending_view_state = self._text_view_state()
            self.text.setPlainText('Updating…')
            self._last_text = None
        # A short quiet period avoids starting a full pass for every rapidly
        # changing trajectory frame. All work stays on the GUI thread, using
        # its current model; set_frame invalidates the job before any mutation.
        self._text_job = _selection_plain_text_chunks(self.model)
        self._text_timer.start(100)

    def _format_text_chunk(self):
        job = self._text_job
        if job is None:
            return
        if not self.isVisible():
            self._cancel_text_job()
            return
        generation = self._text_generation
        try:
            next(job)
        except StopIteration as finished:
            if generation == self._text_generation and job is self._text_job:
                self._text_job = None
                self._text_dirty = False
                self._apply_text(finished.value)
        else:
            if generation == self._text_generation and job is self._text_job:
                self._text_timer.start(0)

    def _text_view_state(self):
        cursor = self.text.textCursor()
        return (cursor.position(), cursor.anchor(), self.text.horizontalScrollBar().value(),
                self.text.verticalScrollBar().value())

    def _apply_text(self, value):
        if value == self._last_text:
            return
        position, anchor, horizontal, vertical = self._pending_view_state or self._text_view_state()
        self._pending_view_state = None
        self.text.setPlainText(value)
        self._last_text = value
        cursor = self.text.textCursor()
        end = self.text.document().characterCount() - 1
        cursor.setPosition(min(anchor, end))
        cursor.setPosition(min(position, end), QTextCursor.MoveMode.KeepAnchor)
        self.text.setTextCursor(cursor)
        self.text.horizontalScrollBar().setValue(horizontal)
        self.text.verticalScrollBar().setValue(vertical)


class FragmentPanel(QWidget):
    saveRequested = Signal()
    deleteRequested = Signal(str)
    selectRequested = Signal(list)
    moveRequested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = None
        self._editable = False
        self._records_source = None
        self._atom_count = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setMinimumWidth(0)
        self.list_widget.itemClicked.connect(self._select_item)
        self.list_widget.currentItemChanged.connect(lambda *_: self._update_buttons())
        layout.addWidget(self.list_widget, 1)
        self.save_button = QToolButton()
        self.delete_button = QToolButton()
        self.front_button = QToolButton()
        self.back_button = QToolButton()
        row = QHBoxLayout()
        row.setSpacing(3)
        for button, text in ((self.save_button, 'Save'), (self.delete_button, 'Delete'),
                             (self.front_button, 'To first'), (self.back_button, 'To last')):
            button.setText(text)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.save_button.clicked.connect(self.saveRequested)
        self.delete_button.clicked.connect(lambda: self._emit_current(self.deleteRequested))
        self.front_button.clicked.connect(lambda: self._move('front'))
        self.back_button.clicked.connect(lambda: self._move('back'))
        self.save_button.setToolTip('Save the selected atoms as fragment1, fragment2, … in this frame.')
        self.front_button.setToolTip('Move these atoms together to the beginning of the atom sequence; retain their internal order.')
        self.back_button.setToolTip('Move these atoms together to the end of the atom sequence; retain their internal order.')
        self._selection = []
        self.set_frame(None, [])

    def current_name(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole)['name'] if item is not None else None

    def set_frame(self, frame, selection, editable=True):
        records = frame.info.get('saved_fragments') if frame is not None else None
        atom_count = len(frame.symbols) if frame is not None else 0
        unchanged = (frame is self._frame and records is self._records_source
                     and atom_count == self._atom_count)
        name = self.current_name() if frame is self._frame else None
        self._frame = frame
        # Only emptiness is needed to enable Save; the save helper validates
        # and sorts indices once when an actual fragment is created.
        self._selection = selection if frame is not None else []
        self._editable = bool(editable and frame is not None)
        if unchanged:
            self._update_buttons()
            return
        self._records_source = records
        self._atom_count = atom_count
        with QSignalBlocker(self.list_widget):
            self.list_widget.clear()
            for record in fragments(frame):
                item = QListWidgetItem(f'{record["name"]}  ({len(record["indices"])} atoms)')
                item.setData(Qt.ItemDataRole.UserRole, record)
                item.setToolTip(f'{record["name"]}\nIndex (1-based): {index_summary(record["indices"])}')
                self.list_widget.addItem(item)
                if record['name'] == name:
                    self.list_widget.setCurrentItem(item)
        self._update_buttons()

    def select_fragment_name(self, name):
        """Keep the newly saved fragment highlighted without selecting atoms again."""
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            if item.data(Qt.ItemDataRole.UserRole)['name'] == name:
                self.list_widget.setCurrentItem(item)
                return

    def _update_buttons(self):
        exists = self.current_name() is not None
        self.save_button.setEnabled(self._editable and bool(self._selection))
        for button in (self.delete_button, self.front_button, self.back_button):
            button.setEnabled(self._editable and exists)

    def _select_item(self, item):
        self.selectRequested.emit(list(item.data(Qt.ItemDataRole.UserRole)['indices']))

    def _emit_current(self, signal):
        name = self.current_name()
        if self._editable and name is not None:
            signal.emit(name)

    def _move(self, destination):
        name = self.current_name()
        if self._editable and name is not None:
            self.moveRequested.emit(name, destination)
