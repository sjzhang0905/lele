"""Preload scientific modules after the welcome window has been painted."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QCoreApplication, QThread, Signal


def load_backend_modules():
    """Import libraries only; widgets and VTK objects belong to the GUI thread."""
    from . import formats, renderer, interaction  # noqa: F401
    from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget  # noqa: F401
    import vtkmodules.vtkRenderingFreeType  # noqa: F401 - register text before first draw
    # The file tree, footer, overlays and edit table are also needed for a plain XYZ.
    from . import (  # noqa: F401
        annotations, atom_constraints, bond_filter, boundary, boundary_selection, camera_views,
        chemical_analysis, energy_units, nmr_input, stm, structure_summary,
        trajectory_io, trajectory_storage, workflow_ui,
    )
    from ._cube_native import preload_readers
    preload_readers()


def load_idle_modules(file_requested):
    """Use welcome time for likely readers. A selected file takes priority."""
    if file_requested():
        return
    from scipy import spatial  # noqa: F401
    from ase import geometry, neighborlist  # noqa: F401
    if file_requested():
        return
    from ase import constraints, io  # noqa: F401
    from ase.io import extxyz, vasp, cif, proteindatabank  # noqa: F401
    if file_requested():
        return
    from ase.io import gaussian, orca, espresso, nwchem  # noqa: F401
    # These are the explicit fallback formats advertised by
    # legacy_converter.GENERIC_SUFFIX_READERS, not ASE's entire plugin set.
    from ase.io import (  # noqa: F401
        cfg, cube, gen, gromacs, gromos, mol, res, sdf,
        siesta, trajectory, wien2k, xsd, xsf, xtd,
    )
    if file_requested():
        return
    from . import (  # noqa: F401
        coordinate_templates_poscar,
        cube_input, fchk_input, field_mapping, gaussian_properties,
        gaussian_vibrations, molden_input, nwchem_trajectory,
        orca_results, orca_vibrations, orca_properties, orca_neb, orca_goat,
        orca_soc, orca_scan, cp2k_input, cp2k_results, qe_results, qe_phonons,
        pqr_input, siesta_results, siesta_trajectory, surface_rendering,
        vasp_results, volumetric_input, xtb_results,
    )
    if file_requested():
        return
    from PIL import Image, PngImagePlugin, GifImagePlugin  # noqa: F401


class BackendLoader(QThread):
    graphics_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('LELE backend preload')
        from threading import Event
        self._file_requested = Event()
        self.graphics_loaded = False
        self.loaded = False
        self.error = ''

    def prioritize_file(self):
        self._file_requested.set()

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
            self.graphics_loaded = True
            self.graphics_ready.emit()
            try:
                load_idle_modules(self._file_requested.is_set)
            except Exception:
                # Only the reader that actually needs an optional module should
                # report its failure. The ordinary structure view is ready.
                import logging
                logging.getLogger(__name__).debug('Optional reader preload failed', exc_info=True)
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
        app.aboutToQuit.connect(loader.prioritize_file)
        app.aboutToQuit.connect(loader.wait)
    return loader
