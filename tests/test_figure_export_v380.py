"""Publication export preserves curves, editable text and exact raster pixels."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('VTK_DEFAULT_OPENGL_WINDOW', 'vtkEGLRenderWindow')
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET
import numpy as np
import pytest
from PIL import Image
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from lele.figure_export import export_figure, figure_output_path, save_figure_dialog
from lele.png_export import PngSettings


@pytest.fixture
def figure():
    fig = Figure(figsize=(4, 3), dpi=100)
    FigureCanvasAgg(fig)
    axis = fig.add_subplot()
    axis.plot([0, 1, 2], [0, 1, 0], label='signal')
    axis.set_xlabel('Distance (Å)')
    return fig


def test_svg_contains_vector_curve_and_editable_axis_text(tmp_path, figure):
    output = export_figure(tmp_path / 'spectrum.svg', figure)
    root = ET.parse(output).getroot()
    ns = {'s': 'http://www.w3.org/2000/svg'}
    assert root.findall('.//s:path', ns)
    assert not root.findall('.//s:image', ns)
    assert 'Distance (Å)' in [''.join(n.itertext()) for n in root.findall('.//s:text', ns)]


@pytest.mark.parametrize('suffix,mode', [('.png', 'RGBA'), ('.jpg', 'RGB'), ('.tif', 'RGBA')])
@pytest.mark.parametrize('supersample', [1, 2])
def test_raster_exact_pixels_and_figure_state_restored(tmp_path, figure, suffix, mode, supersample):
    size = figure.get_size_inches().copy()
    dpi = figure.dpi
    values = figure.axes[0].lines[0].get_ydata().copy()
    export_figure(tmp_path / ('curve' + suffix), figure, PngSettings(500, 320, supersample))
    with Image.open(tmp_path / ('curve' + suffix)) as image:
        assert image.size == (500, 320)
        assert image.mode == mode
        assert len(np.unique(np.asarray(image).reshape(-1, len(mode)), axis=0)) > 20
    np.testing.assert_array_equal(figure.get_size_inches(), size)
    assert figure.dpi == dpi
    np.testing.assert_array_equal(figure.axes[0].lines[0].get_ydata(), values)


def test_failed_export_preserves_destination_and_figure(tmp_path, figure):
    path = tmp_path / 'existing.png'
    path.write_bytes(b'old')
    size = figure.get_size_inches().copy()
    with patch.object(figure, 'savefig', side_effect=RuntimeError('test renderer failure')):
        with pytest.raises(RuntimeError, match='renderer failure'):
            export_figure(path, figure, PngSettings(500, 320))
    assert path.read_bytes() == b'old'
    np.testing.assert_array_equal(figure.get_size_inches(), size)
    assert not list(tmp_path.glob('.lele-figure-*'))


def test_raster_requires_settings_and_rejects_unsafe_capture(tmp_path, figure):
    with pytest.raises(ValueError, match='resolution'):
        export_figure(tmp_path / 'x.png', figure)
    with pytest.raises(ValueError, match='smaller'):
        export_figure(tmp_path / 'x.png', figure, PngSettings(8192, 8192, 2))


def test_output_suffix_matches_explicit_type_or_selected_filter():
    assert figure_output_path('spectrum') == Path('spectrum.svg')
    assert figure_output_path('spectrum.raw', 'PNG image (*.png)') == Path('spectrum.raw.png')
    assert figure_output_path('spectrum.PNG') == Path('spectrum.PNG')


def test_save_dialog_defaults_svg_and_raster_prompts_quality(tmp_path, figure):
    from PySide6.QtWidgets import QApplication, QWidget, QDialog
    from lele.png_dialog import PngExportDialog
    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    with patch('lele.figure_export.QFileDialog.getSaveFileName', return_value=(str(tmp_path / 'vector'), 'SVG vector (*.svg)')) as chooser:
        path = save_figure_dialog(parent, figure, tmp_path / 'suggested')
        assert chooser.call_args.args[2].endswith('suggested.svg')
        assert chooser.call_args.args[3].startswith('SVG')
        assert path.suffix == '.svg'
    with patch('lele.figure_export.QFileDialog.getSaveFileName', return_value=(str(tmp_path / 'raster'), 'PNG image (*.png)')):
        with patch.object(PngExportDialog, 'exec', return_value=QDialog.DialogCode.Accepted), patch.object(PngExportDialog, 'settings', return_value=PngSettings(320, 240, 1)):
            path = save_figure_dialog(parent, figure)
        with Image.open(path) as image:
            assert image.size == (320, 240)
    parent.close()


def test_world_text_quality_scaling_preserves_anchor_rotation_and_restores():
    from vtkmodules.vtkRenderingCore import vtkRenderer
    from lele.annotations import AnnotationRenderer, TextAnnotation
    from lele.png_export import scaled_world_text
    scene = vtkRenderer()
    manager = AnnotationRenderer(scene)
    manager.set_annotations([TextAnnotation('Surface', position=[2, 3, 4], height=.7,
        rotation=[[0, -1, 0], [1, 0, 0], [0, 0, 1]])])
    actor = manager.actors[0]
    old_matrix = actor.GetUserMatrix()
    matrix = np.array([[old_matrix.GetElement(i, j) for j in range(4)] for i in range(4)])
    old_size = actor.GetTextProperty().GetFontSize()
    with scaled_world_text([actor], 3):
        changed = np.array([[actor.GetUserMatrix().GetElement(i, j) for j in range(4)] for i in range(4)])
        assert actor.GetTextProperty().GetFontSize() == 3 * old_size
        np.testing.assert_allclose(changed[:3, :3] * 3, matrix[:3, :3])
        np.testing.assert_allclose(changed[:3, 3], [2, 3, 4])
    assert actor.GetTextProperty().GetFontSize() == old_size
    assert actor.GetUserMatrix() is old_matrix
    manager.clear()


def test_animation_offscreen_scene_includes_document_text():
    from lele.animation_export import _OffscreenScene, GifSettings
    from lele.annotations import TextAnnotation
    from lele.core import Document, Frame
    from lele.render_options import RenderOptions
    from vtkmodules.vtkRenderingCore import vtkCamera
    frame = Frame(['C'], [[0, 0, 0]])
    document = Document(Path('sample.xyz'), 'XYZ', [frame])
    camera = vtkCamera()
    camera.ParallelProjectionOn()
    camera.SetPosition(0, 0, 10)
    camera.SetFocalPoint(0, 0, 0)
    camera.SetParallelScale(2)
    options = RenderOptions()
    options.axes_position = 'Off'
    options.unit_cell = False
    drawing = _OffscreenScene(GifSettings(width=320, height=240, supersample=1),
        options, camera, [], (320, 240))
    drawing.document = document
    try:
        first = drawing.render(frame, None)
        base = np.asarray(first).copy()
        first.close()
        document.annotations = [TextAnnotation('LELE', position=[0, 1, 0], height=.7)]
        second = drawing.render(frame, None)
        annotated = np.asarray(second).copy()
        second.close()
        assert np.count_nonzero(np.any(annotated != base, axis=2)) > 100
        assert len(drawing.annotation_renderer.actors) == 1
        np.testing.assert_allclose(document.annotations[0].position, [0, 1, 0])
    finally:
        drawing.close()
