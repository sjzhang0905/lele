"""Physical units, spectra, moment types, boundary images and clipboard data."""
from pathlib import Path
from dataclasses import replace
import csv
import numpy as np
import pytest
from ase.units import Hartree
from lele.core import Frame,Document,visible_bonds
from lele.formats import load_document
from lele.gaussian_properties import read_gaussian_properties,selected_dipole,AU_TO_DEBYE
from lele.spectra import simulated_spectrum,broaden,vibrational_lines,raman_strength
from lele.energy_units import display_energy,EV_TO_KCAL_MOL,rigid_equivalent
from lele.property_export import export_transitions,export_dipoles,transition_rows
from lele.boundary import boundary_view
from lele.atom_clipboard import copy_atoms,read_atoms,paste_atoms
from lele.atom_appearance import AtomAppearance

EXAMPLE=Path(__file__).resolve().parents[1]/'examples/synthetic_properties.log'

def test_gaussian_moment_types_gauges_and_conversion():
    d=load_document(EXAMPLE);assert len(d.dipoles)==2 and len(d.electronic_spectra)==1
    assert [(r.kind,r.density,r.state_number) for r in d.dipoles]==[('permanent','SCF',None),('excited permanent','CI',1)]
    t=d.electronic_spectra[0].transitions[0]
    np.testing.assert_allclose(t.electric_dipole_au,[1,-1,2.1915]);np.testing.assert_allclose(t.velocity_dipole_au,[.1,.2,.3])
    np.testing.assert_allclose(t.magnetic_dipole_au,[.001,.002,.003])
    assert abs(transition_rows(d)[0]['oscillator_strength_from_mu']-.5)<2e-5
    f=d.frames[-1]
    np.testing.assert_allclose(selected_dipole(d,f,'transition:0:1'),t.electric_dipole_au*AU_TO_DEBYE)
    np.testing.assert_allclose(selected_dipole(d,f,'permanent'),[1,-2,2])
    np.testing.assert_allclose(selected_dipole(d,f,'permanent:1'),[1.5,-.5,2.5])

def test_rotated_dipoles_follow_rigid_geometry_only():
    d=load_document(EXAMPLE);f=d.frames[-1].clone();r=np.array([[0,-1,0],[1,0,0],[0,0,1]])
    f.positions=f.positions@r.T+[4,5,6]
    np.testing.assert_allclose(selected_dipole(d,f,'permanent'),np.array([1,-2,2])@r.T)
    f.positions[0,0]+=.1;assert selected_dipole(d,f,'permanent') is None

def test_repeated_td_missing_moments_and_ci_without_td_not_excited(tmp_path):
    text=EXAMPLE.read_text();extra='\n Excited State 1: Singlet-A 3.5 eV 354.2 nm f=0.2\n'
    path=tmp_path/'repeat.log';path.write_text(text[:text.rfind(' Normal termination')]+extra)
    _,spectra=read_gaussian_properties(path);assert len(spectra)==2
    assert spectra[-1].transitions[0].electric_dipole_au is None
    cut=text[:text.index(' Ground to excited')].replace('SCF Density','CI Density')
    path.write_text(cut);records,_=read_gaussian_properties(path);assert records[0].kind=='permanent'

def test_csv_raw_values_missing_zero_and_permanent_record_ids(tmp_path):
    d=load_document(EXAMPLE)
    d.electronic_spectra[0].transitions.append(replace(d.electronic_spectra[0].transitions[0],number=4,electric_dipole_au=None))
    path=tmp_path/'td.csv';assert export_transitions(path,d)==4
    assert path.read_bytes().startswith(b'\xef\xbb\xbf')
    rows=list(csv.DictReader(path.open(encoding='utf-8-sig')))
    assert rows[2]['electric_x_au']=='0.0' and rows[3]['electric_x_au']==''
    assert rows[0]['to_state']=='1' and float(rows[0]['oscillator_strength'])==.5
    assert export_dipoles(tmp_path/'mu.csv',d)==6
    rows=list(csv.DictReader((tmp_path/'mu.csv').open(encoding='utf-8-sig')))
    assert rows[1]['kind']=='excited permanent' and rows[1]['record']=='2' and rows[1]['calculation']==''

def test_ir_raman_positive_modes_and_uv_peak():
    d=load_document(EXAMPLE);assert [m.raman_activity for m in d.vibrations[0].modes]==[1,2,3]
    assert len(vibrational_lines(d.vibrations[0],'IR'))==2
    assert len(vibrational_lines(d.vibrations[0],'Raman'))==2
    x,y,_=simulated_spectrum(d,'UV-Vis',fwhm=.05)
    assert abs(x[y.argmax()]-413.2807)<.5
    x,y,_=simulated_spectrum(d,'IR',fwhm=8);assert abs(x[y.argmax()]-3600)<2
    assert raman_strength(1500,2,532,500)>raman_strength(1500,2,532,100)
    assert raman_strength(25000,1,532) is None
    d.vibrations[0].modes[1].raman_activity=None;d.vibrations[0].modes[2].raman_activity=None
    with pytest.raises(ValueError):simulated_spectrum(d,'Raman')

