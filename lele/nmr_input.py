"""NMR output readers. Preserve program conventions and separate datasets.

No chemical-shift references are assumed. In VASP ISO_SHIFT tables the printed
absolute shift is minus shielding; ISO_SHIELD tables are already shieldings.
"""
from pathlib import Path
import re
import numpy as np
from .nmr import NMRNucleus,NMRResult
from .output_text import read_output_lines,progress_items,check_load_cancelled

NUMBER=r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?'


def number(text):
    value=float(text.replace('D','E').replace('d','e'))
    if not np.isfinite(value):raise ValueError('Non-finite NMR value')
    return value


def labeled_tensor(lines):
    try:
        entries={key:number(value) for line in lines for key,value in
                 re.findall(r'\b([XYZ]{2})\s*=\s*('+NUMBER+r')',line,re.I)}
    except ValueError:return None
    entries={key.upper():value for key,value in entries.items()}
    if len(entries)!=9:return None
    return np.array([[entries[a+b] for b in 'XYZ'] for a in 'XYZ'])


def matrix_rows(lines):
    rows=[]
    for line in lines:
        bits=line.split()
        if len(bits)!=3:break
        try:rows.append([number(v) for v in bits])
        except ValueError:break
        if len(rows)==3:return np.array(rows)
    return None


def gaussian(lines):
    results=[];current=None;invalid=0
    record=re.compile(r'^\s*(\d+)\s+([A-Za-z]+)\s+Isotropic\s*=\s*('+NUMBER+r')\s+Anisotropy\s*=\s*('+NUMBER+r')',re.I)
    for i,line in progress_items(enumerate(lines),'Reading Gaussian NMR'):
        if re.search(r'Magnetic shielding.*\(ppm\)',line,re.I):
            current=NMRResult('Gaussian',line.strip().rstrip(':'),i+1)
            results.append(current)
        match=record.match(line)
        if match and current is not None:
            source=int(match[1]);symbol=match[2].capitalize()
            # Multiple methods or repeated NMR steps must remain distinct.
            if any(n.source_number==source for n in current.nuclei):
                current=NMRResult('Gaussian',current.label,i+1);results.append(current)
            try:
                current.nuclei.append(NMRNucleus(source,symbol,number(match[3]),number(match[4]),
                    labeled_tensor(lines[i+1:i+4]),source,i+1))
            except ValueError:invalid+=1
        elif current is not None and re.search(r'Isotropic\s*=',line,re.I):invalid+=1
        if '--Link1--' in line or 'termination' in line.lower():current=None
    if invalid:
        for r in results:r.note=f'{invalid} non-finite or incomplete printed NMR record(s) omitted.'
    return [r for r in results if r.nuclei]


def orca(lines):
    results=[];current=None;details={};i=0
    header=re.compile(r'CHEMICAL SHIELDINGS?\s*\(ppm\)',re.I)
    summary=re.compile(r'CHEMICAL SHIELDING SUMMARY\s*\(ppm\)',re.I)
    atom=re.compile(r'^\s*Nucleus\s+(\d+)\s*([A-Za-z]+)\s*:')
    row=re.compile(r'^\s*(\d+)\s+([A-Za-z]+)\s+('+NUMBER+r')\s+('+NUMBER+r')\s*$')
    while i<len(lines):
        if i%128==0:check_load_cancelled()
        line=lines[i]
        if header.search(line):
            current=NMRResult('ORCA','Chemical shielding',i+1,note='Source nucleus numbers are 0-based; LELE atom numbers are 1-based.')
            results.append(current);details={}
        match=atom.match(line)
        if match and current is not None:
            no=int(match[1]);j=i+1
            while j<min(i+70,len(lines)) and not atom.match(lines[j]) and not summary.search(lines[j]):
                if 'Total shielding tensor (ppm)' in lines[j]:
                    tensor=matrix_rows(lines[j+1:j+4])
                    if tensor is not None:
                        details[no]=NMRNucleus(no+1,match[2].capitalize(),float(np.trace(tensor)/3),
                            tensor=tensor,source_number=no,source_line=i+1)
                    break
                j+=1
        if summary.search(line):
            if current is None or current.nuclei:
                current=NMRResult('ORCA','Chemical shielding summary',i+1,
                    note='Source nucleus numbers are 0-based; LELE atom numbers are 1-based.')
                results.append(current);details={}
            j=i+1;started=False
            while j<len(lines):
                if j%128==0:check_load_cancelled()
                m=row.match(lines[j])
                if m:
                    no=int(m[1]);n=details.get(no)
                    try:
                        current.nuclei.append(NMRNucleus(no+1,m[2].capitalize(),number(m[3]),number(m[4]),
                            None if n is None else n.tensor,no,j+1))
                    except ValueError:pass
                    started=True
                elif started and lines[j].strip():break
                elif not started and j-i>12:break
                j+=1
            i=j-1
        if ('ORCA TERMINATED' in line or i==len(lines)-1) and current is not None:
            if not current.nuclei and details:
                current.nuclei=list(details.values());current.note+=' Summary absent; isotropy from printed total tensor trace.'
            current=None;details={}
        i+=1
    return [r for r in results if r.nuclei]


