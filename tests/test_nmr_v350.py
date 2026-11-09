"""Numerical NMR acceptance: synthetic records, independent expected values."""
from pathlib import Path
import csv
import numpy as np
import pytest

from lele.nmr import NMRNucleus,NMRResult,chemical_shift,spectrum,export_nmr_csv
from lele.nmr_input import gaussian,orca,cp2k,gipaw,vasp,nwchem
from lele.formats import load_document

GAUSSIAN=''' SCF GIAO Magnetic shielding tensor (ppm):
 1 O Isotropic = 200.0000 Anisotropy = 30.0000
 XX=190.0 YX=1.0 ZX=2.0
 XY=3.0 YY=200.0 ZY=4.0
 XZ=5.0 YZ=6.0 ZZ=210.0
 2 H Isotropic = 28.0000 Anisotropy = 3.0000
 XX=27.0 YX=0.0 ZX=0.0
 XY=0.0 YY=28.0 ZY=0.0
 XZ=0.0 YZ=0.0 ZZ=29.0
 3 H Isotropic = 26.0000 Anisotropy = 6.0000
 XX=24.0 YX=0.0 ZX=0.0
 XY=0.0 YY=26.0 ZY=0.0
 XZ=0.0 YZ=0.0 ZZ=28.0
'''

ORCA='''CHEMICAL SHIELDINGS (ppm)
Nucleus 1H :
Total shielding tensor (ppm):
 27.0 1.0 2.0
 3.0 28.0 4.0
 5.0 6.0 29.0
CHEMICAL SHIELDING SUMMARY (ppm)
 Nucleus Element Isotropic Anisotropy
 1 H 28.000 3.000
 2 H 26.000 6.000

****ORCA TERMINATED NORMALLY****
'''

CP2K=''' Shielding atom at atomic positions. # tensors printed 1
     3H_kind  H  0.000000 1.800000 0.000000
 SIGMA from SOFT J
 XX=999 XY=0 XZ=0
 YX=0 YY=999 YZ=0
 ZX=0 ZY=0 ZZ=999
 SIGMA TOTAL
 XX=24 XY=1 XZ=2
 YX=3 YY=26 YZ=4
 ZX=5 ZY=6 ZZ=28
 ISOTROPY = 26.0 ANISOTROPY = 6.0
'''

GIPAW=''' Program GIPAW v.7.0
 Synthetic test data, not a physical calculation.
 Atom 1 Si pos: (0 0 0) Total sigma: 999
 Total NMR chemical shifts in ppm:
 Atom 1 Si pos: (0 0 0) Total sigma: 430.00
 420 1 2
 3 430 4
 5 6 440
 Si 1 anisotropy: 30.00 eta: .50
 Atom 2 O pos: (1 1 1) Total sigma: 250.00
 240 0 0
 0 250 0
 0 0 260
 O 2 anisotropy: 30.00 eta: .50
'''

VASP_LEGACY=''' CSA tensor (J. Mason convention)
 EXCLUDING G=0 CONTRIBUTION INCLUDING G=0 CONTRIBUTION
 ATOM ISO_SHIFT SPAN SKEW ISO_SHIFT SPAN SKEW
 (absolute, valence only)
 1 -100.0 21.0 0.1 -105.0 22.0 0.2
 (absolute, valence and core)
 1 -110.0 21.0 0.1 -115.0 22.0 0.2
 IF SPAN.EQ.0 SKEW IS NOT DEFINED
'''

VASP_MODERN=''' CSA tensor (J. Mason convention)
 for chemical shielding (including isotropic core contribution)
 EXCLUDING G=0 CONTRIBUTION INCLUDING G=0 CONTRIBUTION
 ion BDIR X Y Z X Y Z
 ( iso_shield span skew ) ( iso_shield span skew )
 1 1 100 1 2 105 1 2
   2 3 110 4 3 115 4
   3 5 6 120 5 6 125
 (110 21 .1) (115 22 .2)
 IF SPAN.EQ.0
'''

