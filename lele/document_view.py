"""Session-local camera and display settings for each open document.

This module stays Qt-only until a camera is actually available after preload.
"""
from copy import deepcopy
from dataclasses import dataclass
from PySide6.QtCore import QSignalBlocker


@dataclass
class DocumentView:
    document: object
    options: object
    custom_style: dict
    preset: str
    camera: object = None
    frame_index: int = 0
    field_orbital: tuple | None = None


class DocumentViewActions:
    def _init_document_views(self):
        self._document_views = {}
        self._document_labels = {}
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

    def _new_document_view(self, document, surface_layers=None):
        # Appearance can carry over, but every new file starts with its
        # own enabled one-cell Boundary rather than another file's range.
        from .render_options import RenderOptions
        options = deepcopy(self.render_options)
        defaults = RenderOptions()
        options.boundary_enabled = defaults.boundary_enabled
        options.boundary_bounds = defaults.boundary_bounds
        options.boundary_preserve_origin = False if document.cell_reference else defaults.boundary_preserve_origin
        options.volume_hidden_regions = []
        # Dataset references belong to one document. Retain them when
        # switching back, but never bind them to unrelated newly opened grids.
        if any(layer.get('dataset', -1) >= 0 or layer.get('map_dataset', -1) >= 0
               for layer in options.volume_surfaces):
            options.volume_surfaces = []
        if (document.format_name == 'XCrySDen XSF' and document.volume is not None
                and options.volume_iso == defaults.volume_iso and options.volume_signs == 'Both'
                and not options.volume_surfaces and not options.volume_independent_negative):
            from .field_mapping import suggested_isovalue
            from .render_options import MIN_ISOVALUE
            data = document.volume.data
            low, high = float(data.min()), float(data.max())
            level = options.volume_iso
            if low < high and not (low < level < high or low < -level < high):
                options.volume_iso = max(MIN_ISOVALUE, abs(suggested_isovalue([low, high], level)))
        state = DocumentView(document, options,
                             deepcopy(self._custom_style_state), self.preset_combo.currentData())
        self._initialize_document_pair_rules(document, state.options)
        if surface_layers is not None:
            options.show_volume = True
            options.volume_signs = "Both"
            options.volume_surfaces = surface_layers
            options.lattice_planes = []
        return state

    def _activate_document(self, index):
        document = self.documents[index]
        if document is self._view_document:
            self.current_doc = index
            return False
        # A native trackball press can outlive a focus/file switch. Finish the
        # outgoing gesture before saving its view and restoring another file.
        cancel_interaction = getattr(self.vtk, 'cancel_interaction', None)
        if cancel_interaction is not None:
            cancel_interaction()
        self._remember_document_view()
        state = self._document_views.get(id(document))
        if state is None:
            state = self._new_document_view(document)
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
        self.cancel_pointer_action()
        self.playback.stop()
        self.play_btn.setText('Play')
        self._sync_document_view_widgets(state.preset)
        return True

    def _sync_document_view_widgets(self, preset):
        opts = self.render_options
        for index, action in enumerate(self.light_actions):
            with QSignalBlocker(action):
                action.setChecked(opts.light_enabled[index])
        if preset == 'Space filling (CPK)':preset = 'Space filling (VESTA)'
        self._sync_style_widgets()
        controls = [
            (self.preset_combo, 'setCurrentIndex', self.preset_combo.findData(preset)),
            (self.bond_model_combo, 'setCurrentText', opts.bond_model),
            (self.cutoff_slider, 'setValue', round(opts.bond_cutoff * 100)),
            (self.cutoff_spin, 'setValue', opts.bond_cutoff),
            (self.hbond_check, 'setChecked', opts.hydrogen_bonds),
            (self.cell_check, 'setChecked', opts.unit_cell),
            (self.label_combo, 'setCurrentIndex', self.label_combo.findText(opts.labels)),
            (self.label_font_combo, 'setCurrentIndex', -1 if opts.label_font_file else self.label_font_combo.findText(opts.label_font)),
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
            self.cutoff_slider.setCenter(118 if opts.bond_model == 'Covalent radii' else 88)
            for widget, method, value in controls:
                getattr(widget, method)(value)
        finally:
            del blockers
        self.coordinate_axes.set_values(opts)
        self.boundary_panel.set_values(opts.boundary_bounds, opts.boundary_preserve_origin)
        self.crystal_panel.set_values(opts)
        self.fitted_plane_controls.set_values(opts.fitted_plane_style)

    def _apply_document_camera(self, reset_camera):
        # Restore after constructing the target scene, so neither fit-to-window
        # nor a frequency/Boundary refresh can overwrite a returning view.
        if self._pending_view_camera is not None:
            camera = self.scene.GetActiveCamera()
            camera.DeepCopy(self._pending_view_camera)
            # vtkCamera.DeepCopy does not advance the destination MTime.
            # OpenGL can therefore retain the preceding file's projection
            # until the first mouse gesture modifies the camera. Invalidate
            # its render caches explicitly while keeping the camera identity.
            camera.Modified()
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