def cp2k(lines):
    results=[];current=None;pending=None
    atom=re.compile(r'^\s*(\d+)\s*\S+\s+([A-Z][a-z]?)\s+('+NUMBER+r')\s+('+NUMBER+r')\s+('+NUMBER+r')\s*$')
    for i,line in progress_items(enumerate(lines),'Reading CP2K NMR'):
        if 'Shielding atom at atomic positions' in line:
            current=NMRResult('CP2K','Total shielding at atomic positions',i+1,
                note='From the CP2K SHIFT print file; anisotropy follows the printed CP2K convention. No geometry association is inferred from a subset of nuclei.')
            results.append(current);pending=None
        if current is None:continue
        m=atom.match(line)
        if m:pending=(int(m[1]),m[2],i+1,None)
        if pending is not None and line.strip()=='SIGMA TOTAL':
            pending=(*pending[:3],labeled_tensor(lines[i+1:i+4]))
        m=re.search(r'ISOTROPY\s*=\s*('+NUMBER+r')\s+ANISOTROPY\s*=\s*('+NUMBER+r')',line)
        if m and pending is not None:
            no,sym,start,tensor=pending
            try:current.nuclei.append(NMRNucleus(no,sym,number(m[1]),number(m[2]),tensor,no,start))
            except ValueError:pass
            pending=None
        if 'NICS' in line.upper() and 'shielding' in line.lower():current=None;pending=None
    return [r for r in results if r.nuclei]


def gipaw(lines):
    results=[];current=None
    atom=re.compile(r'^\s*Atom\s+(\d+)\s+([A-Z][a-z]?)\s+pos:.*?Total sigma:\s*('+NUMBER+r')',re.I)
    for i,line in progress_items(enumerate(lines),'Reading QE GIPAW NMR'):
        if re.search(r'Total NMR chemical (?:shifts|shieldings) in ppm',line,re.I):
            current=NMRResult('QE GIPAW','Total NMR shielding',i+1,
                note='Total sigma is absolute shielding. Anisotropy retains GIPAW’s printed convention; component contributions are not counted as extra nuclei.')
            results.append(current)
        m=atom.match(line)
        if m and current is not None:
            aniso=None
            for follow in lines[i+4:i+8]:
                a=re.search(r'anisotropy:\s*('+NUMBER+r')',follow,re.I)
                if a:
                    try:aniso=number(a[1])
                    except ValueError:pass
                    break
            no=int(m[1])
            try:current.nuclei.append(NMRNucleus(no,m[2],number(m[3]),aniso,
                matrix_rows(lines[i+1:i+4]),no,i+1))
            except ValueError:pass
    return [r for r in results if r.nuclei]


def nwchem(lines):
    results=[];current=None;pending=None
    for i,line in progress_items(enumerate(lines),'Reading NWChem NMR'):
        if re.search(r'Chemical Shielding Tensors.*ppm',line,re.I):
            current=NMRResult('NWChem',line.strip(),i+1,
                note='Printed total shielding only; separate diamagnetic / paramagnetic terms are not duplicated.');results.append(current)
        if 'NWChem Input Module' in line or 'Task  times' in line:
            current=None;pending=None
        if current is None:continue
        m=re.match(r'^\s*Atom:\s*(\d+)\s+([A-Z][a-z]?)\b',line)
        if m:pending=(int(m[1]),m[2],i+1)
        if 'Total Shielding Tensor' in line and pending is not None:
            no,sym,start=pending;tensor=matrix_rows(lines[i+1:i+4])
            iso=None;aniso=None
            for follow in lines[i+4:i+9]:
                m=re.match(r'^\s*(isotropic|anisotropy)\s*=\s*('+NUMBER+r')',follow)
                if m:
                    try:value=number(m[2])
                    except ValueError:continue
                    if m[1]=='isotropic':iso=value
                    else:aniso=value
            if iso is not None and no>0:
                if any(n.number==no for n in current.nuclei):
                    current=NMRResult('NWChem',current.label,start,note=current.note);results.append(current)
                current.nuclei.append(NMRNucleus(no,sym,iso,aniso,tensor,no,start))
            pending=None
    return [r for r in results if r.nuclei]