NWCHEM=''' Northwest Computational Chemistry Package (NWChem)
 Chemical Shielding Tensors (GIAO, in ppm)
 Atom: 3 H
 Diamagnetic
 50 0 0
 0 50 0
 0 0 50
 Paramagnetic
 -26 1 2
 3 -24 4
 5 6 -22
 Total Shielding Tensor
 24 1 2
 3 26 4
 5 6 28
 isotropic = 26.0
 anisotropy = 6.0
 Task  times cpu: 10
'''


def test_nwchem_total_tensor_and_printed_atom_subset(tmp_path):
    r=nwchem(NWCHEM.splitlines())[0]
    assert len(r.nuclei)==1 and r.nuclei[0].number==3
    assert r.nuclei[0].shielding_ppm==26
    np.testing.assert_array_equal(r.nuclei[0].tensor,[[24,1,2],[3,26,4],[5,6,28]])
    path=tmp_path/'nwchem.out';path.write_text(NWCHEM)
    doc=load_document(path)
    assert not doc.frames and doc.nmr_results[0].program=='NWChem'


def test_gaussian_multiple_methods_and_tensor_axis_order():
    results=gaussian((GAUSSIAN+' Normal termination\n--Link1--\n'+GAUSSIAN.replace('SCF GIAO','MP2')).splitlines())
    assert len(results)==2
    assert [n.number for n in results[0].nuclei]==[1,2,3]
    np.testing.assert_array_equal(results[0].nuclei[0].tensor,[[190,3,5],[1,200,6],[2,4,210]])
    assert results[0].reference_shieldings=={}


@pytest.mark.parametrize('bad',['********','NaN','1.0D+999'])
def test_gaussian_omits_nonfinite_preserves_other_nuclei(bad):
    r=gaussian(GAUSSIAN.replace('28.0000',bad).splitlines())[0]
    assert [n.number for n in r.nuclei]==[1,3]
    assert 'omitted' in r.note


def test_orca_subset_zero_based_numbers_and_summary_precision():
    r=orca(ORCA.splitlines())[0]
    assert [(n.number,n.source_number,n.shielding_ppm) for n in r.nuclei]==[(2,1,28.),(3,2,26.)]
    np.testing.assert_array_equal(r.nuclei[0].tensor,[[27,1,2],[3,28,4],[5,6,29]])
    assert r.nuclei[1].tensor is None
    # A truncated run can still expose a fully printed total tensor.
    partial=orca(ORCA.split('CHEMICAL SHIELDING SUMMARY')[0].splitlines())[0]
    assert partial.nuclei[0].shielding_ppm==28
    assert 'Summary absent' in partial.note


def test_cp2k_total_only_kind_suffix_and_gipaw_total_only():
    r=cp2k(CP2K.splitlines())[0]
    assert [(n.number,n.symbol,n.shielding_ppm) for n in r.nuclei]==[(3,'H',26)]
    np.testing.assert_array_equal(r.nuclei[0].tensor,[[24,1,2],[3,26,4],[5,6,28]])
    q=gipaw(GIPAW.splitlines())[0]
    assert [(n.symbol,n.shielding_ppm) for n in q.nuclei]==[('Si',430),('O',250)]
    assert q.nuclei[0].anisotropy_ppm==30


def test_vasp_sign_core_g0_and_column_tensor_conventions():
    old=vasp(VASP_LEGACY.splitlines(),['Si'])
    assert len(old)==4
    assert [r.nuclei[0].shielding_ppm for r in old]==[100,105,110,115]
    assert [r.nuclei[0].raw_value_ppm for r in old]==[-100,-105,-110,-115]
    assert 'valence + core' in old[2].label
    assert old[2].nuclei[0].anisotropy_ppm is None
    new=vasp(VASP_MODERN.splitlines(),['Si'])
    assert [r.nuclei[0].shielding_ppm for r in new]==[110,115]
    np.testing.assert_array_equal(new[0].nuclei[0].tensor,[[100,3,5],[1,110,6],[2,4,120]])
    shift=vasp(VASP_MODERN.replace('iso_shield','iso_shift').splitlines(),['Si'])
    assert shift[0].nuclei[0].shielding_ppm==-110
    np.testing.assert_array_equal(shift[0].nuclei[0].tensor,-new[0].nuclei[0].tensor)


