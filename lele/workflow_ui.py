"""Files-tree groups and frame sequences for multistage scientific results."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from .files_tree import FileItem


def populate_energy_steps(window, index, doc, head):
    """Add selectable energy records that have no associated coordinates."""
    from math import isfinite
    from ase.units import Hartree
    from .energy_units import EV_TO_KCAL_MOL, program_energy_unit
    results=doc.calculation_results
    if results is None:return
    trials = set()
    if results.program == 'CP2K' and any(s.kind == 'optimization' for s in results.stages):
        from .cp2k_results import optimization_trial_indices
        trials = optimization_trial_indices(results.steps)
    groups={};stages={s.index:s for s in results.stages}
    for i,step in enumerate(results.steps):
        if step.energy_ev is None or not isfinite(step.energy_ev):continue
        if doc.frames and step.frame_index is not None:continue
        groups.setdefault((i in trials,step.job_index,step.stage_index),[]).append(i)
    def record_data(i, role):
        step = results.steps[i]
        if role == Qt.ItemDataRole.UserRole:
            return (index, 'energy', i)
        if role == Qt.ItemDataRole.ToolTipRole:
            label = 'E0 (σ→0)' if results.program == 'VASP' else 'Energy'
            return (f'{label}: {step.energy_ev/Hartree:.12f} Eh\n{step.energy_ev:.9f} eV\n'
                    f'{step.energy_ev*EV_TO_KCAL_MOL:.8f} kcal/mol\nSource line: {step.source_line}\nNo structure for this record.')
        if role == Qt.ItemDataRole.DisplayRole:
            cycle = step.cycle if step.cycle is not None else i+1
            unit = program_energy_unit(results.program)
            value = step.energy_ev if unit == 'eV' else step.energy_ev*EV_TO_KCAL_MOL
            prefix = 'E0 ' if results.program == 'VASP' else ''
            final = results.program == 'CP2K' and step.info.get('cp2k_final_reevaluation')
            title = 'Final energy reevaluation' if final else f'Step {cycle}'
            return f'{title} · {prefix}{value:.8f} {unit}'
        return None
    for (trial,job,stage),indices in sorted(groups.items(), key=lambda pair: pair[0][0]):
        stage=stages.get(stage);label=stage.name if stage is not None else f'Job {job+1}'
        title = f'{label} · other force evaluations ({len(indices)})' if trial else label+' · energies without coordinates'
        parent=FileItem([title])
        parent.setData(0,Qt.ItemDataRole.UserRole,(index,0));head.addChild(parent);parent.setExpanded(not trial)
        if len(indices) > EAGER_ROWS:
            parent.add_virtual_rows(len(indices), lambda k, role, ids=indices: record_data(ids[k], role))
        else:
            for i in indices:
                child = FileItem([record_data(i, Qt.ItemDataRole.DisplayRole)])
                child.setData(0, Qt.ItemDataRole.UserRole, record_data(i, Qt.ItemDataRole.UserRole))
                child.setToolTip(0, record_data(i, Qt.ItemDataRole.ToolTipRole))
                parent.addChild(child)


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
    state=_sequence_state(window,doc)
    if isinstance(values, range) and values == state['all'].values:
        return state['all']
    values=tuple(values)
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


EAGER_ROWS=256
FRAME_LABEL_ROLE=int(Qt.ItemDataRole.UserRole)+18


def frame_tree_label(frame, frame_index, format_name, *, title=None, series_step=None):
    """Use the same scientific step names before and after tree selection."""
    from .energy_units import display_energy
    info = frame.info
    if title is None and format_name == 'CP2K output' and 'trajectory_frame' in info and 'cp2k_md_step' not in info:
        title = f'Frame {frame_index + 1}'
        step = info.get('linked_step')
        if info.get('cp2k_final_reevaluation'):
            title += ' · Final energy reevaluation'
        elif step is not None and step != frame_index + 1:
            title += f' · Step {step}'
    if title is None:
        title = ('Final optimized geometry' if info.get('scan_endpoint') and info.get('scan_converged') else
                 f'Latest evaluated geometry · cycle {info.get("optimization_cycle", "?")}' if info.get('scan_endpoint') else
                 info['structure_label'] if info.get('structure_label') else
                 f'Conformer {info["goat_conformer"]}' if 'goat_conformer' in info else
                 f'Image {info["neb_image"]}' if 'neb_image' in info else
                 f'Optimization cycle {info["optimization_cycle"]}' if 'scan_step' in info and info.get('optimization_cycle') is not None else
                 f'MD step {info["linked_step"]}' if 'linked_step' in info and 'cp2k_md_step' in info else
                 f'Step {info["linked_step"]}' if 'linked_step' in info else
                 f'Step {info["optimization_cycle"]}' if info.get('optimization_cycle') is not None else
                 f'Step {series_step}' if series_step is not None else
                 f'Frame {frame_index + 1}')
    energy, unit = display_energy(frame, format_name)
    if energy is not None:
        title += f' · {energy:.5f} {unit}'
    if info.get('optimization_converged'):
        title += ' · converged'
    return title


def add_frame_items(window,index,doc,parent,indices,*,label='',item_labels=None,series=False):
    """Long sequences occupy one flat Qt row range with on-demand labels."""
    sequence = shared_sequence(window,doc,indices)
    if not hasattr(window, '_tree_sequences'):
        window._tree_sequences = {}
    window._tree_sequences[sequence.key] = sequence

    def data(k, role):
        fi = sequence[k]
        if role == Qt.ItemDataRole.UserRole:
            return (index, 'series', sequence.key, k, label) if series else (index, fi)
        title = item_labels[k] if item_labels is not None else None
        if role == FRAME_LABEL_ROLE:
            return title
        if role == Qt.ItemDataRole.DisplayRole:
            return frame_tree_label(doc.frames[fi], fi, doc.format_name, title=title,
                                    series_step=k+1 if series else None)
        return None

    if len(sequence) > EAGER_ROWS:
        start = parent.add_virtual_rows(len(sequence), data)
        if not hasattr(window, '_sequence_ranges'):
            window._sequence_ranges = {}
        window._sequence_ranges[index, sequence.key] = (parent, start)
    else:
        children = []
        for k, fi in enumerate(sequence):
            child = FileItem([data(k, Qt.ItemDataRole.DisplayRole)])
            child.setData(0, Qt.ItemDataRole.UserRole, data(k, Qt.ItemDataRole.UserRole))
            if item_labels is not None:
                child.setData(0, FRAME_LABEL_ROLE, item_labels[k])
            children.append(child)
            window._series_tree_items[index,sequence.key,fi] = child
            window._frame_tree_items.setdefault((index,fi),child)
        parent.addChildren(children)
    return sequence


def frame_tree_item(window,index,sequence,frame_index,head):
    key = (index, getattr(sequence, 'key', None))
    span = getattr(window, '_sequence_ranges', {}).get(key)
    if span is not None:
        parent, start = span
        return parent.child(start + sequence.index(frame_index))
    return getattr(window, '_series_tree_items', {}).get((*key, frame_index),
               window._frame_tree_items.get((index,frame_index),head))


def populate_tree(window,index,doc,head):
    results=doc.calculation_results
    stages=[] if results is None else results.stages
    window._frame_tree_items={k:v for k,v in window._frame_tree_items.items() if k[0]!=index}
    if not hasattr(window,'_series_tree_items'):window._series_tree_items={}
    window._series_tree_items={k:v for k,v in window._series_tree_items.items() if k[0]!=index}
    window._vibration_tree_items={k:v for k,v in window._vibration_tree_items.items() if k[0]!=index}
    scans = [] if results is None else getattr(results, 'scans', [])
    if not (len(stages)>1 or scans or doc.neb_runs or doc.conformer_ensembles):return False
    parents={};covered=set()

    def series(parent,label,indices,item_labels=None,*,last=False):
        indices=[i for i in indices if i is not None]
        if not indices:return None
        group=FileItem([label+f' ({len(indices)} structures)']);parent.addChild(group)
        sequence=add_frame_items(window,index,doc,group,indices,label=label,item_labels=item_labels,series=True)
        group.setData(0,Qt.ItemDataRole.UserRole,(index,'series',sequence.key,len(sequence)-1 if last else 0,label))
        covered.update(indices)
        return group

    state=_sequence_state(window,doc)
    scan_parents = {}
    for run in scans:
        completed = sum(p.converged for p in run.points)
        planned = f' / {run.expected_points} planned' if run.expected_points is not None else ''
        kind = 'simultaneous scan path' if run.simultaneous and len(run.coordinates)>1 else 'relaxed scan'
        root = FileItem([f'ORCA {kind} · {completed} converged{planned}'])
        head.addChild(root)
        root.setToolTip(0, '\n'.join(c.label + f' ({c.unit})' for c in run.coordinates))
        endpoints = [p for p in run.points if p.converged and p.frame_index is not None]
        def point_label(point):
            from .orca_scan import scan_point_label
            return scan_point_label(run.coordinates, point)
        series(root, 'Scan curve · converged endpoints', [p.frame_index for p in endpoints],
               [point_label(p) for p in endpoints])
        pending = [p for p in run.points if not p.converged and p.frame_index is not None]
        series(root, 'Incomplete scan points · latest evaluated structures', [p.frame_index for p in pending],
               [point_label(p) + ' · incomplete' for p in pending])
        history = FileItem(['Optimization history by scan step']);root.addChild(history)
        for point in run.points:scan_parents[point.stage_index] = history
        root.setExpanded(True)
    for s in stages:
        ids=state['stages'].get(s.index,())
        if s.kind=='neb':continue
        stage_parent=scan_parents.get(s.index,head)
        # Selecting a scan-step heading displays its completed optimization,
        # while its children still expose every individual optimization cycle.
        is_scan = s.index in scan_parents or any('scan_step' in doc.frames[i].info for i in ids)
        parent=series(stage_parent,s.name+' · '+s.status,ids,last=is_scan)
        if parent is None:
            parent=FileItem([s.name+' · '+s.status]);stage_parent.addChild(parent)
        parents[s.index]=parent
    for run in doc.neb_runs:
        root=FileItem([f'NEB / NEB-TS · {run.nimages or "?"} images']);root.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','neb'));head.addChild(root)
        paths=FileItem(['Paths by snapshot']);root.addChild(paths)
        for p in run.profiles:
            if p.frame_indices and any(i is not None for i in p.frame_indices):
                series(paths,p.label,p.frame_indices,[f'Image {i}' for i,v in enumerate(p.frame_indices) if v is not None])
            else:
                child=FileItem([p.label+' · energy only']);child.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','neb'));paths.addChild(child)
        history=FileItem(['History by image']);root.addChild(history)
        snapshots=sorted([p for p in run.profiles if '.NEB.log' in p.source and p.iteration is not None and p.frame_indices],key=lambda p:p.iteration)
        for image in range(run.nimages or 0):
            items=[(p.iteration,p.frame_indices[image]) for p in snapshots if image<len(p.frame_indices) and p.frame_indices[image] is not None]
            series(history,f'Image {image} history',[f for it,f in items],[f'Iteration {it}' for it,f in items])
        if run.stage_index is not None:parents[run.stage_index]=root
    for ei,e in enumerate(doc.conformer_ensembles):
        ids=[c.frame_index for c in e.conformers if c.frame_index is not None]
        group=series(head,f'GOAT ensemble {ei+1}',ids,[f'Conformer {c.number}' for c in e.conformers if c.frame_index is not None])
        if group is None:
            group=FileItem([f'GOAT ensemble {ei+1} · energy only']);head.addChild(group)
            group.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','goat'))
    unused=[i for i in range(len(doc.frames)) if i not in covered]
    series(head,'Other printed reference geometries',unused)
    for ai,a in enumerate(doc.vibrations):
        title=a.purpose or f'Frequencies {ai+1}'
        group=FileItem([f'{title} ({len(a.modes)} modes · {sum(m.imaginary for m in a.modes)} imaginary)'])
        group.setData(0,Qt.ItemDataRole.UserRole,(index,'frequencies',ai));parents.get(a.stage_index,head).addChild(group)
        for mi,m in enumerate(a.modes):
            child=FileItem([f'{m.number}  {m.frequency_cm1:.4f} cm⁻¹'+(' · imaginary' if m.imaginary else '')])
            child.setData(0,Qt.ItemDataRole.UserRole,(index,'mode',ai,mi));group.addChild(child)
            if m.imaginary:child.setForeground(0,QColor('#c43b35'))
            child.setToolTip(0,a.note);window._vibration_tree_items[index,ai,mi]=child
    if results is not None and results.hessians:
        group=FileItem([f'Hessian history ({len(results.hessians)} events)']);head.addChild(group);group.setData(0,Qt.ItemDataRole.UserRole,(index,'analysis','hessian'))
    head.setExpanded(True)
    return True
