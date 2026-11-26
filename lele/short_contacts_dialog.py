"""Readable short-contact details for a captured source geometry."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QDialogButtonBox, QDoubleSpinBox, QHBoxLayout
from .dialog_policy import QDialog

from .periodic_geometry import short_contact_details, periodic_basis


class ShortContactsDialog(QDialog):
    thresholdChanged = Signal(float)

    def __init__(self, frame, context, parent=None, threshold=.6):
        super().__init__(parent)
        self.frame = frame.clone()
        periodic = periodic_basis(self.frame) is not None
        self.setWindowTitle('Short contacts'); self.resize(650 if periodic else 500, 420)
        layout = QVBoxLayout(self)
        self.context_label = QLabel(context); self.context_label.setWordWrap(True)
        layout.addWidget(self.context_label)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Distance threshold'))
        self.threshold = QDoubleSpinBox()
        self.threshold.setDecimals(3)
        self.threshold.setRange(0., 1.e6)
        self.threshold.setSingleStep(.05)
        self.threshold.setSuffix(' Å')
        self.threshold.setKeyboardTracking(False)
        self.threshold.setValue(threshold)
        controls.addWidget(self.threshold)
        controls.addStretch()
        layout.addLayout(controls)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4 if periodic else 3)
        headers = ['Atom 1', 'Atom 2', 'Distance (Å)']
        if periodic: headers.append('Atom 2 image (a, b, c)')
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)
        details = ('Shortest periodic image of each source atom pair. The image column gives the lattice '
                   'translation applied to Atom 2 in the original coordinates. Cell display copies are not counted again.'
                   if periodic else 'Each source atom pair is listed once.')
        self.details = details + '\nSnapshot of the geometry shown when this window opened.'
        self.note = QLabel()
        self.note.setWordWrap(True); layout.addWidget(self.note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close); layout.addWidget(buttons)
        self.table.sortItems(2, Qt.SortOrder.AscendingOrder)
        self._update_contacts(self.threshold.value())
        self.threshold.valueChanged.connect(self._update_contacts)

    def _update_contacts(self, threshold):
        self.contacts = short_contact_details(self.frame, threshold)
        self.summary.setText(f'{len(self.contacts)} short contacts · distance < {threshold:g} Å')
        self.note.setText(('' if self.contacts else 'No short contacts in this geometry.\n') + self.details)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.contacts))
        for row, contact in enumerate(self.contacts):
            labels = [f'{self.frame.symbols[i]}{i+1}' for i in (contact.first, contact.second)]
            for column, text in enumerate(labels): self.table.setItem(row, column, QTableWidgetItem(text))
            distance = QTableWidgetItem()
            distance.setData(Qt.ItemDataRole.DisplayRole, round(contact.distance, 6))
            distance.setToolTip(f'{contact.distance:.12g} Å'); self.table.setItem(row, 2, distance)
            if self.table.columnCount() == 4:
                self.table.setItem(row, 3, QTableWidgetItem(' '.join(str(x) for x in contact.image_shift)))
        self.table.setSortingEnabled(True)
        self.thresholdChanged.emit(threshold)
