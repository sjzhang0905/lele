"""Multiple field surfaces, Cartesian scalar mapping and periodic instances."""
import numpy as np
from vtkmodules.vtkCommonDataModel import vtkImageData, vtkPolyData, vtkPlane
from vtkmodules.vtkCommonMath import vtkMatrix4x4
from vtkmodules.vtkCommonTransforms import vtkTransform
from vtkmodules.vtkFiltersCore import vtkContourFilter
from vtkmodules.vtkFiltersGeneral import vtkTransformPolyDataFilter
from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, vtkColorTransferFunction
from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
from .field_legend import field_legend
from .field_mapping import sample_field, mapping_limits, validate_layer_mapping, DEFAULT_PALETTE, legend_unit
from .output_text import check_load_cancelled
from .operations import ui_checkpoint


def color_lookup(palette, limits):
    lo,hi=limits
    lut=vtkColorTransferFunction();lut.SetColorSpaceToRGB();lut.SetNanColor(.55,.55,.55)
    if palette=='Viridis':
        from matplotlib import colormaps
        for t in np.linspace(0,1,65):lut.AddRGBPoint(lo+t*(hi-lo),*colormaps['viridis'](t)[:3])
    elif palette.startswith('VMD '):
        # VMD Scene.C: RWB/BWR endpoints are pure primaries, scale midpoint .5.
        red=(1.,0.,0.);blue=(0.,0.,1.)
        low,high=(red,blue) if palette=='VMD RWB' else (blue,red)
        lut.AddRGBPoint(lo,*low);lut.AddRGBPoint((lo+hi)/2,1.,1.,1.);lut.AddRGBPoint(hi,*high)
    else:
        red=(.80,.08,.12);blue=(.08,.22,.80)
        low,high=(red,blue) if palette=='Red-white-blue' else (blue,red)
        lut.AddRGBPoint(lo,*low);lut.AddRGBPoint(0.,1.,1.,1.);lut.AddRGBPoint(hi,*high)
    lut.Build()
    return lut


def update_mapping_colors(draw, previous, layers):
    """Recolor existing meshes for slider edits; return False for geometry edits.

    Avoid contour extraction and field interpolation on every slider event.
    Existing actor scalars and original color-grid data remain authoritative.
    """
    if not previous or len(previous)!=len(layers):return False
    color_keys={'map_palette','map_range'}
    for before,after in zip(previous,layers):
        if {k:v for k,v in before.items() if k not in color_keys}!={k:v for k,v in after.items() if k not in color_keys}:
            return False
    updates=[];lookups={};groups={}
    for actor in draw.field_actors:
        number=getattr(actor,'_lele_layer_number',None)
        if number is None:return False
        spec=layers[number-1]
        if spec.get('map_dataset',-1)<0:continue
        samples=getattr(actor,'_lele_mapping_values',None)
        color_field=getattr(actor,'_lele_mapping_field',None)
        if samples is None or color_field is None:return False
        groups.setdefault(number,[]).append((actor.GetMapper(),samples,color_field))
    for number,records in groups.items():
        spec=layers[number-1]
        # A nonperiodic color grid can assign different values to each periodic
        # surface copy; legacy auto ranges must include all copies, just as the
        # initial renderer does. Explicit slider ranges need no concatenation.
        samples=(np.concatenate([record[1] for record in records])
                 if spec.get('map_range') is None else records[0][1])
        limits=mapping_limits(spec,samples,records[0][2].data)
        lut=color_lookup(spec.get('map_palette',DEFAULT_PALETTE),limits)
        lookups[number]=(lut,limits)
        updates.extend((mapper,lut,limits) for mapper,_,_ in records)
    for mapper,lut,limits in updates:
        mapper.SetLookupTable(lut);mapper.SetScalarRange(*limits)
    for bar in draw.field_scalar_bars:
        number=getattr(bar,'_lele_layer_number',None)
        if number in lookups:bar.SetLookupTable(lookups[number][0])
    return True


def draw_fields(draw, active, fields, active_index):
    # None suppresses every layer while leaving the fields available to slices.
    if draw.options.volume_signs == 'None':return
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
    visible = {(id(fields[i].data), fields[i].periodic) for i in groups}
    draw._scalar_grids = {k: v for k, v in draw._scalar_grids.items() if k in visible}
    for index,layers in groups.items():
        draw_volume(draw,fields[index],layers,fields)


