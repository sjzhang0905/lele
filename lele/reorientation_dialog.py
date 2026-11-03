"""Origin/X/Z selection and a compatible row-matrix paste mode."""
import re
import numpy as np
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QLabel,QComboBox,
    QSpinBox,QPlainTextEdit,QCheckBox,QDialogButtonBox,QMessageBox)
from .coordinate_reorientation import local_axis_rotation,proper_rotation
from .periodic_geometry import periodic_basis


def parse_row_matrix(text):
    tokens=re.sub(r'[\s,;\[\]()]',' ',text).split()
    if len(tokens)!=9:raise ValueError('Paste nine matrix entries in three rows (row-vector convention).')
    try:matrix=np.asarray([float(v.replace('D','E').replace('d','e')) for v in tokens]).reshape(3,3)
    except ValueError:raise ValueError('Use nine finite numeric matrix entries.') from None
    return proper_rotation(matrix).T


class ReorientationDialog(QDialog):
    def __init__(self,frame,selection=(),parent=None):
        super().__init__(parent);self.frame=frame
        self.setWindowTitle('Reorient complete structure / crystal');self.resize(610,540)
        layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.mode=QComboBox();self.mode.addItems(['Origin + X/Z atoms','Paste rotation matrix (row vectors)'])
        form.addRow('Define orientation',self.mode)
        defaults=list(selection[:3])
        for i in range(len(frame.symbols)):
            if len(defaults)>=3:break
            if i not in defaults:defaults.append(i)
        self.origin=QSpinBox();self.x_atom=QSpinBox();self.z_atom=QSpinBox()
        for i,spin in enumerate((self.origin,self.x_atom,self.z_atom)):
            spin.setRange(1,max(1,len(frame.symbols)))
            spin.setValue(defaults[i]+1 if i<len(defaults) else 1)
        form.addRow('Origin atom (1-based)',self.origin)
        form.addRow('X hint atom (1-based)',self.x_atom)
        form.addRow('Z direction atom (1-based)',self.z_atom)
        note=QLabel('Select origin → X hint → Z, or enter their atom indices. '
            'Z is kept exact; X is projected perpendicular to Z. '
            'Coordinates and cell rotate together; lengths, angles and volume are preserved.')
        note.setWordWrap(True);layout.addWidget(note)
        self.nearest=QCheckBox('Use nearest periodic images around the origin')
        periodic=periodic_basis(frame) is not None
        self.nearest.setChecked(periodic);self.nearest.setEnabled(periodic)
        self.nearest.setToolTip('Also use the nearest periodic bond directions. Atom count and atom order are unchanged; negative Cartesian coordinates are allowed.')
        layout.addWidget(self.nearest)
        self.matrix_label=QLabel('Paste Q from the analyzer/rotation script: r_new(row) = r_old(row) @ Q + t')
        self.matrix_label.setWordWrap(True);layout.addWidget(self.matrix_label)
        self.matrix=QPlainTextEdit('1 0 0\n0 1 0\n0 0 1');self.matrix.setMaximumHeight(100)
        layout.addWidget(self.matrix)
        layout.addWidget(QLabel('Calculated row-vector matrix Q = R.T (copyable):'))
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setMaximumHeight(112)
        layout.addWidget(self.preview)
        self.quality=QLabel();self.quality.setWordWrap(True);layout.addWidget(self.quality)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Apply rotation')
        self.buttons.accepted.connect(self._accept_plan);self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.mode.currentIndexChanged.connect(self._update_preview)
        for spin in (self.origin,self.x_atom,self.z_atom):spin.valueChanged.connect(self._update_preview)
        self.nearest.toggled.connect(self._update_preview);self.matrix.textChanged.connect(self._update_preview)
        self._update_preview()

    def plan(self):
        origin=self.origin.value()-1;center=self.frame.positions[origin].copy()
        if self.mode.currentIndex()==0:
            rotation,details=local_axis_rotation(self.frame,origin,self.x_atom.value()-1,self.z_atom.value()-1,
                                                nearest_images=self.nearest.isChecked())
        else:
            rotation=parse_row_matrix(self.matrix.toPlainText());details={'selection':[origin],'axes_convention':'Imported row-vector matrix Q = R.T'}
        return rotation,-center@rotation.T,center if self.nearest.isChecked() else None,details

    def _update_preview(self,*_):
        manual=self.mode.currentIndex()==1
        self.matrix.setVisible(manual);self.matrix_label.setVisible(manual)
        self.x_atom.setEnabled(not manual);self.z_atom.setEnabled(not manual)
        try:
            rotation,translation,_,details=self.plan()
            self.preview.setPlainText('\n'.join(' '.join(f'{v: .12f}' for v in row) for row in rotation.T))
            text=f'det(Q) = {np.linalg.det(rotation):.10f}; origin atom #{self.origin.value()} → (0, 0, 0).'
            if 'raw_x_z_angle_deg' in details:
                text+=f' Original X–Z angle: {details["raw_x_z_angle_deg"]:.6f}°. Z stays exact; X uses its perpendicular projection.'
            self.quality.setText(text);valid=True
        except ValueError as exc:
            self.preview.clear();self.quality.setText(str(exc));valid=False
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)

    def _accept_plan(self):
        try:self.plan()
        except ValueError as exc:QMessageBox.warning(self,'Orientation unavailable',str(exc));return
        self.accept()
