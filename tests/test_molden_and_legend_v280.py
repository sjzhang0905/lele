"""Independent Molden modes and a legend-only window, with numeric/native QA."""
from pathlib import Path
from math import pi
from unittest.mock import patch
import os
import numpy as np
import pytest
from ase.units import Bohr
from lele.formats import load_document
from lele.core import Document,Frame
from lele.legacy_converter import detect_format,read_structure
from lele.output_text import LoadCancelled
from test_periodic_fragment_ui_v171 import gui

MOLDEN=''' [Molden Format]
 [Atoms] AU
 O 1 8 0 0 0
 H 2 1 0 0 2
 H 3 1 2 0 0
 [FREQ]
 -125.5
 1600.25
 [FR-COORD]
 O 0 0 0
 H 0 0 2
 H 2 0 0
 [FR-NORM-COORD]
 vibration 1
 0 0 0
 0 0 1
 0 0 -1
 vibration 2
 0 0 0
 1 0 0
 -1 0 0
'''


def write(tmp_path,text=MOLDEN,name='water-VIBRATIONS-1.mol',encoding='utf-8'):
    p=tmp_path/name;p.write_text(text,encoding=encoding);return p


def attach(gui,doc):
    w=gui.window;w.documents=[doc];w.current_doc=0;w.frame_index=0
    w.files_tree.clear();w._add_document_tree(0,doc);w.change_frame(0)
    gui.addCleanup(lambda:[d.close() for d in list(w._analysis_windows)])
    return w


def test_cp2k_molden_numeric_reference_modes_and_legacy_structure_adapter(tmp_path):
    p=write(tmp_path);assert detect_format(p).kind=='molden_vib'
    doc=load_document(p);ref=doc.vibrations[0].reference;first,second=doc.vibrations[0].modes
    np.testing.assert_array_equal(ref.positions,np.array([[0,0,0],[0,0,2],[2,0,0]])*Bohr)
    np.testing.assert_array_equal(first.displacements,np.array([[0,0,0],[0,0,1],[0,0,-1]])*Bohr)
    assert first.frequency_cm1==-125.5 and first.imaginary and second.frequency_cm1==1600.25
    assert all(m.can_animate and m.ir_intensity is None for m in (first,second))
    assert ref.energy_ev is None and not any(ref.pbc) and not ref.cell.any()
    assert not ref.info.get('optimization_converged')
    atoms,_=read_structure(p);np.testing.assert_array_equal(atoms.positions,ref.positions)


@pytest.mark.parametrize('extension,encoding',[('mol','utf-16'),('molden','utf-8'),('txt','utf-8')])
def test_molden_is_recognized_by_content_not_mdl_suffix(tmp_path,extension,encoding):
    doc=load_document(write(tmp_path,name='modes.'+extension,encoding=encoding))
    assert len(doc.vibrations[0].modes)==2


def test_standard_mdl_mol_still_uses_its_existing_reader(tmp_path):
    from ase import Atoms
    from ase.io import write as ase_write
    p=tmp_path/'ordinary.mol';ase_write(p,Atoms('OH',positions=[[0,0,0],[0,0,1]]),format='mol')
    assert detect_format(p).kind=='ase_generic'
    doc=load_document(p);assert doc.frames[0].symbols==['O','H'] and not doc.vibrations


def test_fr_reference_and_explicit_cell_units_without_inventing_periodicity(tmp_path):
    s=MOLDEN.replace(' [FREQ]',' [Cell] Angs\n 8 0 0\n 0 9 0\n 0 0 10\n [FREQ]')
    doc=load_document(write(tmp_path,s))
    np.testing.assert_array_equal(doc.frames[0].cell,np.diag([8,9,10]))
    assert doc.frames[0].pbc==(False,False,False)
    s=MOLDEN[MOLDEN.index(' [FREQ]'):]
    doc=load_document(write(tmp_path,'[Molden Format]\n'+s));assert len(doc.frames[0].symbols)==3


