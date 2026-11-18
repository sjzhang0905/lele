"""Give the main window the same neutral gray caption as its Qt panels."""
import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStyle, QToolButton, QWidget


def caption_colors(palette):
    panel = palette.color(QPalette.ColorRole.Window)
    level = min(226, panel.lightness())
    return QColor(level, level, level), palette.color(QPalette.ColorRole.WindowText)


def _native_colors(window):
    """Windows 11 supports coloring the existing nonclient frame and buttons."""
    import ctypes
    from ctypes import wintypes

    set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
    set_attribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    set_attribute.restype = wintypes.LONG
    handle = int(window.winId())
    for attribute, color in zip((35, 36), caption_colors(window.palette())):
        value = wintypes.DWORD(color.red() | color.green() << 8 | color.blue() << 16)
        if set_attribute(handle, attribute, ctypes.byref(value), ctypes.sizeof(value)) != 0:
            return False
    return True


class _NativeCaption(QObject):
    def eventFilter(self, window, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.PaletteChange, QEvent.Type.WinIdChange):
            if window.windowHandle() is not None and window.isVisible():
                _native_colors(window)
        return False


class _ResizeEdge(QWidget):
    def __init__(self, window, edges, cursor):
        super().__init__(window)
        self.edges = edges
        self.setCursor(cursor)

    def mousePressEvent(self, event):
        handle = self.window().windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle and handle.startSystemResize(self.edges):
            event.accept()
        else:
            super().mousePressEvent(event)


class PanelCaption(QWidget):
    """A panel-colored title bar on platforms without a native caption tint."""
    def __init__(self, window):
        window.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        super().__init__(window)
        self.owner = window
        self.setAutoFillBackground(True)
        self.setFixedHeight(max(29, self.fontMetrics().height() + 10))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 0, 0, 0)
        layout.setSpacing(5)
        self.icon = QLabel()
        self.title = QLabel()
        for label in (self.icon, self.title):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(label)
        layout.addStretch(1)
        self._button(layout, 'Minimize', QStyle.StandardPixmap.SP_TitleBarMinButton, window.showMinimized)
        self.maximize = self._button(layout, 'Maximize', QStyle.StandardPixmap.SP_TitleBarMaxButton, self.toggle_size)
        self._button(layout, 'Close', QStyle.StandardPixmap.SP_TitleBarCloseButton, window.close)
        self._refresh()
        e, c = Qt.Edge, Qt.CursorShape
        self.grips = [
            _ResizeEdge(window, e.LeftEdge, c.SizeHorCursor), _ResizeEdge(window, e.RightEdge, c.SizeHorCursor),
            _ResizeEdge(window, e.TopEdge, c.SizeVerCursor), _ResizeEdge(window, e.BottomEdge, c.SizeVerCursor),
            _ResizeEdge(window, e.TopEdge | e.LeftEdge, c.SizeFDiagCursor),
            _ResizeEdge(window, e.TopEdge | e.RightEdge, c.SizeBDiagCursor),
            _ResizeEdge(window, e.BottomEdge | e.LeftEdge, c.SizeBDiagCursor),
            _ResizeEdge(window, e.BottomEdge | e.RightEdge, c.SizeFDiagCursor),
        ]
        window.installEventFilter(self)
        self._fit()

    def _button(self, layout, name, icon, action):
        button = QToolButton()
        button.setAccessibleName(name)
        button.setToolTip(name)
        button.setIcon(self.style().standardIcon(icon))
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setFixedSize(40, self.height())
        button.clicked.connect(action)
        layout.addWidget(button)
        return button

    def _refresh(self):
        window = self.owner
        palette = window.palette()
        bg, fg = caption_colors(palette)
        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.WindowText, fg)
        self.setPalette(palette)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setText(window.windowTitle())
        self.icon.setPixmap(window.windowIcon().pixmap(18, 18))
        name = 'Restore' if window.isMaximized() else 'Maximize'
        icon = QStyle.StandardPixmap.SP_TitleBarNormalButton if window.isMaximized() else QStyle.StandardPixmap.SP_TitleBarMaxButton
        self.maximize.setAccessibleName(name)
        self.maximize.setToolTip(name)
        self.maximize.setIcon(self.style().standardIcon(icon))

    def _fit(self):
        window = self.owner
        fullscreen = window.isFullScreen()
        edge = 0 if window.isMaximized() or fullscreen else 5
        top = 0 if fullscreen else self.height() + edge
        window.setContentsMargins(edge, top, edge, edge)
        w, h = window.width(), window.height()
        self.setGeometry(edge, edge, max(0, w - 2 * edge), self.height())
        self.setVisible(not fullscreen)
        self.raise_()
        rects = ((0, edge, edge, h-2*edge), (w-edge, edge, edge, h-2*edge),
                 (edge, 0, w-2*edge, edge), (edge, h-edge, w-2*edge, edge),
                 (0, 0, edge, edge), (w-edge, 0, edge, edge),
                 (0, h-edge, edge, edge), (w-edge, h-edge, edge, edge))
        for grip, rect in zip(self.grips, rects):
            grip.setGeometry(*rect)
            grip.setVisible(bool(edge))
            grip.raise_()

    def toggle_size(self):
        if self.owner.isMaximized():
            self.owner.showNormal()
        else:
            self.owner.showMaximized()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_size()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        handle = self.owner.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle and handle.startSystemMove():
            event.accept()
        else:
            super().mousePressEvent(event)

    def eventFilter(self, window, event):
        kind = event.type()
        if kind in (QEvent.Type.WindowTitleChange, QEvent.Type.WindowIconChange, QEvent.Type.PaletteChange):
            self._refresh()
        elif kind in (QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.WindowStateChange):
            self._fit()
            if kind == QEvent.Type.WindowStateChange:
                self._refresh()
        return False


def install_caption(window):
    if sys.platform == 'win32':
        try:
            if _native_colors(window):
                listener = _NativeCaption(window)
                window.installEventFilter(listener)
                return listener
        except (AttributeError, OSError):
            pass
    return PanelCaption(window)
