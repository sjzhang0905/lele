"""Shared publication figure export: vectors first, configurable raster quality.

Import only from plotting windows: Matplotlib and Qt remain deferred at startup.
"""
from contextlib import ExitStack, contextmanager
from io import BytesIO
from pathlib import Path
import os
import tempfile

from .dialog_policy import QDialog, QFileDialog, QMessageBox
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from .png_export import MAX_CAPTURE_PIXELS, PngSettings

VECTOR_FORMATS = {'.svg', '.pdf'}
RASTER_FORMATS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff'}
FILTERS = 'SVG vector (*.svg);;PDF vector (*.pdf);;PNG image (*.png);;JPEG image (*.jpg);;TIFF image (*.tif)'


def figure_output_path(filename, selected_filter='SVG vector (*.svg)'):
    """Honor an explicit supported suffix; otherwise append the selected one."""
    path = Path(filename)
    if path.suffix.lower() in VECTOR_FORMATS | RASTER_FORMATS:
        return path
    suffix = next((ext for label, ext in (('PDF', '.pdf'), ('PNG', '.png'),
        ('JPEG', '.jpg'), ('TIFF', '.tif')) if selected_filter.startswith(label)), '.svg')
    return path.with_name(path.name + suffix)


def default_figure_path(parent, default_stem=None):
    if default_stem is not None:
        path = Path(default_stem)
        return path.with_suffix('.svg') if path.suffix.lower() in VECTOR_FORMATS | RASTER_FORMATS else path.with_name(path.name + '.svg')
    widget = parent
    while widget is not None:
        document = getattr(widget, 'document', None)
        path = getattr(document, 'path', None)
        if path is not None:
            source = Path(path)
            return source.with_name(source.stem + '_plot.svg')
        path = getattr(widget, 'source_path', None)
        if path is not None:
            source = Path(path)
            return source.with_name(source.stem + '_plot.svg')
        widget = widget.parent() if hasattr(widget, 'parent') else None
    return Path('lele_plot.svg')


@contextmanager
def _figure_background(figure, use_white):
    """Apply an opaque white page and plotting area only for this export."""
    from .render_options import WHITE_BACKGROUND
    with ExitStack() as restore:
        restore.callback(figure.canvas.draw_idle)
        if use_white:
            page = figure.patch
            restore.callback(page.set_visible, page.get_visible())
            restore.callback(page.set_alpha, page.get_alpha())
            page.set_visible(True)
            page.set_alpha(1.)
            for axis in figure.axes:
                patch = axis.patch
                color = patch.get_facecolor()
                if patch.get_visible() and color[3]:
                    restore.callback(patch.set_facecolor, color)
                    patch.set_facecolor(WHITE_BACKGROUND)
            yield dict(facecolor=WHITE_BACKGROUND, edgecolor=WHITE_BACKGROUND, transparent=False)
        else:
            yield dict(facecolor=figure.get_facecolor(), edgecolor=figure.get_edgecolor(), transparent=False)


@contextmanager
def _figure_size(figure, settings):
    old_size = figure.get_size_inches().copy()
    old_dpi = figure.dpi
    try:
        # Preserve font/line proportions while accommodating exact raster pixels.
        width = max(.1, float(old_size[0]))
        figure.set_size_inches(width, width * settings.height / settings.width, forward=False)
        yield settings.width / width * settings.supersample
    finally:
        figure.set_size_inches(old_size, forward=False)
        figure.set_dpi(old_dpi)


def export_figure(path, figure, settings=None):
    """Write atomically; SVG retains vector paths and editable text.

    Raster settings select exact output pixels and optional 2× supersampling.
    Smoothing changes rendering quality only, never the scientific data.
    """
    from matplotlib import rc_context
    from PIL import Image
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in VECTOR_FORMATS | RASTER_FORMATS:
        raise ValueError('Choose SVG, PDF, PNG, JPEG or TIFF.')
    if suffix in RASTER_FORMATS:
        if settings is None:
            raise ValueError('Raster export requires explicit resolution and smoothing settings.')
        if settings.width * settings.height * settings.supersample ** 2 > MAX_CAPTURE_PIXELS:
            raise ValueError('Choose a smaller image or turn off Smooth edges.')
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.lele-figure-', suffix=suffix)
    os.close(descriptor)
    temporary = Path(name)
    try:
        white = settings is None or settings.white_background
        with (rc_context({'svg.fonttype': 'none', 'savefig.bbox': None}),
              _figure_background(figure, white) as background_args):
            if suffix in VECTOR_FORMATS:
                figure.savefig(temporary, format=suffix[1:], bbox_inches=None, **background_args)
            else:
                with _figure_size(figure, settings) as dpi, BytesIO() as buffer:
                    figure.savefig(buffer, format='png', dpi=dpi, bbox_inches=None, **background_args)
                    buffer.seek(0)
                    with Image.open(buffer) as source:
                        result = source.convert('RGB' if suffix in {'.jpg', '.jpeg'} else 'RGBA')
                    try:
                        if result.size != (settings.width, settings.height):
                            resized = result.resize((settings.width, settings.height), Image.Resampling.LANCZOS)
                            result.close()
                            result = resized
                        if settings.cropped:
                            from .png_export import crop_background
                            background = ((255, 255, 255) if white else
                                          tuple(round(255 * v) for v in figure.get_facecolor()[:3]))
                            cropped = crop_background(result, background)
                            result.close()
                            result = cropped
                        fmt = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.tif': 'TIFF', '.tiff': 'TIFF'}[suffix]
                        extra = {'quality': 95, 'subsampling': 0} if fmt == 'JPEG' else {}
                        result.save(temporary, format=fmt, dpi=(300, 300), **extra)
                    finally:
                        result.close()
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def save_figure_dialog(parent, figure, default_stem=None):
    """SVG-first file chooser, followed by quality controls for raster output."""
    path, selected_filter = QFileDialog.getSaveFileName(parent, 'Save plot',
        str(default_figure_path(parent, default_stem)), FILTERS, 'SVG vector (*.svg)')
    if not path:
        return None
    path = figure_output_path(path, selected_filter)
    settings = None
    if path.suffix.lower() in RASTER_FORMATS:
        from .png_dialog import PngExportDialog
        width, height = figure.canvas.get_width_height()
        dialog = PngExportDialog(parent, view_size=(width, height),
            title='Plot image quality', note='Choose output pixels and edge smoothing for this plot.',
            scene_image=False,
            format_name={'.jpg': 'JPEG', '.jpeg': 'JPEG', '.tif': 'TIFF', '.tiff': 'TIFF'}.get(path.suffix.lower(), 'PNG'))
        dialog.smooth_check.setToolTip('Render twice as many pixels per side, then downsample with Lanczos. Data are unchanged.')
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings = dialog.settings()
    try:
        from .operations import ui_operation
        with ui_operation(parent, 'Exporting plot'):
            return export_figure(path, figure, settings)
    except Exception as exc:
        QMessageBox.warning(parent, 'Could not export plot', str(exc))
        return None


class FigureExportToolbar(NavigationToolbar2QT):
    """The usual plot controls, with the shared SVG-first Save action."""
    def save_figure(self, *args):
        return save_figure_dialog(self.parent(), self.canvas.figure)
