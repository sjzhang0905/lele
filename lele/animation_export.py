"""GIF planning and export. Scientific/image imports are deferred until export."""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from math import isfinite, tau
from pathlib import Path
import os
import tempfile


class ExportCancelled(Exception):
    """A cancelled export leaves the destination untouched."""


@dataclass(frozen=True)
class GifSettings:
    source: str = 'trajectory'
    width: int = 960
    height: int = 540
    fps: int = 24
    first_frame: int = 1
    last_frame: int = 1
    stride: int = 1
    ping_pong: bool = False
    cycle_seconds: float = 1.
    amplitude: float = .35
    loop: bool = True
    supersample: int = 2
    dither: bool = True

    def __post_init__(self):
        if self.source not in ('trajectory', 'vibration'):
            raise ValueError('Choose a trajectory or a vibration mode')
        if self.supersample not in (1,2):raise ValueError('Supersampling must be 1 or 2')
        if not (1 <= self.width <= 4096 and 1 <= self.height <= 4096):
            raise ValueError('GIF dimensions must be between 1 and 4096 pixels')
        if not 1 <= self.fps <= 50:
            raise ValueError('GIF frame rate must be between 1 and 50 FPS')
        if (not isfinite(self.cycle_seconds) or not .2 <= self.cycle_seconds <= 10
                or not isfinite(self.amplitude) or not .01 <= self.amplitude <= 2):
            raise ValueError('Invalid vibration duration or amplitude')

    def trajectory_indices(self, total):
        if not 1 <= self.first_frame <= self.last_frame <= total or self.stride < 1:
            raise ValueError('Choose a valid trajectory frame range and step')
        indices = list(range(self.first_frame - 1, self.last_frame, self.stride))
        if len(indices) < 2:
            raise ValueError('Select at least two trajectory frames')
        # Endpoints occur once, including across a continuously looping GIF.
        return indices + indices[-2:0:-1] if self.ping_pong else indices

    def vibration_frame_count(self):
        # Keep every delay at least two GIF ticks when rounding short cycles.
        count = min(round(self.fps * self.cycle_seconds), round(self.cycle_seconds * 100) // 2)
        if count < 8:
            raise ValueError('Use at least eight frames per vibration cycle')
        return count


def gif_delays(count, fps, *, cycle_seconds=None):
    """Distribute GIF's 10 ms ticks without accumulating per-frame rounding."""
    if count < 1 or not 1 <= fps <= 50:
        raise ValueError('Invalid GIF frame count or rate')
    total_ticks = round(cycle_seconds * 100) if cycle_seconds is not None else None
    boundaries = ([round(i * total_ticks / count) for i in range(count + 1)]
                  if total_ticks is not None else [round(i * 100 / fps) for i in range(count + 1)])
    delays = [(b - a) * 10 for a, b in zip(boundaries, boundaries[1:])]
    if min(delays) < 10:
        raise ValueError('GIF frames need at least 10 ms each')
    return delays


def vibration_frames(reference, mode, count, amplitude, cutoff=1.):
    if not mode.can_animate:
        raise ValueError('The selected mode has no usable displacement data')
    for i in range(count):
        yield mode.preview_frame(reference,tau*i/count,amplitude,cutoff)


def write_gif(path, images, delays, *, loop=True, progress=None, cancelled=None, palette=None, dither=True):
    """Encode one frame at a time; replace an existing file only on success.

    Pillow's documented GIF plugin primitives avoid collecting an entire
    high-resolution trajectory in memory. Each full frame has its own palette.
    """
    from PIL import GifImagePlugin, Image

    path = Path(path)
    if not delays:
        raise ValueError('No GIF frames to save')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=path.parent,
                                         prefix='.lele-gif-', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            size = None
            for i, (image, delay) in enumerate(zip(images, delays, strict=True)):
                if cancelled is not None and cancelled():
                    raise ExportCancelled()
                if size is not None and image.size != size:
                    raise ValueError('GIF frame dimensions differ')
                size = image.size
                rgb=image.convert('RGB')
                frame = rgb.quantize(palette=palette,dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE) if palette is not None else rgb.quantize(
                    colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
                rgb.close()
                try:
                    frame.info.clear()
                    if i == 0:
                        info = {'duration': delay}
                        if loop:
                            info['loop'] = 0
                        for part in GifImagePlugin.getheader(frame, info=info)[0]:
                            output.write(part)
                    for part in GifImagePlugin.getdata(frame, duration=delay, disposal=2,
                                                       include_color_table=i > 0 and palette is None):
                        output.write(part)
                finally:
                    frame.close()
                if progress is not None:
                    progress(i + 1, len(delays))
            if cancelled is not None and cancelled():
                raise ExportCancelled()
            output.write(b';')
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class _OffscreenScene:
    def __init__(self, settings, options, camera, selected, source_size):
        from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkRenderWindowInteractor
        from vtkmodules.vtkInteractionWidgets import vtkOrientationMarkerWidget
        from .renderer import MoleculeRenderer

        self.window = vtkRenderWindow()
        self.window.SetOffScreenRendering(True)
        self.settings=settings
        self.document=None
        self.dipole_reference=None
        self.window.SetSize(settings.width*settings.supersample, settings.height*settings.supersample)
        self.window.SetMultiSamples(0)
        self.scene = vtkRenderer()
        self.window.AddRenderer(self.scene)
        self.draw = MoleculeRenderer(self.scene)
        self.draw.options = deepcopy(options)
        if source_size is not None and source_size[0] > 0:
            self.draw.options.label_font_size = max(1, round(options.label_font_size * settings.width*settings.supersample / source_size[0]))
        self.camera_supplied = camera is not None
        if camera is not None:
            self.scene.GetActiveCamera().DeepCopy(camera)
        self.selected = list(selected)
        self.interactor = vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.window)
        self.marker = vtkOrientationMarkerWidget()
        self.marker.SetInteractor(self.interactor)
        self.marker.SetViewport(.015, .015, .225, .225)
        self.first = True

    def render(self, frame, volume):
        from PIL import Image
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter
        from vtkmodules.util.numpy_support import vtk_to_numpy

        self.draw.selected = [i for i in self.selected if i < len(frame.symbols)]
        if self.document is not None:
            from .gaussian_properties import selected_dipole,dipole_label
            self.draw.dipole_vector=selected_dipole(self.document,self.dipole_reference or frame,self.draw.options.dipole_source)
            self.draw.dipole_label=dipole_label(self.document,self.draw.options.dipole_source)
        self.draw.set_scene(frame, volume)
        if self.first and not self.camera_supplied:
            self.scene.ResetCamera()
        self.first = False
        self.scene.ResetCameraClippingRange()
        if self.draw.options.axes_position == 'Corner':
            if self.marker.GetEnabled():
                self.marker.SetEnabled(0)
            self.marker.SetOrientationMarker(self.draw.make_corner_marker(self.draw.frame))
            self.marker.SetEnabled(1)
            self.draw.attach_corner_labels(self.marker.GetRenderer())
            self.marker.InteractiveOff()
        self.window.Render()
        capture = vtkWindowToImageFilter()
        capture.SetInput(self.window)
        capture.SetInputBufferTypeToRGB()
        capture.ReadFrontBufferOff()
        capture.ShouldRerenderOff()
        capture.Update()
        data = capture.GetOutput()
        width, height, _ = data.GetDimensions()
        values = vtk_to_numpy(data.GetPointData().GetScalars()).reshape(height, width, 3)
        image=Image.fromarray(values[::-1].copy())
        if self.settings.supersample>1:
            resized=image.resize((self.settings.width,self.settings.height),Image.Resampling.LANCZOS);image.close();image=resized
        return image

    def close(self):
        self.draw.detach_corner_labels()
        if self.marker.GetEnabled():
            self.marker.SetEnabled(0)
        self.marker.SetInteractor(None)
        self.window.Finalize()
        self.interactor.SetRenderWindow(None)


def export_animation_gif(path, document, settings, options, *, camera=None,
                         reference=None, mode=None, selected=(), source_size=None,
                         progress=None, cancelled=None, alignment=None,
                         mode_arrows=False, mode_arrow_length=1., mode_arrow_indices=None):
    """Render a snapshot of the chosen data, without touching the live canvas."""
    if settings.source == 'trajectory':
        indices = settings.trajectory_indices(len(document.frames))
        frames = (document.frames[i] for i in indices)
        count = len(indices)
        delays = gif_delays(count, settings.fps)
        volume = document.volume
    else:
        if reference is None or mode is None or not mode.can_animate:
            raise ValueError('Select a vibration mode with complete displacement data')
        count = settings.vibration_frame_count()
        frames = vibration_frames(reference,mode,count,settings.amplitude,options.bond_cutoff)
        delays = gif_delays(count, settings.fps, cycle_seconds=settings.cycle_seconds)
        volume = None
    if cancelled is not None and cancelled():
        raise ExportCancelled()
    renderer = _OffscreenScene(settings, options, camera, selected, source_size)
    renderer.draw.alignment = deepcopy(alignment) if settings.source == 'trajectory' else None
    if mode_arrows and settings.source == 'vibration':
        renderer.draw.mode_vectors = mode.arrow_vectors() if hasattr(mode,'arrow_vectors') else mode.displacements
        renderer.draw.mode_vector_length = mode_arrow_length
        renderer.draw.mode_vector_indices = mode_arrow_indices
    renderer.document=document
    renderer.dipole_reference=reference if settings.source=='vibration' else None
    try:
        if settings.source == 'vibration':
            from .core import visible_bonds
            renderer.draw.fixed_bonds = visible_bonds(reference, options.bond_cutoff)

        def frame_at(i):
            if settings.source=='trajectory':return document.frames[indices[i]]
            return mode.preview_frame(reference,tau*i/count,settings.amplitude,options.bond_cutoff)

        from PIL import Image
        import numpy as np
        samples=np.unique(np.linspace(0,count-1,min(8,count),dtype=int))
        sheet=Image.new('RGB',(256,144*len(samples)))
        for j,i in enumerate(samples):
            if progress is not None:progress(0,count)
            if cancelled is not None and cancelled():raise ExportCancelled()
            sample=renderer.render(frame_at(int(i)),volume);sample.thumbnail((256,144),Image.Resampling.LANCZOS)
            sheet.paste(sample,(0,j*144));sample.close()
        palette=sheet.quantize(colors=256,method=Image.Quantize.MEDIANCUT);sheet.close()
        def images():
            for i in range(count):
                if cancelled is not None and cancelled():
                    raise ExportCancelled()
                image=renderer.render(frame_at(i), volume)
                try:yield image
                finally:image.close()

        try:write_gif(path, images(), delays, loop=settings.loop, progress=progress, cancelled=cancelled,palette=palette,dither=settings.dither)
        finally:palette.close()
    finally:
        renderer.close()
    return count
