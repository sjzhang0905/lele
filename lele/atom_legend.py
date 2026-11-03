"""Unbonded atom samples on a dedicated legend canvas, independent of a model."""
from copy import deepcopy
import numpy as np
from vtkmodules.vtkFiltersSources import vtkSphereSource
from vtkmodules.vtkRenderingCore import vtkActor,vtkPolyDataMapper,vtkTextActor
from .atom_appearance import appearance,atom_is_drawn
from .core import radius


def legend_samples(owner):
    """Snapshot the first visible sample of each element in source order."""
    frame=getattr(owner,'source_frame',owner.frame)
    if frame is None:return []
    visible={int(i) for i,_ in owner.displayed_atoms()};samples=[];seen=set()
    from .site_occupancy import site_species
    for i,symbol in enumerate(frame.symbols):
        if i not in visible or not atom_is_drawn(frame,i):continue
        for species,fraction in site_species(frame,i).items():
            if species in seen or fraction<=0:continue
            seen.add(species)
            size=(max(.09,radius(species)*owner.options.atom_scale)
                  if owner.options.style=='Wireframe' else owner._atom_radius(species))
            color=appearance(frame,i).color or owner._display_color(species)
            samples.append(dict(symbol=species,source_index=i,color=color,
                                opacity=appearance(frame,i).opacity,radius=size))
    return samples


class AtomLegend:
    """A complete standalone VTK scene: spheres and element labels only."""
    def __init__(self,renderer):
        self.renderer=renderer;self.samples=[];self.actors=[];self.labels=[];self.spheres=[]
        cam=renderer.GetActiveCamera();cam.ParallelProjectionOn()
        cam.SetPosition(0,0,10);cam.SetFocalPoint(0,0,0);cam.SetViewUp(0,1,0);cam.SetParallelScale(2.)
        renderer.AddObserver('StartEvent',lambda *_:self.layout())

    def set_samples(self,samples,options):
        from .renderer import rgb
        self.renderer.RemoveAllViewProps();self.actors=[];self.labels=[];self.spheres=[]
        self.samples=deepcopy(samples);self.renderer.SetBackground(rgb(options.background))
        for sample in self.samples:
            sphere=vtkSphereSource();sphere.SetThetaResolution(40);sphere.SetPhiResolution(32)
            mapper=vtkPolyDataMapper();mapper.SetInputConnection(sphere.GetOutputPort())
            actor=vtkActor();actor.SetMapper(mapper);actor.PickableOff()
            prop=actor.GetProperty();prop.SetColor(rgb(sample['color']));prop.SetOpacity(sample['opacity'])
            ambient,diffuse,specular,power={'Glossy':(.17,.70,.78,60),'Matte':(.32,.67,.05,9)}.get(options.surface_finish,(.22,.72,.36,24))
            prop.SetAmbient(ambient);prop.SetDiffuse(diffuse);prop.SetSpecular(specular);prop.SetSpecularPower(power)
            self.renderer.AddActor(actor);self.actors.append(actor);self.spheres.append(sphere)
            label=vtkTextActor();label.SetInput(sample['symbol']);label.PickableOff()
            label.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
            label.GetTextProperty().SetJustificationToCentered();label.GetTextProperty().SetBold(True)
            light=np.mean(rgb(options.background))>.48
            label.GetTextProperty().SetColor(*((.10,.13,.18) if light else (.93,.95,.98)))
            self.renderer.AddViewProp(label);self.labels.append(label)
        self.layout()

    def layout(self):
        if not self.samples:return
        window=self.renderer.GetRenderWindow()
        width,height=window.GetSize() if window is not None else (800,300)
        width=max(1,width);height=max(1,height);aspect=width/height
        span=4*aspect;spacing=min(2.4,max(.05,(span-.4)/len(self.samples)))
        maximum=max(sample['radius'] for sample in self.samples)
        scale=min(.62,spacing*.32)/maximum
        for k,(sample,actor,label,sphere) in enumerate(zip(self.samples,self.actors,self.labels,self.spheres)):
            x=(k-(len(self.samples)-1)/2)*spacing
            actor.SetPosition(x,.35,0);sphere.SetRadius(sample['radius']*scale)
            label.SetPosition(.5+x/span,.20)
            label.GetTextProperty().SetFontSize(max(6,min(24,int(height*.075),int(width/len(self.samples)/3))))
        self.renderer.ResetCameraClippingRange()
