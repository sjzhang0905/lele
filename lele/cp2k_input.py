"""Read inline CP2K input/restart data without opening referenced files."""
import re
import shlex
from itertools import product
from math import prod
import numpy as np
from ase.data import atomic_numbers
from ase.geometry import cellpar_to_cell
from ase.units import Bohr
from .core import Frame
from .output_text import read_output_lines


class Section:
    def __init__(self, name='', argument='', line=0):
        self.name=name;self.argument=argument;self.line=line;self.entries=[];self.children=[]

    def all(self, name):return [s for s in self.children if s.name==name]
    def child(self, name):return next(iter(self.all(name)), Section())
    def get(self, key, default=()):
        return next((v for _, k, v in reversed(self.entries) if k==key), default)


def input_tree(lines):
    root=Section();stack=[root];variables={};notes=[]
    for index, raw in enumerate(lines):
        raw=re.sub(r'\$\{(\w+)\}|\$(\w+)', lambda m:variables.get(m[1] or m[2], m[0]), raw)
        lexer=shlex.shlex(raw,posix=True);lexer.whitespace_split=True;lexer.commenters='#!'
        parts=list(lexer)
        if not parts:continue
        key=parts[0].upper()
        if key=='@SET' and len(parts)>=3:variables[parts[1]]=' '.join(parts[2:]);continue
        if key.startswith('@'):
            notes.append('External includes and conditional preprocessing are not evaluated.')
            continue
        if key=='&END':
            if len(stack)>1:stack.pop()
        elif key.startswith('&'):
            node=Section(key[1:], ' '.join(parts[1:]), index+1)
            stack[-1].children.append(node);stack.append(node)
        else:stack[-1].entries.append((index+1,key,parts[1:]))
    return root,notes


def real(value):
    result=float(value.replace('D','E').replace('d','e'))
    if not np.isfinite(result):raise ValueError('Non-finite CP2K value')
    return result


def length_values(values, default='angstrom'):
    values=list(values);unit=default.lower()
    if values and values[0].startswith('['):unit=values.pop(0).strip('[]').lower()
    factor={'angstrom':1.,'ang':1.,'bohr':Bohr,'a.u.':Bohr,'au':Bohr,'nm':10.}.get(unit)
    if factor is None:raise ValueError('Unsupported CP2K length unit: '+unit)
    return np.asarray([real(x) for x in values])*factor


def angle_values(values):
    values=list(values);unit='deg'
    if values and values[0].startswith('['):unit=values.pop(0).strip('[]').lower()
    if unit not in ('deg','rad'):raise ValueError('Unsupported CP2K angle unit: '+unit)
    if len(values)!=3:raise ValueError('CP2K cell angles require three values')
    angles=np.asarray([real(x) for x in values])
    if unit=='rad':angles=np.degrees(angles)
    if np.any((angles<=0)|(angles>=180)):raise ValueError('Invalid CP2K cell angles')
    return angles


def repeat_factors(section, name):
    try:values=tuple(int(x) for x in section.get('MULTIPLE_UNIT_CELL',('1','1','1')))
    except ValueError:raise ValueError(f'Invalid CP2K {name}/MULTIPLE_UNIT_CELL') from None
    if len(values)!=3 or min(values)<1:
        raise ValueError(f'Invalid CP2K {name}/MULTIPLE_UNIT_CELL: three positive integers required')
    return values


