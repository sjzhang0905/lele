"""Explicit atom constraints, with source coordinate basis and unknown states.

``fixed_axes`` uses True=fixed, False=not fixed, None=unknown. Its absence
means the source did not provide a reliable atom-wise constraint description.
Bond, angle, rigid-body and harmonic restraints are never atom freezes.
"""
from __future__ import annotations

import re
import numpy as np


def _gaussian_geometry_start(lines):
    """Locate the charge line after route and title, excluding title integers."""
    start=next((i for i,line in enumerate(lines) if line.lstrip().startswith('#')),None)
    if start is None:return None
    i=start
    while i<len(lines) and lines[i].strip():i+=1
    while i<len(lines) and not lines[i].strip():i+=1
    while i<len(lines) and lines[i].strip():i+=1
    while i<len(lines) and not lines[i].strip():i+=1
    if i<len(lines) and re.fullmatch(r'\s*[+-]?\d+[\s,]+\d+(?:[\s,]+[+-]?\d+[\s,]+\d+)*\s*',lines[i]):return i+1
    return None


def _gaussian_tokens(line):
    line=line.split('!',1)[0].strip()
    match=re.match(r'^([^\s,(]+(?:\([^)]*\))?)\s*,?\s*(.*)$',line)
    if not match:return []
    return [match[1]]+[word for word in re.split(r'[\s,]+',match[2]) if word]


def read_gaussian_atoms(path):
    """Allow ordinary Cartesian freeze columns without editing source bytes.

    ASE rejects freeze codes. Remove that optional field in a temporary
    in-memory reader input; the original input supplies metadata below.
    All other Gaussian grammar remains the responsibility of its existing
    reader. In particular, no Z-matrix is converted by guessing coordinates.
    """
    from io import StringIO
    from ase.io import read
    from .output_text import read_output_lines
    lines=list(read_output_lines(path));start=_gaussian_geometry_start(lines)
    candidates=[];cartesian=start is not None
    if start is not None:
        lines[start-1]=lines[start-1].replace(',',' ')
        for i in range(start,len(lines)):
            if not lines[i].strip():break
            parts=_gaussian_tokens(lines[i])
            offset=1
            if len(parts)==5 and re.fullmatch(r'[+-]?\d+',parts[1]) and int(parts[1])<=0:offset=2
            if len(parts)!=offset+3:cartesian=False;break
            try:coordinates=[float(value.replace('D','E').replace('d','e')) for value in parts[offset:]]
            except ValueError:cartesian=False;break
            label='TV' if parts[0].upper()=='TV' else parts[0]
            candidates.append((i,label+' '+' '.join(repr(value) for value in coordinates)))
    if cartesian:
        for i,line in candidates:lines[i]=line
    route='\n'.join(lines[:start or 0])
    unit_match=re.search(r'(?i)\bunits?\s*=\s*(\([^)]*\)|[A-Za-z]+)',route)
    units=unit_match[1] if unit_match else ''
    if not cartesian and re.search(r'(?i)\brad(?:ians)?\b',units):
        raise ValueError('Gaussian radian Z-matrix coordinates require a sample; they are not interpreted as degrees.')
    atoms=read(StringIO('\n'.join(lines)+'\n'),index=-1,format='gaussian-in')
    if start is not None:
        charge,multiplicity=lines[start-1].split()[:2]
        atoms.info.update(converter_charge=int(charge),converter_mult=int(multiplicity))
    if re.search(r'(?i)\b(?:au|bohr)\b',units):
        from ase.units import Bohr
        atoms.positions *= Bohr
        atoms.set_cell(atoms.cell.array*Bohr)
    return atoms


def _result(flags, basis, source, notes=()):
    result = {'constraint_notes': list(dict.fromkeys(notes))} if notes else {}
    if flags is not None:
        result.update(fixed_axes=np.asarray(flags, dtype=object).tolist(),
                      fixed_axes_basis=basis, fixed_axes_source=source)
    return result


