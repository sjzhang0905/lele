"""GUI actions restored from the 1.4/1.5 feature set; backend imports are lazy."""
from pathlib import Path
from PySide6.QtCore import Qt,QSignalBlocker,QMimeData
from PySide6.QtWidgets import QApplication,QPushButton,QFileDialog,QMessageBox,QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox


class RestoredActions:
    def _install_restored_controls(self):
        from .dipole_panel import DipolePanel
        from .boundary_panel import BoundaryPanel
        self._pending_paste=None
        self.copy_action=self._action(self.edit_menu,'Copy selected atoms',self.copy_selected_atoms,'Ctrl+C')
        self.paste_action=self._action(self.edit_menu,'Paste atoms at next click',self.begin_paste_atoms,'Ctrl+V')
        self.box_select_action=self._action(self.edit_menu,'Box select atoms',lambda:None,'Ctrl+Shift+B')
        self.box_select_action.setCheckable(True);self.box_select_action.toggled.connect(self._set_box_select)
        self._action(self.edit_menu,'Cancel paste / box selection',self.cancel_pointer_action,'Esc')
        self.box_select_button=QPushButton('Box select atoms (Ctrl+Shift+B)');self.box_select_button.setCheckable(True)
        self.box_select_button.setToolTip('Each rectangle adds atoms to the selection. Ctrl+Z undoes the last addition; Esc exits.')
        self.box_select_button.toggled.connect(self.box_select_action.setChecked)
        self.atom_panel.layout().insertWidget(0,self.box_select_button)
        self.dipole_panel=DipolePanel();self.sidebar_tabs.addTab(self.dipole_panel,'Dipole')
        self.dipole_panel.sourceChanged.connect(lambda v:self._set_option('dipole_source',v))
        self.dipole_panel.modeChanged.connect(lambda v:self._set_option('dipole_mode',v))
        self.dipole_panel.scaleChanged.connect(lambda v:self._set_option('dipole_scale',v))
        self.dipole_panel.saveImageRequested.connect(self.save_dipole_image)
        self.dipole_panel.exportDataRequested.connect(self.export_dipole_data)
        self.dipole_panel.exportTransitionsRequested.connect(self.export_transition_data)
        self.boundary_panel=BoundaryPanel();self.sidebar_tabs.addTab(self.boundary_panel,'Boundary')
        self.boundary_panel.applyRequested.connect(self._apply_boundary)
        for kind in ('IR','Raman','UV-Vis'):
            self._action(self.analysis_menu,kind+' spectrum…',lambda checked=False,k=kind:self.show_spectrum(k))

    def _save_path(self,suffix):
        return str(self.doc.path.with_name(self.doc.path.stem+suffix)) if self.doc else str(Path.home()/('lele'+suffix))

    def _refresh_properties(self):
        from .gaussian_properties import selected_dipole,dipole_label
        from .periodic_geometry import periodic_basis
        source=self.dipole_panel.prepare_document(self.doc,self.render_options.dipole_source)
        self.render_options.dipole_source=source
        self.renderer.dipole_vector=selected_dipole(self.doc,self.frame,source)
        self.renderer.dipole_label=dipole_label(self.doc,source)
        self.dipole_panel.set_vector(self.renderer.dipole_vector,self.render_options.dipole_mode,self.render_options.dipole_scale)
        self.boundary_panel.setEnabled(periodic_basis(self.frame) is not None)
        self.boundary_panel.set_values(self.render_options.boundary_enabled,self.render_options.boundary_bounds)

    def _apply_boundary(self,enabled,bounds):
        if self.frame is None:return
        from .boundary import boundary_view
        if enabled:
            try:boundary_view(self.frame,bounds,self.render_options.bond_cutoff)
            except ValueError as ex:
                self.boundary_panel.set_values(self.render_options.boundary_enabled,self.render_options.boundary_bounds)
                QMessageBox.warning(self,'Invalid boundary',str(ex));return
        self.render_options.boundary_enabled=enabled
        self.render_options.boundary_bounds=tuple(tuple(v) for v in bounds)
        self.renderer.periodic_preview=None;self.refresh_scene(reset_camera=True)

    def show_spectrum(self,kind='IR'):
        if self.doc is None:return
        from .spectrum_dialog import SpectrumDialog
        SpectrumDialog(self.doc,kind,self).exec()

    def save_dipole_image(self):
        old=self.render_options.dipole_mode
        try:
            if old=='Off':self.render_options.dipole_mode='Total';self.refresh_scene()
            source=self.render_options.dipole_source
            suffix='_'+source.replace(':','_')+'_dipole.png'
            self.save_png(suffix)
        finally:
            self.render_options.dipole_mode=old;self.refresh_scene()

    def _export_property_csv(self,kind):
        if self.doc is None:return
        from .property_export import export_dipoles,export_transitions
        path,_=QFileDialog.getSaveFileName(self,'Export '+kind,self._save_path('_'+kind+'.csv'),'CSV (*.csv)')
        if path:
            try:
                count=(export_dipoles if kind=='dipoles' else export_transitions)(path,self.doc)
                self.statusBar().showMessage(f'Exported {count} records: {path}',7000)
            except (OSError,ValueError) as ex:QMessageBox.warning(self,'Export failed',str(ex))

    def export_dipole_data(self):self._export_property_csv('dipoles')
    def export_transition_data(self):self._export_property_csv('transitions')

    def _text_editor_active(self):
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox)):return True
        return self.atom_table.state()==self.atom_table.State.EditingState

    def copy_selected_atoms(self):
        if self.frame is None or self._text_editor_active():return
        from .atom_clipboard import copy_atoms,MIME
        try:text,metadata=copy_atoms(self.frame,self.selection,self.render_options.bond_cutoff)
        except ValueError as ex:self.statusBar().showMessage(str(ex),4000);return
        mime=QMimeData();mime.setText(text);mime.setData(MIME,metadata.encode());QApplication.clipboard().setMimeData(mime)
        self.statusBar().showMessage(f'Copied {len(self.selection)} atoms',4000)

    def begin_paste_atoms(self):
        if self.frame is None or self._text_editor_active() or not self._geometry_edit_allowed():return
        from .atom_clipboard import read_atoms,MIME
        mime=QApplication.clipboard().mimeData()
        if mime is None:return
        try:self._pending_paste=read_atoms(mime.text(),bytes(mime.data(MIME)).decode() if mime.hasFormat(MIME) else None)
        except (ValueError,KeyError,TypeError,IndexError) as ex:
            self.statusBar().showMessage('Clipboard has no valid atom coordinates: '+str(ex),5000);return
        self.box_select_action.setChecked(False)
        self.statusBar().showMessage('Click in the view to paste on the camera focal plane. Esc to cancel.',10000)

    def _paste_at_click(self,x,y):
        if self._pending_paste is None:return False
        if not self._geometry_edit_allowed():return True
        from .interaction import vtk_display_from_qt
        from .atom_clipboard import paste_atoms
        import numpy as np
        width,height=self.vtk.GetRenderWindow().GetSize()
        dx,dy=vtk_display_from_qt(x,y,self.vtk.width(),self.vtk.height(),width,height)
        points=[]
        for depth in (0.,1.):
            self.scene.SetDisplayPoint(dx,dy,depth);self.scene.DisplayToWorld();p=np.array(self.scene.GetWorldPoint());points.append(p[:3]/p[3])
        camera=self.scene.GetActiveCamera();normal=np.asarray(camera.GetDirectionOfProjection());ray=points[1]-points[0]
        denominator=np.dot(normal,ray)
        if abs(denominator)<1e-12:return True
        point=points[0]+ray*np.dot(normal,np.asarray(camera.GetFocalPoint())-points[0])/denominator
        self._record_undo()
        had_volume = self.doc.volume is not None
        self.selection=paste_atoms(self.frame,self._pending_paste,point,self.render_options.bond_cutoff)
        # A volumetric field belongs to the pre-paste atom set.  Keep it in
        # the undo snapshot, but detach it from the edited structure.
        self.doc.volume = None
        self._pending_paste=None;self.doc.modified=True;self._refresh_after_geometry_edit()
        message=f'Pasted {len(self.selection)} atoms. Ctrl+Z to undo.'
        if had_volume:
            message += ' The input volumetric field was detached.'
        self.statusBar().showMessage(message,6000);return True

    def _set_box_select(self,enabled):
        if enabled:self._pending_paste=None
        with QSignalBlocker(self.box_select_button):self.box_select_button.setChecked(enabled)
        if self.vtk is not None and hasattr(self.vtk,'set_box_selection'):self.vtk.set_box_selection(enabled)

    def cancel_pointer_action(self):
        self._pending_paste=None;self.box_select_action.setChecked(False)

    def _rectangle_selected(self,x1,y1,x2,y2,append=False):
        if self.frame is None:return
        from .interaction import vtk_display_from_qt
        from .atom_appearance import atom_is_drawn
        vw,vh=self.vtk.GetRenderWindow().GetSize()
        a=vtk_display_from_qt(x1,y1,self.vtk.width(),self.vtk.height(),vw,vh)
        b=vtk_display_from_qt(x2,y2,self.vtk.width(),self.vtk.height(),vw,vh)
        lowx,highx=sorted((a[0],b[0]));lowy,highy=sorted((a[1],b[1]));indices=[]
        for i,p in self.renderer.displayed_atoms():
            if not atom_is_drawn(self.frame,i):continue
            self.scene.SetWorldPoint(*p,1.);self.scene.WorldToDisplay();x,y,z=self.scene.GetDisplayPoint()
            if lowx<=x<=highx and lowy<=y<=highy and 0<=z<=1 and i not in indices:indices.append(i)
        selected=list(dict.fromkeys(self.selection+indices))
        if selected!=self.selection:
            self._record_selection_undo()
            self.selection=selected
            self._sync_selection_to_table();self.refresh_scene()