def inline_frame(subsys):
    cell_node=subsys.child('CELL');cell=np.zeros((3,3))
    if all(cell_node.get(key) for key in 'ABC'):
        cell=np.asarray([length_values(cell_node.get(key)) for key in 'ABC']).reshape(3,3)
    elif cell_node.get('ABC'):
        abc=length_values(cell_node.get('ABC'))
        angles=angle_values(cell_node.get('ALPHA_BETA_GAMMA',cell_node.get('ANGLES',('90','90','90'))))
        if len(abc)!=3 or np.any(abc<=0):raise ValueError('Invalid CP2K ABC cell lengths')
        try:cell=cellpar_to_cell([*abc,*angles])
        except (AssertionError,ValueError):raise ValueError('Invalid CP2K cell lengths or angles') from None
        if abs(np.linalg.det(cell))<1.e-12:raise ValueError('Degenerate CP2K cell angles')
    cell_repeats=repeat_factors(cell_node,'CELL')
    coord_repeats=repeat_factors(subsys.child('TOPOLOGY'),'TOPOLOGY')
    periodic=''.join(cell_node.get('PERIODIC',('XYZ',))).upper()
    if periodic not in ('NONE','X','Y','Z','XY','XZ','YZ','XYZ'):raise ValueError('Invalid CP2K periodicity')
    pbc=tuple(axis in periodic for axis in 'XYZ') if np.linalg.det(cell)!=0 else (False,)*3
    kinds={k.argument:(k.get('ELEMENT',(k.argument,))[0]) for k in subsys.all('KIND')}
    coord=subsys.child('COORD');symbols=[];positions=[]
    unit=next(iter(coord.get('UNIT',('angstrom',))), 'angstrom')
    scaled=next(iter(coord.get('SCALED',('FALSE',))), 'TRUE').upper() in ('T','TRUE','.TRUE.','YES','1')
    for _, key, values in coord.entries:
        if key in ('UNIT','SCALED'):continue
        # Preserve case of kinds/symbols: the parser uppercases keyword tokens.
        symbol=next((v for k,v in kinds.items() if k.upper()==key), key.title())
        if symbol not in atomic_numbers or len(values)<3:raise ValueError('Incomplete or unidentified CP2K coordinates')
        vector=np.asarray([real(x) for x in values[:3]]) if scaled else length_values(values[:3],unit)
        symbols.append(symbol);positions.append(vector)
    if not symbols:return None
    if scaled:
        if abs(np.linalg.det(cell))<1.e-12:raise ValueError('Scaled CP2K coordinates require an inline cell')
        positions=np.asarray(positions)@cell
    copies=prod(coord_repeats)
    if copies!=1:
        if len(symbols)*copies>100000:raise ValueError('Excessive CP2K TOPOLOGY/MULTIPLE_UNIT_CELL')
        if abs(np.linalg.det(cell))<1.e-12:raise ValueError('CP2K coordinate repetition requires an inline cell')
        # Both fractional coordinates and replica translations use the original
        # unit cell. CP2K enumerates replicas with X changing fastest.
        shifts=np.asarray([(x,y,z) for z,y,x in product(*(range(n) for n in coord_repeats[::-1]))])@cell
        positions=(np.asarray(positions)[None,:,:]+shifts[:,None,:]).reshape(-1,3)
        symbols=symbols*copies
    # CELL changes only the displayed cell, never the coordinate count/scale.
    try:cell=cell*np.asarray(cell_repeats,dtype=float)[:,None]
    except OverflowError:raise ValueError('Excessive CP2K CELL/MULTIPLE_UNIT_CELL') from None
    if not np.all(np.isfinite(cell)):raise ValueError('Non-finite repeated CP2K cell')
    return Frame(symbols,positions,cell,pbc,info={'source_line':coord.line,'source_kind':'cp2k_in',
                 'cp2k_cell_repeats':cell_repeats,'cp2k_topology_repeats':coord_repeats})


def read_cp2k_input(path):
    from .cp2k_results import Cp2kResults,Cp2kStep
    from .calculation_results import CalculationJob,CalculationStage
    lines=read_output_lines(path);root,notes=input_tree(lines);results=Cp2kResults('CP2K')
    conditional=any(re.match(r'\s*@(?:IF|ELIF|ELSE)\b',line,re.I) for line in lines)
    global_node=root.child('GLOBAL');run=' '.join(global_node.get('RUN_TYPE',('Input',)))
    project=' '.join(global_node.get('PROJECT',global_node.get('PROJECT_NAME',())))
    frames=[]
    for index,force in enumerate(root.all('FORCE_EVAL')):
        dft=force.child('DFT');subsys=force.child('SUBSYS')
        job=CalculationJob(index,force.line,tasks={'Input / '+run},termination='Input only; no calculation result assumed')
        job.charge=int(real(dft.get('CHARGE',('0',))[0]));job.multiplicity=int(real(dft.get('MULTIPLICITY',('1',))[0]))
        xc=dft.child('XC').child('XC_FUNCTIONAL')
        job.method=xc.argument or ' / '.join(s.name for s in xc.children)
        job.basis=' / '.join(dict.fromkeys(' '.join(k.get('BASIS_SET')) for k in subsys.all('KIND') if k.get('BASIS_SET')))
        job.route=f'PROJECT={project}; RUN_TYPE={run}; METHOD={" ".join(force.get("METHOD"))}'
        results.jobs.append(job);results.stages.append(CalculationStage(index,index,'Inline input / restart','input',force.line,status='Not evaluated'))
        try:
            if conditional:
                raise ValueError('Conditional preprocessing is not evaluated; inline structure is withheld.')
            frame=inline_frame(subsys)
        except (ValueError,IndexError) as exc:notes.append(str(exc));frame=None
        if frame is not None:
            if frame.info['cp2k_topology_repeats']!=(1,1,1) and frame.info['cp2k_topology_repeats']!=frame.info['cp2k_cell_repeats']:
                notes.append('CP2K requires matching CELL/TOPOLOGY MULTIPLE_UNIT_CELL when TOPOLOGY repeats coordinates; independent input specifications are shown.')
            frame.info.update(converter_charge=job.charge,converter_mult=job.multiplicity,cp2k_project=project,
                              cp2k_run_type=run,calculation_index=index,stage_index=index)
            frames.append(frame)
            results.steps.append(Cp2kStep(index,frame.info['source_line'],frame,frame_index=len(frames)-1,stage_index=index))
        else:notes.append('No complete inline coordinates; referenced coordinate files are not opened.')
    if not results.jobs:raise ValueError('No CP2K FORCE_EVAL section found')
    results.note='Input/restart coordinates and settings only. No energy is assumed. '+' '.join(dict.fromkeys(notes))
    return results,frames
