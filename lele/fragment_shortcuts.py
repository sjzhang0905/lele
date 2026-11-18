"""Decode canvas-only numbered-fragment keys without VTK key side effects."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def fragment_key_request(event, *, platform=None):
    """Return (operation, slot) or None, including shifted native digit keys.

    Native codes distinguish Shift+2 from punctuation keys on non-US layouts.
    The symbol fallback is for synthetic Qt events without native information.
    """
    modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
    if modifiers == Qt.KeyboardModifier.NoModifier:
        operation = 'select'
    elif modifiers == Qt.KeyboardModifier.ControlModifier:
        operation = 'save'
    elif modifiers == Qt.KeyboardModifier.ShiftModifier:
        operation = 'append'
    else:
        return None
    key = int(event.key())
    if int(Qt.Key.Key_1) <= key <= int(Qt.Key.Key_9):
        return operation, key - int(Qt.Key.Key_0)

    native = int(event.nativeVirtualKey())
    scan = int(event.nativeScanCode())
    platform = (platform if platform is not None else QApplication.platformName()).lower()
    slot = None
    if platform == 'windows' and native:
        if 0x31 <= native <= 0x39:
            slot = native - 0x30
        elif 0x61 <= native <= 0x69:  # numeric keypad
            slot = native - 0x60
        return (operation, slot) if slot is not None else None
    if platform in ('xcb', 'wayland', 'wayland-egl') and scan:
        if 10 <= scan <= 18:  # XKB keycode = evdev keycode + 8
            slot = scan - 9
        return (operation, slot) if slot is not None else None
    if platform in ('eglfs', 'linuxfb') and scan:
        if 2 <= scan <= 10:
            slot = scan - 1
        return (operation, slot) if slot is not None else None
    if platform == 'cocoa' and (native or scan):
        slot = {18: 1, 19: 2, 20: 3, 21: 4, 23: 5, 22: 6,
                26: 7, 28: 8, 25: 9}.get(native)
        return (operation, slot) if slot is not None else None
    if operation == 'append' and not native and not scan:
        slot = {ord(symbol): number for number, symbol in enumerate('!@#$%^&*(', 1)}.get(key)
        if slot is not None:
            return operation, slot
    return None
