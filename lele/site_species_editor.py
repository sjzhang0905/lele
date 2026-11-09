"""Two-column element / occupancy editor for a single atomic site."""
from PySide6.QtCore import Signal,Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QTableWidget,QTableWidgetItem,
    QHeaderView,QPushButton,QLabel,QAbstractItemView)

from .site_occupancy import site_species,validate_site_species


class SiteSpeciesEditor(QWidget):
    validityChanged=Signal(bool)

    def __init__(self,frame,atom,*,editable=True,parent=None):
        super().__init__(parent)
        self._editable=editable
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0)
        self.table=QTableWidget(0,2)
        self.table.setHorizontalHeaderLabels(['Element','Occupancy (0–1)'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(130)
        layout.addWidget(self.table)
        actions=QHBoxLayout();layout.addLayout(actions)
        self.add_button=QPushButton('Add element');self.remove_button=QPushButton('Remove row')
        self.add_button.clicked.connect(lambda:self.add_row())
        self.remove_button.clicked.connect(self.remove_rows)
        actions.addWidget(self.add_button);actions.addWidget(self.remove_button);actions.addStretch()
        self.total=QLabel();self.total.setWordWrap(True);layout.addWidget(self.total)
        note=QLabel('Enter fractions, for example Fe 0.6 and Ni 0.3 → vacancy 0.1. '
                    'Total occupancy must be ≤ 1. Applies to this atom in the current frame. Ctrl+Z to undo.')
        note.setWordWrap(True);layout.addWidget(note)
        for symbol,weight in site_species(frame,atom).items():self.add_row(symbol,repr(weight))
        self.add_row()
        self.table.cellChanged.connect(self._validate)
        self.add_button.setEnabled(editable);self.remove_button.setEnabled(editable)
        if not editable:self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._validate()

    def add_row(self,symbol='',weight=''):
        row=self.table.rowCount();self.table.insertRow(row)
        for column,text in enumerate((symbol,weight)):
            self.table.setItem(row,column,QTableWidgetItem(str(text)))
        if symbol:
            self.table.item(row,1).setData(Qt.ItemDataRole.UserRole,(str(weight),float(weight)))
        if not symbol:self.table.setCurrentCell(row,0)

    def remove_rows(self):
        rows=sorted({item.row() for item in self.table.selectedItems()},reverse=True)
        for row in rows:self.table.removeRow(row)
        if not self.table.rowCount():self.add_row()
        self._validate()

    def requested_rows(self):
        rows=[]
        for row in range(self.table.rowCount()):
            cells=[self.table.item(row,c) for c in range(2)]
            symbol,weight=[item.text().strip() if item is not None else '' for item in cells]
            original=cells[1].data(Qt.ItemDataRole.UserRole) if cells[1] is not None else None
            if original is not None and weight==original[0]:weight=original[1]
            if symbol or weight!='':rows.append((symbol,weight))
        return rows

    def requested_species(self):
        return validate_site_species(self.requested_rows())

    def _validate(self,*_):
        try:
            values=self.requested_species()
            from math import fsum
            total=fsum(values.values());vacancy=max(0.,1-total)
            self.total.setText(f'Total occupancy {total:.12g}   ·   Vacancy {vacancy:.12g}')
            self.total.setStyleSheet('');self.valid=True
        except ValueError as exc:
            self.total.setText(str(exc));self.total.setStyleSheet('color: #AD2437;');self.valid=False
        self.validityChanged.emit(self.valid and self._editable)