def constraint_rows(info):
    """The editable mask is authoritative; older projects may only have VASP flags."""
    return info.get('fixed_axes', info.get('vasp_fixed_axes'))


def fixed_atom_indices(frame):
    rows = constraint_rows(frame.info)
    if rows is None:
        return []
    if len(rows) != len(frame.symbols):
        raise ValueError('Fixed-axis records do not match the atom count.')
    return [i for i, row in enumerate(rows) if len(row) == 3 and all(row)]


def edited_constraints(frame, selection, fixed):
    """Copy on write so trajectory frames, earlier undo states and source flags stay independent."""
    old = constraint_rows(frame.info)
    axes = [bool(fixed)] * 3
    if old is None:
        rows = [[None] * 3 for _ in frame.symbols]
    else:
        if len(old) != len(frame.symbols):
            raise ValueError('Fixed-axis records do not match the atom count.')
        rows = list(old)
    if all(list(rows[i]) == axes for i in selection):
        return {}
    for i in selection:
        rows[i] = axes.copy()
    basis = frame.info.get('fixed_axes_basis', 'direct' if 'vasp_fixed_axes' in frame.info else 'cartesian')
    result = dict(fixed_axes=rows, fixed_axes_basis=basis)
    source = frame.info.get('fixed_axes_source', '')
    if 'LELE' not in source:
        result['fixed_axes_source'] = (source + ' / LELE').strip(' /')
    if 'vasp_fixed_axes' in frame.info:
        legacy = list(frame.info['vasp_fixed_axes'])
        for i in selection:
            legacy[i] = axes.copy()
        result['vasp_fixed_axes'] = legacy
    return result


def export_fixed_mask(info, count):
    rows = constraint_rows(info)
    if rows is None:
        return None
    rows = np.asarray(rows, dtype=object)
    if rows.shape != (count, 3):
        raise ValueError('Fixed-axis records do not match the atom order.')
    # Undeclared axes do not create optimization constraints on export.
    return rows.astype(bool)


def _indices(text, count, *, zero=False, symbols=None):
    result = set()
    for value in re.split(r'[\s,]+', text.strip()):
        if not value:continue
        if value in ('*', 'all'):result.update(range(count));continue
        if symbols is not None and value.capitalize() in symbols:
            result.update(i for i, symbol in enumerate(symbols) if symbol == value.capitalize());continue
        match = re.fullmatch(r'(\d+)(?:[:-](\d+))?', value)
        if not match:raise ValueError('Unrecognized atom list: ' + text)
        lo = int(match[1]) - (0 if zero else 1)
        hi = int(match[2]) - (0 if zero else 1) if match[2] else lo
        if not 0 <= lo <= hi < count:raise ValueError('Constraint atom index outside the loaded structure.')
        result.update(range(lo, hi + 1))
    return sorted(result)


def from_ase_constraints(atoms):
    """Retain ASE Cartesian/scaled constraints without confusing their bases."""
    from ase.constraints import FixAtoms, FixCartesian, FixScaled
    masks = {}; whole = np.zeros((len(atoms), 3), dtype=bool); notes=[];seen=False
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            whole[constraint.get_indices()] = True;seen=True
        elif isinstance(constraint, (FixCartesian, FixScaled)):
            basis = 'direct' if isinstance(constraint, FixScaled) else 'cartesian'
            mask=masks.setdefault(basis, np.zeros_like(whole))
            mask[constraint.get_indices()] |= constraint.mask;seen=True
        else:notes.append(type(constraint).__name__ + ': not a per-axis atom freeze.')
    if not seen:return _result(None, '', '', notes)
    partial = [basis for basis,mask in masks.items() if np.any(mask.any(1) & ~mask.all(1))]
    if len(partial)>1:
        return _result(None, '', '', notes + ['Mixed Cartesian and direct partial constraints cannot share one axis mask.'])
    basis=partial[0] if partial else next(iter(masks), 'cartesian')
    flags=whole.copy()
    for other,mask in masks.items():
        if other==basis:flags |= mask
        else:flags[mask.all(1)] = True
    return _result(flags, basis, 'ASE constraints', notes)