def _grid_signature(data):
    # Arrays also have public, mutable NumPy views. Key cached meshes by the
    # actual scalar contents so an in-place edit cannot leave a stale surface.
    from hashlib import sha256
    if data.flags.c_contiguous or data.flags.f_contiguous:
        return sha256(data.ravel(order='K').view(np.uint8)).digest()
    digest = sha256()
    for block in np.nditer(data, flags=['external_loop', 'buffered', 'zerosize_ok'],
                           op_flags=['readonly', 'contig'], order='K', buffersize=262144):
        digest.update(block.view(np.uint8))
    return digest.digest()


def _prepared_grid(draw, volume):
    source = volume.data
    key = (id(source), volume.periodic)
    signature = _grid_signature(source)
    cached = draw._scalar_grids.get(key)
    if cached is not None and cached[0] is source and cached[1] == signature and cached[2] == source.shape:
        return cached[3:]
    if volume.periodic:
        ordered = np.empty(tuple(n+1 for n in source.shape), dtype=source.dtype, order='F')
        ordered[:-1, :-1, :-1] = source
        ordered[-1, :-1, :-1] = source[0]
        ordered[:, -1, :-1] = ordered[:, 0, :-1]
        ordered[:, :, -1] = ordered[:, :, 0]
    else:
        ordered = np.asfortranarray(source)
    grid = vtkImageData()
    grid.SetDimensions(*ordered.shape)
    values = numpy_to_vtk(ordered.ravel(order='F'), deep=False)
    values.SetName('volume_field')
    grid.GetPointData().SetScalars(values)
    limits = float(source.min()), float(source.max())
    item = (source, signature, source.shape, grid, values, ordered, limits, {})
    draw._scalar_grids[key] = item
    return item[3:]