def test_atoms_angstrom_fallback_and_intensity_source_units(tmp_path):
    a=MOLDEN.index(' [FR-COORD]');b=MOLDEN.index(' [FR-NORM-COORD]')
    s=MOLDEN[:a]+MOLDEN[b:];s=s.replace('[Atoms] AU','[Atoms] Angs')+' [INT]\n 1.25\n 2.5\n'
    doc=load_document(write(tmp_path,s));np.testing.assert_array_equal(doc.frames[0].positions,[[0,0,0],[0,0,2],[2,0,0]])
    assert [m.ir_intensity for m in doc.vibrations[0].modes]==[1.25,2.5]
    assert all(m.ir_intensity_unit=='source units' for m in doc.vibrations[0].modes)


def test_partial_modes_retain_frequencies_without_fabricated_vectors(tmp_path):
    doc=load_document(write(tmp_path,MOLDEN.rsplit(' -1 0 0',1)[0]))
    modes=doc.vibrations[0].modes
    assert len(modes)==2 and modes[0].can_animate and modes[1].displacements is None
    assert 'incomplete' in doc.note
    with pytest.raises(ValueError,match='sequences differ'):
        load_document(write(tmp_path,MOLDEN.replace(' H 0 0 2\n',' C 0 0 2\n')))


def test_mode_number_mapping_cancellation_and_project_roundtrip(gui,tmp_path):
    s=MOLDEN.replace('vibration 1','vibration 9').replace('vibration 2','vibration 1').replace('vibration 9','vibration 2')
    doc=load_document(write(tmp_path,s));assert doc.vibrations[0].modes[0].displacements[1,0]==Bohr
    phase=['']
    def progress(label,*_):phase[0]=label
    with pytest.raises(LoadCancelled):
        load_document(write(tmp_path),progress=progress,cancelled=lambda:phase[0]=='Molden: Cartesian vibration vectors')
    w=attach(gui,doc);path=tmp_path/'molden.lele';assert w.save_project_to(path)
    from lele.project_file import load_project
    restored=load_project(path)['documents'][0]['document']
    np.testing.assert_array_equal(restored.vibrations[0].modes[0].displacements,doc.vibrations[0].modes[0].displacements)
    w.select_vibration(0,0,0,autoplay=False)
    assert w.vibration_controls.play_button.isEnabled() and '-125.5000' in w.vibration_controls.description.text()
    assert w.gif_action.isEnabled()


@pytest.fixture
def actual_file():
    p=os.environ.get('LELE_CP2K_MOLDEN_EXAMPLE')
    if not p:pytest.skip('Set LELE_CP2K_MOLDEN_EXAMPLE to the supplied private example; it is not redistributed.')
    return Path(p)


def test_actual_124_atom_example_all_frequencies_and_frozen_rows(actual_file,tmp_path):
    from lele.animation_export import export_animation_gif,GifSettings
    from lele.render_options import RenderOptions
    doc=load_document(actual_file);ref=doc.vibrations[0].reference;modes=doc.vibrations[0].modes
    assert len(ref.symbols)==124 and ref.symbols[-2:]==['O','O']
    assert [m.frequency_cm1 for m in modes]==[239.777289,252.259862,312.216834,318.175319,324.214973,1548.774920]
    for mode in modes:
        assert mode.can_animate
        np.testing.assert_array_equal(mode.displacements[:122],np.zeros((122,3)))
        shifted=mode.positions_at(ref,pi/2,.3)
        np.testing.assert_array_equal(shifted[:122],ref.positions[:122])
        assert np.max(np.linalg.norm(shifted-ref.positions,axis=1))==pytest.approx(.3)
    settings=GifSettings(source='vibration',width=480,height=320,fps=8,cycle_seconds=1,supersample=1)
    options=RenderOptions();options.axes_position='Off'
    path=tmp_path/'actual_mode.gif';export_animation_gif(path,doc,settings,options,reference=ref,mode=modes[-1])
    from PIL import Image
    with Image.open(path) as image:assert image.n_frames==8 and image.size==(480,320)


