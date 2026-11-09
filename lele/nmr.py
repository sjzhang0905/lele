"""Printed NMR shieldings, explicit references and uncoupled display spectra."""
from dataclasses import dataclass,field
from math import isfinite
import csv
import numpy as np


@dataclass
class NMRNucleus:
    number: int                         # LELE / structure index, 1-based
    symbol: str
    shielding_ppm: float
    anisotropy_ppm: float | None = None  # retain each program's convention
    tensor: object = None               # rows X,Y,Z; columns X,Y,Z
    source_number: int | None = None
    source_line: int = 0
    span_ppm: float | None = None
    skew: float | None = None
    raw_value_ppm: float | None = None

    def __post_init__(self):
        if self.number<1 or not isfinite(self.shielding_ppm):
            raise ValueError('NMR atom numbers must be positive and shieldings finite.')
        if self.tensor is not None:
            self.tensor=np.asarray(self.tensor,float).reshape(3,3)
            if not np.isfinite(self.tensor).all():raise ValueError('Invalid NMR tensor.')


@dataclass
class NMRResult:
    program: str
    label: str
    source_line: int
    nuclei: list[NMRNucleus] = field(default_factory=list)
    note: str = ''
    frame_index: int | None = None
    reference: object = None
    reference_shieldings: dict = field(default_factory=dict)
    source_path: str = ''

    def elements(self):
        return list(dict.fromkeys(n.symbol for n in self.nuclei))


def chemical_shift(shielding,reference):
    if reference is None or not isfinite(reference):
        raise ValueError('Enter a finite reference shielding for this element before plotting chemical shifts.')
    return float(reference)-float(shielding)


def spectrum(result,element,*,shift=False,fwhm=.3,shape='Lorentzian',points=4096):
    """Equal-area lines per printed nucleus; no J splitting or abundance model."""
    if shape not in ('Lorentzian','Gaussian','Sticks'):raise ValueError('Unknown NMR line shape.')
    if not isfinite(fwhm) or fwhm<=0:raise ValueError('NMR linewidth must be positive.')
    nuclei=[n for n in result.nuclei if n.symbol==element]
    peaks=np.asarray([chemical_shift(n.shielding_ppm,result.reference_shieldings.get(element))
                      if shift else n.shielding_ppm for n in nuclei])
    if not len(peaks):return np.array([]),np.array([]),peaks
    margin=max(2.,8*fwhm,.08*np.ptp(peaks));lo=peaks.min()-margin;hi=peaks.max()+margin
    required=max(points,int((hi-lo)/fwhm*12))
    if shape!='Sticks' and required>100_000:
        raise ValueError('Linewidth too narrow for this range. Increase FWHM or use Sticks to avoid undersampled peaks.')
    count=min(100_000,points if shape=='Sticks' else required)
    x=np.linspace(lo,hi,count);y=np.zeros_like(x)
    if shape!='Sticks':
        # Bound temporary arrays for many nuclei / a very narrow linewidth.
        for peak in peaks:
            t=(x-peak)/fwhm
            if shape=='Lorentzian':y+=(.5/np.pi/fwhm)/(t*t+.25)
            else:y+=np.sqrt(4*np.log(2)/np.pi)/fwhm*np.exp(-4*np.log(2)*t*t)
    return x,y,peaks


def export_nmr_csv(path,result):
    from pathlib import Path
    import os,tempfile
    headings=['program','dataset','atom_1based','element','source_atom','shielding_ppm',
              'reference_shielding_ppm','chemical_shift_ppm','anisotropy_ppm','span_ppm','skew','raw_source_value_ppm',
              *['sigma_'+a+b+'_ppm' for a in 'XYZ' for b in 'XYZ'],'source_line','source_file','note']
    rows=[]
    for n in result.nuclei:
        ref=result.reference_shieldings.get(n.symbol)
        tensor=['']*9 if n.tensor is None else np.asarray(n.tensor).ravel().tolist()
        rows.append([result.program,result.label,n.number,n.symbol,n.source_number,n.shielding_ppm,
                     ref,'' if ref is None else chemical_shift(n.shielding_ppm,ref),n.anisotropy_ppm,
                     n.span_ppm,n.skew,n.raw_value_ppm,*tensor,n.source_line,result.source_path,result.note])
    path=Path(path);temporary=None
    try:
        with tempfile.NamedTemporaryFile('w',encoding='utf-8-sig',newline='',dir=path.parent,
                prefix='.'+path.name+'.',suffix='.tmp',delete=False) as out:
            temporary=Path(out.name)
            writer=csv.writer(out);writer.writerow(headings);writer.writerows(rows)
        os.replace(temporary,path);temporary=None
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)
    return len(rows)
