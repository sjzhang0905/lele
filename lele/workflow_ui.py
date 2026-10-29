"""Files-tree groups and frame sequences for multistage scientific results."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTreeWidgetItem


def populate_energy_steps(window, index, doc, head):
    """Energy records without coordinates are selectable results, not frames."""
    from math import isfinite
    from ase.units import Hartree
    from .energy_units import EV_TO_KCAL_MOL
    results = doc.calculation_results
    if results is None: return
    groups = {}
    for i, step in enumerate(results.steps):
        if step.energy_ev is None or not isfinite(step.energy_ev): continue
        if doc.frames and step.frame_index is not None: continue
        key = (step.job_index, step.stage_index)
        if key not in groups:
            stage = next((s for s in results.stages if s.index == step.stage_index), None)
            label = stage.name if stage is not None else f'Job {step.job_index+1}'
            parent = QTreeWidgetItem([label + ' · energies without coordinates'])
            parent.setData(0, Qt.ItemDataRole.UserRole, (index, 0)); head.addChild(parent)
            parent.setExpanded(True); groups[key] = parent
        cycle = step.cycle if step.cycle is not None else i+1
        value = step.energy_ev * EV_TO_KCAL_MOL
        child = QTreeWidgetItem([f'Step {cycle} · {value:.8f} kcal/mol'])
        child.setData(0, Qt.ItemDataRole.UserRole, (index, 'energy', i))
        child.setToolTip(0, f'Energy: {step.energy_ev/Hartree:.12f} Eh\n'
                           f'{step.energy_ev:.9f} eV\n{value:.8f} kcal/mol\n'
                           f'Source line: {step.source_line}\nNo structure for this record.')
        groups[key].addChild(child)


def sequence_for(window, index=None):
    doc=window.doc
    if doc is None or not doc.frames or window.frame is None:return []
    index=window.frame_index if index is None else index
    context=getattr(window,'_result_sequence',None)
    if context is not None and context[0] is doc and index in context[1]:return list(context[1])
    info=doc.frames[index].info
    if 'series_key' in info:return [i for i,f in enumerate(doc.frames) if f.info.get('series_key')==info['series_key']]
    if 'stage_index' in info:return [i for i,f in enumerate(doc.frames) if f.info.get('stage_index')==info['stage_index']]
    if doc.neb_runs or doc.conformer_ensembles:
        return [i for i,f in enumerate(doc.frames) if 'stage_index' not in f.info and 'series_key' not in f.info]
    return list(range(len(doc.frames)))


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
        group.setData(0,Qt.ItemDataRole.UserRole,(index,'series',tuple(indices),0,label))
        for k,frame_index in enumerate(indices):
            f=doc.frames[frame_index]
            title=item_labels[k] if item_labels is not None else f'Step {f.info.get("optimization_cycle") or k+1}'
            from .energy_units import display_energy
            energy,unit=display_energy(f,doc.format_name)
            if energy is not None:title+=f' · {energy:.5f} {unit}'
            child=QTreeWidgetItem([title]);child.setData(0,Qt.ItemDataRole.UserRole,(index,'series',tuple(indices),k,label));group.addChild(child)
            window._series_tree_items[index,tuple(indices),frame_index]=child
            window._frame_tree_items.setdefault((index,frame_index),child);covered.add(frame_index)
        return group

    for s in stages:
        ids=[i for i,f in enumerate(doc.frames) if f.info.get('stage_index')==s.index]
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
