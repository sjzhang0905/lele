"""Volumetric field selection and explicit molecular-orbital evaluation."""
from PySide6.QtCore import QSignalBlocker
from .panel_controls import PanelComboBox
from PySide6.QtWidgets import (QLabel, QDoubleSpinBox, QPushButton,
                              QHBoxLayout, QMessageBox, QGroupBox, QFormLayout, QSpinBox,
                              QCheckBox, QColorDialog, QDialog)
from .operations import run_data_task
from .output_text import LoadCancelled


def field_reference(document, volume):
    """Retain source geometry so channel changes follow display geometry edits."""
    return volume.reference_origin, volume.reference_voxel_vectors


def select_field(document, index):
    """Select without resurrecting detached fields or losing shared transforms."""
    if document.volume is None:
        raise ValueError('The volumetric fields were detached by a structure edit.')
    import numpy as np
    target = document.volumes[index]
    old = document.volume
    if target is old:
        return target
    original_origin, original_basis = field_reference(document, old)
    target_origin, target_basis = field_reference(document, target)
    transform = np.linalg.solve(original_basis, old.voxel_vectors)
    translation = old.origin - original_origin @ transform
    target.origin = target_origin @ transform + translation
    target.voxel_vectors = target_basis @ transform
    document.volume = target
    return target