def qe_position_constraints(rows):
    """QE if_pos acts on Cartesian force components even for crystal input."""
    flags=[];seen=False
    for row in rows:
        parts=row.split('!',1)[0].split()
        values=parts[4:]
        if values:
            if len(values)!=3 or any(value not in ('0','1') for value in values):
                raise ValueError('Invalid QE if_pos flags; expected three 0/1 values.')
            seen=True;flags.append([value=='0' for value in values])
        else:flags.append([False]*3)
    return _result(flags if seen else None, 'cartesian', 'QE if_pos (0=fixed)')


def xtb_fixed_table(lines, start):
    """Parse the explicitly printed xTB fixed-atom table during its main scan."""
    match=re.search(r'(\d+)\s+fixed atom positions',lines[start],re.I)
    if not match:return None
    count=int(match[1]);records=[]
    if count==0:return records
    for line in lines[start+1:start+count+16]:
        fields=line.split()
        if len(fields)==6 and fields[0].isdigit() and fields[1].isdigit() and fields[2].isalpha():
            try:[float(value.replace('D','E').replace('d','e')) for value in fields[3:]]
            except ValueError:break
            records.append((int(fields[0])-1,int(fields[1]),fields[2].capitalize()))
            if len(records)==count:return records
        elif records:break
    return None


def xtb_fixed_constraints(records, frame):
    from ase.data import atomic_numbers
    flags=np.zeros((len(frame.symbols),3),bool)
    for index,number,symbol in records:
        if not 0<=index<len(frame.symbols) or frame.symbols[index]!=symbol or atomic_numbers.get(symbol)!=number:
            return _result(None,'','',['xTB fixed-atom table does not match the loaded geometry.'])
        flags[index]=True
    return _result(flags,'cartesian','xTB printed Fixed Atoms table')


def _cp2k(lines, frame):
    from .cp2k_input import input_tree
    root, notes = input_tree(lines)
    constraint=root.child('MOTION').child('CONSTRAINT')
    nodes=constraint.all('FIXED_ATOMS')
    if not nodes:return {}
    if notes:
        return _result(None,'','',notes+['CP2K preprocessing may supply additional constraints; free-axis flags are not inferred.'])
    if len(root.all('FORCE_EVAL'))>1:
        return _result(None,'','',['CP2K multiple FORCE_EVAL constraint indexing needs a sample.'])
    flags=np.zeros((len(frame.symbols),3), dtype=bool);seen=False
    for node in nodes:
        if node.all('RESTRAINT'):
            notes.append('CP2K FIXED_ATOMS/RESTRAINT is a soft restraint, not an exact atom freeze.');continue
        if any(node.get(key) for key in ('MOLNAME','QM_SUBSYS','MM_SUBSYS','EXCLUDE_MM','EXCLUDE_QM')):
            return _result(None,'','',notes+['CP2K molecule/QM/MM constraint selectors are not resolved.'])
        components=''.join(node.get('COMPONENTS_TO_FIX',('XYZ',))).upper()
        if components not in ('X','Y','Z','XY','XZ','YZ','XYZ'):
            raise ValueError('Unknown CP2K COMPONENTS_TO_FIX value.')
        entries=[values for _,key,values in node.entries if key=='LIST']
        for values in entries:
            indices=_indices(' '.join(values),len(frame.symbols))
            flags[np.ix_(indices,[i for i,c in enumerate('XYZ') if c in components])]=True
            seen=True
    if any(node.name!='FIXED_ATOMS' for node in constraint.children):
        notes.append('Other CP2K constraints are retained as non-atom constraints.')
    return _result(flags if seen else None,'direct','CP2K FIXED_ATOMS (fractional components)',notes)


