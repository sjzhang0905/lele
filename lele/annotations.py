"""World-space text annotations and their VTK presentation.

Annotation positions are in Angstrom. Free text has a user-defined 3D
orientation. ESP values have a world-space anchor and face the screen.
"""
from dataclasses import dataclass, field

FONT_PIXELS = 128
import math
import re
import numpy as np

EXTREMUM_RADIUS = .08
EXTREMUM_GOLD = (212 / 255, 175 / 255, 55 / 255)


@dataclass
class TextAnnotation:
    text: str
    position: list = field(default_factory=lambda: [0., 0., 0.])
    rotation: list = field(default_factory=lambda: np.eye(3).tolist())
    height: float = .5
    color: str = '#202020'
    font_file: str = ''
    bold: bool = False

    def __post_init__(self):
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 10000:
            raise ValueError('Text must contain between 1 and 10000 characters.')
        position = np.asarray(self.position, float)
        rotation = np.asarray(self.rotation, float)
        if position.shape != (3,) or not np.isfinite(position).all():
            raise ValueError('Text position must be a finite 3D vector.')
        if (rotation.shape != (3, 3) or not np.isfinite(rotation).all()
                or not np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-6)
                or not np.isclose(np.linalg.det(rotation), 1., atol=1e-6)):
            raise ValueError('Text orientation must be a proper rotation.')
        if not math.isfinite(self.height) or not .001 <= self.height <= 1000.:
            raise ValueError('Text size must be between 0.001 and 1000 Angstrom.')
        if not isinstance(self.color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', self.color):
            raise ValueError('Text color must be an RGB hex color.')
        if not isinstance(self.font_file, str):
            raise ValueError('Invalid text font file.')
        self.position = position.tolist()
        self.rotation = rotation.tolist()
        self.height = float(self.height)
        self.bold = bool(self.bold)


@dataclass
class EspExtremum(TextAnnotation):
    """One fixed data point and its independently positioned energy label."""
    point: list = field(default_factory=lambda: [0., 0., 0.])
    value: float = 0.

    def __post_init__(self):
        point = np.asarray(self.point, float)
        if point.shape != (3,) or not np.isfinite(point).all() or not math.isfinite(self.value):
            raise ValueError('An ESP extremum requires three finite coordinates and a finite value.')
        self.point = point.tolist()
        self.value = float(self.value)
        self.text = f'{self.value:.1f}'
        super().__post_init__()


def extremum_display_transform(volume, drawing):
    """Row-vector transform from original file coordinates to the displayed field."""
    rotation = drawing.display_rotation
    translation = drawing.display_translation
    if volume is not None and not (np.array_equal(volume.origin, volume.reference_origin)
                                    and np.array_equal(volume.voxel_vectors, volume.reference_voxel_vectors)):
        from .field_mapping import field_transform
        field_rotation, shift = field_transform(volume)
        return field_rotation @ rotation, shift @ rotation + translation
    return rotation, translation


def transform_annotation(annotation, *, translation=None, rotation=None):
    """Translate or rotate about the annotation's own central anchor."""
    if translation is not None:
        offset = np.asarray(translation, float)
        if offset.shape != (3,) or not np.isfinite(offset).all():
            raise ValueError('Invalid text translation.')
        annotation.position = (np.asarray(annotation.position) + offset).tolist()
    if rotation is not None:
        matrix = np.asarray(rotation, float)
        if (matrix.shape != (3, 3) or not np.allclose(matrix @ matrix.T, np.eye(3), atol=1e-6)
                or not np.isclose(np.linalg.det(matrix), 1., atol=1e-6)):
            raise ValueError('Invalid text rotation.')
        annotation.rotation = (matrix @ np.asarray(annotation.rotation)).tolist()


class AnnotationRenderer:
    """Small independent actor collection; geometry edits do not rebuild text."""
    def __init__(self, scene):
        self.scene = scene
        self.actors = []
        self.annotations = []
        self.outline = None
        self.selected = None
        self.markers = None
        self._facing_actors = []
        self._view_orientation = None
        self._camera_observer = None

    def clear(self):
        if self._camera_observer is not None:
            self.scene.RemoveObserver(self._camera_observer)
            self._camera_observer = None
        self._facing_actors.clear()
        self._view_orientation = None
        for actor in self.actors:
            self.scene.RemoveViewProp(actor)
        self.actors = []
        if self.markers is not None:
            self.scene.RemoveViewProp(self.markers)
            self.markers = None
        if self.outline is not None:
            self.scene.RemoveViewProp(self.outline)
        self.outline = None

    def set_annotations(self, annotations, selected=None, extremum_transform=None):
        from pathlib import Path
        from vtkmodules.vtkRenderingCore import vtkTextActor3D
        import vtkmodules.vtkRenderingFreeType  # register text renderer
        self.clear()
        self.annotations = annotations
        self.selected = selected
        self.extremum_rotation, self.extremum_shift = (
            extremum_transform if extremum_transform is not None else (np.eye(3), np.zeros(3)))
        points = []
        for annotation in annotations:
            annotation.__post_init__()
            actor = vtkTextActor3D()
            if isinstance(annotation, EspExtremum):
                points.append(annotation.point)
                self._facing_actors.append(actor)
            actor.SetInput(annotation.text)
            prop = actor.GetTextProperty()
            prop.SetFontSize(FONT_PIXELS)
            prop.SetFontFamilyToArial()
            if annotation.font_file and Path(annotation.font_file).is_file():
                prop.SetFontFamily(4)  # VTK_FONT_FILE
                prop.SetFontFile(annotation.font_file)
            prop.SetBold(annotation.bold)
            prop.SetColor(*[int(annotation.color[i:i+2], 16) / 255. for i in (1, 3, 5)])
            prop.SetJustificationToCentered()
            prop.SetVerticalJustificationToCentered()
            actor.PickableOn()
            self.actors.append(actor)
            self.scene.AddActor(actor)
            self.update_transform(len(self.actors)-1)
        if points:
            self._add_markers(np.asarray(points) @ self.extremum_rotation + self.extremum_shift)
            self._camera_observer = self.scene.AddObserver('StartEvent', self._face_camera)
            self._face_camera()
        self._update_outline()

    def _face_camera(self, *_):
        if not self._facing_actors:
            return
        from vtkmodules.vtkCommonMath import vtkMatrix4x4
        from vtkmodules.vtkCommonTransforms import vtkTransform
        # The inverse view maps screen right and up to world directions, including camera roll.
        view_to_world = vtkMatrix4x4()
        vtkMatrix4x4.Invert(self.scene.GetActiveCamera().GetViewTransformMatrix(), view_to_world)
        orientation = [0., 0., 0.]
        vtkTransform.GetOrientation(orientation, view_to_world)
        if orientation == self._view_orientation:
            return
        self._view_orientation = orientation
        for actor in self._facing_actors:
            actor.SetOrientation(orientation)
        if self.outline is not None:
            self._update_outline()

    def _add_markers(self, locations):
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkPolyData
        from vtkmodules.vtkFiltersSources import vtkSphereSource
        from vtkmodules.vtkRenderingCore import vtkActor, vtkGlyph3DMapper
        from vtkmodules.util.numpy_support import numpy_to_vtk
        points = vtkPoints()
        points.SetData(numpy_to_vtk(np.ascontiguousarray(locations), deep=True))
        sites = vtkPolyData()
        sites.SetPoints(points)
        sphere = vtkSphereSource()
        sphere.SetRadius(EXTREMUM_RADIUS)
        sphere.SetThetaResolution(24)
        sphere.SetPhiResolution(16)
        mapper = vtkGlyph3DMapper()
        mapper.SetSourceConnection(sphere.GetOutputPort())
        mapper.SetInputData(sites)
        mapper.ScalingOff()
        mapper.ScalarVisibilityOff()
        actor = vtkActor()
        actor.SetMapper(mapper)
        gold = actor.GetProperty()
        gold.SetColor(*EXTREMUM_GOLD)
        gold.SetAmbient(.22)
        gold.SetDiffuse(.50)
        gold.SetSpecular(.50)
        gold.SetSpecularPower(34.)
        actor.PickableOff()
        self.scene.AddActor(actor)
        self.markers = actor

    def update_transform(self, index):
        from vtkmodules.vtkCommonMath import vtkMatrix4x4
        annotation = self.annotations[index]
        matrix = vtkMatrix4x4()
        rotation = np.asarray(annotation.rotation)
        position = np.asarray(annotation.position)
        if isinstance(annotation, EspExtremum):
            position = position @ self.extremum_rotation + self.extremum_shift
            # The camera controls the actor's local orientation. The user matrix
            # contains only the anchor and physical size, also during tiled export.
            rotation = np.eye(3)
        # Fixed font raster size with a world-space scale: output resolution
        # comes from the scene exporter, position and orientation stay exact.
        for i in range(3):
            for j in range(3):
                matrix.SetElement(i, j, float(rotation[i, j]) * annotation.height / FONT_PIXELS)
            matrix.SetElement(i, 3, position[i])
        self.actors[index].SetUserMatrix(matrix)
        if self.selected == index:
            self._update_outline()

    def corners(self, index):
        bounds = [0, 0, 0, 0]
        self.actors[index].GetBoundingBox(bounds)
        x0, x1, y0, y1 = bounds
        local = np.array([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], float)
        matrix = self.actors[index].GetMatrix()
        return np.array([matrix.MultiplyPoint((*point, 1.))[:3] for point in local])

    def _update_outline(self):
        from vtkmodules.vtkCommonCore import vtkPoints
        from vtkmodules.vtkCommonDataModel import vtkPolyData, vtkCellArray
        from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper
        if self.selected is None or not 0 <= self.selected < len(self.actors):
            if self.outline is not None:
                self.scene.RemoveViewProp(self.outline)
                self.outline = None
            return
        if self.outline is not None:
            points = self.outline.GetMapper().GetInput().GetPoints()
            for i, point in enumerate(self.corners(self.selected)):
                points.SetPoint(i, *point)
            points.Modified()
            return
        points = vtkPoints()
        for point in self.corners(self.selected):
            points.InsertNextPoint(*point)
        lines = vtkCellArray()
        lines.InsertNextCell(5)
        for i in (0, 1, 2, 3, 0):
            lines.InsertCellPoint(i)
        data = vtkPolyData();data.SetPoints(points);data.SetLines(lines)
        mapper = vtkPolyDataMapper();mapper.SetInputData(data)
        actor = vtkActor();actor.SetMapper(mapper)
        actor.GetProperty().SetColor(.05, .65, .25)
        actor.GetProperty().SetLineWidth(2.5)
        actor.GetProperty().LightingOff()
        actor.PickableOff()
        self.scene.AddActor(actor)
        self.outline = actor

    def pick(self, x, y):
        """Hit-test the projected text rectangles, including spaces in text."""
        self._face_camera()
        hits = []
        for index in range(len(self.actors)):
            corners = []
            for point in self.corners(index):
                self.scene.SetWorldPoint(*point, 1.)
                self.scene.WorldToDisplay()
                corners.append(self.scene.GetDisplayPoint())
            q = np.asarray(corners)
            if not np.isfinite(q).all() or np.any(q[:, 2] < 0) or np.all(q[:, 2] > 1):
                continue
            # Cross products have the same sign inside a convex quadrilateral.
            edges = np.roll(q[:, :2], -1, axis=0) - q[:, :2]
            rel = np.array([x, y]) - q[:, :2]
            cross = edges[:, 0] * rel[:, 1] - edges[:, 1] * rel[:, 0]
            area = abs(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - q[:, 1] * np.roll(q[:, 0], -1)))
            if area > 1. and (np.all(cross >= -1e-6) or np.all(cross <= 1e-6)):
                hits.append((float(np.mean(q[:, 2])), index))
        return min(hits)[1] if hits else None
