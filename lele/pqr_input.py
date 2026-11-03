"""PQR records parsed consistently as whitespace fields or fixed columns."""
from pathlib import Path
import re
import numpy as np
from ase import Atoms
from .output_text import open_output_text, check_load_cancelled


_BIOMOLECULE_RESIDUES=set(('ALA ARG ASN ASP ASH CYS CYM CYX GLN GLU GLH GLY HIS HID HIE HIP '
    'ILE LEU LYS LYN MET MSE PHE PRO SER THR TRP TYR VAL ASX GLX ACE NME '
    'A C G U T I DA DC DG DT DU DI HOH WAT H2O').split())


def _element(name,residue,normalize):
    clean=re.sub(r'^\d+','',name)
    # Protein/nucleic atom labels (CA, CD1, NE2, HG1) name positions,
    # not calcium/cadmium/neon/mercury. Proper-case element labels and
    # ion residues keep the general element-name interpretation.
    if residue.upper()=='MSE' and clean.upper()=='SE':return 'Se'
    if (residue.upper() in _BIOMOLECULE_RESIDUES and clean
            and clean[0].upper() in 'CHNOPS' and not clean[1:2].islower()):
        return clean[0].upper()
    return normalize(clean)


def _real(value):
    value=float(value.replace('D','E').replace('d','e'))
    if not np.isfinite(value):raise ValueError('Non-finite PQR numeric value.')
    return value


def _fields(parts):
    if len(parts) not in (10,11):raise ValueError('Expected 10 or 11 PQR fields (optional chain ID).')
    int(parts[1]);int(parts[-6])
    values=[_real(value) for value in parts[-5:]]
    if values[-1]<0:raise ValueError('PQR radius cannot be negative.')
    return parts[2],parts[3],values[:3]


def _fixed(raw):
    # Preserve historical PDB-column PQR input as a complete separate record.
    # Never combine coordinates from one layout with an atom name from another.
    if raw[:6] not in ('ATOM  ','HETATM'):raise ValueError('Not a fixed-column atom record.')
    int(raw[6:11]);int(raw[22:26]);name=raw[12:16].strip()
    if not name or not raw[17:20].strip():raise ValueError('Invalid fixed-column PQR atom name/residue.')
    coordinates=[_real(raw[a:b].strip()) for a,b in ((30,38),(38,46),(46,54))]
    tail=raw[54:].split()
    if len(tail) not in (2,3):raise ValueError('Missing fixed-column PQR charge/radius.')
    _real(tail[0])
    if _real(tail[1])<0:raise ValueError('PQR radius cannot be negative.')
    # A genuine explicit element column is an optional legacy extension.
    element=raw[76:78].strip() if len(raw)>=78 else ''
    if len(tail)==3:
        if not element or tail[2]!=element:raise ValueError('Invalid PQR trailing field.')
        name=element
    return name,'' if len(tail)==3 else raw[17:20].strip(),coordinates


def read_pqr_atoms(path):
    from .legacy_converter import ConversionError,normalize_element
    symbols=[];positions=[]
    with open_output_text(Path(path)) as stream:
        for number,raw in enumerate(stream,1):
            check_load_cancelled();parts=raw.split()
            if not parts or parts[0] not in ('ATOM','HETATM'):continue
            try:
                try:name,residue,coordinates=_fields(parts)
                except (ValueError,IndexError):name,residue,coordinates=_fixed(raw)
                symbol=_element(name,residue,normalize_element)
            except (ValueError,IndexError,ConversionError) as exc:
                raise ConversionError(f'Invalid PQR atom record at line {number}: {exc}') from exc
            symbols.append(symbol);positions.append(coordinates)
    if not positions:raise ConversionError('No ATOM/HETATM coordinates were found in PQR file')
    return Atoms(symbols=symbols,positions=positions)
