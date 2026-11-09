"""Preload scientific modules after the welcome window has been painted."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QCoreApplication, QThread


def load_backend_modules():
    """Import libraries only; widgets and VTK objects belong to the GUI thread."""
    from . import (formats, renderer, interaction)  # noqa: F401
    from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget  # noqa: F401
    # Analysis, image export and ASE's format registry load when requested.
    # None is needed to display the welcome page or construct the 3D canvas.


class BackendLoader(QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('LELE backend preload')
        self.loaded = False
        self.error = ''

    def ensure_started(self):
        if self.loaded or self.isRunning():
            return
        self.error = ''
        self.start()

    def run(self):
        try:
            load_backend_modules()
        except Exception:
            self.error = traceback.format_exc()
        else:
            self.loaded = True


def get_backend_loader():
    """Share imports across windows and keep the thread alive until app exit."""
    app = QCoreApplication.instance()
    loader = getattr(app, '_lele_backend_loader', None)
    if loader is None:
        loader = BackendLoader(app)
        app._lele_backend_loader = loader
        # Closing a window need not wait. Application shutdown must finish any
        # active import before Qt or Python tears down the native libraries.
        app.aboutToQuit.connect(loader.wait)
    return loader