def _orca(lines, frame):
    text='\n'.join(line.split('#',1)[0] for line in lines)
    notes=[];flags=np.zeros((len(frame.symbols),3), dtype=bool);seen=False
    if re.search(r'(?im)^\s*\$new_job|\b(?:FixFrags|RelaxFrags|RelaxHFrags|Frags|ConstrainFragments)\b',text):
        return _result(None,'','',['ORCA multi-job/fragment constraints require explicit fragment mapping.'])
    if re.search(r'(?i)\boptimizehydrogens\s+true\b',text):
        flags[:]=[[symbol!='H']*3 for symbol in frame.symbols];seen=True
    for block in re.finditer(r'(?is)\bconstraints\b(.*?)\bend\b',text):
        for match in re.finditer(r'\{([^{}]*)\}',block[1]):
            words=match[1].upper().split()
            if len(words)==3 and words[0] in ('C','X','Y','Z') and words[2]=='C':
                indices=_indices(words[1],len(frame.symbols),zero=True)
                axes=range(3) if words[0]=='C' else ['XYZ'.index(words[0])]
                flags[np.ix_(indices,list(axes))]=True;seen=True
            else:notes.append('ORCA internal-coordinate constraint: '+match[0])
    if re.search(r'(?i)\bfreezehydrogens\s+true\b',text):
        notes.append('ORCA freezeHydrogens is relative to heavy atoms, not an absolute Cartesian freeze.')
    # MD commands are sequential; unknown remove operations must not retain a
    # stale mask. Internal-coordinate commands do not imply fixed atoms.
    for match in re.finditer(r'(?im)^\s*Constraint\s+(Add|Remove)\s+(.*)$',text):
        action,body=match[1].lower(),match[2].split()
        if action=='remove':
            if body and body[0].lower()=='all':flags[:]=False;seen=True;continue
            return _result(None,'','',notes+['ORCA MD constraint removal could not be mapped to axes.'])
        if len(body)>=2 and body[0].lower()=='cartesian':
            indices=_indices(body[1],len(frame.symbols),zero=True)
            axis=next((w.upper() for w in body[2:] if w.upper() in ('X','Y','Z','XY','XZ','YZ','XYZ')),'XYZ')
            flags[np.ix_(indices,[i for i,c in enumerate('XYZ') if c in axis])]=True;seen=True
        else:notes.append('ORCA MD internal/collective constraint: '+match[0].strip())
    return _result(flags if seen else None,'cartesian','ORCA explicit Cartesian constraints',notes)