class FieldActions:
    def _build_field_controls(self, form):
        self.field_combo = PanelComboBox()
        self.field_combo.currentIndexChanged.connect(self._select_field)
        form.addRow('Dataset', self.field_combo)
        self.field_import_button=QPushButton('Import another field file…')
        self.field_import_button.clicked.connect(self._import_field_file);form.addRow(self.field_import_button)
        self.field_note = QLabel('No volumetric field loaded.')
        self.field_note.setWordWrap(True); form.addRow(self.field_note)
        self.field_signs = PanelComboBox(); self.field_signs.addItems(['Both', 'Positive', 'Negative'])
        self.field_signs.currentTextChanged.connect(lambda value: self._set_option('volume_signs', value))
        form.addRow('Isosurface signs', self.field_signs)
        self._build_isosurface_style_controls(form)
        self.mo_combo = PanelComboBox(); form.addRow('Molecular orbital', self.mo_combo)
        self.mo_spacing = QDoubleSpinBox(); self.mo_spacing.setRange(.08, 1.)
        self.mo_spacing.setDecimals(2); self.mo_spacing.setSingleStep(.05); self.mo_spacing.setValue(.25)
        self.mo_spacing.setSuffix(' Å'); form.addRow('Grid spacing', self.mo_spacing)
        self.mo_generate = QPushButton('Calculate orbital grid')
        self.mo_generate.setToolTip('Evaluate the stored wavefunction on a grid. This is not a new electronic-structure calculation.')
        self.mo_generate.clicked.connect(self._generate_orbital_grid); form.addRow(self.mo_generate)
        self._field_document = None
        self._build_wavecar_controls(form)

    def _build_isosurface_style_controls(self, form):
        from .numeric_controls import IsovalueSpinBox
        self.surface_group = QGroupBox('Isosurface appearance')
        appearance = QFormLayout(self.surface_group)
        self.surface_form = appearance
        self.negative_independent = QCheckBox('Independent negative level')
        self.negative_independent.toggled.connect(lambda value:self._set_surface_option('volume_independent_negative',value))
        appearance.addRow(self.negative_independent)
        self.negative_iso = IsovalueSpinBox();self.negative_iso.setValue(.035)
        self.negative_iso.valueChanged.connect(lambda value:self._set_surface_option('volume_negative_iso',value))
        appearance.addRow('Negative |isovalue|',self.negative_iso)
        self.positive_color = QPushButton();self.negative_color = QPushButton()
        self.positive_color.clicked.connect(lambda:self._pick_surface_color('volume_positive_color'))
        self.negative_color.clicked.connect(lambda:self._pick_surface_color('volume_negative_color'))
        appearance.addRow('Positive color',self.positive_color);appearance.addRow('Negative color',self.negative_color)
        self.negative_opacity_independent = QCheckBox('Independent negative opacity')
        self.negative_opacity_independent.toggled.connect(lambda value:self._set_surface_option('volume_independent_opacity',value))
        appearance.addRow(self.negative_opacity_independent)
        self.negative_opacity = QDoubleSpinBox();self.negative_opacity.setRange(0,1)
        self.negative_opacity.setDecimals(2);self.negative_opacity.setSingleStep(.05);self.negative_opacity.setValue(.65)
        self.negative_opacity.valueChanged.connect(lambda value:self._set_surface_option('volume_negative_opacity',value))
        appearance.addRow('Negative opacity',self.negative_opacity)
        self.surface_style = PanelComboBox();self.surface_style.addItems(['Surface','Wireframe','Points'])
        self.surface_style.currentTextChanged.connect(lambda value:self._set_surface_option('volume_representation',value))
        appearance.addRow('Representation',self.surface_style)
        self.surface_line_width = QDoubleSpinBox();self.surface_line_width.setRange(.1,10.)
        self.surface_line_width.setSingleStep(.5);self.surface_line_width.setValue(1.)
        self.surface_line_width.valueChanged.connect(lambda value:self._set_surface_option('volume_line_width',value))
        appearance.addRow('Line / point size',self.surface_line_width)
        self.surface_smooth = QCheckBox('Smooth surface lighting');self.surface_smooth.setChecked(True)
        self.surface_smooth.setToolTip('Interpolate surface normals for lighting; grid values are unchanged.')
        self.surface_smooth.toggled.connect(lambda value:self._set_surface_option('volume_smooth_normals',value))
        appearance.addRow(self.surface_smooth)
        self.layers_button = QPushButton('Surface layers / ESP color mapping…')
        self.layers_button.clicked.connect(self._edit_surface_layers);appearance.addRow(self.layers_button)
        self.layers_note=QLabel();self.layers_note.setWordWrap(True);appearance.addRow(self.layers_note)
        form.addRow(self.surface_group)
        self.slice_button=QPushButton('Planar slice…');self.slice_button.clicked.connect(self._show_field_slice)
        form.addRow(self.slice_button)
        self.field_export_button=QPushButton('Export active field CUBE…')
        self.field_export_button.clicked.connect(self._export_active_field);form.addRow(self.field_export_button)

    def _set_surface_option(self,option,value):
        self._set_option(option,value)
        # Display settings remain editable before any structure is loaded.
        self._refresh_isosurface_style_controls()

    def _pick_surface_color(self, option):
        from PySide6.QtGui import QColor
        color=QColorDialog.getColor(QColor(getattr(self.render_options,option)),self,'Isosurface color')
        if color.isValid():self._set_surface_option(option,color.name())

    def _edit_surface_layers(self):
        from .isosurface_dialog import IsosurfaceLayersDialog
        fields=[] if self.doc is None else self.doc.volumes
        active=next((i for i,v in enumerate(fields) if v is self.doc.volume),-1) if self.doc else -1
        dialog=IsosurfaceLayersDialog(self.render_options,self,fields=fields,active_index=active)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self._set_surface_option('volume_surfaces',dialog.layers)

    def _import_field_file(self):
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        from .formats import load_document
        from .field_mapping import prepare_field_attachment
        doc=self.doc;frame=getattr(self,'frame',None)
        if doc is None or frame is None:return
        path,_=QFileDialog.getOpenFileName(self,'Import scalar field for overlay / ESP',str(doc.path.parent),
            'Scalar grids (*.cube *.cub CHGCAR* CHG PARCHG* ELFCAR* LOCPOT* AECCAR*);;All files (*)')
        if not path:return
        def prepare():
            incoming=load_document(Path(path))
            return prepare_field_attachment(doc,frame,incoming)
        try:added=run_data_task(self,'Importing scalar fields',prepare,cancellable=True)
        except LoadCancelled:return
        except Exception as exc:
            QMessageBox.warning(self,'Cannot attach scalar field',str(exc));return
        first=doc.volume is None
        doc.volumes.extend(added)
        if first:doc.volume=added[0]
        self.refresh_scene()
        if first and hasattr(self,'reset_camera'):self.reset_camera()
        self.statusBar().showMessage(f'Added {len(added)} field(s). Choose Surface layers / ESP color mapping to overlay or map them.',10000)

    def _show_field_slice(self):
        if self.doc is None or self.doc.volume is None:return
        from .field_slice_dialog import FieldSliceDialog
        FieldSliceDialog(self.doc.volume,self).exec()

    def _export_active_field(self):
        if self.doc is None or self.doc.volume is None:return
        from .field_export import export_active_field_dialog
        export_active_field_dialog(self)

    def _refresh_isosurface_style_controls(self):
        opts=self.render_options;custom=bool(opts.volume_surfaces)
        states=((self.negative_independent,'setChecked',opts.volume_independent_negative),
                (self.negative_iso,'setValue',opts.volume_negative_iso),
                (self.negative_opacity_independent,'setChecked',opts.volume_independent_opacity),
                (self.negative_opacity,'setValue',opts.volume_negative_opacity),
                (self.surface_style,'setCurrentText',opts.volume_representation),
                (self.surface_line_width,'setValue',opts.volume_line_width),
                (self.surface_smooth,'setChecked',opts.volume_smooth_normals))
        for widget,method,value in states:
            with QSignalBlocker(widget):getattr(widget,method)(value)
        for button,color in ((self.positive_color,opts.volume_positive_color),(self.negative_color,opts.volume_negative_color)):
            button.setText(color);button.setStyleSheet('border: 3px solid '+color+'; padding: 3px;')
        for widget in (self.negative_independent,self.negative_opacity_independent,self.surface_style,
                       self.positive_color,self.negative_color,self.field_signs):widget.setEnabled(not custom)
        self.negative_iso.setEnabled(not custom and opts.volume_independent_negative)
        self.negative_opacity.setEnabled(not custom and opts.volume_independent_opacity)
        for name in ('iso_spin','opacity_slider','iso_apply_button'):
            widget=getattr(self,name,None)
            if widget is not None:widget.setEnabled(not custom)
        explicit=any(layer.get('dataset',-1)>=0 for layer in opts.volume_surfaces)
        self.layers_note.setText(f'{len(opts.volume_surfaces)} independent layers on '+
            ('selected source fields.' if explicit else 'the active dataset.')+' Basic +/− controls are overridden.'
            if custom else 'Basic +/− controls active. Add layers to overlay fields or color a surface by ESP.')
        attached=self.doc is not None and self.doc.volume is not None
        self.slice_button.setEnabled(attached);self.field_export_button.setEnabled(attached and bool(self.doc.frames))
        self.field_import_button.setEnabled(self.doc is not None and bool(self.doc.frames) and
            not (self.doc.modified and self.doc.volume is None))

    def _refresh_field_controls(self):
        doc = self.doc
        volume = None if doc is None else doc.volume
        fields = [] if doc is None else doc.volumes
        if volume is not None and not any(volume is item for item in fields):
            fields.append(volume)
        for item in fields:
            field_reference(doc, item)
        with QSignalBlocker(self.field_combo):
            self.field_combo.clear()
            for i, item in enumerate(fields):
                self.field_combo.addItem(item.label or f'Field {i+1}')
            index = next((i for i, item in enumerate(fields) if item is volume), -1)
            self.field_combo.setCurrentIndex(index)
        self.field_combo.setEnabled(volume is not None)
        with QSignalBlocker(self.field_signs):
            self.field_signs.setCurrentText(self.render_options.volume_signs)
        if volume is None:
            self.field_note.setText('No volumetric field attached.' if not fields else
                                    'Fields detached by a structure edit. Undo or reopen to restore.')
        else:
            lo, hi = float(volume.data.min()), float(volume.data.max())
            unit = volume.unit or 'source-file units'
            note = f'{volume.data.shape} · {unit}\nRange {lo:.6g} to {hi:.6g}.'
            from .isosurface_dialog import basic_surface_layers
            layers=self.render_options.volume_surfaces or basic_surface_layers(self.render_options)
            if not any(layer.get('visible',True) and layer.get('opacity',.65)>0 and
                       (layer.get('dataset',-1)>=0 or lo <= layer['value'] <= hi) for layer in layers):
                note += '\nNo visible isovalue lies within this field’s range.'
            self.field_note.setText(note)
        wf = None if doc is None else doc.wavefunction
        if wf is not None and (not hasattr(wf, "evaluate_orbital") or not hasattr(wf, "orbitals")):
            wf = None
        if doc is not self._field_document:
            self._field_document = doc
            self.mo_combo.clear()
            if wf is not None:
                for channel, number, occupation, energy in wf.orbitals:
                    energy_text = '' if energy is None else f' · {energy:.5g} eV'
                    self.mo_combo.addItem(f'{channel} MO {number} · occ {occupation:g}{energy_text}', (channel, number))
                # A useful initial orbital is the highest occupied entry.
                occupied = [i for i, row in enumerate(wf.orbitals) if row[2] > 1e-8]
                if occupied: self.mo_combo.setCurrentIndex(occupied[-1])
        enabled = wf is not None and getattr(wf, "can_evaluate", True) and self.mo_combo.count() > 0 and not doc.modified
        self.mo_combo.setEnabled(wf is not None)
        self.mo_generate.setEnabled(enabled)
        self.mo_spacing.setEnabled(enabled)
        if wf is not None and not getattr(wf, "can_evaluate", True):
            self.mo_generate.setToolTip(getattr(wf, "unsupported_reason", "Orbital evaluation is unavailable for this basis."))
        elif wf is not None and doc.modified:
            self.mo_generate.setToolTip('Reopen the source before evaluating orbitals: stored coefficients refer to the original geometry.')

        self._refresh_isosurface_style_controls()
        self._refresh_wavecar_controls()

    def _select_field(self, index):
        if self.doc is None or index < 0 or self.doc.volume is None:
            return
        select_field(self.doc, index)
        self.refresh_scene()

    def _generate_orbital_grid(self):
        doc = self.doc
        if doc is None or doc.wavefunction is None or doc.modified:
            return
        if not getattr(doc.wavefunction, "can_evaluate", True): return
        selection = self.mo_combo.currentData()
        if selection is None: return
        channel, number = selection
        first_field = doc.volume is None
        spacing = self.mo_spacing.value()
        try:
            volume = run_data_task(self, 'Evaluating stored molecular orbital',
                lambda: doc.wavefunction.evaluate_orbital(channel, number, spacing=spacing, padding=3.),
                cancellable=True)
        except LoadCancelled:
            return
        except Exception as exc:
            QMessageBox.warning(self, 'Orbital grid unavailable', str(exc)); return
        if not volume.label: volume.label = f'{channel} MO {number}'
        if not volume.unit: volume.unit = 'Bohr⁻³ᐟ² (orbital amplitude)'
        doc.volumes.append(volume); field_reference(doc, volume)
        doc.volume = volume
        self.refresh_scene()
        if first_field and hasattr(self, "reset_camera"): self.reset_camera()

    def _build_wavecar_controls(self, form):
        self.wavecar_group = QGroupBox('VASP WAVECAR pseudo-wavefunction')
        layout = QFormLayout(self.wavecar_group)
        self.wavecar_spin = PanelComboBox(); layout.addRow('Spin channel', self.wavecar_spin)
        self.wavecar_kpoint = PanelComboBox(); layout.addRow('k-point', self.wavecar_kpoint)
        self.wavecar_band = QSpinBox(); self.wavecar_band.setMinimum(1)
        layout.addRow('Band (1-based)', self.wavecar_band)
        self.wavecar_kind = PanelComboBox()
        self.wavecar_kind.addItem('Single-band density |ψ|²', 'density')
        self.wavecar_kind.addItem('Real part Re ψ', 'real')
        self.wavecar_kind.addItem('Imaginary part Im ψ', 'imag')
        layout.addRow('Field', self.wavecar_kind)
        self.wavecar_state = QLabel(); self.wavecar_state.setWordWrap(True); layout.addRow(self.wavecar_state)
        self.wavecar_warning = QLabel(
            'Stored pseudo-wavefunction only; PAW augmentation is absent. '
            'Single-band |ψ|² is not the total CHGCAR density. Real/imaginary parts '
            'depend on the arbitrary wavefunction phase and may not be periodic '
            'at nonzero k. Gamma-only half-storage and spinor/SOC layouts are rejected.')
        self.wavecar_warning.setWordWrap(True); layout.addRow(self.wavecar_warning)
        self.wavecar_generate = QPushButton('Reconstruct WAVECAR field')
        self.wavecar_generate.clicked.connect(self._generate_wavecar_grid); layout.addRow(self.wavecar_generate)
        self.wavecar_spin.currentIndexChanged.connect(self._wavecar_spin_changed)
        self.wavecar_kpoint.currentIndexChanged.connect(self._wavecar_state_changed)
        self.wavecar_band.valueChanged.connect(self._wavecar_state_changed)
        self._wavecar_document = None
        self.wavecar_group.hide(); form.addRow(self.wavecar_group)

    def _refresh_wavecar_controls(self):
        doc = self.doc
        wave = None if doc is None else getattr(doc, 'wavecar', None)
        self.wavecar_group.setVisible(wave is not None)
        if doc is not self._wavecar_document:
            self._wavecar_document = doc
            with QSignalBlocker(self.wavecar_spin), QSignalBlocker(self.wavecar_band):
                self.wavecar_spin.clear()
                self.wavecar_band.setRange(1, wave.nbands if wave is not None else 1)
                if wave is not None:
                    for spin in range(wave.spins):
                        self.wavecar_spin.addItem(f'Spin {spin+1}', spin)
                self.wavecar_band.setValue(1)
            self._wavecar_spin_changed()
        if wave is None:
            self.wavecar_generate.setEnabled(False)
            return
        self.wavecar_generate.setEnabled(bool(doc.frames) and not doc.modified and wave.path.is_file() and bool(getattr(wave, "reconstruction_supported", False)))
        if not getattr(wave, 'reconstruction_supported', False):
            self.wavecar_generate.setToolTip(getattr(wave, 'reconstruction_reason', 'Reconstruction has not been validated for this file.'))
        elif not wave.path.is_file():
            self.wavecar_generate.setToolTip('Original WAVECAR unavailable. Reopen the binary source; projects contain metadata only.')
        elif doc.modified:
            self.wavecar_generate.setToolTip('Reopen the original source before reconstruction; the structure has been edited.')
        elif not doc.frames:
            self.wavecar_generate.setToolTip('Geometry is unavailable. Open WAVECAR alongside a matching POSCAR, CONTCAR or supported OUTCAR.')
        else:
            self.wavecar_generate.setToolTip('Reconstruct the selected stored state on an FFT grid. Unsupported layouts are checked before display.')
        self._wavecar_state_changed()

    def _wavecar_spin_changed(self, *_):
        wave = None if self.doc is None else getattr(self.doc, 'wavecar', None)
        previous = max(0, self.wavecar_kpoint.currentIndex())
        with QSignalBlocker(self.wavecar_kpoint):
            self.wavecar_kpoint.clear()
            if wave is not None and self.wavecar_spin.currentIndex() >= 0:
                spin = self.wavecar_spin.currentData()
                for index, point in enumerate(wave.kpoints[spin]):
                    self.wavecar_kpoint.addItem(f'{index+1}: '+', '.join(f'{x:.6g}' for x in point), index)
                self.wavecar_kpoint.setCurrentIndex(min(previous, wave.nkpoints-1))
        self._wavecar_state_changed()

    def _wavecar_state_changed(self, *_):
        wave = None if self.doc is None else getattr(self.doc, 'wavecar', None)
        if wave is None or self.wavecar_spin.currentIndex() < 0 or self.wavecar_kpoint.currentIndex() < 0:
            self.wavecar_state.setText(''); return
        spin = self.wavecar_spin.currentData(); kpoint = self.wavecar_kpoint.currentData()
        band = self.wavecar_band.value()-1
        self.wavecar_state.setText(
            f'Energy {wave.energies[spin,kpoint,band]:.8g} eV · '
            f'raw occupation weight {wave.occupations[spin,kpoint,band]:.6g}\n'
            f'{wave.ncoeff[spin,kpoint]:,} stored coefficients; '
            f'ENCUT {wave.encut_ev:g} eV.' +
            ('\nReconstruction unavailable: '+getattr(wave, 'reconstruction_reason', 'layout not validated')
             if not getattr(wave, 'reconstruction_supported', False) else ''))

    def _generate_wavecar_grid(self):
        doc = self.doc
        wave = None if doc is None else getattr(doc, 'wavecar', None)
        if wave is None or doc.modified or not doc.frames or not getattr(wave, "reconstruction_supported", False):
            return
        first_field = doc.volume is None
        spin = self.wavecar_spin.currentData(); kpoint = self.wavecar_kpoint.currentData()
        band = self.wavecar_band.value()-1; kind = self.wavecar_kind.currentData()
        if spin is None or kpoint is None: return
        try:
            volume = run_data_task(self, 'Reconstructing WAVECAR pseudo-wavefunction',
                lambda: wave.volume(spin=spin, kpoint=kpoint, band=band, kind=kind), cancellable=True)
        except LoadCancelled:
            return
        except Exception as exc:
            QMessageBox.warning(self, 'WAVECAR field unavailable', str(exc)); return
        if not volume.label:
            volume.label = f'Spin {spin+1} · k {kpoint+1} · band {band+1} · {kind}'
        if not volume.unit:
            volume.unit = 'Å⁻³ (single-band pseudo-density)' if kind == 'density' else 'Å⁻³ᐟ² (pseudo-wavefunction amplitude)'
        doc.volumes.append(volume); doc.volume = volume
        self.refresh_scene()
        if first_field and hasattr(self, "reset_camera"): self.reset_camera()
