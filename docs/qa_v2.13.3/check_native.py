"""Measure production Qt/VTK geometry through selection and numeric edits."""
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton
from vtkmodules.qt import QVTKRenderWindowInteractor as adapter
from vtkmodules.vtkRenderingOpenGL2 import vtkEGLRenderWindow
from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
from vtkmodules.util.numpy_support import vtk_to_numpy

import lele.app as application
from lele.core import measure
from lele.style_presets import BUILTIN_PRESETS

destination = Path(sys.argv[1]).resolve()
destination.mkdir(parents=True, exist_ok=True)
result = {}


class OffscreenRenderWindow(vtkEGLRenderWindow):
    def SetWindowInfo(self, _handle):
        self.SetOffScreenRendering(True)


def settle():
    for _ in range(8):
        QApplication.processEvents()


def dimensions(window):
    return dict(window=[window.width(), window.height()],
                canvas=[window.vtk.width(), window.vtk.height()],
                footer=window.footer_row.height(), status=window.statusBar().height(),
                panels=window.structure_page.sizes())


def run(window):
    import lele
    result.update(version=lele.__version__, source=lele.__file__)
    sample = destination / 'layout_water.xyz'
    sample.write_text('5\nfooter selection demo\nO 0 0 0\nH .96 0 0\nH -.24 .93 0\nHe 3 2 1\nNe 3 -2 2\n')
    window._open_path_now(sample)
    settle()
    assert window.render_options.background == '#FFFFFF'
    assert BUILTIN_PRESETS['Classic ball and stick']['background'] == '#FFFFFF'
    assert window.scene.GetBackground() == (1., 1., 1.)
    result['background'] = window.render_options.background
    baseline = dimensions(window)
    states = []
    for indices in ([], [0], [0, 1], [0, 1, 2], [0, 1, 2, 3], [], [0, 1], []):
        window.atom_table.clearSelection()
        for index in indices:
            rect = window.atom_table.visualItemRect(window.atom_table.item(index, 0))
            QTest.mouseClick(window.atom_table.viewport(), Qt.MouseButton.LeftButton,
                             Qt.KeyboardModifier.ControlModifier, rect.center())
        settle()
        assert window.selection == indices, (window.selection, indices)
        state = dimensions(window)
        assert state == baseline, (indices, baseline, state)
        if len(indices) == 2:
            assert window.measurement_value.isVisible() and window.measurement_set.isVisible()
        states.append(dict(selected=indices, **state))
        if indices in ([], [0, 1]):
            name = 'native_two_atoms.png' if indices else 'native_unselected.png'
            window.grab().save(str(destination / name))
    result['selection_states'] = states

    window.selection = [0, 1]
    window._sync_selection_to_table()
    window.refresh_scene()
    settle()
    field = window.measurement_value.lineEdit()
    field.setFocus()
    field.selectAll()
    QTest.keyClicks(field, '1.1000')
    QTest.keyClick(field, Qt.Key.Key_Return)
    settle()
    assert abs(measure(window.frame, [0, 1])[1] - 1.1) < 1e-8
    assert dimensions(window) == baseline
    window.undo_edit()
    settle()
    assert abs(measure(window.frame, [0, 1])[1] - .96) < 1e-8
    assert dimensions(window) == baseline
    result['numeric_edit_and_undo'] = True

    window.preset_combo.setCurrentIndex(window.preset_combo.findData('Dark presentation'))
    buttons = [b for b in window.findChildren(QPushButton) if b.text() == 'Light background']
    assert len(buttons) == 1
    buttons[0].click()
    settle()
    assert window.scene.GetBackground() == (1., 1., 1.)
    window.preset_combo.setCurrentIndex(window.preset_combo.findData('Classic ball and stick'))
    settle()
    assert window.scene.GetBackground() == (1., 1., 1.)
    window.clear_selection()
    render = window.vtk.GetRenderWindow()
    render.Render()
    capture = vtkWindowToImageFilter()
    capture.SetInput(render)
    capture.ReadFrontBufferOff()
    capture.Update()
    data = capture.GetOutput()
    width, height, _ = data.GetDimensions()
    pixels = vtk_to_numpy(data.GetPointData().GetScalars()).reshape(height, width, -1)[::-1].copy()
    assert np.array_equal(pixels[0, 0, :3], [255, 255, 255]), pixels[0, 0]
    assert np.array_equal(pixels[0, -1, :3], [255, 255, 255]), pixels[0, -1]
    assert pixels.std() > 1
    Image.fromarray(pixels).save(destination / 'white_default_render.png')
    result['render_corner_rgb'] = pixels[0, 0, :3].tolist()
    result['light_button_and_default_preset'] = True
    result['ok'] = True


class ObservedApplication(QApplication):
    def exec(self):
        start = time.monotonic()

        def poll():
            window = next((w for w in self.topLevelWidgets() if isinstance(w, application.LELEWindow)), None)
            if window is None or window._backend_state != 'ready':
                if time.monotonic() - start < 30:
                    QTimer.singleShot(100, poll)
                    return
                result['error'] = 'Backend startup timeout'
            else:
                try:
                    run(window)
                except BaseException:
                    result['error'] = traceback.format_exc()
            (destination / 'native_window.json').write_text(json.dumps(result, indent=2) + '\n')
            if window:
                for document in window.documents:
                    document.modified = False
                window.close()
            self.quit()

        QTimer.singleShot(100, poll)
        return super().exec()


adapter.vtkRenderWindow = OffscreenRenderWindow
application.QApplication = ObservedApplication
application.main([])
print(json.dumps(result, indent=2))
sys.exit(0 if result.get('ok') else 1)
