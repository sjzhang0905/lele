"""NWChem SCF chunks with bounded continuation context and progress.

ASE may reparse a growing history when successive electronic modules omit a
geometry. Retain only its last geometry/gradient/cell and energy lines for a
continuation. These are exactly the fields consumed by LELE's Frame adapter;
orbital, stress and multipole tables are not Frame data.
"""
from .output_text import read_output_lines,scan_lines,check_load_cancelled


def _context(text,reader):
    patterns=[reader._geom,reader._cell_block,reader._gto_grad,*reader._e_gto.values(),
              reader._nwpw_energy,reader._nwpw_grad,reader._paw_grad]
    pieces=[]
    for pattern in patterns:
        match=None
        for match in pattern.finditer(text):pass
        if match is not None:pieces.append((match.start(),match.group(0)))
    return '\n'.join(value for _,value in sorted(pieces))+'\n'


def read_nwchem_frames(path,max_frames=None):
    from ase.io.nwchem import nwreader as reader
    from .formats import _frame_from_ase
    lines=read_output_lines(path);frames=[];group=[];parser=None
    header=True;context='';last_parser=None;last_converged=False

    def append(atoms,text):
        if atoms is None:raise ValueError('Incomplete NWChem calculation chunk')
        if max_frames is not None and len(frames)>=max_frames:
            raise ValueError(f'Trajectory exceeds {max_frames} frames')
        frame=_frame_from_ase(atoms)
        if any(line.strip()=='Optimization converged' for line in text.splitlines()):
            frame.info['optimization_converged']=True
        frames.append(frame)
        return bool(frame.info.get('optimization_converged'))

    for _,line in scan_lines(lines,'NWChem: electronic modules and geometries'):
        raw=line+'\n';group.append(raw)
        if reader._gauss_block.match(raw):next_parser=reader.parse_gto_chunk
        elif reader._pw_block.match(raw):next_parser=reader.parse_pw_chunk
        else:continue
        if header:header=False
        else:
            check_load_cancelled();text=''.join(group);atoms=parser(text)
            if atoms is None and parser is last_parser:
                combined=context+text
                atoms=parser(combined)
                if atoms is not None:
                    frame=_frame_from_ase(atoms)
                    if last_converged or any(l.strip()=='Optimization converged' for l in text.splitlines()):
                        frame.info['optimization_converged']=True;last_converged=True
                    frames[-1]=frame
                    context=_context(combined,reader)
            else:
                last_converged=append(atoms,text)
                context=text;last_parser=parser
            group=[]
        parser=next_parser
    if not header:
        text=''.join(group);atoms=parser(text)
        if atoms is not None:append(atoms,text)
        elif frames and parser is last_parser and any(l.strip()=='Optimization converged' for l in text.splitlines()):
            frames[-1].info['optimization_converged']=True
    if not frames:raise ValueError('No complete NWChem geometries')
    return frames
