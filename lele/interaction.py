#!/usr/bin/env python3
"""Qt-native pointer handling for the embedded VTK viewport.

Why this lives at the QWidget level:
The VTK interactor/style may consume events before a Python observer attached to
vtkRenderWindowInteractor sees the corresponding button-release callback. Qt
is the actual receiver of native Windows pointer events, so a short click is
reported here, after forwarding the ordinary left-button event to VTK.

Left drag uses the VTK trackball. Right drag rolls about the geometric center of the atoms. Wheel zooms.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
import vtkmodules.qt
vtkmodules.qt.PyQtImpl = 'PySide6'
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor


def vtk_display_from_qt(x: float, y: float, qt_width: int, qt_height: int,
                        vtk_width: int, vtk_height: int) -> tuple[float, float]:
    """Convert Qt top-left device-independent pixels to VTK bottom-left pixels.

    Using the two viewport sizes independently accommodates Windows DPI
    scaling, where a Qt widget can report logical rather than physical pixels.
    """
    if min(qt_width, qt_height, vtk_width, vtk_height) <= 0:
        raise ValueError('Viewport dimensions must all be positive')
    return (float(x) * vtk_width / qt_width,
            (qt_height - float(y)) * vtk_height / qt_height)


def roll_camera(camera, center, dx):
    """Roll the view around the atom centroid, preserving its projected position."""
    angle = -.65 * dx
    if center is not None:
        import numpy as np
        from lele.fragment import rotation_about_axis
        focus = np.asarray(camera.GetFocalPoint())
        position = np.asarray(camera.GetPosition())
        rotation = rotation_about_axis(camera.GetDirectionOfProjection(), angle)
        # A lateral camera translation moves the roll axis from its focal
        # line to the centroid, including after a pan or an off-center fit.
        offset = focus - center
        shift = rotation @ offset - offset
        camera.SetFocalPoint(*(focus + shift))
        camera.SetPosition(*(position + shift))
    camera.Roll(angle)
    camera.OrthogonalizeViewUp()


class InteractiveVTKView(QVTKRenderWindowInteractor):
    """A reliable, Qt-level single-click signal and dedicated right-button roll."""

    atomClick = Signal(float, float)  # Qt logical top-left pixel coordinates
    atomContextClick = Signal(float,float)
    clearSelectionClick = Signal()  # right click without dragging
    fragmentGestureBegin = Signal(str, float, float)
    fragmentGestureMove = Signal(str, float, float)
    fragmentGestureEnd = Signal(str)
    fragmentSlotRequested = Signal(str, int)
    rectangleSelected = Signal(float,float,float,float,bool)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._left_start = None
        self._right_last = None
        self._right_start = None
        self._right_dragged = False
        self._right_center = None
        self._fragment_mode = None
        self._fragment_start = None
        self._fragment_last = None
        self._fragment_dragged = False
        self.scene_renderer = None
        self.rotation_center = None
        self._box_enabled=False
        self._box_start=None
        self._rubber_band=None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _fragment_key_request(self, event):
        if not self.hasFocus():
            return None
        from .fragment_shortcuts import fragment_key_request
        return fragment_key_request(event)

    def event(self, event):
        from PySide6.QtCore import QEvent
        if (event.type() == QEvent.Type.ShortcutOverride
                and self._fragment_key_request(event) is not None):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        request = self._fragment_key_request(event)
        if request is not None:
            if not event.isAutoRepeat():
                self.fragmentSlotRequested.emit(*request)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # VTK's character shortcuts (notably '3' for stereo) must never receive
        # either half of a numbered-fragment key stroke.
        if self._fragment_key_request(event) is not None:
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        if getattr(self,'_box_enabled',False) and event.button()==Qt.MouseButton.LeftButton:
            from PySide6.QtCore import QRect,QPoint
            from .selection_outline import SelectionOutline
            self._box_start=event.position()
            if self._rubber_band is None:self._rubber_band=SelectionOutline(self)
            start=QPoint(round(event.position().x()),round(event.position().y()))
            self._rubber_band.setGeometry(QRect(start,start));self._rubber_band.show()
            self.setFocus(Qt.FocusReason.MouseFocusReason);event.accept();return
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if alt and event.button() in (Qt.MouseButton.LeftButton,
                                       Qt.MouseButton.RightButton,
                                       Qt.MouseButton.MiddleButton):
            self._fragment_mode = {
                Qt.MouseButton.LeftButton: 'orbit',
                Qt.MouseButton.RightButton: 'roll',
                Qt.MouseButton.MiddleButton: 'pan',
            }[event.button()]
            self._fragment_start = event.position()
            self._fragment_last = event.position()
            self._fragment_dragged = False
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.fragmentGestureBegin.emit(self._fragment_mode,
                                           float(event.position().x()),
                                           float(event.position().y()))
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._right_last = event.position()
            self._right_start = event.position()
            self._right_dragged = False
            self._right_center = self.rotation_center() if self.rotation_center is not None else None
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return  # never enter VTK's right-button dolly state
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_start = event.position()
        super().mousePressEvent(event)

    def _update_fragment_drag(self, now):
        dx = float(now.x() - self._fragment_last.x())
        dy = float(now.y() - self._fragment_last.y())
        if not self._fragment_dragged:
            # Keep the initial displacement so fine mouse movements accumulate.
            if self._fragment_mode == 'roll':
                if abs(dx) < 1.:
                    return
            elif dx * dx + dy * dy <= 9.:
                return
            self._fragment_dragged = True
        self._fragment_last = now
        if dx or dy:
            self.fragmentGestureMove.emit(self._fragment_mode, dx, dy)

    def _update_right_drag(self, now):
        if not self._right_dragged:
            dx = now.x() - self._right_start.x()
            dy = now.y() - self._right_start.y()
            if dx * dx + dy * dy <= 64:
                return
            self._right_dragged = True
        dx = now.x() - self._right_last.x()
        self._right_last = now
        if dx and self.scene_renderer is not None:
            roll_camera(self.scene_renderer.GetActiveCamera(), self._right_center, dx)
            self.GetRenderWindow().Render()

    def mouseMoveEvent(self, event):
        if getattr(self,'_box_start',None) is not None:
            from PySide6.QtCore import QRect,QPoint
            a=self._box_start;b=event.position()
            self._rubber_band.setGeometry(QRect(QPoint(round(a.x()),round(a.y())),QPoint(round(b.x()),round(b.y()))).normalized())
            event.accept();return
        if self._fragment_mode is not None:
            self._update_fragment_drag(event.position())
            event.accept()
            return
        if self._right_last is not None:
            self._update_right_drag(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self,'_box_start',None) is not None and event.button()==Qt.MouseButton.LeftButton:
            start=self._box_start;self._box_start=None;self._rubber_band.hide()
            append=bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier))
            self.rectangleSelected.emit(start.x(),start.y(),event.position().x(),event.position().y(),append)
            event.accept();return
        if self._fragment_mode is not None:
            self._update_fragment_drag(event.position())
            mode = self._fragment_mode
            self._fragment_mode = None
            self._fragment_last = None
            self._fragment_start = None
            self._fragment_dragged = False
            self.fragmentGestureEnd.emit(mode)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            if self._right_start is not None:
                self._update_right_drag(event.position())
                if not self._right_dragged:
                    self.atomContextClick.emit(float(event.position().x()),float(event.position().y()))
            self._right_start = None
            self._right_last = None
            self._right_dragged = False
            self._right_center = None
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            start = self._left_start
            self._left_start = None
            super().mouseReleaseEvent(event)
            if start is not None:
                end = event.position()
                if (end.x()-start.x())**2 + (end.y()-start.y())**2 <= 64:
                    self.atomClick.emit(float(end.x()), float(end.y()))
            return
        super().mouseReleaseEvent(event)

    def focusOutEvent(self, event):
        self.cancel_interaction()
        super().focusOutEvent(event)

    def cancel_interaction(self):
        """End both Qt and native VTK gestures without moving the camera."""
        if getattr(self,'_box_start',None) is not None:
            self._box_start=None;self._rubber_band.hide()
        # Clearing the Python flags alone leaves vtkInteractorStyle in Rotate
        # or Pan state: a later no-button mouse move would move another file.
        window = self.GetRenderWindow()
        interactor = window.GetInteractor() if hasattr(window, 'GetInteractor') else None
        style = interactor.GetInteractorStyle() if interactor is not None else None
        if style is not None:
            if style.GetState():
                style.StopState()
            style.ReleaseFocus()
        if hasattr(self, '_ActiveButton'):
            self._ActiveButton = Qt.MouseButton.NoButton
        self._right_last = None
        self._right_start = None
        self._right_dragged = False
        self._right_center = None
        self._left_start = None
        if self._fragment_mode is not None:
            mode = self._fragment_mode
            self._fragment_mode = None
            self._fragment_last = None
            self._fragment_start = None
            self._fragment_dragged = False
            self.fragmentGestureEnd.emit(mode)

    def set_box_selection(self,enabled):
        self._box_enabled=bool(enabled)
        if not enabled and self._box_start is not None:
            self._box_start=None;self._rubber_band.hide()
