#!/usr/bin/env python3
"""Qt-native pointer handling for the embedded VTK viewport.

Why this lives at the QWidget level:
The VTK interactor/style may consume events before a Python observer attached to
vtkRenderWindowInteractor sees the corresponding button-release callback. Qt
is the actual receiver of native Windows pointer events, so a short click is
reported here, after forwarding the ordinary left-button event to VTK.

Left drag: VTK trackball rotation. Right drag: camera roll around the view
axis (no VTK zoom). Wheel: VTK zoom.
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


class InteractiveVTKView(QVTKRenderWindowInteractor):
    """A reliable, Qt-level single-click signal and dedicated right-button roll."""

    atomClick = Signal(float, float)  # Qt logical top-left pixel coordinates
    atomContextClick = Signal(float,float)
    clearSelectionClick = Signal()  # right click without dragging
    fragmentGestureBegin = Signal(str, float, float)
    fragmentGestureMove = Signal(str, float, float)
    fragmentGestureEnd = Signal(str)
    rectangleSelected = Signal(float,float,float,float,bool)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._left_start = None
        self._right_last = None
        self._right_start = None
        self._right_dragged = False
        self._fragment_mode = None
        self._fragment_start = None
        self._fragment_last = None
        self._fragment_dragged = False
        self.scene_renderer = None
        self._box_enabled=False
        self._box_start=None
        self._rubber_band=None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            event.accept()
            return  # never enter VTK's right-button dolly state
        if event.button() == Qt.MouseButton.LeftButton:
            self._left_start = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self,'_box_start',None) is not None:
            from PySide6.QtCore import QRect,QPoint
            a=self._box_start;b=event.position()
            self._rubber_band.setGeometry(QRect(QPoint(round(a.x()),round(a.y())),QPoint(round(b.x()),round(b.y()))).normalized())
            event.accept();return
        if self._fragment_mode is not None:
            now = event.position()
            if not self._fragment_dragged:
                dx_total = now.x() - self._fragment_start.x()
                dy_total = now.y() - self._fragment_start.y()
                if dx_total**2 + dy_total**2 > 9:
                    self._fragment_dragged = True
            if self._fragment_dragged:
                self.fragmentGestureMove.emit(
                    self._fragment_mode,
                    float(now.x() - self._fragment_last.x()),
                    float(now.y() - self._fragment_last.y()))
            self._fragment_last = now
            event.accept()
            return
        if self._right_last is not None:
            now = event.position()
            dx = now.x() - self._right_last.x()
            dy = now.y() - self._right_last.y()
            self._right_last = now
            if self._right_start is not None:
                dx_total = now.x() - self._right_start.x()
                dy_total = now.y() - self._right_start.y()
                if dx_total ** 2 + dy_total ** 2 > 64:
                    self._right_dragged = True
            if self.scene_renderer is not None:
                # Consistent gesture: right-drag RIGHT = clockwise on screen,
                # right-drag LEFT = counterclockwise. Unlike VTK's default
                # right button, this never changes zoom or camera distance.
                angle = float(dx) * 0.65
                if self._right_dragged and abs(angle) > 1.e-8:
                    camera = self.scene_renderer.GetActiveCamera()
                    camera.Roll(-angle)  # visual turn follows the pointer
                    camera.OrthogonalizeViewUp()
                    self.GetRenderWindow().Render()
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
            mode = self._fragment_mode
            self._fragment_mode = None
            self._fragment_last = None
            self._fragment_start = None
            self._fragment_dragged = False
            self.fragmentGestureEnd.emit(mode)
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            if (self._right_start is not None and not self._right_dragged
                and (event.position().x()-self._right_start.x())**2
                  + (event.position().y()-self._right_start.y())**2 <= 64):
                self.atomContextClick.emit(float(event.position().x()),float(event.position().y()))
            self._right_start = None
            self._right_last = None
            self._right_dragged = False
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
        if getattr(self,'_box_start',None) is not None:
            self._box_start=None;self._rubber_band.hide()
        # Never leave the widget in rolling mode if focus was lost mid-drag.
        self._right_last = None
        self._right_start = None
        self._right_dragged = False
        self._left_start = None
        if self._fragment_mode is not None:
            mode = self._fragment_mode
            self._fragment_mode = None
            self._fragment_last = None
            self._fragment_start = None
            self._fragment_dragged = False
            self.fragmentGestureEnd.emit(mode)
        super().focusOutEvent(event)

    def set_box_selection(self,enabled):
        self._box_enabled=bool(enabled)
        if not enabled and self._box_start is not None:
            self._box_start=None;self._rubber_band.hide()
