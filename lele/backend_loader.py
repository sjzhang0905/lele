"""Preload scientific modules after the welcome window has been painted."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QCoreApplication, QThread


def load_backend_modules():
    """Import libraries only; widgets and VTK objects belong to the GUI thread."""
    from . import (formats, renderer, interaction)  # noqa: F401
    from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget  # noqa: F401
    # A hidden empty renderer is not first-file readiness: bond inference,
    # periodic boundaries and readers otherwise pay these imports only when
    # the first structure is opened. Preload after the complete welcome paint.
    from scipy import spatial  # noqa: F401
    from ase import constraints, geometry, neighborlist  # noqa: F401
    from ase import io  # noqa: F401
    from ase.io import (extxyz, vasp, cif, gaussian, orca, espresso, nwchem)  # noqa: F401
    # These are the explicit fallback formats advertised by
    # legacy_converter.GENERIC_SUFFIX_READERS, not ASE's entire plugin set.
    from ase.io import (  # noqa: F401
        cfg, cube, gen, gromacs, gromos, mol, proteindatabank, res, sdf,
        siesta, trajectory, wien2k, xsd, xsf, xtd,
    )
    from . import (  # noqa: F401
        atom_constraints, boundary, chemical_analysis, coordinate_templates_poscar,
        cube_input, fchk_input, field_mapping, gaussian_properties,
        gaussian_vibrations, molden_input, nmr_input, nwchem_trajectory,
        orca_results, orca_vibrations, orca_properties, orca_neb, orca_goat,
        orca_soc, orca_scan, cp2k_input, cp2k_results, qe_results, qe_phonons,
        pqr_input, siesta_results, siesta_trajectory, surface_rendering, trajectory_io,
        vasp_results, volumetric_input, xtb_results,
    )
    from PIL import Image, PngImagePlugin, GifImagePlugin  # noqa: F401


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
