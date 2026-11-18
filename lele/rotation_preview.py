"""Canvas-only rotation previews; source frames stay untouched until Apply.

The immutable reference and frozen connectivity prevent cumulative drift and
bond reinference. Keeping previews outside the document also means switching
documents, cancelling, or editing the source can never require writing old
coordinates back over a newer edit.
"""
from copy import deepcopy

from PySide6.QtCore import QTimer
from shiboken6 import isValid

from .core import freeze_bonds, measure
from .dialog_policy import _context
from .element_rules import frame_rules, rule_signature
from .internal_coordinates import InternalEdit


class RotationPreview:
    def __init__(self, owner, dialog, *, dihedral=False):
        self.owner = owner
        self.dialog = dialog
        self.dihedral = dihedral
        self.source = owner.frame
        self.selection = tuple(owner.selection)
        self.cutoff = owner.render_options.bond_cutoff
        self.base = deepcopy(self.source)
        freeze_bonds(self.base, self.cutoff)
        self.base.positions.setflags(write=False)
        self.base.cell.setflags(write=False)
        self.source_context = self._source_context()
        self.edit = None
        self.display_frame = None
        self.closed = False
        self.stale = False
        self.started = False
        self.timer = QTimer(dialog)
        self.timer.setInterval(75)
        self.timer.timeout.connect(self._check_source)
        dialog.angleChanged.connect(self.update)
        # Run only after the modeless source guard has captured its context.
        QTimer.singleShot(0, self.start)

    def _source_context(self):
        owner = self.owner
        if not isValid(owner) or getattr(owner, '_closing', False):
            return None
        frame = owner.frame
        return (_context(owner), owner.current_doc, owner.frame_index, owner.render_options.bond_cutoff,
                owner.render_options.bond_model,
                bool(owner._alignment_enabled()),
                None if frame is None else (repr(frame.hbond_added), repr(frame.hbond_removed),
                    frame.info.get('bond_model', 'Chemcraft pair ranges'),
                    rule_signature(*frame_rules(frame))))

    def is_current(self):
        return (not self.closed and not self.stale and self.source_context is not None
                and self.source_context == self._source_context())

    def start(self):
        if self.closed or self.started or not isValid(self.dialog) or not self.dialog.isVisible():
            return
        if not self._check_source():
            return
        previous = getattr(self.owner, '_rotation_preview', None)
        if previous is not None and previous is not self:
            previous.dialog.reject()
            previous.finish(False)
        self.started = True
        self.owner.playback.stop()
        self.owner.play_btn.setText('Play')
        self.owner._rotation_preview = self
        self.update(self.dialog.value())
        if not self.closed and not self.stale:
            self.timer.start()

    def _check_source(self):
        if self.is_current():
            return True
        if not self.closed:
            self.stale = True
            self.timer.stop()
            if isValid(self.dialog):
                self.dialog.reject()
            if isValid(self.owner) and not getattr(self.owner, '_closing', False):
                self.owner.statusBar().showMessage(
                    'Rotation preview cancelled because its source or selection changed. '
                    'The source coordinates were not changed by the preview.', 8000)
        return False

    def _plan(self, value):
        if self.dihedral:
            from .internal_coordinates import plan_internal_edit
            edit = plan_internal_edit(self.base, self.selection, value, self.cutoff)
            _, current = measure(self.base, self.selection)
            unchanged = abs((float(value) - current + 180) % 360 - 180) < 1.e-10
        else:
            from .axis_rotation import plan_axis_rotation
            edit = plan_axis_rotation(self.base, self.selection, value, self.cutoff)
            unchanged = abs((float(value) + 180) % 360 - 180) < 1.e-12
        # At zero/full turns retain the original periodic representatives too.
        if unchanged:
            return InternalEdit(self.base.positions.copy(), edit.moving,
                                self.base.periodic_bond_snapshot, dict(self.base.hbond_added))
        return edit

    def update(self, value):
        if self.closed or not self.started or not self._check_source():
            return
        try:
            self.edit = self._plan(value)
        except (ValueError, IndexError) as exc:
            self.edit = None
            self.dialog.set_preview_error(str(exc))
            self._restore_canvas()
            return
        self.dialog.set_preview_error('')
        frame = self.frame_for_scene(self.owner.frame)
        renderer = self.owner.renderer
        renderer.selected = list(self.selection)
        renderer.set_scene(frame, self.owner.doc.volume, reset_camera=False,
                           volumes=self.owner.doc.volumes)
        self.owner.vtk.GetRenderWindow().Render()

    def frame_for_scene(self, source):
        """Use from ordinary refresh_scene so appearance changes retain preview."""
        if (source is not self.source or not self.started or self.edit is None
                or not self.is_current()):
            return source
        # Take current styling, but compute every geometry from the fixed base.
        frame = source.clone()
        frame.positions = self.edit.positions.copy()
        frame.bond_snapshot = self.base.bond_snapshot
        frame.periodic_bond_snapshot = self.edit.periodic_edges
        frame.hbond_added = dict(self.edit.hbond_added)
        frame.energy_ev = None
        frame.info.pop('optimization_converged', None)
        self.display_frame = frame
        return frame

    def _restore_canvas(self):
        owner = self.owner
        if (not isValid(owner) or getattr(owner, '_closing', False)
                or owner.renderer.source_frame is not self.display_frame
                or self.display_frame is None):
            return
        self.display_frame = None
        if owner.frame is None:
            owner.renderer.clear()
            owner.renderer.frame = owner.renderer.source_frame = None
            owner.vtk.GetRenderWindow().Render()
        else:
            owner.refresh_scene()

    def finish(self, accepted):
        """Commit exactly once, or remove only this controller's displayed clone."""
        if self.closed:
            return False
        valid = self.is_current()
        self.closed = True
        self.timer.stop()
        if getattr(self.owner, '_rotation_preview', None) is self:
            self.owner._rotation_preview = None
        try:
            if accepted and valid:
                try:
                    edit = self._plan(self.dialog.value())
                except (ValueError, IndexError):
                    return False
                value = self.dialog.value()
                message = (f'Set dihedral to {value:.4f}°' if self.dihedral
                           else f'Rotated about selected axis by {value:.4f}°')
                return self.owner._commit_rotation_edit(edit, message)
            return False
        finally:
            self._restore_canvas()