def _gaussian(lines, frame):
    text='\n'.join(lines);notes=[];n=len(frame.symbols)
    if re.search(r'(?im)^\s*--link1--|\bqst[23]\b',text):
        return _result(None,'','',['Gaussian multi-geometry/job constraint mapping needs a sample.'])
    route_match=re.search(r'(?ms)^\s*#([^\n]*(?:\n[^\n]+)*)',text)
    route=route_match[0].lower() if route_match else ''
    flags=np.full((n,3),False,dtype=object);seen=False
    start=_gaussian_geometry_start(lines)
    if start is None:return {}
    row=0;end=start
    for end in range(start,len(lines)):
        line=lines[end].strip()
        if not line:break
        # Commas inside atom properties are retained. Data separators are
        # commas or whitespace outside parentheses.
        parts=_gaussian_tokens(line)
        if parts[0].upper()=='TV':continue
        if row>=n:raise ValueError('Gaussian atom count does not match loaded coordinates.')
        if len(parts)>=5 and re.fullmatch(r'[+-]?\d+',parts[1]):
            try:[float(v.replace('D','E').replace('d','e')) for v in parts[2:5]]
            except ValueError:return _result(None,'','',['Gaussian internal-coordinate freezes are not Cartesian atom freezes.'])
            code=int(parts[1]);seen=True
            if code in (-1,0):flags[row]=[code==-1]*3
            else:
                flags[row]=[None]*3
                notes.append('Gaussian rigid-block or nonstandard freeze code is not a fixed Cartesian atom.')
        elif len(parts)<4:return _result(None,'','',['Gaussian Z-matrix constraints require internal-coordinate interpretation.'])
        row+=1
    if row!=n:return _result(None,'','',['Gaussian atom list does not match loaded geometry.'])
    tail='\n'.join(lines[end+1:])
    if re.search(r'\b(?:readopt(?:imize)?|rdopt|readfreeze|rdfreeze)\b',route):
        if re.search(r'(?i)\b(?:block|notblock|layer|notlayer|residue|notresidue)\s*=',tail):
            return _result(None,'','',notes+['Gaussian ReadOpt layer/block/residue selectors need a sample.'])
        options=re.search(r'(?is)(?:^|\n)\s*((?:noatoms\b|atoms\s*=|notatoms\s*=)[^\n]*(?:\n[^\n]+)*)',tail)
        if not options:return _result(None,'','',notes+['Gaussian ReadOpt atom selection was not found.'])
        body=options[1].strip();active={i for i in range(n) if not all(v is True for v in flags[i])}
        if re.match(r'(?i)^noatoms\b',body):active=set();body=re.sub(r'(?i)^noatoms\b','',body).strip()
        chunks=list(re.finditer(r'(?i)\b(notatoms|atoms)\s*=\s*(.*?)(?=\b(?:notatoms|atoms)\s*=|$)',body,re.S))
        if not chunks:active.update(_indices(body,n,symbols=frame.symbols))
        for chunk in chunks:
            selected=set(_indices(chunk[2],n,symbols=frame.symbols))
            if chunk[1].lower()=='atoms':active.update(selected)
            else:active.difference_update(selected)
        flags[:]=[[i not in active]*3 for i in range(n)];seen=True
    if re.search(r'\b(?:modredundant|addredundant)\b',route):
        if 'gic' in route:notes.append('Gaussian GIC constraints are not represented as Cartesian fixed flags.')
        else:
            for line in tail.splitlines():
                words=line.split('!',1)[0].upper().split()
                if words and words[0]=='X':words=words[1:]
                if len(words)==2 and words[1] in ('F','A') and (words[0].isdigit() or words[0]=='*'):
                    flags[_indices(words[0],n)]=words[1]=='F';seen=True
                elif words and words[-1] in ('F','A'):
                    notes.append('Gaussian bond/angle/internal-coordinate constraint: '+line.strip())
    if re.search(r'\bnofreeze\b',route):flags[:]=False;seen=True
    return _result(flags if seen else None,'cartesian','Gaussian freeze codes / atom constraints',notes)


