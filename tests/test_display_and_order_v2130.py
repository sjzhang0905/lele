"""Default palette provenance, structure-aware axes and stable atom export."""
from hashlib import sha256
from pathlib import Path
import json
import re
from unittest.mock import patch
import zipfile

import numpy as np
import pytest
from ase.io import read
from vtkmodules.vtkRenderingCore import vtkRenderer

from lele.atom_appearance import AtomAppearance
from lele.atom_clipboard import paste_atoms
from lele.atom_indices import reorder_atoms
from lele.core import Document, Frame, axis_vectors, colour
from lele.formats import export_frame, load_document
from lele.project_file import load_project, save_project
from lele.render_options import RenderOptions
from lele.renderer import MoleculeRenderer
from lele.sibyl_palette import SIBYL_COLORS, SIBYL_RGB, SOURCE_SHA256
from lele.style_presets import element_palette_color
from test_periodic_fragment_ui_v171 import gui

ROOT=Path(__file__).resolve().parents[1]


def crystal():
    return Frame(['O','C','H'],[[1,1,1],[3,2,1],[1,3,2]],[[8,0,0],[1,9,0],[2,1,10]],(True,)*3)


def project_roundtrip(tmp_path,frame,options):
    path=tmp_path/'display.lele'
    doc=Document(Path('source.xyz'),'test',[frame])
    save_project(path,dict(documents=[dict(document=doc,options=options)],current_document=0))
    return load_project(path)['documents'][0],path


def test_all_111_sibyl_rgb_values_match_the_supplied_tcl():
    path=ROOT/'docs/reference_data/Sibyl.tcl';data=path.read_bytes()
    assert sha256(data).hexdigest()==SOURCE_SHA256
    text=data.decode();definitions={}
    for line in text.splitlines():
        fields=line.split()
        if fields[:3]==['color','change','rgb']:
            definitions[int(fields[3])]=tuple(map(float,fields[4:7]))
    fields=re.search(r'set elem_color_list\s*\{([^}]+)\}',text)[1].split()
    expected={s:definitions[int(fields[i+1])] for i,s in enumerate(fields) if i%2==0}
    assert len(expected)==111 and SIBYL_RGB==expected
    assert {s:SIBYL_COLORS[s] for s in expected}=={s:'#'+''.join(f'{round(v*255):02X}' for v in rgb) for s,rgb in expected.items()}
    assert {s:SIBYL_COLORS[s] for s in ('H','C','N','O','S','Co','Ni')}=={
        'H':'#CCCCCC','C':'#8E8E8E','N':'#1919E5','O':'#E50000','S':'#FFC628','Co':'#5B6DFF','Ni':'#5B7AC1'}


def test_glossy_sibyl_defaults_reach_real_vtk_atoms_and_element_bonds():
    draw=MoleculeRenderer(vtkRenderer());frame=Frame(['C','O'],[[0,0,0],[1.2,0,0]])
    assert draw.options.surface_finish=='Glossy' and draw.options.atom_palette=='Default'
    draw.set_scene(frame)
    assert draw.atom_color(frame,0)=='#9E9E9E'
    assert draw.atom_color(frame,1,for_bond=True)=='#E92525'
    actors=[a for a in draw.dynamic if a.IsA('vtkActor')]
    assert actors
    assert all(a.GetProperty().GetSpecular()==pytest.approx(.78) and a.GetProperty().GetSpecularPower()==60 for a in actors)
    frame.atom_appearance[1]=AtomAppearance(color='#123456')
    assert draw.atom_color(frame,1)==draw.atom_color(frame,1,for_bond=True)=='#123456'
    assert element_palette_color(draw.options,'D')=='#D3D3D3'
    og=colour('Og')
    expected='#'+''.join(f'{round(int(og[i:i+2],16)*.9+25.5):02X}' for i in (1,3,5))
    expected='#'+''.join(f'{round(int(expected[i:i+2],16)*.95+12.75):02X}' for i in (1,3,5))
    assert element_palette_color(draw.options,'Og')==expected


def test_old_palette_remains_explicitly_selectable():
    opts=RenderOptions(atom_palette='GaussView style (Chemcraft)',surface_finish='Balanced')
    assert element_palette_color(opts,'O')==colour('O')=='#FF4040'
    opts.atom_palette='Sibyl'
    assert element_palette_color(opts,'O')=='#E92525'
    assert RenderOptions(atom_palette='Sibyl').atom_palette=='Default'


@pytest.mark.parametrize('periodic',[True,False])
def test_auto_axes_use_true_cell_vectors_for_periodic_frames_and_xyz_for_molecules(periodic):
    frame=crystal()
    if not periodic:frame.pbc=(False,)*3
    opts=RenderOptions();vectors=axis_vectors(frame,opts.axes_basis,length=4)
    assert [s for s,_ in vectors]==list('abc' if periodic else 'XYZ')
    np.testing.assert_array_equal([v for _,v in vectors],frame.cell if periodic else 4*np.eye(3))
    draw=MoleculeRenderer(vtkRenderer());draw.make_corner_marker(frame)
    assert [a.GetInput() for a in draw.corner_labels]==list('abc' if periodic else 'XYZ')
    opts.axes_basis='XYZ'
    assert [s for s,_ in axis_vectors(frame,opts.axes_basis)]==list('XYZ')


def test_auto_axes_tracks_cell_and_rotates_with_structure():
    frame=crystal();rotation=np.array([[0,0,1],[0,1,0],[-1,0,0]])
    frame.cell=frame.cell@rotation;frame.positions=frame.positions@rotation
    np.testing.assert_allclose([v for _,v in axis_vectors(frame,RenderOptions().axes_basis)],frame.cell)
    frame.cell[:]=0
    assert [s for s,_ in axis_vectors(frame,RenderOptions().axes_basis)]==list('XYZ')


