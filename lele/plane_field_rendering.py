"""Native VTK sampling, filled colors and contours on arbitrary display planes."""
import numpy as np
from vtkmodules.vtkCommonCore import vtkLookupTable
from vtkmodules.vtkCommonDataModel import vtkPlane, vtkPolyData
from vtkmodules.vtkCommonExecutionModel import vtkAlgorithm
from vtkmodules.vtkFiltersCore import vtkClipPolyData, vtkContourFilter
from vtkmodules.vtkFiltersSources import vtkPlaneSource
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from .field_mapping import sample_field
from .plane_field import (plane_grid, field_covered_polygon, plane_color_limits,
                          validate_plane_style)
from .operations import ui_checkpoint


def sampled_plane_mesh(volume, polygon, normal, resolution=256):
    """Clip to the true convex plane boundary, then sample every mesh vertex."""
    polygon=field_covered_polygon(polygon,volume)
    if len(polygon)<3:return None,False
    origin,u,v,count,reduced=plane_grid(polygon,normal,volume,resolution)
    source=vtkPlaneSource();source.SetOutputPointsPrecision(vtkAlgorithm.DOUBLE_PRECISION)
    source.SetOrigin(*origin);source.SetPoint1(*(origin+u));source.SetPoint2(*(origin+v))
    source.SetXResolution(count[0]-1);source.SetYResolution(count[1]-1);source.Update()
    mesh=source.GetOutput();center=polygon.mean(axis=0)
    normal=np.array(normal,float,copy=True);normal/=np.linalg.norm(normal)
    for i,p in enumerate(polygon):
        edge=polygon[(i+1)%len(polygon)]-p
        inward=np.cross(normal,edge)
        if np.dot(center-p,inward)<0:inward=-inward
        if np.linalg.norm(inward)<1e-12:continue
        plane=vtkPlane();plane.SetOrigin(*p);plane.SetNormal(*inward)
        clip=vtkClipPolyData();clip.SetInputData(mesh);clip.SetClipFunction(plane);clip.Update()
        output=vtkPolyData();output.ShallowCopy(clip.GetOutput());mesh=output
    if not mesh.GetNumberOfPoints():return None,reduced
    points=vtk_to_numpy(mesh.GetPoints().GetData())
    values=sample_field(volume,points,progress=ui_checkpoint)
    if not np.isfinite(values).all():raise ValueError('Slice contains non-finite or uncovered grid samples.')
    scalars=numpy_to_vtk(values,deep=True);scalars.SetName('plane_field_value')
    mesh.GetPointData().SetScalars(scalars)
    return mesh,reduced


def slice_lookup(palette,limits):
    from matplotlib import colormaps
    lut=vtkLookupTable();lut.SetNumberOfTableValues(257);lut.SetRange(*limits)
    cmap=colormaps['viridis' if palette=='Viridis' else 'RdBu_r']
    # Diverging zero stays white even for asymmetric fixed ranges.
    lo,hi=limits
    for i,value in enumerate(np.linspace(lo,hi,257)):
        if palette=='Blue-white-red' and lo<0<hi:
            t=.5+.5*value/(hi if value>=0 else -lo)
        else:t=i/256
        lut.SetTableValue(i,*cmap(t))
    lut.Build();return lut