def _siesta(lines, frame):
    blocks=[];active=False
    for raw in lines:
        line=raw.split('#',1)[0].strip()
        normalized=re.sub(r'[._-]','',line.lower())
        if re.match(r'%block\s+geometryconstraints\b',normalized):active=True;continue
        if active and normalized.startswith('%endblock'):active=False;continue
        if active and line:blocks.append(line)
    if not blocks:return {}
    if any(re.match(r'\s*%include\b',line,re.I) for line in lines):
        return _result(None,'','',['SIESTA external includes may supply additional constraints; free-axis flags are not inferred.'])
    n=len(frame.symbols);counts=np.zeros((n,3),np.int64);seen=False;notes=[];contributions=[]
    for line in blocks:
        words=line.split();kind=words.pop(0).lower();direction=None
        if len(words)>=3 and all(re.fullmatch(r'[-+]?(?:\d*\.\d*|\d+[EeDd][-+]?\d+)',w) for w in words[-3:]):
            direction=np.array([float(w.replace('D','E').replace('d','e')) for w in words[-3:]])
            words=words[:-3]
        if kind not in ('atom','position','z','species-i','clear','clear-prev'):
            notes.append('SIESTA non-atom constraint: '+line);continue
        if direction is not None and np.count_nonzero(direction)!=1:
            return _result(None,'','',notes+['SIESTA non-axis directional constraints cannot be shown as independent X/Y/Z flags.'])
        if kind=='z':
            from ase.data import atomic_numbers
            z=int(words[0]);indices=[i for i,s in enumerate(frame.symbols) if atomic_numbers[s]==z]
        elif kind=='species-i':
            source=[];in_coordinates=False
            for raw in lines:
                clean=raw.split('#',1)[0].strip();normalized=re.sub(r'[._-]','',clean.lower())
                if re.match(r'%block\s+atomiccoordinatesandatomicspecies\b',normalized):in_coordinates=True;continue
                if in_coordinates and normalized.startswith('%endblock'):break
                if in_coordinates and clean:source.append(int(clean.split()[3]))
            if len(source)!=n:raise ValueError('SIESTA species constraint does not match coordinates.')
            indices=[i for i,species in enumerate(source) if species==int(words[0])]
        else:
            selection=' '.join(words)
            match=re.fullmatch(r'from\s+(\d+)\s+(to|plus|minus)\s+(\d+)(?:\s+step\s+(\d+))?',selection,re.I)
            if match:
                lo,value=int(match[1]),int(match[3]);step=int(match[4] or 1)
                hi=value if match[2].lower()=='to' else lo+(value-1)*(1 if match[2].lower()=='plus' else -1)
                if not step or not 1<=lo<=n or not 1<=hi<=n:raise ValueError('Invalid SIESTA atom range.')
                direction_sign=1 if hi>=lo else -1
                indices=list(range(lo-1,hi-1+direction_sign,step*direction_sign))
            elif selection.startswith('[') and selection.endswith(']'):
                indices=[]
                for entry in selection[1:-1].split(','):
                    match=re.fullmatch(r'\s*(\d+)\s*--\s*(\d+)(?:\s+step\s+(\d+))?\s*',entry,re.I)
                    if match:
                        lo,hi=int(match[1]),int(match[2]);step=int(match[3] or 1)
                        if not step or not 1<=lo<=hi<=n:raise ValueError('Invalid SIESTA atom range.')
                        indices.extend(range(lo-1,hi,step))
                    else:indices.extend(_indices(entry,n))
            else:indices=_indices(selection,n)
        if kind in ('clear','clear-prev'):
            selected=set(indices)
            for members,axes in contributions if kind=='clear' else contributions[-1:]:
                removed=members & selected
                if removed:counts[np.ix_(list(removed),axes)]-=1;members.difference_update(removed)
            seen=True;continue
        axes=list(range(3)) if direction is None else list(np.flatnonzero(direction))
        members=set(indices);counts[np.ix_(list(members),axes)]+=1
        contributions.append((members,axes));seen=True
    return _result(counts>0 if seen else None,'cartesian','SIESTA Geometry.Constraints',notes)


def _nwchem(lines, frame):
    text='\n'.join(line.split('#',1)[0] for line in lines);n=len(frame.symbols);notes=[]
    blocks=list(re.finditer(r'(?ims)^\s*constraints([^\n]*)\n(.*?)^\s*end\s*$',text))
    if not blocks:return {}
    # Multiple tasks may select different constraint sets. There is no safe
    # single mask for a legacy reader which supplies only one final geometry.
    if len(re.findall(r'(?im)^\s*task\s+',text))>1:
        return _result(None,'','',['NWChem multiple-task constraint association needs a sample.'])
    selected=re.findall(r'(?im)^\s*set\s+constraints\s+(\S+)',text)
    selected=selected[-1].lower() if selected else 'default'
    flags=np.zeros((n,3),bool);seen=False;enabled=True
    for block in blocks:
        name=block[1].strip().lower() or 'default'
        if name!=selected:continue
        for line in block[2].splitlines():
            words=line.split()
            if not words:continue
            if words[0].lower()=='clear':flags[:]=False;seen=True
            elif words[0].lower()=='enable':enabled=True
            elif words[0].lower()=='disable':enabled=False;seen=True
            elif re.match(r'(?i)^\s*fix\s+atom\b',line):
                flags[_indices(' '.join(words[2:]),n)]=True;seen=True
            else:notes.append('NWChem non-atom constraint: '+line.strip())
    if not enabled:flags[:]=False
    return _result(flags if seen else None,'cartesian','NWChem selected constraints / fix atom',notes)