@pytest.mark.parametrize('shape',['Gaussian','Lorentzian'])
def test_broadening_width_and_area(shape):
    x=np.linspace(-1000,1000,100001);y=broaden(x,[0],[1],10,shape)
    assert abs(np.trapezoid(y,x)-1)<.004
    assert abs(y[np.argmin(abs(x-5))]/y.max()-.5)<1e-9

def test_energy_contract_source_software_and_rigidity():
    f=Frame(['C','H','H'],[[0,0,0],[1,0,0],[0,1,0]],np.eye(3)*10,(True,)*3,1.)
    f.info['source_kind']='gaussian_out';value,unit=display_energy(f);assert unit=='kcal/mol'
    assert abs(value-EV_TO_KCAL_MOL)<1e-12 and abs(Hartree*EV_TO_KCAL_MOL-627.509)<.001
    f.info['source_kind']='siesta_out';f.pbc=(False,)*3;assert display_energy(f)==(1.,'eV')
    f.info['source_kind']='ase_generic';f.info['source_format']='VASP vasprun.xml'
    assert display_energy(f)==(1.,'eV')
    g=f.clone();g.positions+=3;assert rigid_equivalent(f,g)
    g.positions[0,0]+=.1;assert not rigid_equivalent(f,g)
    f.energy_ev=float('nan');assert display_energy(f)[0] is None

def test_occluded_long_bond_removed_triangle_and_manual_override_preserved():
    f=Frame(['C']*3,[[0,0,0],[.8,0,0],[1.6,0,0]])
    assert visible_bonds(f)==[(0,1),(1,2)]
    f.bond_added.add((0,2));assert (0,2) in visible_bonds(f)
    triangle=Frame(['C']*3,[[0,0,0],[1.2,0,0],[.6,1.,0]])
    assert len(visible_bonds(triangle))==3

def test_boundary_whole_cells_bonds_source_ids_and_skew_ranges():
    f=Frame(['Si'],[[0,0,0]],np.eye(3)*2.2,(True,)*3,atom_appearance={0:AtomAppearance(opacity=.3)})
    v=boundary_view(f,((0,2),(0,2),(0,1)));assert len(v.source_indices)==4 and len(v.bonds)==4
    assert set(v.source_indices)=={0} and all(s.opacity==.3 for s in v.frame.atom_appearance.values())
    assert len(f.symbols)==1;np.testing.assert_allclose(f.cell,np.eye(3)*2.2)
    f.cell=np.array([[3,0,0],[.5,4,0],[.4,.2,5]])
    v=boundary_view(f,((-1,2),(0,1),(0,1)));fractions=v.frame.positions@np.linalg.inv(f.cell)
    assert np.all(fractions[:,0]>=-1) and np.all(fractions[:,0]<2)
    for bounds in [((0,0),(0,1),(0,1)),((-10,10),)*3]:
        with pytest.raises(ValueError):boundary_view(f,bounds)

def test_clipboard_metadata_cross_file_paste_target_cell_and_undo_ready_data():
    f=Frame(['O','H','H'],[[0,0,0],[1,0,0],[0,1,0]],bond_removed={(0,1)},atom_appearance={1:AtomAppearance(opacity=.4,color='#123456')})
    text,data=copy_atoms(f,[0,1]);fragment=read_atoms(text,data)
    target=Frame(['Si'],[[0,0,0]],np.eye(3)*6,(True,)*3,-12.,{'poscar_groups':[('Si',1)]})
    assert paste_atoms(target,fragment,[4,3,2])==[1,2]
    np.testing.assert_allclose(target.positions[1:].mean(axis=0),[4,3,2]);np.testing.assert_allclose(target.cell,np.eye(3)*6)
    assert target.atom_appearance[2].opacity==.4 and target.bond_removed=={(1,2)} and target.energy_ev is None
    assert target.info['poscar_groups']==[('Si',1),('O',1),('H',1)]
    assert read_atoms(text).symbols==['O','H']

def test_shared_palette_dithering_stream_and_supersampled_render(tmp_path):
    from PIL import Image
    from lele.animation_export import write_gif,GifSettings,_OffscreenScene
    from lele.render_options import RenderOptions
    gradient=np.tile(np.arange(128,dtype=np.uint8),(64,1));a=np.dstack((gradient*2,gradient,255-gradient))
    b=a.copy();b[20:40,20:40]=[255,0,0]
    images=[Image.fromarray(a),Image.fromarray(b)]
    atlas=Image.new('RGB',(128,128));atlas.paste(images[0],(0,0));atlas.paste(images[1],(0,64));palette=atlas.quantize(colors=256)
    path=tmp_path/'shared.gif';write_gif(path,images,[100,100],palette=palette,dither=True)
    with Image.open(path) as gif:
        assert gif.n_frames==2 and gif.size==(128,64)
        first=np.asarray(gif.convert('RGB')).copy();gif.seek(1);second=np.asarray(gif.convert('RGB'))
        np.testing.assert_array_equal(first[:15],second[:15])
        assert np.sqrt(np.mean((first.astype(float)-a)**2))<10
    scene=_OffscreenScene(GifSettings(width=100,height=80,supersample=2),RenderOptions(),None,(),(100,80))
    try:
        assert scene.window.GetSize()==(200,160)
        image=scene.render(Frame(['C'],[[0,0,0]]),None);assert image.size==(100,80)
        assert all(label.IsA('vtkBillboardTextActor3D') for label in scene.draw.corner_labels)
        image.close()
    finally:scene.close()
