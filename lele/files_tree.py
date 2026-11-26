"""Files tree with sparse Qt rows for long trajectories and energy histories."""
from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QTreeView


class FileItem(QStandardItem):
    """One ordinary tree node; a contiguous run of leaves can be computed on demand."""
    def __init__(self, labels):
        super().__init__(labels[0])
        self.setEditable(False)
        self.rows = None

    def addChild(self, item):
        self.appendRow(item)

    def addChildren(self, items):
        self.appendRows(items)

    def add_virtual_rows(self, count, data):
        start = self.rowCount()
        self.rows = (start, start + count, data)
        self.setColumnCount(1)
        self.setRowCount(start + count)
        return start

    def childCount(self):
        return self.rowCount()

    def child(self, row, column=0):
        if self.rows and self.rows[0] <= row < self.rows[1]:
            return FileRow(self, row)
        return super().child(row, column)

    def branches(self):
        if self.rows is None:
            return (self.child(row) for row in range(self.rowCount()))
        start, stop, _ = self.rows
        from itertools import chain
        return (self.child(row) for row in chain(range(start), range(stop, self.rowCount())))

    def text(self, column=0):
        return super().text()

    def setText(self, *args):
        super().setText(args[-1])

    def setToolTip(self, *args):
        super().setToolTip(args[-1])

    def toolTip(self, column=0):
        return super().toolTip()

    def setForeground(self, *args):
        super().setForeground(args[-1])

    def foreground(self, column=0):
        return super().foreground()

    def setData(self, *args):
        if len(args) == 3:
            _, role, value = args
            super().setData(value, role)
        else:
            super().setData(*args)

    def data(self, *args):
        return super().data(args[-1]) if args else super().data()

    def setExpanded(self, value):
        if self.model() is not None:
            self.model().parent().setExpanded(self.index(), value)

    def isExpanded(self):
        return self.model() is not None and self.model().parent().isExpanded(self.index())


class FileRow:
    """A transient handle for an addressable frame or energy record."""
    def __init__(self, parent, row):
        self.group = parent
        self.row = row

    def index(self):
        return self.group.model().index(self.row, 0, self.group.index())

    def parent(self):
        return self.group

    def data(self, column, role):
        start, _, provider = self.group.rows
        return provider(self.row - start, role)

    def text(self, column=0):
        return self.data(column, Qt.ItemDataRole.DisplayRole)

    def toolTip(self, column=0):
        return self.data(column, Qt.ItemDataRole.ToolTipRole) or ''

    def childCount(self):
        return 0


class FileModel(QStandardItemModel):
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole,
                                       Qt.ItemDataRole.UserRole, Qt.ItemDataRole.AccessibleTextRole):
            parent = index.parent()
            if parent.isValid():
                group = self.itemFromIndex(parent)
                span = getattr(group, 'rows', None)
                if span and span[0] <= index.row() < span[1]:
                    if role == Qt.ItemDataRole.AccessibleTextRole:
                        role = Qt.ItemDataRole.DisplayRole
                    return span[2](index.row() - span[0], role)
        return super().data(index, role)

class FilesTree(QTreeView):
    currentItemChanged = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.setModel(FileModel(0, 1, self))
        self.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)

    def _item(self, index):
        if not index.isValid():
            return None
        parent = index.parent()
        if not parent.isValid():
            return self.topLevelItem(index.row())
        return self.model().itemFromIndex(parent).child(index.row())

    def currentChanged(self, current, previous):
        super().currentChanged(current, previous)
        self.currentItemChanged.emit(self._item(current), self._item(previous))

    def currentItem(self):
        return self._item(self.currentIndex())

    def setCurrentItem(self, item):
        self.setCurrentIndex(item.index() if item is not None else QModelIndex())

    def itemAt(self, position):
        return self._item(self.indexAt(position))

    def scrollToItem(self, item):
        self.scrollTo(item.index())

    def clear(self):
        self.model().removeRows(0, self.model().rowCount())

    def topLevelItem(self, index):
        return self.model().item(index)

    def topLevelItemCount(self):
        return self.model().rowCount()

    def addTopLevelItem(self, item):
        self.model().appendRow(item)

    def indexOfTopLevelItem(self, item):
        return item.row()

    def takeTopLevelItem(self, index):
        row = self.model().takeRow(index)
        return row[0] if row else None

    def insertTopLevelItem(self, index, item):
        self.model().insertRow(index, item)
