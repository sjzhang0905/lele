"""High-resolution PNG capture of the current scene, with reversible quality changes."""
from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil
from pathlib import Path
import os
import tempfile

MAX_OUTPUT_SIDE = 8192
MAX_CAPTURE_PIXELS = 128_000_000


@dataclass(frozen=True)
class PngSettings:
    width: int
    height: int
    supersample: int = 2

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX_OUTPUT_SIDE
               for v in (self.width, self.height)):
            raise ValueError('PNG dimensions must be between 1 and 8192 pixels.')
        if self.supersample not in (1, 2):
            raise ValueError('Choose standard or smooth edges.')

    def capture_scale(self, source_size):
        width, height = source_size
        if width < 1 or height < 1:
            raise ValueError('The canvas has no renderable size.')
        scale = max(1, ceil(max(self.width / width, self.height / height) * self.supersample))
        if width * height * scale * scale > MAX_CAPTURE_PIXELS:
            raise ValueError('Choose a smaller PNG width or turn off Smooth edges.')
        return scale


def _objects(items):
    for item in items:
        if isinstance(item, (tuple, list)):
            yield from _objects(item)
        else:
            yield item


@contextmanager
def smooth_meshes(items, enabled):
    """Increase sphere/tube/arrow tessellation for capture, then restore it."""
    changed = []
    seen = set()
    try:
        if enabled:
            for obj in _objects(items):
                if id(obj) in seen or not hasattr(obj, 'IsA'):
                    continue
                seen.add(id(obj))
                if obj.IsA('vtkSphereSource'):
                    values = [('ThetaResolution', obj.GetThetaResolution(), 64),
                              ('PhiResolution', obj.GetPhiResolution(), 48)]
                elif obj.IsA('vtkTubeFilter'):
                    values = [('NumberOfSides', obj.GetNumberOfSides(), 32)]
                elif obj.IsA('vtkArrowSource'):
                    values = [('TipResolution', obj.GetTipResolution(), 32),
                              ('ShaftResolution', obj.GetShaftResolution(), 32)]
                else:
                    continue
                changed.append((obj, values))
                for name, old, requested in values:
                    getattr(obj, 'Set' + name)(max(old, requested))
                obj.Update()
        yield
    finally:
        for obj, values in reversed(changed):
            for name, old, _ in values:
                getattr(obj, 'Set' + name)(old)
            obj.Update()


@contextmanager
def frozen_overlays(window):
    """Render overlay snapshots without orientation-widget tile callbacks."""
    from vtkmodules.vtkRenderingCore import vtkCamera, vtkRenderer, vtkTextProperty

    def copy_prop(prop):
        duplicate = prop.NewInstance()
        if prop.IsA('vtkPropAssembly'):
            for field in ('Visibility', 'Pickable', 'UseBounds'):
                getattr(duplicate, 'Set' + field)(getattr(prop, 'Get' + field)())
            for part in prop.GetParts():
                duplicate.AddPart(copy_prop(part))
        else:
            duplicate.ShallowCopy(prop)
        if hasattr(prop, 'GetTextProperty'):
            text = vtkTextProperty()
            text.ShallowCopy(prop.GetTextProperty())
            duplicate.SetTextProperty(text)
            duplicate.SetInput(prop.GetInput())
            if hasattr(prop, 'GetDisplayOffset'):
                duplicate.SetDisplayOffset(prop.GetDisplayOffset())
        return duplicate

    changed = []
    try:
        for original in list(window.GetRenderers()):
            if original.GetLayer() == 0 or not original.GetDraw():
                continue
            clone = vtkRenderer()
            clone.SetLayer(original.GetLayer())
            clone.SetViewport(original.GetViewport())
            clone.SetBackground(original.GetBackground())
            clone.SetPreserveColorBuffer(original.GetPreserveColorBuffer())
            clone.SetPreserveDepthBuffer(original.GetPreserveDepthBuffer())
            camera = vtkCamera()
            camera.DeepCopy(original.GetActiveCamera())
            clone.SetActiveCamera(camera)
            for prop in original.GetViewProps():
                # Billboard actors retain renderer-specific text geometry.
                # Use independent actors so capture cannot poison live caches.
                clone.AddViewProp(copy_prop(prop))
            for light in original.GetLights():
                clone.AddLight(light)
            changed.append((original, clone, original.GetViewport()))
            # Keep the widget's renderer attached: its native callbacks still
            # expect a window, but must not redraw/reframe the captured overlay.
            original.DrawOff()
            window.AddRenderer(clone)
        yield
    finally:
        for original, clone, viewport in reversed(changed):
            window.RemoveRenderer(clone)
            original.SetViewport(viewport)
            original.DrawOn()