def draw_volume(draw, volume, specs, fields=()):
    from .renderer import rgb
    if not specs or draw.options.volume_signs == 'None':return
    grid, values, buffer, limits, contours = _prepared_grid(draw, volume)
    draw._keepalive.append((grid, values, buffer))
    active_levels = {spec['value'] for spec in specs if spec['opacity']}
    for level in tuple(contours):
        if level not in active_levels:
            del contours[level]
    matrix=vtkMatrix4x4()
    for i in range(3):
        for j in range(3):matrix.SetElement(i,j,float(volume.voxel_vectors[j,i]))
        matrix.SetElement(i,3,float(volume.origin[i]))
    transform=vtkTransform();transform.SetMatrix(matrix)
    tiles=[np.zeros(3)];boundary_clips=[]
    boundary=getattr(draw,'boundary_display',None)
    if boundary is not None:
        from .cell_origin import cell_origin
        from .periodic_geometry import full_cell
        box_origin=(cell_origin(draw.frame) if draw.options.boundary_preserve_origin else np.zeros(3))
        intervals = np.asarray(volume.data.shape)
        if volume.provenance.get('grid_extent') == 'first_to_last_sample':
            intervals = intervals - 1
        extent = intervals[:, None] * volume.voxel_vectors
        same_box = np.allclose(extent, draw.frame.cell, rtol=1e-6, atol=2e-4)
        if same_box and (not volume.periodic or full_cell(draw.frame.cell)):
            if volume.periodic:
                from itertools import product
                inverse=np.linalg.inv(draw.frame.cell)
                fractional_origin=(volume.origin-draw.display_translation-box_origin)@inverse
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
                        plane.SetOrigin(*(draw.display_translation+box_origin+edge*draw.frame.cell[axis]))
                        boundary_clips.append(plane)
            else:
                # Repeat the existing finite box with the displayed cells.
                # Values at opposite faces may differ.
                tiles=[np.asarray(t)@draw.frame.cell for t in boundary.tiles]
        elif volume.periodic and same_box:
            draw.field_warnings.append('Periodic grid repetition requires a full cell.')
        elif volume.periodic:
            draw.field_warnings.append('Periodic grid period differs from the structure cell; field repetition is disabled.')
        elif boundary.tiles != ((0,0,0),):
            draw.field_warnings.append('Grid extent differs from the structure cell; field repetition is disabled.')
    if len(tiles)*len(specs)>512:
        draw.field_warnings.append('Too many surface copies (limit 512 per source field); reduce Boundary or layers.')
        return
    low,high=limits
    for spec in specs:
        check_load_cancelled();validate_layer_mapping(spec)
        if not low<=spec['value']<=high:
            draw.field_warnings.append(f'Layer {spec.get("_layer_number",1)}: isovalue {spec["value"]:.6g} '
                                       f'is outside source range [{low:.6g}, {high:.6g}]; no surface.')
            continue
        if spec['opacity']==0:continue
        level = spec['value']
        contour = contours.get(level)
        if contour is None:
            contour = vtkContourFilter()
            contour.SetInputData(grid)
            contour.SetValue(0, level)
            contour.AddObserver('ProgressEvent', lambda a, _: ui_checkpoint('Computing isosurface', a.GetProgress(), 1))
            contour.Update()
            contours[level] = contour
        transformed=vtkTransformPolyDataFilter();transformed.SetInputConnection(contour.GetOutputPort())
        transformed.SetTransform(transform);transformed.Update()
        poly=transformed.GetOutput()
        if not poly.GetNumberOfPoints():
            draw.field_warnings.append(f'Layer {spec.get("_layer_number",1)}: no surface at isovalue {spec["value"]:.6g}.')
            continue
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
                limits=mapping_limits(spec,joined,color_field.data)
                lut=color_lookup(spec.get('map_palette',DEFAULT_PALETTE),limits)
                if not finite.all():
                    draw.field_warnings.append(f'Layer {spec.get("_layer_number",1)}: {np.count_nonzero(~finite):,}/{len(finite):,} vertices outside color grid or non-finite; shown gray.')
            except ValueError as exc:
                draw.field_warnings.append(str(exc)+' Mapped layer omitted.');continue
        layer_actor_count=len(draw.field_actors)
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
            regions=getattr(draw.options,'volume_hidden_regions',[])
            if regions:
                # Subtract after placing each Boundary instance. Thus a box
                # hides only the copies that were actually under that box.
                from .surface_erase import hide_polydata
                mapper.Update()
                clipped,resources=hide_polydata(mapper.GetInput(),regions,
                    rotation=draw.display_rotation,translation=draw.display_translation)
                draw._keepalive.extend(resources)
                if not clipped.GetNumberOfCells():continue
                mapper.SetInputData(clipped)
            actor=vtkActor();actor.SetMapper(mapper)
            actor._lele_layer_number=spec.get('_layer_number',1)
            if mapped:
                actor._lele_mapping_values=samples[tile]
                actor._lele_mapping_field=color_field
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
            # Mapped fields get their diffuse color from the lookup table.
            # _finish supplies neutral specular reflections for both paths.
            prop.SetColor((1.,1.,1.) if mapped else rgb(spec['color']))
            prop.SetOpacity(spec['opacity']);draw._finish(prop)
            if spec['style']=='Wireframe':prop.SetRepresentationToWireframe()
            elif spec['style']=='Points':prop.SetRepresentationToPoints()
            width=max(.1,float(draw.options.volume_line_width))
            prop.SetLineWidth(width);prop.SetPointSize(max(1.,width*2))
            if draw.options.volume_smooth_normals:prop.SetInterpolationToGouraud()
            else:prop.SetInterpolationToFlat()
            draw._add_actor(actor);draw.field_actors.append(actor)
            # Preserve the contour resource tuple used by PNG mesh export.
            draw._keepalive.append((contour,mapper,transformed,transform))
        if mapped and spec.get('map_legend',True) and len(draw.field_actors)>layer_actor_count:
            if len(draw.field_scalar_bars)>=4:
                draw.field_warnings.append('Only the first four color scales are shown; disable extra legends in layer settings.')
                continue
            source=fields[map_index]
            bar = field_legend(source, lut, legend_unit(source.unit),
                               len(draw.field_scalar_bars), draw.options.background)
            bar._lele_layer_number=spec.get('_layer_number',1)
            draw.renderer.AddViewProp(bar);draw.dynamic.append(bar);draw.field_scalar_bars.append(bar)
            draw._keepalive.append((bar,lut))
