"""Session-local camera and display settings for each open document.

This module stays Qt-only until a camera is actually available after preload.
"""
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from PySide6.QtCore import QSignalBlocker


@dataclass
class DocumentView:
    document: object
    options: object
    custom_style: dict
    preset: str
    camera: object = None
    frame_index: int = 0


class DocumentViewActions:
    def _init_document_views(self):
        self._document_views = {}
        self._view_document = None
        self._scene_document = None
        self._pending_view_camera = None
        self._view_fit_pending = False

    def _remember_document_view(self):
        if self._view_document is None:
            return
        state = self._document_views[id(self._view_document)]
        state.options = self.render_options
        state.custom_style = deepcopy(self._custom_style_state)
        state.preset = self.preset_combo.currentData()
        state.frame_index = self.frame_index
        # A results-only page may still have another file's canvas behind it.
        if self.scene is not None and self._scene_document is self._view_document:
            from vtkmodules.vtkRenderingCore import vtkCamera
            state.camera = vtkCamera()
            state.camera.DeepCopy(self.scene.GetActiveCamera())

    def _has_document_camera(self, document):
        state = self._document_views.get(id(document))
        return state is not None and state.camera is not None

    def _activate_document(self, index):
        document = self.documents[index]
        if document is self._view_document:
            self.current_doc = index
            return False
        self._remember_document_view()
        state = self._document_views.get(id(document))
        if state is None:
            # Appearance can carry over, but every new file starts with its
            # own enabled one-cell Boundary rather than another file's range.
            from .render_options import RenderOptions
            options = deepcopy(self.render_options)
            defaults = RenderOptions()
            options.boundary_enabled = defaults.boundary_enabled
            options.boundary_bounds = defaults.boundary_bounds
            # Dataset references belong to one document. Retain them when
            # switching back, but never bind them to unrelated newly opened grids.
            if any(layer.get('dataset', -1) >= 0 or layer.get('map_dataset', -1) >= 0
                   for layer in options.volume_surfaces):
                options.volume_surfaces = []
            state = DocumentView(document, options,
                                 deepcopy(self._custom_style_state), self.preset_combo.currentData())
            self._initialize_document_pair_rules(document, state.options)
            self._document_views[id(document)] = state
        self.current_doc = index
        # Widget synchronization can inspect the active frame before the
        # caller's change_frame() has assigned its requested index.
        self.frame_index = min(state.frame_index, max(0, len(document.frames)-1))
        self._view_document = document
        self.render_options = state.options
        self._custom_style_state = deepcopy(state.custom_style)
        self._pending_view_camera = state.camera
        self._view_fit_pending = state.camera is None
        if self.renderer is not None:
            self.renderer.options = self.render_options
        self.selection.clear()
        self._fragment_gesture = None
        self._pending_paste = None
        self.playback.stop()
        self.play_btn.setText('Play')
        self._sync_document_view_widgets(state.preset)
        self._update_source_view()
        return True

    def _sync_document_view_widgets(self, preset):
        opts = self.render_options
        if preset == 'Space filling (CPK)':preset = 'Space filling (VESTA)'
        self._sync_style_widgets()
        controls = [
            (self.preset_combo, 'setCurrentIndex', self.preset_combo.findData(preset)),
            (self.bond_model_combo, 'setCurrentText', opts.bond_model),
            (self.cutoff_slider, 'setValue', round(opts.bond_cutoff * 100)),
            (self.cutoff_spin, 'setValue', opts.bond_cutoff),
            (self.hbond_check, 'setChecked', opts.hydrogen_bonds),
            (self.cell_check, 'setChecked', opts.unit_cell),
            (self.axes_position_combo, 'setCurrentIndex', self.axes_position_combo.findData(opts.axes_position)),
            (self.axes_basis_combo, 'setCurrentIndex', self.axes_basis_combo.findData(opts.axes_basis)),
            (self.axes_length_spin, 'setValue', opts.axes_length),
            (self.label_combo, 'setCurrentText', opts.labels),
            (self.label_font_combo, 'setCurrentText', opts.label_font),
            (self.label_size_spin, 'setValue', opts.label_font_size),
            (self.label_bold_check, 'setChecked', opts.label_bold),
            (self.volume_check, 'setChecked', opts.show_volume),
            (self.iso_spin, 'setValue', opts.volume_iso),
            (self.opacity_slider, 'setValue', round(opts.volume_opacity * 100)),
            (self.dipole_panel.mode, 'setCurrentText', opts.dipole_mode),
            (self.dipole_panel.scale, 'setValue', opts.dipole_scale),
        ]
        blockers = [QSignalBlocker(widget) for widget, _, _ in controls]
        try:
            for widget, method, value in controls:
                getattr(widget, method)(value)
        finally:
            del blockers
        self.custom_font_btn.setText('Font file: ' + Path(opts.label_font_file).name
                                    if opts.label_font_file else 'Choose TTF/OTF font file…')
        self.boundary_panel.set_values(opts.boundary_enabled, opts.boundary_bounds)
        self.crystal_panel.set_values(opts)

    def _apply_document_camera(self, reset_camera):
        # Restore after constructing the target scene, so neither fit-to-window
        # nor a frequency/Boundary refresh can overwrite a returning view.
        if self._pending_view_camera is not None:
            self.scene.GetActiveCamera().DeepCopy(self._pending_view_camera)
            self._pending_view_camera = None
        elif reset_camera or self._view_fit_pending:
            self._set_projection_mode('Isometry')
        elif (self._active_vibration is not None or self.render_options.dipole_mode != 'Off'
              or (self.doc.volume is not None and self.render_options.show_volume)
              or (self.renderer.boundary_display is not None
                  and self.renderer.boundary_display.tiles != ((0, 0, 0),))):
            # New surfaces/isolevels need updated depth bounds. Preserve the
            # ordinary structure-only camera, including saved clipping values.
            self.scene.ResetCameraClippingRange()
        self._view_fit_pending = False
        self._scene_document = self.doc
        projection = ('Orthographic' if self.scene.GetActiveCamera().GetParallelProjection()
                      else 'Perspective')
        self.projection_actions[projection].setChecked(True)
