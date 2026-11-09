"""Files-tree groups and frame sequences for multistage scientific results."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem


def populate_energy_steps(window, index, doc, head):
    """Energy records without coordinates are selectable results, not frames."""
    from math import isfinite
    from ase.units import Hartree
    from .energy_units import EV_TO_KCAL_MOL, program_energy_unit
    results=doc.calculation_results
    if results is None:return
    groups={};stages={s.index:s for s in results.stages}
    for i,step in enumerate(results.steps):
        if step.energy_ev is None or not isfinite(step.energy_ev):continue
        if doc.frames and step.frame_index is not None:continue
        groups.setdefault((step.job_index,step.stage_index),[]).append(i)
    def fill(parent,indices):
        children=[]
        for i in indices:
            step=results.steps[i];cycle=step.cycle if step.cycle is not None else i+1
            unit=program_energy_unit(results.program)
            value=step.energy_ev if unit=='eV' else step.energy_ev*EV_TO_KCAL_MOL
            energy_label='E0 ' if results.program=='VASP' else ''
            child=QTreeWidgetItem([f'Step {cycle} · {energy_label}{value:.8f} {unit}'])
            child.setData(0,Qt.ItemDataRole.UserRole,(index,'energy',i))
            child.setToolTip(0,f'{"E0 (σ→0)" if results.program=="VASP" else "Energy"}: {step.energy_ev/Hartree:.12f} Eh\n'
                f'{step.energy_ev:.9f} eV\n{step.energy_ev*EV_TO_KCAL_MOL:.8f} kcal/mol\n'
                f'Source line: {step.source_line}\nNo structure for this record.')
            children.append(child)
        parent.addChildren(children)
    for (job,stage),indices in groups.items():
        stage=stages.get(stage);label=stage.name if stage is not None else f'Job {job+1}'
        parent=QTreeWidgetItem([label+' · energies without coordinates'])
        parent.setData(0,Qt.ItemDataRole.UserRole,(index,0));head.addChild(parent);parent.setExpanded(True)
        if len(indices)<=PAGE_SIZE:fill(parent,indices)
        else:
            for start in range(0,len(indices),PAGE_SIZE):
                stop=min(start+PAGE_SIZE,len(indices));chunk=indices[start:stop]
                page=QTreeWidgetItem([f'Records {start+1}–{stop}'])
                page.setData(0,Qt.ItemDataRole.UserRole,(index,'energy',chunk[0]));parent.addChild(page)
                _defer(page,lambda p=page,ids=chunk:fill(p,ids))


class FrameSequence:
    """One shared sequence with constant-time membership and frame lookup."""
    def __init__(self, values):
        self.values=values if isinstance(values,range) else tuple(values)
        self.positions=None if isinstance(self.values,range) else {v:i for i,v in enumerate(self.values)}
        self.key=id(self)

    def __len__(self):return len(self.values)
    def __iter__(self):return iter(self.values)
    def __getitem__(self, key):return self.values[key]
    def __contains__(self, value):return value in (self.values if self.positions is None else self.positions)
    def __eq__(self, other):return list(self.values)==list(other)
    def index(self, value):
        if self.positions is None:return self.values.index(value)
        try:return self.positions[value]
        except KeyError:raise ValueError(value) from None


def _sequence_state(window,doc):
    if not hasattr(window,'_sequence_cache'):window._sequence_cache={}
    key=id(doc);state=window._sequence_cache.get(key)
    if state is not None and state['frames'] is doc.frames and state['count']==len(doc.frames):return state
    all_frames=FrameSequence(range(len(doc.frames)))
    stages={};series={};other=[]
    for i,f in enumerate(doc.frames):
        if 'stage_index' in f.info:stages.setdefault(f.info['stage_index'],[]).append(i)
        if 'series_key' in f.info:series.setdefault(f.info['series_key'],[]).append(i)
        if 'stage_index' not in f.info and 'series_key' not in f.info:other.append(i)
    make=lambda ids:all_frames if len(ids)==len(doc.frames) else FrameSequence(ids)
    state=dict(frames=doc.frames,count=len(doc.frames),all=all_frames,
        stages={k:make(v) for k,v in stages.items()},series={k:make(v) for k,v in series.items()},
        other=make(other),custom={},context=None)
    window._sequence_cache[key]=state
    return state


def shared_sequence(window,doc,values):
    if isinstance(values,FrameSequence):return values
    state=_sequence_state(window,doc);values=tuple(values)
    if not values:return FrameSequence(())
    info=doc.frames[values[0]].info
    candidates=[state['all'],state['stages'].get(info.get('stage_index')),state['series'].get(info.get('series_key')),state['other']]
    for candidate in candidates:
        if candidate is not None and len(candidate)==len(values) and all(a==b for a,b in zip(candidate,values)):
            return candidate
    if values not in state['custom']:state['custom'][values]=FrameSequence(values)
    return state['custom'][values]


def sequence_for(window, index=None):
    doc=window.doc
    if doc is None or not doc.frames or window.frame is None:return []
    index=window.frame_index if index is None else index
    state=_sequence_state(window,doc)
    context=getattr(window,'_result_sequence',None)
    if context is not None and context[0] is doc:
        if state['context'] is not context:
            state['context']=context;state['context_sequence']=shared_sequence(window,doc,context[1])
        sequence=state['context_sequence']
        if index in sequence:return sequence
    info=doc.frames[index].info
    if 'series_key' in info:return state['series'][info['series_key']]
    if 'stage_index' in info:return state['stages'][info['stage_index']]
    return state['other'] if doc.neb_runs or doc.conformer_ensembles else state['all']


PAGE_SIZE=256
LAZY_ROLE=int(Qt.ItemDataRole.UserRole)+17
FRAME_LABEL_ROLE=int(Qt.ItemDataRole.UserRole)+18


def frame_tree_label(frame, frame_index, format_name, *, title=None, series_step=None):
    """Use the same scientific step names before and after tree selection."""
    from .energy_units import display_energy
    info = frame.info
    if title is None:
        title = (info['structure_label'] if info.get('structure_label') else
                 f'Conformer {info["goat_conformer"]}' if 'goat_conformer' in info else
                 f'Image {info["neb_image"]}' if 'neb_image' in info else
                 f'Step {info["optimization_cycle"]}' if info.get('optimization_cycle') is not None else
                 f'Step {series_step}' if series_step is not None else
                 f'Frame {frame_index + 1}')
    energy, unit = display_energy(frame, format_name)
    if energy is not None:
        title += f' · {energy:.5f} {unit}'
    if info.get('optimization_converged'):
        title += ' · converged'
    return title


def expand_tree_item(item):
    maker=item.data(0,LAZY_ROLE)
    if maker is not None:
        item.setData(0,LAZY_ROLE,None)
        maker()
        item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicatorWhenChildless)


def _defer(item,maker):
    item.setData(0,LAZY_ROLE,maker)
    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)


def add_frame_items(window,index,doc,parent,indices,*,label='',item_labels=None,series=False):
    """Retain every frame while creating only expanded pages of tree widgets."""
    sequence=shared_sequence(window,doc,indices)
    if not hasattr(window,'_tree_sequences'):window._tree_sequences={}
    if not hasattr(window,'_sequence_pages'):window._sequence_pages={}
    window._tree_sequences[sequence.key]=sequence
    def data(k):
        return (index,'series',sequence.key,k,label) if series else (index,sequence[k])
    def fill(target,start,stop):
        children=[]
        for k in range(start,stop):
            fi=sequence[k];f=doc.frames[fi]
            custom_title = item_labels[k] if item_labels is not None else None
            title = frame_tree_label(f, fi, doc.format_name, title=custom_title,
                                     series_step=k+1 if series else None)
            child=QTreeWidgetItem([title]);child.setData(0,Qt.ItemDataRole.UserRole,data(k));children.append(child)
            if custom_title is not None:child.setData(0,FRAME_LABEL_ROLE,custom_title)
            window._series_tree_items[index,sequence.key,fi]=child
            window._frame_tree_items.setdefault((index,fi),child)
        target.addChildren(children)
    if len(sequence)<=PAGE_SIZE:
        fill(parent,0,len(sequence))
    else:
        step_items = series or all(doc.frames[fi].info.get('optimization_cycle') is not None for fi in sequence)
        pages=[]
        for start in range(0,len(sequence),PAGE_SIZE):
            stop=min(start+PAGE_SIZE,len(sequence))
            page=QTreeWidgetItem([f'{"Steps" if step_items else "Frames"} {start+1}–{stop}'])
            page.setData(0,Qt.ItemDataRole.UserRole,data(start));parent.addChild(page);pages.append(page)
            _defer(page,lambda p=page,a=start,b=stop:fill(p,a,b))
        window._sequence_pages[index,sequence.key]=pages
    return sequence


def frame_tree_item(window,index,sequence,frame_index,head):
    item=getattr(window,'_series_tree_items',{}).get((index,getattr(sequence,'key',None),frame_index))
    if item is None:
        pages=getattr(window,'_sequence_pages',{}).get((index,getattr(sequence,'key',None)))
        if pages is not None:
            page=pages[sequence.index(frame_index)//PAGE_SIZE];expand_tree_item(page);page.setExpanded(True)
            item=window._series_tree_items.get((index,sequence.key,frame_index))
    return item if item is not None else window._frame_tree_items.get((index,frame_index),head)


def populate_tree(window,index,doc,head):
    results=doc.calculation_results
    stages=[] if results is None else results.stages
    window._frame_tree_items={k:v for k,v in window._frame_tree_items.items() if k[0]!=index}
    if not hasattr(window,'_series_tree_items'):window._series_tree_items={}
    window._series_tree_items={k:v for k,v in window._series_tree_items.items() if k[0]!=index}
    window._vibration_tree_items={k:v for k,v in window._vibration_tree_items.items() if k[0]!=index}
    if not (len(stages)>1 or doc.neb_runs or doc.conformer_ensembles):return False
    parents={};covered=set()

    def series(parent,label,indices,item_labels=None):
        indices=[i for i in indices if i is not None]
        if not indices:return None
        group=QTreeWidgetItem([label+f' ({len(indices)} structures)']);parent.addChild(group)
        sequence=add_frame_items(window,index,doc,group,indices,label=label,item_labels=item_labels,series=True)
        group.setData(0,Qt.ItemDataRole.UserRole,(index,'series',sequence.key,0,label))
        covered.update(indices)
        return group

    state=_sequence_state(window,doc)
    for s in stages:
        ids=state['stages'].get(s.index,())
        if s.kind=='neb':continue
        parent=series(head,s.name+' · '+s.status,ids)
        if parent is None:
            parent=QTreeWidgetItem([s.name+' · '+s.status]);head.addChild(parent)
        parents[s.index]=parent
    for run in doc.neb_runs:
        root=QTreeWidgetItem([f'NEB / NEB-TS · {run.nimages or "?"} images']);root.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','neb'));head.addChild(root)
        paths=QTreeWidgetItem(['Paths by snapshot']);root.addChild(paths)
        for p in run.profiles:
            if p.frame_indices and any(i is not None for i in p.frame_indices):
                series(paths,p.label,p.frame_indices,[f'Image {i}' for i,v in enumerate(p.frame_indices) if v is not None])
            else:
                child=QTreeWidgetItem([p.label+' · energy only']);child.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','neb'));paths.addChild(child)
        history=QTreeWidgetItem(['History by image']);root.addChild(history)
        snapshots=sorted([p for p in run.profiles if '.NEB.log' in p.source and p.iteration is not None and p.frame_indices],key=lambda p:p.iteration)
        for image in range(run.nimages or 0):
            items=[(p.iteration,p.frame_indices[image]) for p in snapshots if image<len(p.frame_indices) and p.frame_indices[image] is not None]
            series(history,f'Image {image} history',[f for it,f in items],[f'Iteration {it}' for it,f in items])
        if run.stage_index is not None:parents[run.stage_index]=root
    for ei,e in enumerate(doc.conformer_ensembles):
        ids=[c.frame_index for c in e.conformers if c.frame_index is not None]
        group=series(head,f'GOAT ensemble {ei+1}',ids,[f'Conformer {c.number}' for c in e.conformers if c.frame_index is not None])
        if group is None:
            group=QTreeWidgetItem([f'GOAT ensemble {ei+1} · energy only']);head.addChild(group)
            group.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','goat'))
    unused=[i for i in range(len(doc.frames)) if i not in covered]
    series(head,'Other printed reference geometries',unused)
    for ai,a in enumerate(doc.vibrations):
        title=a.purpose or f'Frequencies {ai+1}'
        group=QTreeWidgetItem([f'{title} ({len(a.modes)} modes · {sum(m.imaginary for m in a.modes)} imaginary)'])
        group.setData(0,Qt.ItemDataRole.UserRole,(index,'frequencies',ai));parents.get(a.stage_index,head).addChild(group)
        for mi,m in enumerate(a.modes):
            child=QTreeWidgetItem([f'{m.number}  {m.frequency_cm1:.4f} cm⁻¹'+(' · imaginary' if m.imaginary else '')])
            child.setData(0,Qt.ItemDataRole.UserRole,(index,'mode',ai,mi));group.addChild(child)
            if m.imaginary:child.setForeground(0,QColor('#c43b35'))
            child.setToolTip(0,a.note);window._vibration_tree_items[index,ai,mi]=child
    if results is not None and results.hessians:
        group=QTreeWidgetItem([f'Hessian history ({len(results.hessians)} events)']);head.addChild(group);group.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','hessian'))
    head.setExpanded(True)
    return True