def draw_plane_slice(draw,polygon,normal,style,title):
    """Return the colored plane actor; geometry-only fallback belongs to caller."""
    style=validate_plane_style(style);volume=draw.volume
    if volume is None or not style['field']:return None
    key=(id(volume.data),tuple(volume.origin),tuple(volume.voxel_vectors.ravel()),
         tuple(np.asarray(polygon).ravel()),tuple(normal),style['field_resolution'],volume.periodic)
    cache=getattr(draw,'_plane_field_cache',{})
    try:
        if key in cache:_,mesh,reduced=cache[key]
        else:
            mesh,reduced=sampled_plane_mesh(volume,polygon,normal,style['field_resolution'])
            new_size=mesh.GetNumberOfPoints() if mesh is not None else 0
            while cache and (len(cache)>=8 or new_size+sum(
                    item[1].GetNumberOfPoints() if item[1] is not None else 0
                    for item in cache.values())>1_100_000):
                cache.pop(next(iter(cache)))
            cache[key]=(volume.data,mesh,reduced);draw._plane_field_cache=cache
        if mesh is None:
            draw.field_warnings.append(f'{title}: plane does not intersect the finite field grid.');return None
        values=vtk_to_numpy(mesh.GetPointData().GetScalars())
        palette,limits=plane_color_limits(volume,values,style)
    except (ValueError,np.linalg.LinAlgError) as exc:
        draw.field_warnings.append(f'{title}: {exc}');return None
    lut=slice_lookup(palette,limits)
    mapper=vtkPolyDataMapper();mapper.SetInputData(mesh);mapper.SetLookupTable(lut);mapper.SetScalarRange(*limits)
    mapper.SetColorModeToMapScalars();mapper.SetScalarModeToUsePointData();mapper.InterpolateScalarsBeforeMappingOn()
    actor=vtkActor();actor.SetMapper(mapper);actor.PickableOff()
    actor.GetProperty().SetOpacity(style['opacity']);actor.GetProperty().LightingOff()
    draw._add_actor(actor);draw.plane_field_actors.append(actor)
    draw._keepalive.append((mesh,mapper,lut))
    if reduced:
        draw.field_warnings.append(f'{title}: slice sampling limited to {style["field_resolution"]} points per axis; increase Slice resolution for finer features.')
    if style['field_contours'] and float(values.min())<float(values.max()):
        contour=vtkContourFilter();contour.SetInputData(mesh)
        for i,value in enumerate(np.linspace(*limits,9)[1:-1]):contour.SetValue(i,float(value))
        contour.Update()
        lines=vtkPolyDataMapper();lines.SetInputConnection(contour.GetOutputPort());lines.ScalarVisibilityOff()
        outline=vtkActor();outline.SetMapper(lines);outline.PickableOff()
        outline.SetPosition(*(np.asarray(normal)/np.linalg.norm(normal)*1e-5))
        outline.GetProperty().SetColor(.10,.10,.10);outline.GetProperty().SetLineWidth(1.)
        outline.GetProperty().SetOpacity(style['opacity']);outline.GetProperty().LightingOff()
        draw._add_actor(outline);draw.plane_contour_actors.append(outline)
        draw._keepalive.append((contour,lines))
    if style['field_legend'] and style['opacity']>0:
        existing=len(draw.field_scalar_bars)+len(draw.plane_field_bars)
        if existing<4:
            bar=vtkScalarBarActor();bar.SetLookupTable(lut);bar.SetOrientationToHorizontal()
            bar.SetTitle(f'{title}: {volume.label or "Field"} [{volume.unit or "source units"}]')
            bar.SetNumberOfLabels(5);bar.SetLabelFormat('%.3g')
            bar.SetPosition(.12,.02+existing*.09);bar.SetWidth(.76);bar.SetHeight(.08)
            bar.SetUnconstrainedFontSize(True)
            from .renderer import rgb
            light=np.mean(rgb(draw.options.background))>.5
            for text in (bar.GetTitleTextProperty(),bar.GetLabelTextProperty()):
                text.SetColor((.1,.1,.1) if light else (.95,.95,.95));text.SetFontSize(12)
                text.BoldOff();text.ItalicOff();text.ShadowOff()
            bar.PickableOff();bar.UseBoundsOff();draw.renderer.AddViewProp(bar)
            draw.dynamic.append(bar);draw.plane_field_bars.append(bar);draw._keepalive.append(bar)
        else:draw.field_warnings.append('Only the first four field color scales are shown.')
    return actor
