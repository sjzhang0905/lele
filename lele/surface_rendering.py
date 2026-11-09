"""Multiple field surfaces, Cartesian scalar mapping and periodic instances."""
import numpy as np
from vtkmodules.vtkCommonDataModel import vtkImageData, vtkPolyData, vtkPlane
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkContourFilter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkColorTransferFunction
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from .field_mapping import sample_field, mapping_limits, validate_layer_mapping
from .output_text import check_load_cancelled
from .operations import ui_checkpoint


def color_lookup(palette, limits):
    lo,hi=limits
    lut=vtkColorTransferFunction();lut.SetColorSpaceToRGB();lut.SetNanColor(.55,.55,.55)
    if palette=='Viridis':
        from matplotlib import colormaps
        for t in np.linspace(0,1,65):lut.AddRGBPoint(lo+t*(hi-lo),*colormaps['viridis'](t)[:3])
    else:
        red=(.80,.08,.12);blue=(.08,.22,.80)
        low,high=(red,blue) if palette=='Red-white-blue' else (blue,red)
        lut.AddRGBPoint(lo,*low);lut.AddRGBPoint(0.,1.,1.,1.);lut.AddRGBPoint(hi,*high)
    lut.Build()
    return lut


def draw_fields(draw, active, fields, active_index):
    from .renderer import volume_surface_specs
    specs=volume_surface_specs(draw.options)
    numbers=([i+1 for i,s in enumerate(draw.options.volume_surfaces) if s.get('visible',True)]
             if draw.options.volume_surfaces else list(range(1,len(specs)+1)))
    groups={}
    for number,spec in zip(numbers,specs):
        index=spec.get('dataset',-1)
        if index<0:index=active_index
        if not 0<=index<len(fields):
            draw.field_warnings.append(f'Layer {number}: source field is unavailable.');continue
        spec={**spec,'_layer_number':number}
        groups.setdefault(index,[]).append(spec)
    for index,layers in groups.items():
        draw_volume(draw,fields[index],layers,fields)


