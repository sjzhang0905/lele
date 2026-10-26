#!/usr/bin/env python3
"""White startup canvas with a four-frame parrot gait (Qt only)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPixmap, QTransform
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import APP_CONTACT_EMAIL, APP_FULL_NAME, APP_NAME, __version__


POSE_INTERVAL_MS = 800
ARTWORK_PATH = Path(__file__).with_name('assets') / 'lele_walk.png'
# The supplied strip has uneven spacing. Equal fifths would cut the fourth
# bird's beak into the third pose. All crops share the same ground baseline.
# Omit the final standing pose: the next cycle already starts with standing.
POSE_RECTS = ((14, 174, 400, 350), (408, 174, 400, 350),
              (805, 174, 400, 350), (1197, 174, 400, 350))
# Complete eight gaits before returning to the left edge, without cutting a
# gait short or repeating the standing pose at either loop boundary.
WALK_STEP_COUNT = len(POSE_RECTS) * 8
WALK_DURATION_MS = WALK_STEP_COUNT * POSE_INTERVAL_MS

SHORTCUT_GROUPS = (
    ('Files & editing', (
        ('Ctrl+O', 'Open files'),
        ('Ctrl+Shift+S', 'Export structure'),
        ('Ctrl+S', 'Save PNG'),
        ('Ctrl+Z', 'Undo edit'),
    )),
    ('Atoms & fragments', (
        ('Ctrl+I', 'Invert atom selection'),
        ('Delete', 'Delete selected atoms'),
        ('Ctrl+G', 'Select connected fragments'),
        ('Ctrl+B', 'Toggle selected bonds'),
        ('Alt + drag', 'Left: rotate fragment; right: roll; middle: move'),
    )),
    ('Mouse & navigation', (
        ('Click atom', 'Add / remove selection'),
        ('Right click', 'Clear selection'),
        ('Left drag', 'Rotate view'),
        ('Right drag', 'Roll view'),
        ('Middle drag', 'Pan view'),
        ('Wheel', 'Zoom'),
        ('Up / Down', 'Browse frames in Files tree'),
    )),
)


def _white(widget):
    palette = widget.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor('#FFFFFF'))
    palette.setColor(QPalette.ColorRole.Base, QColor('#FFFFFF'))
    palette.setColor(QPalette.ColorRole.WindowText, QColor('#303343'))
    widget.setPalette(palette)
    widget.setAutoFillBackground(True)


class ParrotWalk(QWidget):
    """Hold each pose and position for 800 ms, then jump to the next step."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('parrotWalk')
        self.setFixedHeight(192)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _white(self)
        source = QPixmap(str(ARTWORK_PATH))
        if source.isNull():
            raise RuntimeError(f'Could not load LELE welcome artwork: {ARTWORK_PATH}')
        # The original bird faces left. Mirror each pose to face its travel.
        mirror = QTransform().scale(-1, 1)
        self.poses = [source.copy(*rect).transformed(mirror) for rect in POSE_RECTS]
        self.step_index = 0
        self.setToolTip("乐乐 (Lè Lè) · LELE's little explorer")
        self.setAccessibleName('Parrot 乐乐 walking from left to right')

        self.pose_timer = QTimer(self)
        self.pose_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.pose_timer.setInterval(POSE_INTERVAL_MS)
        self.pose_timer.timeout.connect(self._next_pose)

    def sizeHint(self):
        return QSize(700, 192)

    @property
    def pose_index(self):
        return self.step_index % len(self.poses)

    def bird_rect(self):
        width = max(1.0, min(168.0, self.width() - 24.0))
        height = width * 350.0 / 400.0
        distance = max(0.0, self.width() - width - 24.0)
        progress = self.step_index / (WALK_STEP_COUNT - 1)
        return QRectF(12.0 + distance * progress,
                      self.height() - height - 4.0, width, height)

    def _next_pose(self):
        # One clock changes both pose and position; there is no travel between
        # ticks, including when the current pose shows the bird standing still.
        self.step_index = (self.step_index + 1) % WALK_STEP_COUNT
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.step_index = 0
        self.update()
        self.pose_timer.start()

    def hideEvent(self, event):
        self.pose_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#FFFFFF'))
        # Keep the pixel-art edge character while Qt handles display DPI.
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        pose = self.poses[self.pose_index]
        painter.drawPixmap(self.bird_rect(), pose, QRectF(pose.rect()))


