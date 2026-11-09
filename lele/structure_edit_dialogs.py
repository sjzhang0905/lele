"""Atom index and slab vacuum editors with explicit current-geometry previews."""
from PySide6.QtWidgets import (QDialog,QWidget,QTabWidget,QVBoxLayout,QFormLayout,QLabel,QSpinBox,QDoubleSpinBox,
                              QComboBox,QDialogButtonBox,QPushButton,QMessageBox)
from .site_occupancy import description
from .vacuum import slab_vacuum


def confirm_maximum_occupancy_export(parent):
    message=QMessageBox(QMessageBox.Icon.Question,'Mixed / partial occupancy export',
        'This format cannot preserve mixed element occupancies or vacancy fractions.\n'
        'Use the highest-occupancy element at each site in an ordered export copy?\n\n'
        'Exported sites will be fully occupied; partial vacancies are ignored.\n'
        'Completely vacant sites are omitted.\n'
        'The current structure, occupancies and coordinates remain unchanged.',parent=parent)
    use=message.addButton('Use highest-occupancy element',QMessageBox.ButtonRole.AcceptRole)
    cancel=message.addButton('Cancel',QMessageBox.ButtonRole.RejectRole)
    message.setDefaultButton(cancel);message.setEscapeButton(cancel)
    message.exec()
    return message.clickedButton() is use


class AtomIndexDialog(QDialog):
    def __init__(self,frame,atom,selection=(),*,editable=True,parent=None):
        super().__init__(parent);self.setWindowTitle('Atom element / occupancy / index');self.operation='move';self.atom=atom
        self.editable=editable
        layout=QVBoxLayout(self);label=QLabel(f'Atom #{atom+1} · {frame.symbols[atom]}\nOccupancy: '+description(frame,atom))
        label.setWordWrap(True);layout.addWidget(label)
        layout.addWidget(QLabel('Cartesian / Å: '+', '.join(f'{v:.8f}' for v in frame.positions[atom])))
        self.tabs=QTabWidget();layout.addWidget(self.tabs)
        from .site_species_editor import SiteSpeciesEditor
        self.species=SiteSpeciesEditor(frame,atom,editable=editable)
        self.tabs.addTab(self.species,'Element / occupancy')
        self.index_page=QWidget();index_layout=QVBoxLayout(self.index_page)
        self.tabs.addTab(self.index_page,'Index')
        form=QFormLayout();index_layout.addLayout(form);self.index=QSpinBox();self.index.setRange(1,len(frame.symbols));self.index.setValue(atom+1)
        self.index.setEnabled(editable);form.addRow('New index (1-based)',self.index)
        note=QLabel('Moving to a new index shifts intervening indices. Atom coordinates and identities stay attached to their atoms. Applies to the current frame; Ctrl+Z restores its order.')
        note.setWordWrap(True);index_layout.addWidget(note)
        self.swap=None
        if len(selection)==2 and atom in selection:
            self.swap=next(i for i in selection if i!=atom)
            button=QPushButton(f'Swap indices #{selection[0]+1} ↔ #{selection[1]+1}')
            button.setEnabled(editable);button.clicked.connect(self._swap);index_layout.addWidget(button);self.swap_button=button
        index_layout.addStretch()
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._apply);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.tabs.currentChanged.connect(self._sync_apply)
        self.species.validityChanged.connect(self._sync_apply)
        self._sync_apply();self.resize(500,440)

    def _swap(self):self.operation='swap';self.accept()

    def _sync_apply(self,*_):
        species=self.tabs.currentWidget() is self.species
        button=self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        button.setText('Set element / occupancy' if species else 'Set index')
        button.setEnabled(self.editable and (not species or self.species.valid))

    def _apply(self):
        if not self.editable:return
        if self.tabs.currentWidget() is self.species:
            if not self.species.valid:return
            self.operation='species'
        else:self.operation='move'
        self.accept()


class VacuumDialog(QDialog):
    def __init__(self,frame,parent=None):
        super().__init__(parent);self.frame=frame;self.setWindowTitle('Modify slab vacuum');self.resize(530,340)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.axis=QComboBox();self.axis.addItems(['Automatic (largest periodic gap)','a normal','b normal','c normal'])
        form.addRow('Surface normal',self.axis)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.gap=QDoubleSpinBox();self.gap.setDecimals(6);self.gap.setRange(0,1000000);self.gap.setSuffix(' Å');self.gap.setKeyboardTracking(False)
        form.addRow('Vacuum spacing',self.gap)
        note=QLabel('Spacing is measured between outermost atomic planes and the neighboring slab, along the surface normal. Only the normal component of the chosen cell vector changes. Cartesian atom coordinates and the other two cell vectors stay fixed.')
        note.setWordWrap(True);layout.addWidget(note)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        self.axis.currentIndexChanged.connect(self._refresh);self._refresh()

    def selected_axis(self):return self.axis.currentIndex()-1 if self.axis.currentIndex() else None

    def requested_gap(self):
        return self._detected_gap if self.gap.value()==self._displayed_gap else self.gap.value()

    def _refresh(self,*_):
        try:
            data=slab_vacuum(self.frame,self.selected_axis());self.gap.setValue(data['gap'])
            self._detected_gap=data['gap'];self._displayed_gap=self.gap.value()
            self.info.setText(f'Normal to the other two cell vectors: {"abc"[data["axis"]]} direction\n'
                f'Cell height {data["height"]:.6f} Å · slab thickness {data["thickness"]:.6f} Å\n'
                f'Lower / upper surface projections {data["lower"]:.6f} / {data["upper"]:.6f} Å\n'
                f'Detected vacuum {data["gap"]:.6f} Å'+
                ('\nSlab crosses the cell boundary; fixed-coordinate adjustment is unavailable.' if data['split'] else ''))
            valid=not data['split']
        except ValueError as exc:self.info.setText(str(exc));valid=False
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