@pytest.mark.parametrize('parser,text',[(gaussian,GAUSSIAN),(orca,ORCA),(cp2k,CP2K),(gipaw,GIPAW),(vasp,VASP_MODERN)])
def test_every_truncation_is_safe_and_only_finite_results(parser,text):
    lines=text.splitlines()
    for end in range(len(lines)+1):
        for r in parser(lines[:end]):
            assert all(np.isfinite(n.shielding_ppm) for n in r.nuclei)


def test_references_line_positions_equal_area_and_csv(tmp_path):
    r=gaussian(GAUSSIAN.splitlines())[0]
    with pytest.raises(ValueError,match='reference'):spectrum(r,'H',shift=True)
    r.reference_shieldings['H']=31.
    for shape in ('Gaussian','Lorentzian','Sticks'):
        x,y,peaks=spectrum(r,'H',shift=True,shape=shape,fwhm=.1)
        np.testing.assert_array_equal(peaks,[3.,5.])
        if shape=='Gaussian':assert np.trapezoid(y,x)==pytest.approx(2.,abs=.0001)
        if shape=='Lorentzian':assert np.trapezoid(y,x)==pytest.approx(2.,abs=.025)
    path=tmp_path/'nmr.csv';assert export_nmr_csv(path,r)==3
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    assert rows[0]['chemical_shift_ppm']==''
    assert float(rows[1]['chemical_shift_ppm'])==3
    assert float(rows[0]['sigma_XY_ppm'])==3
    with pytest.raises(ValueError):chemical_shift(25,float('inf'))


def test_narrow_lines_never_silently_undersampled():
    r=NMRResult('Test','Narrow',1,[NMRNucleus(1,'C',0),NMRNucleus(2,'C',200)])
    with pytest.raises(ValueError,match='undersampled'):spectrum(r,'C',fwhm=.001)
    np.testing.assert_array_equal(spectrum(r,'C',fwhm=.001,shape='Sticks')[2],[0,200])


@pytest.mark.parametrize('suffix,text,expected',[('.data',CP2K,'CP2K'),('.out',GIPAW,'QE GIPAW'),
    ('.log',' Entering Gaussian System\n'+GAUSSIAN,'Gaussian'),('.out',' O   R   C   A\n'+ORCA,'ORCA')])
def test_results_only_import_no_invented_geometry(tmp_path,suffix,text,expected):
    path=tmp_path/('nmr'+suffix);path.write_text(text)
    doc=load_document(path)
    assert not doc.frames
    assert doc.nmr_results[0].program==expected
    assert doc.nmr_results[0].frame_index is None


def test_full_gaussian_import_frame_link_and_project_roundtrip(tmp_path):
    from lele.project_file import save_project,load_project
    from test_projects_v230 import state_for
    base=Path(__file__).resolve().parents[1]/'examples/synthetic_properties.log'
    text=base.read_text().split(' Normal termination')[0]+'\n'+GAUSSIAN+' Normal termination of Gaussian 16\n'
    path=tmp_path/'nmr.log';path.write_text(text.replace('freq b3lyp','nmr b3lyp'))
    doc=load_document(path);r=doc.nmr_results[0]
    assert r.frame_index==len(doc.frames)-1
    assert r.reference.symbols==['O','H','H']
    assert 'NMR' in doc.calculation_results.jobs[0].tasks
    r.reference_shieldings={'H':31.0}
    project=tmp_path/'nmr.lele';save_project(project,state_for(doc))
    restored=load_project(project)['documents'][0]['document'].nmr_results[0]
    assert restored.reference_shieldings=={'H':31.0}
    np.testing.assert_array_equal(restored.nuclei[0].tensor,r.nuclei[0].tensor)
    # A subsequent checkpoint-only job must not attach to earlier geometry.
    path.write_text(text+'--Link1--\n #p nmr geom=allcheck\n\n'+GAUSSIAN)
    doc=load_document(path)
    assert doc.nmr_results[-1].frame_index is None