def read_input_constraints(kind, lines, frame):
    readers={'cp2k_in':_cp2k,'orca_in':_orca,'gaussian_in':_gaussian,'siesta_in':_siesta,'nwchem_in':_nwchem}
    try:
        if kind=='qe_in':
            start=next((i+1 for i,line in enumerate(lines) if re.match(r'\s*ATOMIC_POSITIONS\b',line,re.I)),None)
            return qe_position_constraints(lines[start:start+len(frame.symbols)]) if start is not None else {}
        return readers[kind](lines,frame) if kind in readers else {}
    except (ValueError,IndexError,TypeError) as exc:
        return _result(None,'','',[f'Constraint flags not inferred: {exc}'])


def attach_document_constraints(document, kind):
    frames=document.frames
    if not frames:return
    for frame in frames:
        if ('fixed_axes' not in frame.info or kind in ('vasp_in','vasp_volume')) and 'vasp_fixed_axes' in frame.info:
            frame.info.update(_result(frame.info['vasp_fixed_axes'],'direct','VASP Selective Dynamics (F=fixed)'))
    input_kinds=('cp2k_in','orca_in','gaussian_in','siesta_in','nwchem_in','qe_in')
    if kind not in input_kinds:
        if kind in ('cp2k_out','nwchem_out','siesta_out'):
            from .output_constraints import attach_printed_constraints
            attach_printed_constraints(document, kind)
        if kind.endswith('_out') or kind in ('xtb_trj','cp2k_xyz','vasp_xdatcar','siesta_ani'):
            note='No verified per-atom fixed-axis record was retained from this output/trajectory; missing flags do not mean free atoms.'
            if any('fixed_axes' not in frame.info for frame in frames) and note not in document.note:
                document.note=(document.note+' '+note).strip()
        return
    from .output_text import read_output_lines
    lines=read_output_lines(document.path)
    for frame in frames:frame.info.update(read_input_constraints(kind,lines,frame))


def rotate_fixed_axes(frame, rotation, *, cell_rotated=True, indices=None):
    """Retain exact axis permutations; mark oblique partial constraints unknown."""
    flags=frame.info.get('fixed_axes')
    if flags is None:return
    basis=frame.info.get('fixed_axes_basis','cartesian')
    if basis=='direct' and cell_rotated:return
    rotation=np.asarray(rotation,float).reshape(3,3)
    selected=range(len(frame.symbols)) if indices is None else indices
    out=[list(row) for row in flags];changed=False
    axis_permutation=np.allclose(np.abs(rotation).sum(0),1,atol=1e-10) and np.allclose(np.abs(rotation).sum(1),1,atol=1e-10)
    for index in selected:
        row=out[index]
        if all(v is True for v in row) or all(v is False for v in row):continue
        if axis_permutation and basis=='cartesian':out[index]=[row[int(i)] for i in np.argmax(np.abs(rotation),axis=1)]
        else:out[index]=[None]*3;changed=True
    frame.info['fixed_axes']=out
    if changed:
        notes=list(frame.info.get('constraint_notes',[]))
        notes.append('Partial source constraints were rotated to non-axis directions; axis flags are unknown.')
        frame.info['constraint_notes']=list(dict.fromkeys(notes))