class WelcomePage(QScrollArea):
    """Startup-only document-free page; scroll and reflow on smaller windows."""

    openRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('welcomePage')
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        _white(self)
        _white(self.viewport())
        self.body = QWidget()
        self.body.setObjectName('welcomeBody')
        _white(self.body)
        self.body.setStyleSheet('''
            QLabel { color: #303343; background: transparent; font-size: 13px; }
            QLabel#appName { color: #373145; font-size: 52px; font-weight: 700; }
            QLabel#appFullName { font-size: 17px; }
            QLabel#version { color: #85818D; font-size: 12px; }
            QLabel#contactEmail { font-size: 12px; }
            QLabel#parrotCaption { color: #8B819B; font-size: 12px; }
            QLabel#sectionTitle { font-size: 17px; font-weight: 600; }
            QLabel#groupTitle { color: #77678F; font-size: 13px; font-weight: 600; }
            QLabel#shortcutKey { color: #51475E; font-size: 12px; font-weight: 600; }
            QLabel#shortcutDescription { color: #64616B; font-size: 12px; }
            QPushButton { color: #67567E; background: #FFFFFF; border: 1px solid #D9D0E5;
                          border-radius: 6px; padding: 7px 18px; font-size: 12px; }
            QPushButton:hover { background: #F7F4FC; border-color: #A998BF; }
            QPushButton:focus { border: 2px solid #A998BF; }
        ''')
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(30, 24, 30, 24)
        outer.setSpacing(6)

        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName('appName')
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.title_label)
        self.full_name_label = QLabel(APP_FULL_NAME)
        self.full_name_label.setObjectName('appFullName')
        self.full_name_label.setWordWrap(True)
        self.full_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.full_name_label)
        self.version_label = QLabel(f'Version {__version__}')
        self.version_label.setObjectName('version')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.version_label)
        self.contact_label = QLabel(
            f'<a style="color: #77678F;" href="mailto:{APP_CONTACT_EMAIL}">{APP_CONTACT_EMAIL}</a>')
        self.contact_label.setObjectName('contactEmail')
        self.contact_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.contact_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.contact_label.setOpenExternalLinks(True)
        self.contact_label.setAccessibleName('Contact email: ' + APP_CONTACT_EMAIL)
        outer.addWidget(self.contact_label)
        start_row = QHBoxLayout()
        start_row.addStretch()
        self.open_button = QPushButton('Open a file…  Ctrl+O')
        self.open_button.clicked.connect(self.openRequested.emit)
        start_row.addWidget(self.open_button)
        start_row.addStretch()
        outer.addLayout(start_row)
        outer.addSpacing(4)

        self.parrot_walk = ParrotWalk()
        outer.addWidget(self.parrot_walk)
        caption = QLabel("Meet 乐乐 · LELE's little explorer")
        caption.setObjectName('parrotCaption')
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(caption)
        outer.addSpacing(16)

        heading = QLabel('Shortcuts')
        heading.setObjectName('sectionTitle')
        outer.addWidget(heading)
        self.shortcut_grid = QGridLayout()
        self.shortcut_grid.setHorizontalSpacing(24)
        self.shortcut_grid.setVerticalSpacing(20)
        self.shortcut_groups = []
        for title, rows in SHORTCUT_GROUPS:
            group = QWidget()
            layout = QGridLayout(group)
            layout.setContentsMargins(0, 8, 0, 0)
            layout.setHorizontalSpacing(12)
            layout.setVerticalSpacing(10)
            layout.setColumnStretch(1, 1)
            label = QLabel(title)
            label.setObjectName('groupTitle')
            layout.addWidget(label, 0, 0, 1, 2)
            for i, (key, description) in enumerate(rows, 1):
                key_label = QLabel(key)
                key_label.setObjectName('shortcutKey')
                description_label = QLabel(description)
                description_label.setObjectName('shortcutDescription')
                description_label.setWordWrap(True)
                description_label.setMinimumWidth(0)
                layout.addWidget(key_label, i, 0, Qt.AlignmentFlag.AlignTop)
                layout.addWidget(description_label, i, 1)
            layout.setRowStretch(len(rows) + 1, 1)
            self.shortcut_groups.append(group)
        outer.addLayout(self.shortcut_grid)
        outer.addSpacing(10)
        hint = QLabel('Drop a structure or calculation file anywhere in the window to begin.')
        hint.setWordWrap(True)
        hint.setObjectName('version')
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hint)
        outer.addStretch(1)
        self._columns = 0
        self.setWidget(self.body)
        self._reflow_shortcuts()

    def _reflow_shortcuts(self):
        width = self.viewport().width()
        columns = 3 if width >= 900 else 2 if width >= 640 else 1
        if columns == self._columns:
            return
        while self.shortcut_grid.count():
            self.shortcut_grid.takeAt(0)
        for i, group in enumerate(self.shortcut_groups):
            self.shortcut_grid.addWidget(group, i // columns, i % columns)
        for i in range(3):
            self.shortcut_grid.setColumnStretch(i, 1 if i < columns else 0)
        self._columns = columns

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'shortcut_groups'):
            self._reflow_shortcuts()
