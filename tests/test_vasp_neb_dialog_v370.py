"""NEB chooser order and independent caterpillar rendering contract."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('VTK_DEFAULT_OPENGL_WINDOW', 'vtkEGLRenderWindow')

from pathlib import Path
import numpy as np
import pytest


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def documents():
    from lele.core import Document, Frame
    result = []
    for number, energy, x in ((10, -4., 2.), (2, -3., 1.2), (0, -5., .4)):
        frame = Frame(['Cu', 'Cu', 'H'], [[0., 0., 0.], [2., 0., 0.], [x, 0., 2.]],
                      np.eye(3) * 6., (True,) * 3, energy,
                      info={'source_kind': 'vasp_out', 'vasp_energy_sigma0_ev': energy,
                            'vasp_free_energy_ev': energy - .1})
        result.append(Document(Path(f'/fake/{number:02d}/OUTCAR'), 'VASP OUTCAR', [frame]))
    return result


def test_chooser_check_states_survive_reorder_and_sort(app):
    from PySide6.QtCore import Qt
    from lele.vasp_neb_dialog import VaspNebInputDialog
    chooser = VaspNebInputDialog(documents())
    assert [d.path.parent.name for d in chooser.selected_documents()] == ['00', '02', '10']
    chooser.files.item(1).setSelected(True)
    chooser.move_rows(-1)
    assert [d.path.parent.name for d in chooser.selected_documents()] == ['02', '00', '10']
    chooser.files.item(2).setCheckState(Qt.CheckState.Unchecked)
    chooser.sort_paths()
    assert [d.path.parent.name for d in chooser.selected_documents()] == ['00', '02']
    chooser.build()
    assert len(chooser.path.frames) == 2
    chooser.close()


def test_chooser_multiple_selection_and_validation(app):
    from lele.vasp_neb_dialog import VaspNebInputDialog
    chooser = VaspNebInputDialog(documents())
    chooser.files.item(0).setSelected(True)
    chooser.files.item(2).setSelected(True)
    chooser.use_selected_only()
    assert [d.path.parent.name for d in chooser.selected_documents()] == ['00', '10']
    chooser.files.clearSelection()
    chooser.files.item(2).setSelected(True)
    chooser.use_selected_only()
    chooser.build()
    assert chooser.path is None
    assert 'at least two' in chooser.error.text()
    chooser.close()


def test_caterpillar_controls_reference_and_no_ghost_bonds(app):
    from PySide6.QtWidgets import QMainWindow
    from lele.vasp_neb import build_neb_path, natural_path_key
    from lele.vasp_neb_dialog import VaspNebDialog
    from lele.render_options import RenderOptions
    from lele.core import visible_bonds
    docs = sorted(documents(), key=natural_path_key)
    window = QMainWindow()
    window.doc = docs[0]
    window.selection = [2]
    window.render_options = RenderOptions()
    dialog = VaspNebDialog(build_neb_path(docs), window)
    assert dialog.atoms.text() == '3'
    assert dialog.options.boundary_enabled
    assert dialog.drawing.boundary_display is not None
    assert not dialog.track_drawing.options.boundary_enabled
    assert len(dialog.caterpillar_frame.symbols) == 5
    assert all(i < 2 and j < 2 for i, j in visible_bonds(dialog.caterpillar_frame))
    dialog.reference.setCurrentIndex(2)
    assert dialog.rebuild_caterpillar()
    assert dialog.caterpillar_frame.info['neb_reference_image'] == 2
    dialog.atoms.setText('1, 3')
    assert dialog.rebuild_caterpillar()
    assert len(dialog.caterpillar_frame.symbols) == 7
    assert len(dialog.caterpillar_frame.info['neb_caterpillar_atoms']) == 6
    dialog.atoms.setText('999')
    assert not dialog.rebuild_caterpillar()
    assert 'between 1 and 3' in dialog.scene_note.text()
    assert len(dialog.caterpillar_frame.symbols) == 7
    assert np.allclose(docs[0].frames[0].positions[2], [.4, 0., 2.])
    dialog.close()
    window.close()


def test_curve_uses_zero_based_images_and_relative_first(app):
    from PySide6.QtWidgets import QMainWindow
    from lele.vasp_neb import build_neb_path, natural_path_key
    from lele.vasp_neb_dialog import VaspNebDialog
    from lele.render_options import RenderOptions
    docs = sorted(documents(), key=natural_path_key)
    window = QMainWindow()
    window.doc = docs[0]
    window.selection = []
    window.render_options = RenderOptions()
    dialog = VaspNebDialog(build_neb_path(docs), window)
    assert dialog.atoms.text() == '3'
    assert 'Forward sampled barrier 2 eV' in dialog.summary.text()
    assert 'Reverse sampled barrier 1 eV' in dialog.summary.text()
    dialog.coordinate.setCurrentIndex(1)
    assert np.allclose(dialog.figure.axes[0].lines[0].get_xdata(), [0, 1, 2])
    assert np.allclose(dialog.figure.axes[0].lines[0].get_ydata(), [0, 2, 1])
    assert dialog.table.item(0, 0).text() == '0'
    dialog.close()
    window.close()
