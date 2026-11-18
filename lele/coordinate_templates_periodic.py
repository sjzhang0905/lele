"""Conservative, text-preserving coordinate updates for periodic input files.

Only coordinate tokens and cell definitions are edited. Source labels, units,
comments, line endings and unrelated settings remain verbatim. Unsupported
indirection is rejected before producing any replacement text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO
import re
import numpy as np
from ase.data import atomic_numbers, chemical_symbols
from ase.units import Bohr


NUMBER = re.compile(r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?\Z')


def _fail(message):
    raise ValueError(message + ' Please provide a representative input sample for this syntax.')


def _number(value):
    if not NUMBER.fullmatch(value):_fail('Geometry expressions or variables cannot be replaced safely.')
    value=float(value.replace('D','E').replace('d','e'))
    if not np.isfinite(value):raise ValueError('Non-finite input geometry.')
    return value


def _clean(line, comments='#!'):
    quote=None
    for index, char in enumerate(line):
        if char in "\"'":
            if quote==char:quote=None
            elif quote is None:quote=char
        elif char in comments and quote is None:return line[:index]
    return line.rstrip('\r\n')


def _tokens(line,comments='#!'):return list(re.finditer(r'\S+', _clean(line,comments)))


def _replace_tokens(line, values,comments='#!'):
    tokens=_tokens(line,comments)
    for index, value in sorted(values.items(), reverse=True):
        if index>=len(tokens):raise ValueError('Incomplete geometry record.')
        match=tokens[index];line=line[:match.start()]+str(value)+line[match.end():]
    return line


def _vector(line, start, vector,comments='#!'):
    tokens=_tokens(line,comments)
    if len(tokens)<start+3:raise ValueError('Incomplete geometry record.')
    for token in tokens[start:start+3]:_number(token[0])
    return _replace_tokens(line,{start+i:format(float(value),'.15g') for i,value in enumerate(vector)},comments)


def _newline(text):return '\r\n' if '\r\n' in text else '\n'


def _cell(frame):
    cell=np.asarray(frame.cell,float) if any(frame.pbc) else np.eye(3)*30.
    if cell.shape!=(3,3) or not np.isfinite(cell).all() or abs(np.linalg.det(cell))<1.e-10:
        raise ValueError('A nondegenerate three-dimensional cell is required.')
    return cell


def _length_unit(unit):
    factors={'angstrom':1.,'ang':1.,'bohr':Bohr,'au':Bohr,'a.u.':Bohr,'nm':10.}
    key=unit.lower().strip('[]')
    if key not in factors:_fail('Unsupported length unit '+unit+'.')
    return factors[key]


def _labels(old_labels, symbols, frame, indexed=False):
    resized=len(old_labels)!=len(frame.symbols)
    old_symbols=[symbols[label] for label in old_labels]
    reordered=old_symbols!=list(frame.symbols) or bool(frame.info.get('atom_order_edited'))
    if reordered and indexed:
        subject='Atom count changed' if resized else 'Atom order changed'
        raise ValueError(subject+' while the target contains atom-specific settings; their identity mapping is not verified.')
    by_symbol={}
    for label, symbol in symbols.items():by_symbol.setdefault(symbol,[]).append(label)
    if reordered and any(len(by_symbol.get(symbol,[]))!=1 for symbol in frame.symbols):
        raise ValueError('The target has missing or multiple KIND/species labels for an element; an unambiguous atom mapping is required.')
    return [by_symbol[symbol][0] for symbol in frame.symbols] if reordered else old_labels


def _coordinate_edits(lines,rows,vectors,labels,kind,newline):
    """Keep each original row layout, or replace a verified plain atom list."""
    start=0 if kind=='siesta_in' else 1;label_column=3 if kind=='siesta_in' else 0
    comments='#!;' if kind=='siesta_in' else '#!'
    if len(rows)==len(labels):
        return {i:_replace_tokens(_vector(lines[i],start,vector,comments),{label_column:label},comments)
                for i,vector,label in zip(rows,vectors,labels)}
    if not rows:raise ValueError('The target has no inline atom rows.')
    for i in rows:
        # A row-attached comment or extra field may describe that atom. Its
        # identity cannot be preserved if records are inserted or removed.
        if len(_tokens(lines[i],comments))!=4 or _clean(lines[i],comments).rstrip()!=lines[i].rstrip('\r\n').rstrip():
            raise ValueError('Changing atom count requires plain coordinate records without atom-specific fields or inline comments.')
    indent=re.match(r'\s*',lines[rows[0]])[0].rstrip('\r\n')
    records=[]
    for vector,label in zip(vectors,labels):
        xyz=' '.join(format(float(x),'.15g') for x in vector)
        records.append(indent+(xyz+' '+label if kind=='siesta_in' else label+' '+xyz)+newline)
    edits={i:'' for i in rows};edits[rows[0]]=''.join(records)
    return edits


def _namelist_number_edit(lines,namelist,key,value):
    """Replace one numerical namelist value without altering other tokens."""
    active=False;found=[]
    for i,line in enumerate(lines):
        # Mask quoted strings while keeping exact character offsets.
        chars=list(_clean(line));quote=None
        for j,char in enumerate(chars):
            if char in "\"'":
                if quote==char:quote=None
                elif quote is None:quote=char
                chars[j]=' '
            elif quote:chars[j]=' '
        code=''.join(chars)
        header=re.search(r'&'+re.escape(namelist)+r'\b',code,re.I)
        if header:active=True;offset=header.end()
        else:offset=0
        if not active:continue
        stop=code.find('/',offset);stop=len(code) if stop<0 else stop
        for match in re.finditer(r'\b'+re.escape(key)+r'\s*=\s*([-+]?\d+)\b',code[offset:stop],re.I):
            found.append((i,offset+match.start(1),offset+match.end(1)))
        if stop<len(code):active=False
    if len(found)!=1:_fail('A unique numeric '+key+' value is required in &'+namelist+'.')
    i,start,end=found[0]
    return i,lines[i][:start]+str(int(value))+lines[i][end:]


@dataclass
class _Section:
    name: str
    start: int
    argument: str=''
    end: int=-1
    parent: object=None
    children: list=field(default_factory=list)
    entries: list=field(default_factory=list)

    def all(self,name):return [node for node in self.children if node.name==name]
    def one(self,name):
        found=self.all(name)
        if len(found)!=1:_fail('Exactly one inline CP2K '+name+' section is required.')
        return found[0]


def _cp2k_tree(lines):
    root=_Section('',-1);stack=[root]
    for index,line in enumerate(lines):
        # Restart writers quote KIND names and ELEMENT strings. Nongeometry
        # continuation records may end in a backslash, so only unquote simple
        # tokens here instead of interpreting shell-style escaping globally.
        parts=[part.strip('\"\'') for part in _clean(line).split()]
        if not parts:continue
        if parts[0].startswith('@'):_fail('CP2K preprocessing/includes require a verified template.')
        if parts[0].upper()=='&END':
            if len(stack)==1:raise ValueError('Unbalanced CP2K sections.')
            node=stack.pop()
            if len(parts)>1 and parts[1].upper()!=node.name:raise ValueError('Mismatched CP2K section end.')
            node.end=index
        elif parts[0].startswith('&'):
            node=_Section(parts[0][1:].upper(),index,' '.join(parts[1:]),parent=stack[-1])
            stack[-1].children.append(node);stack.append(node)
        else:stack[-1].entries.append(index)
    if len(stack)!=1:raise ValueError('Unclosed CP2K section.')
    return root


def _cp2k_entries(node,lines):
    values={}
    for i in node.entries:
        parts=[part.strip('\"\'') for part in _clean(lines[i]).split()]
        values.setdefault(parts[0].upper(),[]).append((i,parts[1:]))
    return values


def _single(entries,key,default=None):
    values=entries.get(key,[])
    if len(values)>1:_fail('Repeated geometry keyword '+key+'.')
    return values[0] if values else default


def _cp2k_cell_value(values):
    values=list(values);factor=1.
    if values and values[0].startswith('['):factor=_length_unit(values.pop(0))
    if len(values)!=3:raise ValueError('A CP2K cell vector requires three numeric values.')
    return np.asarray([_number(x) for x in values])*factor


def _comment_only(line,comments='#!'):
    clean=_clean(line,comments)
    tail=line[len(clean):]
    return re.match(r'\s*',line)[0].rstrip('\r\n')+tail if tail.strip() else ''


def _cp2k(text,frame):
    lines=text.splitlines(keepends=True);root=_cp2k_tree(lines)
    force=root.one('FORCE_EVAL');subsys=force.one('SUBSYS')
    coord=subsys.one('COORD');cell_node=subsys.one('CELL')
    if coord.children:_fail('Nested CP2K coordinate sections are unsupported.')
    for i in coord.entries+cell_node.entries:
        if '$' in _clean(lines[i]) or '\\' in _clean(lines[i]):_fail('CP2K geometry variables or continuations require a verified template.')
    ce=_cp2k_entries(cell_node,lines);co=_cp2k_entries(coord,lines)
    if any(key in ce for key in ('CELL_FILE_NAME','CELL_FILE_FORMAT')):_fail('An external CP2K cell cannot be updated inline.')
    for node in [cell_node,*subsys.all('TOPOLOGY')]:
        entries=_cp2k_entries(node,lines)
        if 'MULTIPLE_UNIT_CELL' in entries and _single(entries,'MULTIPLE_UNIT_CELL')[1]!=['1','1','1']:
            _fail('CP2K MULTIPLE_UNIT_CELL requires an explicit mapping to the expanded atoms.')
        if node.name=='TOPOLOGY' and any(k in entries for k in ('COORD_FILE_NAME','COORD_FILE_FORMAT','CONNECTIVITY')):
            _fail('External CP2K coordinates/topology require a verified mapping.')
    labels={}
    for kind in subsys.all('KIND'):
        if kind.argument in labels:_fail('Repeated CP2K KIND label.')
        entries=_cp2k_entries(kind,lines)
        values=_single(entries,'ELEMENT',(None,[kind.argument]))[1]
        if len(values)!=1 or values[0].title() not in atomic_numbers:_fail('Unidentified CP2K KIND element.')
        labels[kind.argument]=values[0].title()
    rows=[];old_labels=[]
    for i in coord.entries:
        parts=[part.strip('\"\'') for part in _clean(lines[i]).split()]
        if parts[0].upper() in ('UNIT','SCALED'):continue
        if len(parts)<4:_fail('Incomplete CP2K coordinate record.')
        if parts[0] not in labels:
            if parts[0].title() not in atomic_numbers:_fail('CP2K KIND aliases require an explicit ELEMENT declaration.')
            labels[parts[0]]=parts[0].title()
        rows.append(i);old_labels.append(parts[0])
    indexed=bool(re.search(r'^\s*&(?:CONSTRAINT|FIXED_ATOMS|COLLECTIVE|COLVAR|VELOCITY|SHELL|CORE|QMMM|CDFT)\b',text,re.I|re.M))
    indexed=indexed or bool(re.search(r'^\s*(?!NUMBER_OF_ATOMS\b)(?:(?:[A-Z0-9]+_)*(?:ATOMS?|INDEX|LIST|RANGE)(?:_[A-Z0-9]+)*|ATOMIC_COEFF)\b',text,re.I|re.M))
    # MOLNAME is optional but atom-specific; do not silently transplant it.
    indexed=indexed or any(len(_tokens(lines[i]))>4 for i in rows)
    new_labels=_labels(old_labels,labels,frame,indexed)
    periodic=''.join(_single(ce,'PERIODIC',(None,['XYZ']))[1]).upper()
    # CP2K still requires an integration cell with PERIODIC NONE. Retain that
    # computational grid instead of deleting it or changing electrostatics.
    update_cell=periodic!='NONE'
    if update_cell:cell=_cell(frame)
    elif all(key in ce for key in ('A','B','C')):
        cell=np.asarray([_cp2k_cell_value(_single(ce,key)[1]) for key in ('A','B','C')])
    elif 'ABC' in ce:
        from ase.geometry import cellpar_to_cell
        lengths=_cp2k_cell_value(_single(ce,'ABC')[1])
        angles=list(_single(ce,'ALPHA_BETA_GAMMA',_single(ce,'ANGLES',(None,['90','90','90'])))[1])
        factor=1.
        if angles and angles[0].startswith('['):
            unit=angles.pop(0).lower()
            if unit not in ('[deg]','[rad]'):_fail('Unsupported CP2K cell angle unit.')
            factor=180/np.pi if unit=='[rad]' else 1.
        cell=cellpar_to_cell([*lengths,*[_number(x)*factor for x in angles]])
    else:_fail('CP2K PERIODIC NONE requires an identifiable integration cell.')
    scaled_values=_single(co,'SCALED',(None,['F']))[1]
    scaled=not scaled_values or scaled_values[0].upper() in ('T','TRUE','.TRUE.','YES','1')
    units=_single(co,'UNIT',(None,['angstrom']))[1]
    if len(units)!=1:_fail('Unsupported CP2K coordinate unit record.')
    vectors=np.asarray(frame.positions)@np.linalg.inv(cell) if scaled else np.asarray(frame.positions)/_length_unit(units[0])
    edits=_coordinate_edits(lines,rows,vectors,new_labels,'cp2k_in',_newline(text))
    if len(rows)!=len(new_labels):
        for topology in subsys.all('TOPOLOGY'):
            count=_single(_cp2k_entries(topology,lines),'NUMBER_OF_ATOMS')
            if count:
                i,values=count
                if len(values)!=1 or int(values[0])!=len(rows):raise ValueError('CP2K TOPOLOGY/NUMBER_OF_ATOMS differs from inline coordinates.')
                edits[i]=_replace_tokens(lines[i],{1:str(len(new_labels))})
    if update_cell:
        if 'SYMMETRY' in ce and ''.join(_single(ce,'SYMMETRY')[1]).upper()!='NONE':
            _fail('An explicit CP2K cell SYMMETRY setting requires a compatible-cell check.')
        explicit=all(key in ce for key in ('A','B','C'))
        if explicit and any(key in ce for key in ('ABC','ALPHA_BETA_GAMMA','ANGLES')):
            _fail('Conflicting CP2K cell descriptions are unsupported.')
        if explicit:
            for key,vector in zip(('A','B','C'),cell):
                i,values=_single(ce,key)
                unit=values[0] if values and values[0].startswith('[') else None
                edits[i]=_vector(lines[i],2 if unit else 1,vector/(_length_unit(unit) if unit else 1.))
        else:
            if any(key in ce for key in ('A','B','C')):_fail('Incomplete CP2K cell vectors.')
            # ABC/angles encode a canonical orientation only. Explicit vectors
            # retain a rotated/skewed source cell without rotating coordinates.
            index=_single(ce,'ABC',(cell_node.end,None))[0]
            indent=re.match(r'\s*',lines[index])[0].rstrip('\r\n') if index!=cell_node.end else '  '
            nl=_newline(text)
            comment=_comment_only(lines[index]) if index!=cell_node.end else ''
            records=''.join(indent+key+' [angstrom] '+' '.join(format(float(x),'.15g') for x in vector)+nl for key,vector in zip(('A','B','C'),cell))
            edits[index]=(comment+records) if index!=cell_node.end else records+lines[index]
            for key in ('ALPHA_BETA_GAMMA','ANGLES'):
                if key in ce:
                    i,_=_single(ce,key);edits[i]=_comment_only(lines[i])
    return ''.join(edits.get(i,line) for i,line in enumerate(lines))


def _card(lines,key):
    found=[i for i,line in enumerate(lines) if re.match(r'^\s*'+key+r'\b',_clean(line),re.I)]
    if len(found)!=1:_fail('Exactly one '+key+' card is required.')
    return found[0]


def _data_rows(lines,start,count):
    rows=[]
    for i in range(start+1,len(lines)):
        if not _clean(lines[i]).strip():continue
        rows.append(i)
        if len(rows)==count:return rows
    raise ValueError('Incomplete input geometry card.')


def _card_unit(line,key,default):
    value=re.sub(r'^\s*'+key+r'\b','',_clean(line),flags=re.I).strip().strip('(){}').strip().lower()
    return value or default


def _qe(text,frame):
    from ase.io.espresso import read_fortran_namelist,label_to_symbol,units
    lines=text.splitlines(keepends=True)
    settings,_=read_fortran_namelist(StringIO(text));system=settings.get('system',{})
    if system.get('ibrav')!=0:_fail('QE templates currently require ibrav=0 and explicit CELL_PARAMETERS.')
    if 'space_group' in system:_fail('QE space-group generated structures require a verified atom mapping.')
    nat=int(system.get('nat',0));ntyp=int(system.get('ntyp',0))
    if nat<=0 or ntyp<=0:raise ValueError('QE nat and ntyp must be positive.')
    positions=_card(lines,'ATOMIC_POSITIONS');cell_card=_card(lines,'CELL_PARAMETERS');species=_card(lines,'ATOMIC_SPECIES')
    rows=_data_rows(lines,positions,nat);cell_rows=_data_rows(lines,cell_card,3)
    aliases={}
    for i in _data_rows(lines,species,ntyp):
        parts=_clean(lines[i]).split()
        if len(parts)<3:_fail('Incomplete QE species definition.')
        aliases[parts[0]]=label_to_symbol(parts[0])
    old_labels=[_clean(lines[i]).split()[0] for i in rows]
    if any(label not in aliases for label in old_labels):raise ValueError('QE coordinates reference an undefined species.')
    indexed=any(len(_tokens(lines[i]))>4 for i in rows) or bool(re.search(r'^\s*(?:CONSTRAINTS|ATOMIC_VELOCITIES|ATOMIC_FORCES|HUBBARD)\b',text,re.I|re.M))
    new_labels=_labels(old_labels,aliases,frame,indexed)
    cell=_cell(frame);cell_unit=_card_unit(lines[cell_card],'CELL_PARAMETERS','alat')
    pos_unit=_card_unit(lines[positions],'ATOMIC_POSITIONS','alat')
    alat=float(system['celldm(1)'])*units['Bohr'] if 'celldm(1)' in system else float(system['a']) if 'a' in system else None
    if 'celldm(1)' in system and 'a' in system:raise ValueError('QE specifies both celldm(1) and A.')
    if cell_unit in ('bohr','angstrom'):
        if alat is not None:raise ValueError('QE lattice parameter is specified twice: A/celldm(1) and physical-unit CELL_PARAMETERS.')
        cell_factor=units['Bohr'] if cell_unit=='bohr' else 1.
        if alat is None:alat=float(np.linalg.norm(cell[0]))
    elif cell_unit=='alat' and alat is not None:cell_factor=alat
    else:_fail('QE CELL_PARAMETERS requires explicit supported units and a defined alat when used.')
    if pos_unit=='crystal':vectors=np.asarray(frame.positions)@np.linalg.inv(cell)
    elif pos_unit=='angstrom':vectors=np.asarray(frame.positions)
    elif pos_unit=='bohr':vectors=np.asarray(frame.positions)/units['Bohr']
    elif pos_unit=='alat' and alat is not None:vectors=np.asarray(frame.positions)/alat
    else:_fail('QE '+pos_unit+' coordinate syntax is not supported for replacement.')
    edits={i:_vector(lines[i],0,vector/cell_factor) for i,vector in zip(cell_rows,cell)}
    edits.update(_coordinate_edits(lines,rows,vectors,new_labels,'qe_in',_newline(text)))
    if len(rows)!=len(new_labels):
        i,line=_namelist_number_edit(lines,'SYSTEM','nat',len(new_labels));edits[i]=line
    return ''.join(edits.get(i,line) for i,line in enumerate(lines))


def _fdf_key(key):return re.sub(r'[-_.]','',key).lower()


def _fdf(text,frame):
    lines=text.splitlines(keepends=True);blocks={};scalars={};current=None
    for i,line in enumerate(lines):
        parts=_clean(line,'#!;').split()
        if not parts:continue
        if '<' in _clean(line,'#!;') or parts[0].lower()=='%include':_fail('SIESTA includes and redirected FDF data require a verified template.')
        if parts[0].lower()=='%block':
            if current or len(parts)!=2:_fail('Unsupported SIESTA block syntax.')
            key=_fdf_key(parts[1])
            if key in blocks:_fail('Duplicate SIESTA geometry blocks are ambiguous.')
            current=(key,i,[])
        elif parts[0].lower()=='%endblock':
            if current is None:raise ValueError('Unbalanced SIESTA block.')
            key,start,rows=current
            if len(parts)>1 and _fdf_key(parts[1])!=key:raise ValueError('Mismatched SIESTA block end.')
            blocks[key]=(start,i,rows);current=None
        elif current:current[2].append(i)
        else:
            key=_fdf_key(parts[0]);scalars.setdefault(key,[]).append((i,parts[1:]))
    if current:raise ValueError('Unclosed SIESTA block.')
    for key in ('zmatrix','supercell','atomiccoordinatesorigin'):
        if key in blocks or key in scalars:_fail('SIESTA '+key+' requires a verified coordinate mapping.')
    for key in ('latticeconstant','atomiccoordinatesformat','numberofatoms'):
        if len(scalars.get(key,[]))>1:_fail('Repeated SIESTA '+key+' declarations are ambiguous.')
    if 'atomiccoordinatesandatomicspecies' not in blocks or 'chemicalspecieslabel' not in blocks:
        _fail('Inline SIESTA coordinates and ChemicalSpeciesLabel blocks are required.')
    rows=blocks['atomiccoordinatesandatomicspecies'][2];aliases={}
    if 'numberofatoms' in scalars:
        values=scalars['numberofatoms'][0][1]
        if len(values)!=1 or int(values[0])!=len(rows):raise ValueError('SIESTA NumberOfAtoms differs from the inline coordinate count.')
    for i in blocks['chemicalspecieslabel'][2]:
        parts=_clean(lines[i],'#!;').split()
        if len(parts)<3:_fail('Incomplete SIESTA species record.')
        z=int(parts[1])
        if z<=0 or z>=len(chemical_symbols):_fail('SIESTA ghost, floating or custom species require a verified mapping.')
        aliases[parts[0]]=chemical_symbols[z]
    old_labels=[]
    for i in rows:
        parts=_clean(lines[i],'#!;').split()
        if len(parts)<4:raise ValueError('Incomplete SIESTA coordinate record.')
        if parts[3] not in aliases:raise ValueError('Undefined SIESTA species index.')
        old_labels.append(parts[3])
    safe_blocks={'latticevectors','latticeparameters','chemicalspecieslabel',
                 'atomiccoordinatesandatomicspecies','kgridmonkhorstpack',
                 'paobasis','paobasissizes','paobasistypes','pseudopotential',
                 'kgridcutoff','bandlines','bandpoints','projecteddensityofstates'}
    # Unknown FDF blocks may contain atom-indexed spin, transport or MD data.
    # The pure-template resize/reorder path accepts only known global blocks.
    indexed=bool(set(blocks)-safe_blocks) or any(len(_tokens(lines[i],'#!;'))>4 for i in rows)
    indexed=indexed or any(key in scalars for key in ('mdfcfirst','mdfclast','tsatomsbuffer'))
    indexed=indexed or any(key.startswith('ts') or 'constraint' in key or 'velocity' in key
                           or ('atom' in key and key not in ('numberofatoms','atomiccoordinatesformat'))
                           for key in scalars)
    if 'dminitspinaf' in scalars:
        values=scalars['dminitspinaf'][0][1]
        indexed=indexed or not values or values[0].lower() not in ('false','.false.','f','no','0')
    new_labels=_labels(old_labels,aliases,frame,indexed)
    lc=scalars.get('latticeconstant',[(None,['1','Ang'])])[0][1]
    if len(lc)!=2:_fail('SIESTA LatticeConstant requires an explicit length unit.')
    factor=_number(lc[0])*_length_unit(lc[1])
    if factor<=0:raise ValueError('SIESTA LatticeConstant must be positive.')
    unit=''.join(scalars.get('atomiccoordinatesformat',[(None,['Bohr'])])[0][1]).lower()
    cell=_cell(frame)
    if unit in ('fractional','scaledbylatticevectors'):vectors=np.asarray(frame.positions)@np.linalg.inv(cell)
    elif unit in ('ang','angstrom','notscaledcartesianang'):vectors=np.asarray(frame.positions)
    elif unit in ('bohr','notscaledcartesianbohr'):vectors=np.asarray(frame.positions)/Bohr
    elif unit in ('latticeconstant','scaledcartesian'):vectors=np.asarray(frame.positions)/factor
    else:_fail('Unsupported SIESTA AtomicCoordinatesFormat '+unit+'.')
    edits=_coordinate_edits(lines,rows,vectors,new_labels,'siesta_in',_newline(text))
    if len(rows)!=len(new_labels) and 'numberofatoms' in scalars:
        i,_=scalars['numberofatoms'][0];edits[i]=_replace_tokens(lines[i],{1:str(len(new_labels))},'#!;')
    if 'latticevectors' in blocks and 'latticeparameters' in blocks:_fail('Conflicting SIESTA cell definitions.')
    if 'latticevectors' in blocks:
        cell_rows=blocks['latticevectors'][2]
        if len(cell_rows)!=3:raise ValueError('SIESTA LatticeVectors requires exactly three rows.')
        edits.update({i:_vector(lines[i],0,vector/factor,'#!;') for i,vector in zip(cell_rows,cell)})
    elif 'latticeparameters' in blocks:
        start,end,cell_rows=blocks['latticeparameters'];nl=_newline(text)
        edits[start]=re.sub(r'Lattice[-_.]?Parameters','LatticeVectors',lines[start],flags=re.I)
        edits[end]=re.sub(r'Lattice[-_.]?Parameters','LatticeVectors',lines[end],flags=re.I)
        for i in cell_rows:edits[i]=_comment_only(lines[i],'#!;')
        records=''.join('  '+' '.join(format(float(x/factor),'.15g') for x in vector)+nl for vector in cell)
        edits[end]=records+edits[end]
    else:
        nl=_newline(text);records='%block LatticeVectors'+nl+''.join('  '+' '.join(format(float(x/factor),'.15g') for x in vector)+nl for vector in cell)+'%endblock LatticeVectors'+nl
        lines.append(('' if not lines or lines[-1].endswith(('\n','\r')) else nl)+records)
    if 'latticeconstant' not in scalars:
        nl=_newline(text)
        lines.append(('' if not lines or lines[-1].endswith(('\n','\r')) else nl)+'LatticeConstant 1.0 Ang'+nl)
    return ''.join(edits.get(i,line) for i,line in enumerate(lines))


def replace_periodic_coordinates(text,kind,frame):
    """Return updated text; never access the filesystem or modify ``frame``."""
    if not frame.symbols or not np.isfinite(frame.positions).all():raise ValueError('No finite structure is selected.')
    readers={'cp2k_in':_cp2k,'qe_in':_qe,'siesta_in':_fdf}
    if kind not in readers:raise ValueError('Unsupported periodic input template: '+str(kind))
    return readers[kind](text,frame)