@pytest.fixture
def legend_canvas(gui):
    from PySide6.QtWidgets import QWidget
    from vtkmodules.vtkRenderingCore import vtkRenderWindow,vtkRenderWindowInteractor
    class Canvas(QWidget):
        def __init__(self,parent):
            super().__init__(parent);self.rw=vtkRenderWindow();self.rw.SetOffScreenRendering(True);self.rw.SetSize(760,260)
            self.interactor=vtkRenderWindowInteractor();self.interactor.SetRenderWindow(self.rw)
        def GetRenderWindow(self):return self.rw
        def Initialize(self):pass
        def render(self):self.rw.Render()
    with patch('lele.atom_legend_dialog.create_legend_canvas',side_effect=Canvas):yield


def test_legend_opens_separate_canvas_only_samples_and_exports(gui,legend_canvas,tmp_path):
    from lele.atom_appearance import AtomAppearance
    frame=Frame(['C','O','H','H'],[[0,0,0],[1.4,0,0],[0,0,1],[-1,0,0]],
        atom_appearance={1:AtomAppearance(color='#12ab34'),2:AtomAppearance(visible=False)})
    w=attach(gui,Document(tmp_path/'model.xyz','XYZ',[frame]));before=frame.positions.copy()
    camera=w.scene.GetActiveCamera();position=camera.GetPosition();count=w.scene.GetViewProps().GetNumberOfItems()
    assert not w.atom_legend_action.isCheckable()
    w.atom_legend_action.trigger();dialog=w._analysis_windows[-1];gui.app.processEvents()
    assert dialog.isVisible() and dialog.canvas is not w.vtk and dialog.scene is not w.scene
    assert [s['symbol'] for s in dialog.legend.samples]==['C','O','H']
    assert dialog.legend.samples[1]['color']=='#12ab34' and dialog.legend.samples[2]['source_index']==3
    assert dialog.scene.GetViewProps().GetNumberOfItems()==6  # exactly 3 spheres + 3 labels
    assert all(a.GetMapper().GetInputConnection(0,0).GetProducer().IsA('vtkSphereSource') for a in dialog.legend.actors)
    assert w.scene.GetViewProps().GetNumberOfItems()==count and camera.GetPosition()==position
    np.testing.assert_array_equal(frame.positions,before)
    path=tmp_path/'legend.png';dialog.write_png(path)
    from PIL import Image
    with Image.open(path) as image:assert image.size==(1520,520)
    w.frame.atom_appearance[1]=AtomAppearance(visible=False);w.refresh_scene()
    assert len(dialog.legend.samples)==3  # source snapshot stays independent until refreshed
    dialog.refresh_button.click();assert [s['symbol'] for s in dialog.legend.samples]==['C','H']
    dialog.close();assert dialog._finalized


def test_production_legend_canvas_paints_native_spheres_and_closes(gui,tmp_path):
    from PySide6.QtCore import QEventLoop,QTimer
    w=attach(gui,Document(tmp_path/'real_canvas.xyz','XYZ',[Frame(['C','O','H'],[[0,0,0],[1.4,0,0],[0,0,1]])]))
    dialog=w.show_atom_legend();loop=QEventLoop();QTimer.singleShot(100,loop.quit);loop.exec()
    assert dialog.canvas.objectName()=='atomLegendCanvas' and dialog.canvas._image is not None
    assert dialog.canvas._image.width()>300 and dialog.canvas._image.height()>150
    path=tmp_path/'native_legend.png';dialog.write_png(path)
    from PIL import Image
    with Image.open(path) as image:
        data=np.asarray(image.convert('RGB'))
        assert len(np.unique(data.reshape(-1,3),axis=0))>100
        assert image.size==tuple(2*v for v in dialog.canvas.GetRenderWindow().GetSize())
    dialog.close();assert dialog.canvas._closed and dialog._finalized
