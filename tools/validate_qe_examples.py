"""Validate the private QE examples and render the actual production phonon path.

Usage: python tools/validate_qe_examples.py /directory/with/four/examples
The input files themselves are not copied into the source distribution.
"""
from pathlib import Path
from math import pi
import hashlib,json,sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lele.formats import load_document
from lele.qe_phonons import bind_qe_phonons
from lele.renderer import MoleculeRenderer
from lele.render_options import RenderOptions
from lele.animation_export import GifSettings,export_animation_gif


def main():
    root=Path(sys.argv[1]);out=Path(__file__).resolve().parents[1]/'docs'/'qa_v2.10.0';out.mkdir(parents=True,exist_ok=True)
    names=['01_vc-relax.in','job.out','job.out03','matdyn.modes']
    docs={name:load_document(root/name) for name in names}
    summary={name:dict(sha256=hashlib.sha256((root/name).read_bytes()).hexdigest(),
        atoms=(len(d.frames[0].symbols) if d.frames else None),frames=len(d.frames),
        qpoints=[list(s.qpoint) for s in d.calculation_results.phonon_sets],
        mode_counts=[len(s.modes) for s in d.calculation_results.phonon_sets]) for name,d in docs.items()}
    pw=docs['job.out'];summary['job.out'].update(energies_ry=[f.info['qe_total_energy_ry'] for f in pw.frames],
        final_volume_A3=float(abs(np.linalg.det(pw.frames[-1].cell))),last_converged=pw.frames[-1].info.get('optimization_converged',False))
    ref=docs['job.out03'].frames[0];bound=bind_qe_phonons(docs['matdyn.modes'],ref,ref.info['qe_alat_ang'],'PHONON printed reference')
    mode=bound.vibrations[1].modes[2]
    summary['bound_modes']=dict(analyses=len(bound.vibrations),animatable=sum(m.can_animate for a in bound.vibrations for m in a.modes),
        q_units='Cartesian 2pi/alat',alat_A=ref.info['qe_alat_ang'],preview_frequency_cm1=mode.frequency_cm1,
        preview_q=mode.qpoint,preview_fractional_q=mode.q_fractional,
        complex_imaginary_components_preserved=True)
    options=RenderOptions(boundary_enabled=True,boundary_bounds=((0,2),(0,1),(0,1)),axes_position='Off',background='#FFFFFF')
    import vtkmodules.vtkRenderingOpenGL2
    import vtkmodules.vtkRenderingFreeType
    from vtkmodules.vtkRenderingCore import vtkRenderer,vtkRenderWindow,vtkWindowToImageFilter
    from vtkmodules.vtkIOImage import vtkPNGWriter
    scene=vtkRenderer();window=vtkRenderWindow();window.SetOffScreenRendering(True);window.SetSize(800,500);window.AddRenderer(scene)
    draw=MoleculeRenderer(scene);draw.options=options;draw.mode_vectors=mode.arrow_vectors();draw.mode_vector_length=1.5
    try:
        draw.set_scene(mode.preview_frame(ref,pi/2,.3),reset_camera=True)
        camera=scene.GetActiveCamera();camera.ParallelProjectionOn();camera.Azimuth(25);camera.Elevation(20)
        window.Render();read=vtkWindowToImageFilter();read.SetInput(window);read.ReadFrontBufferOff();read.Update()
        writer=vtkPNGWriter();writer.SetFileName(str(out/'qe_non_gamma_preview.png'));writer.SetInputConnection(read.GetOutputPort());writer.Write()
        summary['native_scene']=dict(display_atoms=len(draw.boundary_display.frame.symbols),displacement_arrows=len(draw.mode_arrow_actors))
    finally:window.Finalize()
    gif=out/'qe_non_gamma_preview.gif'
    settings=GifSettings(source='vibration',width=480,height=320,fps=8,cycle_seconds=1.,supersample=1)
    export_animation_gif(gif,bound,settings,options,reference=ref,mode=mode,mode_arrows=True,mode_arrow_length=1.5)
    from PIL import Image
    with Image.open(gif) as image:
        summary['native_gif']=dict(frames=image.n_frames,size=image.size)
        assert image.n_frames==8
    assert summary['native_scene']['display_atoms']==8 and summary['native_scene']['displacement_arrows']>0
    (out/'supplied_qe_acceptance.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