def vasp(lines,symbols=()):
    results=[];i=0
    while i<len(lines):
        if i%128==0:check_load_cancelled()
        if 'CSA tensor' not in lines[i]:i+=1;continue
        start=i;j=i+1
        while j<len(lines) and not re.search(r'IF\s+SPAN|CSA tensor',lines[j],re.I):j+=1
        segment=lines[start:j]
        header=' '.join(segment[:20]).lower()
        modern='bdir' in header
        sign=1. if 'iso_shield' in header else -1.
        group='valence + core' if modern and 'core contribution' in header else 'valence only'
        pair=None
        def create_pair(label,line):
            note=('ISO_SHIFT is negated to shielding; no reference shift has been added. ' if sign<0 else
                  'ISO_SHIELD is retained as shielding. ')
            records=[NMRResult('VASP',label+' · '+g,line,
                     note=note+'SPAN and SKEW retain their printed conventions.')
                     for g in ('excluding G=0','including G=0')]
            results.extend(records);return records
        k=0
        while k<len(segment):
            line=segment[k]
            if '(absolute,' in line.lower():
                group='valence + core' if 'core' in line.lower() else 'valence only'
                pair=create_pair(group,start+k+1)
            bits=line.split()
            if not modern and pair is not None and len(bits)==7 and bits[0].isdigit():
                try:vals=[number(v) for v in bits[1:]]
                except ValueError:k+=1;continue
                no=int(bits[0]);sym=symbols[no-1] if 0<no<=len(symbols) else '?'
                if no<1:k+=1;continue
                for g in range(2):
                    iso,span,skew=vals[g*3:g*3+3]
                    pair[g].nuclei.append(NMRNucleus(no,sym,sign*iso,source_number=no,
                        source_line=start+k+1,span_ppm=span,skew=skew,raw_value_ppm=iso))
            elif modern and len(bits)==8 and bits[0].isdigit() and bits[1]=='1':
                no=int(bits[0]);sym=symbols[no-1] if 0<no<=len(symbols) else '?'
                if no<1:k+=1;continue
                try:
                    values=[[number(v) for v in bits[2:]]]
                    for offset in (1,2):
                        rest=segment[k+offset].split()
                        if len(rest)!=7 or rest[0]!=str(offset+1):raise ValueError()
                        values.append([number(v) for v in rest[1:]])
                    iso_values=[number(v) for v in re.findall(NUMBER,segment[k+3])]
                    if len(iso_values)!=6 or '(' not in segment[k+3]:raise ValueError()
                except (ValueError,IndexError):k+=1;continue
                if pair is None:pair=create_pair(group,start+1)
                for g in range(2):
                    iso,span,skew=iso_values[g*3:g*3+3]
                    # Each printed BDIR row is an applied-field column.
                    tensor=sign*np.array(values)[:,g*3:g*3+3].T
                    pair[g].nuclei.append(NMRNucleus(no,sym,sign*iso,tensor=tensor,source_number=no,
                        source_line=start+k+1,span_ppm=span,skew=skew,raw_value_ppm=iso))
                k+=3
            k+=1
        i=j
    return [r for r in results if r.nuclei]


def read_nmr_results(path,kind='',document=None):
    supported={'gaussian_out','orca_out','vasp_out','cp2k_out','qe_out','nwchem_out','nmr_output'}
    if kind not in supported:return []
    lines=read_output_lines(path)
    # Most long MD / optimization outputs contain no shielding calculation.
    # A bounded C-level text search avoids another regex-heavy per-line pass,
    # while still examining the entire file (including NMR appended at EOF).
    marker = {'gaussian_out':'shielding', 'orca_out':'shielding',
              'vasp_out':'csa tensor', 'cp2k_out':'shielding atom at atomic positions',
              'qe_out':'total nmr chemical', 'nwchem_out':'shielding'}.get(kind)
    if marker is not None:
        for offset in range(0,len(lines),4096):
            check_load_cancelled()
            if marker in '\n'.join(lines[offset:offset+4096]).lower():
                break
        else:
            return []
    if kind=='gaussian_out':results=gaussian(lines)
    elif kind=='orca_out':results=orca(lines)
    elif kind=='vasp_out':results=vasp(lines,document.frames[-1].symbols if document and document.frames else ())
    elif kind=='cp2k_out':results=cp2k(lines)
    elif kind=='qe_out':results=gipaw(lines)
    elif kind=='nwchem_out':results=nwchem(lines)
    else:
        header='\n'.join(lines[:150])
        results=cp2k(lines) if 'Shielding atom at atomic positions' in header else gipaw(lines)
    for result in results:
        result.source_path=str(path)
        if document is None or not document.frames:continue
        records=getattr(document.calculation_results,'steps',[])
        possible=[s for s in records if s.source_line<=result.source_line and s.frame_index is not None]
        if possible:
            chosen=max(possible,key=lambda s:s.source_line);index=chosen.frame_index
            # Do not link checkpoint-only later jobs to a previous job's atoms.
            jobs=getattr(document.calculation_results,'jobs',[])
            current=[j for j in jobs if j.start_line<=result.source_line]
            if current and chosen.job_index!=max(current,key=lambda j:j.start_line).index:continue
        elif result.program=='VASP':index=len(document.frames)-1
        else:continue
        frame=document.frames[index]
        if all(0<n.number<=len(frame.symbols) and n.symbol==frame.symbols[n.number-1] for n in result.nuclei):
            result.frame_index=index;result.reference=frame.clone()
    return results


def standalone_nmr_kind(path):
    """Recognize property-only companion files without treating inputs as results."""
    with Path(path).open('r',encoding='utf-8',errors='replace') as stream:head=stream.read(32768)
    if 'Shielding atom at atomic positions' in head:return 'CP2K NMR shielding'
    if re.search(r'Program\s+GIPAW\b',head):return 'QE GIPAW NMR'
    return None