def draw_volume(draw, volume, specs, fields=()):
    from .renderer import rgb
    data=np.pad(volume.data,((0,1),)*3,mode='wrap') if volume.periodic else volume.data
    grid=vtkImageData();grid.SetDimensions(*data.shape)
    values=numpy_to_vtk(np.ascontiguousarray(data.ravel(order='F')),deep=True)
    values.SetName('volume_field');grid.GetPointData().SetScalars(values)
    draw._keepalive.append((grid,values))
    matrix=vtkMatrix4x4()
    for i in range(3):
        for j in range(3):matrix.SetElement(i,j,float(volume.voxel_vectors[j,i]))
        matrix.SetElement(i,3,float(volume.origin[i]))
    transform=vtkTransform();transform.SetMatrix(matrix)
    tiles=[np.zeros(3)];boundary_clips=[]
    boundary=getattr(draw,'boundary_display',None)
    if boundary is not None:
        period=np.asarray(volume.data.shape)[:,None]*volume.voxel_vectors
        if np.allclose(period,draw.frame.cell,rtol=1e-6,atol=2e-4):
            if volume.periodic:
                from itertools import product
                inverse=np.linalg.inv(draw.frame.cell)
                fractional_origin=(volume.origin-draw.display_translation)@inverse
                # A translated periodic grid can straddle the displayed cell.
                # Cover it with neighboring instances, then clip to the requested
                # Boundary parallelepiped in Cartesian coordinates.
                offset=np.floor(fractional_origin+1e-8).astype(int)
                extra=(fractional_origin-offset>1e-8).astype(int)
                bounds=np.asarray(draw.options.boundary_bounds,dtype=int)
                ranges=[range(int(lo-off-e),int(hi-off)) for (lo,hi),off,e in zip(bounds,offset,extra)]
                tiles=[np.asarray(t)@draw.frame.cell for t in product(*ranges)]
                for axis,(lo,hi) in enumerate(bounds):
                    for edge,sign in ((lo,1.),(hi,-1.)):
                        plane=vtkPlane();plane.SetNormal(*(sign*inverse[:,axis]))
                        plane.SetOrigin(*(draw.display_translation+edge*draw.frame.cell[axis]))
                        boundary_clips.append(plane)
            else:
                # CUBE normally defines a cell-sized box without declaring
                # physical periodicity. Copy its existing mesh with the atoms;
                # do not invent wraparound values or clip away its original box.
                tiles=[np.asarray(t)@draw.frame.cell for t in boundary.tiles]
        elif volume.periodic:
            draw.field_warnings.append('Periodic grid period differs from the structure cell; field repetition is disabled.')
        elif boundary.tiles != ((0,0,0),):
            draw.field_warnings.append('Grid extent differs from the structure cell; field repetition is disabled.')
    if len(tiles)*len(specs)>512:
        draw.field_warnings.append('Too many surface copies (limit 512 per source field); reduce Boundary or layers.')
        return
    low,high=float(data.min()),float(data.max())
    for spec in specs:
        check_load_cancelled();validate_layer_mapping(spec)
        if not low<=spec['value']<=high or spec['opacity']==0:continue
        contour=vtkContourFilter();contour.SetInputData(grid);contour.SetValue(0,spec['value'])
        contour.AddObserver('ProgressEvent',lambda a,_:ui_checkpoint('Computing isosurface',a.GetProgress(),1))
        contour.Update()
        transformed=vtkTransformPolyDataFilter();transformed.SetInputConnection(contour.GetOutputPort())
        transformed.SetTransform(transform);transformed.Update()
        poly=transformed.GetOutput()
        if not poly.GetNumberOfPoints():continue
        if poly.GetNumberOfPoints()*len(tiles)>20_000_000:
            draw.field_warnings.append('Surface exceeds 20 million displayed vertices; reduce Boundary or layers.');continue
        map_index=spec.get('map_dataset',-1);mapped=map_index>=0
        samples=[];lut=None;limits=None
        if mapped:
            if map_index>=len(fields):
                draw.field_warnings.append('Color field is unavailable; mapped layer omitted.');continue
            points=vtk_to_numpy(poly.GetPoints().GetData())
            try:
                # Sample every displayed location, including nonperiodic color
                # fields. Periodic color fields wrap in their own grid basis.
                color_field=fields[map_index]
                # Finite CUBE instances copy the source surface and its colors
                # together. Sampling a translated copy in the unshifted finite
                # color box would incorrectly turn it gray/out of range.
                repeat_colors=(not volume.periodic or (color_field.periodic and
                    np.allclose(np.asarray(color_field.data.shape)[:,None]*color_field.voxel_vectors,
                                np.asarray(volume.data.shape)[:,None]*volume.voxel_vectors,atol=2e-4,rtol=1e-6)))
                for shift in tiles:
                    samples.append(samples[0] if samples and repeat_colors else
                                   sample_field(color_field,points+shift if volume.periodic else points,
                                                progress=ui_checkpoint))
                joined=np.concatenate(samples);finite=np.isfinite(joined)
                limits=mapping_limits(spec,joined)
                lut=color_lookup(spec.get('map_palette','Red-white-blue'),limits)
                if not finite.all():
                    draw.field_warnings.append(f'Layer {spec.get("_layer_number",1)}: {np.count_nonzero(~finite):,}/{len(finite):,} vertices outside color grid or non-finite; shown gray.')
            except ValueError as exc:
                draw.field_warnings.append(str(exc)+' Mapped layer omitted.');continue
        for tile,shift in enumerate(tiles):
            ui_checkpoint('Drawing surface copies',tile,len(tiles))
            tile_poly=poly;tile_filter=transformed
            if np.any(shift):
                translation=vtkTransform();translation.Translate(*shift)
                tile_filter=vtkTransformPolyDataFilter();tile_filter.SetInputData(poly)
                tile_filter.SetTransform(translation);tile_filter.Update()
                tile_poly=tile_filter.GetOutput()
                draw._keepalive.append((tile_filter,translation))
            if mapped:
                colored=vtkPolyData();colored.ShallowCopy(tile_poly)
                scalars=numpy_to_vtk(samples[tile],deep=True);scalars.SetName('surface_color_field')
                colored.GetPointData().SetScalars(scalars)
                mapper=vtkPolyDataMapper();mapper.SetInputData(colored)
                mapper.SetLookupTable(lut);mapper.SetScalarRange(*limits)
                mapper.SetColorModeToMapScalars();mapper.SetScalarModeToUsePointData()
                mapper.InterpolateScalarsBeforeMappingOn();mapper.ScalarVisibilityOn()
                draw._keepalive.append((colored,scalars,lut))
            else:
                mapper=vtkPolyDataMapper();mapper.SetInputConnection(tile_filter.GetOutputPort())
                mapper.ScalarVisibilityOff()
            actor=vtkActor();actor.SetMapper(mapper)
            # VTK accepts at most six mapper clipping planes. Crystal cuts
            # also consume that budget, so combine via geometry clipping when
            # both systems are active (handled below).
            clips=boundary_clips+list(getattr(draw,'_vtk_clip_planes',[]))
            if len(clips)>6:
                from vtkmodules.vtkFiltersCore import vtkClipPolyData
                mapper.Update();clipped=mapper.GetInput()
                for plane in boundary_clips:
                    cutter=vtkClipPolyData();cutter.SetInputData(clipped);cutter.SetClipFunction(plane);cutter.Update()
                    clipped=cutter.GetOutput();draw._keepalive.append(cutter)
                mapper.SetInputData(clipped)
            else:
                for plane in boundary_clips:mapper.AddClippingPlane(plane)
            prop=actor.GetProperty()
            # Uniform layer colors also set VTK's specular color. A mapped
            # surface needs neutral material, or highlights tint the ESP scale.
            prop.SetColor((1.,1.,1.) if mapped else rgb(spec['color']))
            prop.SetOpacity(spec['opacity']);prop.SetSpecular(.25)
            if spec['style']=='Wireframe':prop.SetRepresentationToWireframe()
            elif spec['style']=='Points':prop.SetRepresentationToPoints()
            width=max(.1,float(draw.options.volume_line_width))
            prop.SetLineWidth(width);prop.SetPointSize(max(1.,width*2))
            if draw.options.volume_smooth_normals:prop.SetInterpolationToGouraud()
            else:prop.SetInterpolationToFlat()
            draw._add_actor(actor);draw.field_actors.append(actor)
            # Preserve the contour resource tuple used by PNG mesh export.
            draw._keepalive.append((contour,mapper,transformed,transform))
        if mapped and spec.get('map_legend',True):
            if len(draw.field_scalar_bars)>=4:
                draw.field_warnings.append('Only the first four color scales are shown; disable extra legends in layer settings.')
                continue
            source=fields[map_index]
            bar=vtkScalarBarActor();bar.SetLookupTable(lut);bar.SetOrientationToHorizontal()
            bar.SetTitle(f'Layer {spec.get("_layer_number",1)}: {source.label or "Color field"} [{source.unit or "source units"}]')
            bar.SetNumberOfLabels(5);bar.SetLabelFormat('%.3g')
            bar.SetPosition(.12,.02+len(draw.field_scalar_bars)*.09);bar.SetWidth(.76);bar.SetHeight(.08)
            bar.SetUnconstrainedFontSize(True)
            light=np.mean(rgb(draw.options.background))>.5
            for text in (bar.GetTitleTextProperty(),bar.GetLabelTextProperty()):
                text.SetColor((.1,.1,.1) if light else (.95,.95,.95))
                text.SetFontSize(12);text.BoldOff();text.ItalicOff();text.ShadowOff()
            bar.PickableOff();bar.UseBoundsOff()
            draw.renderer.AddViewProp(bar);draw.dynamic.append(bar);draw.field_scalar_bars.append(bar)
            draw._keepalive.append((bar,lut))
