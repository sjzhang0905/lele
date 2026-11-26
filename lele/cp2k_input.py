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
from .periodic_geometry import valid_periodic_cell


class Section:
    def __init__(self, name='', argument='', line=0):
        self.name=name;self.argument=argument;self.line=line;self.entries=[];self.children=[]

    def all(self, name):return [s for s in self.children if s.name==name]
    def child(self, name):return next(iter(self.all(name)), Section())
    def get(self, key, default=()):
        return next((v for _, k, v in reversed(self.entries) if k==key), default)


def logical_input_lines(lines):
    """Join CP2K continuation records while retaining their first source line.

    Restart writers wrap long LIST and other keyword values with a trailing
    backslash. Tokenizing those physical lines separately makes shlex raise
    ``No escaped character`` before even reaching the coordinate section.
    Comment markers inside quotes are data, not the end of a record.
    """
    pending=[];start=0
    for index,raw in enumerate(lines,1):
        raw=raw.rstrip('\r\n');quote=None;escaped=False;end=len(raw)
        for pos,char in enumerate(raw):
            if escaped:escaped=False;continue
            if char=='\\' and quote!="'":escaped=True;continue
            if quote:
                if char==quote:quote=None
            elif char in ('"',"'"):quote=char
            elif char in '#!':end=pos;break
        content=raw[:end].rstrip()
        continuation=quote is None and escaped and content.endswith('\\')
        # A comment can follow the continuation marker; trailing whitespace
        # should not turn an otherwise valid CP2K continuation into a token.
        if quote is None and content.endswith('\\'):
            slash_count=len(content)-len(content.rstrip('\\'))
            continuation=bool(slash_count%2)
        if not pending:start=index
        if continuation:
            pending.append(content[:-1]);continue
        if pending:
            if not content:continue
            pending.append(content)
            yield start,' '.join(pending)
            pending=[]
        else:yield index,raw
    if pending:raise ValueError(f'Incomplete CP2K continuation at line {start}')


def input_tree(lines):
    root=Section();stack=[root];variables={};notes=[]
    for index, raw in logical_input_lines(lines):
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
            node=Section(key[1:], ' '.join(parts[1:]), index)
            stack[-1].children.append(node);stack.append(node)
        else:stack[-1].entries.append((index,key,parts[1:]))
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


def input_cell(cell_node):
    """Return the coordinate basis, repeated simulation cell and requested PBC."""
    cell=np.zeros((3,3))
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
    periodic=''.join(cell_node.get('PERIODIC',('XYZ',))).upper()
    if periodic not in ('NONE','X','Y','Z','XY','XZ','YZ','XYZ'):raise ValueError('Invalid CP2K periodicity')
    requested_pbc = tuple(axis in periodic for axis in 'XYZ')
    try:
        simulation_cell = cell * np.asarray(cell_repeats, dtype=float)[:, None]
    except OverflowError:
        raise ValueError('Excessive CP2K CELL/MULTIPLE_UNIT_CELL') from None
    if not np.all(np.isfinite(simulation_cell)):
        raise ValueError('Non-finite repeated CP2K cell')
    return cell, simulation_cell, requested_pbc, cell_repeats


def inline_frame(subsys):
    cell, simulation_cell, requested_pbc, cell_repeats = input_cell(subsys.child('CELL'))
    coord_repeats=repeat_factors(subsys.child('TOPOLOGY'),'TOPOLOGY')
    pbc = requested_pbc if valid_periodic_cell(cell, requested_pbc) else (False,) * 3
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
    return Frame(symbols,positions,simulation_cell,pbc,info={'source_line':coord.line,'source_kind':'cp2k_in',
                 'cp2k_cell_repeats':cell_repeats,'cp2k_topology_repeats':coord_repeats})


def input_settings(root,force,project,run):
    """Printed settings/state, kept separate from evaluated results."""
    dft=force.child('DFT');motion=root.child('MOTION');md=motion.child('MD')
    settings={'Project':project,'Run type':run}
    def add(label,values):
        if not values:return
        # Explicit non-default units stay attached to their source values;
        # do not label them with the default unit or silently convert them.
        if values[0].startswith('['):
            label=re.sub(r' \([^()]+\)$','',label)
        value=' '.join(values)
        if len(values)==1:
            try:
                number=real(values[0]);value=int(number) if number.is_integer() else number
            except ValueError:pass
        settings[label]=value
    for label,node,key in (
        ('Electronic method',force,'METHOD'),('Quickstep method',dft.child('QS'),'METHOD'),
        ('MD ensemble',md,'ENSEMBLE'),('MD requested steps',md,'STEPS'),
        ('MD time step (fs)',md,'TIMESTEP'),('MD target temperature (K)',md,'TEMPERATURE'),
    ):
        add(label,node.get(key))
    if dft.get('UKS'):
        settings['Spin']='UKS' if dft.get('UKS')[0].upper() in ('T','TRUE','.TRUE.','YES','1') else 'RKS'
    section=md if run.upper()=='MD' else motion.child('CELL_OPT' if run.upper()=='CELL_OPT' else 'GEO_OPT')
    for label,key in (('Optimizer','OPTIMIZER'),('Maximum optimization steps','MAX_ITER'),
                      ('Restart step','STEP_START_VAL'),('Restart time (fs)','TIME_START_VAL')):
        add(label,section.get(key))
    return settings,section


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
        # CP2K restart writers expand a functional shortcut to child sections
        # and serialize XC_FUNCTIONAL NO_SHORTCUT; that token is not a method.
        job.method=(xc.argument if xc.argument.upper() not in ('','NO_SHORTCUT') else
                    ' / '.join(s.name for s in xc.children))
        job.basis=' / '.join(dict.fromkeys(' '.join(k.get('BASIS_SET')) for k in subsys.all('KIND') if k.get('BASIS_SET')))
        job.route=f'PROJECT={project}; RUN_TYPE={run}; METHOD={" ".join(force.get("METHOD"))}'
        settings,state=input_settings(root,force,project,run)
        results.metadata.setdefault('jobs',{})[str(index)]=settings
        state_info={};cycle=None
        if state.get('STEP_START_VAL'):
            try:
                value=real(state.get('STEP_START_VAL')[0])
                if value.is_integer() and value>=0:cycle=int(value);state_info['cp2k_restart_step']=cycle
            except ValueError:pass
        if run.upper()=='MD' and state.get('TIME_START_VAL'):
            try:state_info['time_fs']=real(state.get('TIME_START_VAL')[0])
            except ValueError:pass
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
                              cp2k_run_type=run,calculation_index=index,stage_index=index,**state_info)
            frames.append(frame)
            results.steps.append(Cp2kStep(index,frame.info['source_line'],frame,frame_index=len(frames)-1,
                                         stage_index=index,cycle=cycle,info=state_info))
        else:notes.append('No complete inline coordinates; referenced coordinate files are not opened.')
    if not results.jobs:raise ValueError('No CP2K FORCE_EVAL section found')
    results.note='Input/restart coordinates and settings only. No energy is assumed. '+' '.join(dict.fromkeys(notes))
    return results,frames