def test_gui_default_controls_and_auto_axes_survive_file_switching(gui,tmp_path):
    w=gui.window
    gui.attach(Frame(['C'],[[0,0,0]]));w._sync_corner_axes=lambda:None
    assert w.finish_combo.currentText()=='Glossy' and w.atom_palette_combo.currentText()=='Default'
    assert w.atom_slider.value()==50 and w.bond_slider.value()==7
    assert w.axes_basis_combo.currentData()=='Auto'
    path=tmp_path/'slab.POSCAR';export_frame(crystal(),path,'poscar-cartesian');w._open_path_now(path)
    assert w.axes_basis_combo.currentData()=='Auto'
    w.renderer.make_corner_marker(w.frame)
    assert [a.GetInput() for a in w.renderer.corner_labels]==list('abc')
    w.axes_basis_combo.setCurrentIndex(w.axes_basis_combo.findData('XYZ'))
    w.change_frame(0,switch_doc=0);w.renderer.make_corner_marker(w.frame)
    assert w.axes_basis_combo.currentData()=='Auto' and [a.GetInput() for a in w.renderer.corner_labels]==list('XYZ')
    w.change_frame(0,switch_doc=1)
    assert w.axes_basis_combo.currentData()=='XYZ'


@pytest.mark.parametrize('old_choice',[False,True])
def test_project_roundtrip_preserves_auto_defaults_and_explicit_old_display_choices(tmp_path,old_choice):
    opts=RenderOptions()
    if old_choice:opts=RenderOptions(atom_palette='GaussView style (Chemcraft)',surface_finish='Balanced',axes_basis='XYZ')
    entry,path=project_roundtrip(tmp_path,crystal(),opts)
    saved=entry['options']
    assert (saved.atom_palette,saved.surface_finish,saved.axes_basis)==(opts.atom_palette,opts.surface_finish,opts.axes_basis)
    if old_choice:
        with zipfile.ZipFile(path) as archive:files={n:archive.read(n) for n in archive.namelist()}
        manifest=json.loads(files['manifest.json']);manifest['application_version']='2.12.1';files['manifest.json']=json.dumps(manifest).encode()
        with zipfile.ZipFile(path,'w') as archive:
            for n,b in files.items():archive.writestr(n,b)
        assert load_project(path)['documents'][0]['options'].atom_palette=='GaussView style (Chemcraft)'


def appended_frame():
    frame=Frame(['O','H','C'],[[1,1,1],[2,1,1],[3,1,1]],np.diag([20.,20.,20.]),(True,)*3,
                info={'poscar_groups':[('O',1),('H',1),('C',1)],'vasp_fixed_axes':[[True]*3,[False]*3,[False,True,False]]})
    paste_atoms(frame,Frame(['Fe','N'],[[0,0,0],[0,1.5,0]]),[6,6,6])
    paste_atoms(frame,Frame(['Co','H'],[[0,0,0],[0,1,0]]),[9,9,9])
    return frame


@pytest.mark.parametrize('target',['xyz','gjf','cif','poscar-direct','poscar-cartesian'])
def test_all_exports_keep_existing_rows_then_addition_order(tmp_path,target):
    frame=appended_frame();before=frame.positions.copy()
    assert frame.symbols==['O','H','C','Fe','N','Co','H']
    p=tmp_path/('export.'+{'xyz':'xyz','gjf':'gjf','cif':'cif'}.get(target,'POSCAR'))
    export_frame(frame,p,target)
    fmt={'xyz':'xyz','gjf':'gaussian-in','cif':'cif','poscar-direct':'vasp','poscar-cartesian':'vasp'}[target]
    atoms=read(p,format=fmt)
    assert atoms.get_chemical_symbols()==frame.symbols
    np.testing.assert_allclose(atoms.positions,before,atol=1.e-10)
    np.testing.assert_array_equal(frame.positions,before)
    if target.startswith('poscar'):
        g=load_document(p).frames[0]
        assert g.info['vasp_fixed_axes']==frame.info['vasp_fixed_axes']


@pytest.mark.parametrize('target',['poscar-direct','poscar-cartesian'])
def test_legacy_converter_also_keeps_source_rows_with_appended_atoms(tmp_path,target):
    from lele.legacy_converter import convert_one, DEFAULT_GAUSSIAN_ROUTE
    frame=appended_frame();source=tmp_path/'source.xyz';export_frame(frame,source,'xyz')
    out=tmp_path/'legacy';out.mkdir()
    p,_,_=convert_one(source,target,out,30.,DEFAULT_GAUSSIAN_ROUTE)
    assert read(p,format='vasp').get_chemical_symbols()==frame.symbols


def test_explicit_reindex_is_the_current_export_order_instead_of_automatic_source_sort(tmp_path):
    f=appended_frame();reorder_atoms(f,[2,0,1,3,4,5,6])
    g=project_roundtrip(tmp_path,f,RenderOptions())[0]['document'].frames[0]
    out=tmp_path/'POSCAR';export_frame(g,out,'poscar-cartesian')
    assert read(out,format='vasp').get_chemical_symbols()==['C','O','H','Fe','N','Co','H']


def test_gui_export_path_keeps_order_after_multiple_pastes(gui,tmp_path):
    gui.attach(appended_frame());w=gui.window;out=tmp_path/'gui.POSCAR'
    with patch('lele.app.QInputDialog.getItem',return_value=('POSCAR Cartesian (POSCAR)',True)),patch('lele.app.QFileDialog.getSaveFileName',return_value=(str(out),'')):
        w.export_dialog()
    assert read(out,format='vasp').get_chemical_symbols()==w.frame.symbols
