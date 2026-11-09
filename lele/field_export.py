"""Atomic export of one attached scalar grid to an interoperable CUBE file.

Geometry is always written in Bohr. Recognized density, orbital-amplitude and
potential units are converted to atomic units; unknown units are not guessed.
"""
from pathlib import Path
import json
import os
import tempfile
import numpy as np
from ase.data import atomic_numbers
from ase.units import Bohr, Hartree
from .output_text import check_load_cancelled, load_progress


def cube_scalar_units(unit):
    """Return factor, output unit and explicit conversion note."""
    unit = str(unit or '').strip()
    if unit == 'e/Å³':
        return Bohr**3, 'e/Bohr³', 'Charge density converted from e/Å³ to e/Bohr³.'
    if unit.startswith('Å⁻³ (unweighted pseudo state)'):
        return Bohr**3, 'Bohr⁻³ (unweighted pseudo state)', 'Single-state pseudo density converted from Å⁻³ to Bohr⁻³; not total charge density.'
    if unit == 'Å⁻³ᐟ²':
        return Bohr**1.5, 'Bohr⁻³ᐟ²', 'Orbital amplitude converted from Å⁻³ᐟ² to Bohr⁻³ᐟ².'
    if unit == 'eV':
        return 1/Hartree, 'Hartree', 'Potential converted from eV to Hartree.'
    if unit == 'dimensionless' or 'Bohr' in unit or unit == 'Hartree':
        return 1., unit, 'Scalar values retained in '+unit+'.'
    return 1., unit or 'unknown source units', 'Scalar units are not recognized; values are preserved, not relabeled as atomic units.'


def export_active_cube(path, document, frame):
    """Export the currently attached dataset and current static geometry.

    No isosurface triangulation, renderer smoothing or duplicate periodic
    endpoint is exported. This is the original grid, with display transforms.
    """
    if document is None or document.volume is None:
        raise ValueError('No attached volumetric field to export. Undo the structure edit or reopen the source.')
    if frame is None:
        raise ValueError('No structure frame is available for CUBE export.')
    from .site_occupancy import is_disordered
    if is_disordered(frame):
        raise ValueError('CUBE cannot encode fractional site occupancy; export a fully specified structure and its corresponding field.')
    volume = document.volume
    data = np.asarray(volume.data)
    if data.ndim != 3 or min(data.shape) < 2 or not np.isfinite(data).all():
        raise ValueError('CUBE export requires a finite three-dimensional grid.')
    basis = np.asarray(volume.voxel_vectors, float)
    origin = np.asarray(volume.origin, float)
    if not np.isfinite(basis).all() or not np.isfinite(origin).all() or abs(np.linalg.det(basis)) < 1e-15:
        raise ValueError('CUBE grid vectors must be finite and linearly independent.')
    try:numbers = [atomic_numbers[s] for s in frame.symbols]
    except KeyError as exc:raise ValueError('Unknown atomic symbol in CUBE structure.') from exc
    factor, unit, note = cube_scalar_units(volume.unit)
    metadata = dict(label=volume.label, unit=unit, source_unit=volume.unit,
                    periodic=bool(volume.periodic), atom_pbc=list(frame.pbc),
                    cell=np.asarray(frame.cell).tolist())
    # ASCII JSON survives legacy scientific readers; only standard numeric
    # CUBE records carry the grid, so other tools may simply ignore this line.
    comment = 'LELE_CUBE '+json.dumps(metadata,ensure_ascii=True,separators=(',',':'))
    path = Path(path)
    temporary = None
    report = load_progress('Writing CUBE scalar grid',data.size)
    try:
        with tempfile.NamedTemporaryFile('w',encoding='ascii',newline='\n',dir=path.parent,
                                         prefix='.'+path.name+'.',suffix='.tmp',delete=False) as out:
            temporary = Path(out.name)
            out.write(comment+'\nOUTER LOOP: X, MIDDLE LOOP: Y, INNER LOOP: Z; geometry Bohr\n')
            out.write(f'{len(numbers):5d} '+ ' '.join(f'{x:.15e}' for x in origin/Bohr)+'\n')
            for count, vector in zip(data.shape,basis/Bohr):
                out.write(f'{count:5d} '+' '.join(f'{x:.15e}' for x in vector)+'\n')
            for number, position in zip(numbers,frame.positions/Bohr):
                check_load_cancelled()
                out.write(f'{number:5d} 0.0 '+' '.join(f'{x:.15e}' for x in position)+'\n')
            values=data.ravel(order='C')
            for start in range(0,len(values),6144):
                check_load_cancelled()
                chunk=np.asarray(values[start:start+6144],float)*factor
                for row in range(0,len(chunk),6):
                    out.write(' '.join(f'{x:.9e}' for x in chunk[row:row+6])+'\n')
                report(min(start+6144,len(values)))
            check_load_cancelled()
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:
            try:temporary.unlink()
            except OSError:pass
    return note+' Only the active dataset is exported; atom charge columns are zero, not computed charges.'


def export_active_field_dialog(window):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from .operations import run_data_task
    from .output_text import LoadCancelled
    doc, frame = window.doc, window.frame
    if doc is None or doc.volume is None or frame is None:return
    factor, unit, note=cube_scalar_units(doc.volume.unit)
    answer=QMessageBox.question(window,'Export active field as CUBE',
        note+'\nGeometry is written in Bohr. Only the selected dataset and static structure are exported; surface style is not included.\nContinue?',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes)
    if answer != QMessageBox.StandardButton.Yes:return
    path,_=QFileDialog.getSaveFileName(window,'Export active field as CUBE',window._save_path('_field.cube'),'Gaussian CUBE (*.cube *.cub)')
    if not path:return
    try:
        result=run_data_task(window,'Exporting scalar field',lambda:export_active_cube(path,doc,frame),cancellable=True)
    except LoadCancelled:return
    except Exception as exc:
        QMessageBox.warning(window,'CUBE export failed',str(exc));return
    window.statusBar().showMessage('Exported '+path+' | '+result,10000)