@contextmanager
def scaled_annotations(window, scale):
    """Keep pixel-sized text and lines proportional in the tiled capture."""
    saved = []
    seen = set()

    def props(collection):
        for prop in collection:
            yield prop
            if prop.IsA('vtkPropAssembly'):
                yield from props(prop.GetParts())

    try:
        for renderer in window.GetRenderers():
            if not renderer.GetDraw():
                continue
            for prop in props(renderer.GetViewProps()):
                # VTK's 2-D text actors already account for the tile scale.
                # Billboard text in 3-D needs explicit pixel-size scaling.
                if prop.IsA('vtkBillboardTextActor3D'):
                    text = prop.GetTextProperty()
                    key = (id(text), 'FontSize')
                    if key not in seen:
                        seen.add(key)
                        size = text.GetFontSize()
                        saved.append((text, 'FontSize', size))
                        text.SetFontSize(size * scale)
                if hasattr(prop, 'GetProperty'):
                    material = prop.GetProperty()
                    for name in ('LineWidth', 'PointSize'):
                        if not hasattr(material, 'Get' + name):
                            continue
                        key = (id(material), name)
                        if key not in seen:
                            seen.add(key)
                            value = getattr(material, 'Get' + name)()
                            saved.append((material, name, value))
                            getattr(material, 'Set' + name)(value * scale)
        yield
    finally:
        for obj, name, value in reversed(saved):
            getattr(obj, 'Set' + name)(value)


def export_png(path, window, settings, *, mesh_items=(), progress=None):
    """Capture the live scene in tiles, smooth to exact pixels, and save atomically."""
    from PIL import Image
    from vtkmodules.vtkRenderingCore import vtkCamera, vtkWindowToImageFilter
    from vtkmodules.util.numpy_support import vtk_to_numpy

    scale = settings.capture_scale(window.GetSize())
    path = Path(path)
    tile_scale = window.GetTileScale()
    tile_viewport = window.GetTileViewport()
    cameras = []
    renderers = window.GetRenderers()
    renderers.InitTraversal()
    for _ in range(renderers.GetNumberOfItems()):
        renderer = renderers.GetNextItem()
        camera = renderer.GetActiveCamera()
        saved = vtkCamera()
        saved.DeepCopy(camera)
        cameras.append((camera, saved))

    def report(label, value=0., total=1.):
        if progress is not None:
            progress(label, value, total)

    temporary = None
    image = None
    try:
        with smooth_meshes(mesh_items, settings.supersample > 1), frozen_overlays(window), scaled_annotations(window, scale):
            report('Rendering high-resolution PNG')
            capture = vtkWindowToImageFilter()
            capture.SetInput(window)
            capture.SetInputBufferTypeToRGB()
            capture.SetScale(scale)
            capture.FixBoundaryOn()
            capture.ReadFrontBufferOff()
            capture.AddObserver('ProgressEvent', lambda obj, _: report('Rendering PNG', obj.GetProgress()))
            capture.Update()
            if capture.GetErrorCode():
                raise RuntimeError('The renderer could not capture the PNG image.')
            data = capture.GetOutput()
            width, height, _ = data.GetDimensions()
            if width < 1 or height < 1 or data.GetPointData().GetScalars() is None:
                raise RuntimeError('The renderer returned an empty image.')
            pixels = vtk_to_numpy(data.GetPointData().GetScalars()).reshape(height, width, 3)
            image = Image.fromarray(pixels[::-1].copy())
            if image.size != (settings.width, settings.height):
                report('Smoothing PNG edges')
                resized = image.resize((settings.width, settings.height), Image.Resampling.LANCZOS)
                image.close()
                image = resized
            report('Writing PNG')
            descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.lele-png-', suffix='.tmp')
            os.close(descriptor)
            temporary = Path(name)
            image.save(temporary, format='PNG', dpi=(300, 300))
            os.replace(temporary, path)
            report('PNG saved', 1.)
    finally:
        if image is not None:
            image.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        for camera, saved in cameras:
            camera.DeepCopy(saved)
        window.SetTileScale(tile_scale)
        window.SetTileViewport(tile_viewport)
        window.Render()
    return path
