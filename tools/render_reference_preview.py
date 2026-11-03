"""Render the production VESTA radius choices and record reference values."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vtkmodules.vtkRenderingOpenGL2
import vtkmodules.vtkRenderingFreeType
from vtkmodules.vtkRenderingCore import vtkRenderer, vtkRenderWindow, vtkWindowToImageFilter, vtkTextActor
from vtkmodules.vtkIOImage import vtkPNGWriter
from lele.core import Frame
from lele.renderer import MoleculeRenderer
from lele.render_options import RenderOptions
from lele.display_reference import RADIUS_TYPES, chemcraft_limit
from lele._display_reference_values import (
    SOURCE_SHA256, CHEMCRAFT_LIMITS_SQUARED, GAUSSVIEW_STYLE_COLORS, VESTA_RADII,
)
from lele.atom_legend import legend_samples


def main():
    out = Path(__file__).resolve().parents[1] / 'docs' / 'qa_v2.9.0'
    out.mkdir(parents=True, exist_ok=True)
    frame = Frame(['H', 'C', 'O', 'Cu'], [[-6, 0, 0], [-2, 0, 0], [2, 0, 0], [6, 0, 0]])
    window = vtkRenderWindow()
    window.SetOffScreenRendering(True)
    window.SetSize(1200, 720)
    keep = []
    summary = {}
    try:
        for row, kind in enumerate(RADIUS_TYPES):
            scene = vtkRenderer()
            scene.SetViewport(0, (2 - row) / 3, 1, (3 - row) / 3)
            window.AddRenderer(scene)
            view = MoleculeRenderer(scene)
            view.options = RenderOptions(style='Space filling', space_filling_radii=kind,
                background='#FFFFFF', bonds=False, labels='Element')
            view.set_scene(frame, reset_camera=True)
            camera = scene.GetActiveCamera()
            camera.ParallelProjectionOn()
            camera.SetPosition(0, 0, 30)
            camera.SetFocalPoint(0, 0, 0)
            camera.SetViewUp(0, 1, 0)
            camera.SetParallelScale(2.)
            title = vtkTextActor()
            title.SetInput('VESTA ' + kind + ' | 100%')
            title.SetPosition(12, 212)
            title.GetTextProperty().SetFontSize(22)
            title.GetTextProperty().SetColor(.15, .18, .23)
            scene.AddViewProp(title)
            samples = legend_samples(view)
            summary[kind] = dict(radii_A={s['symbol']: s['radius'] for s in samples},
                                colors={s['symbol']: s['color'] for s in samples})
            keep.append((view, title))
        window.Render()
        read = vtkWindowToImageFilter()
        read.SetInput(window)
        read.ReadFrontBufferOff()
        read.Update()
        writer = vtkPNGWriter()
        writer.SetFileName(str(out / 'vesta_radii_native.png'))
        writer.SetInputConnection(read.GetOutputPort())
        writer.Write()
    finally:
        window.Finalize()
    summary['source_sha256'] = SOURCE_SHA256
    summary['coverage'] = dict(chemcraft_species=len(CHEMCRAFT_LIMITS_SQUARED),
        chemcraft_ordinary_pairs=sum(v is not None for row in CHEMCRAFT_LIMITS_SQUARED for v in row),
        compat_palette_species=len(GAUSSVIEW_STYLE_COLORS), vesta_rows=len(VESTA_RADII))
    summary['ordinary_maximum_A'] = {a + '-' + b: chemcraft_limit(a, b)
        for a, b in [('C', 'C'), ('H', 'C'), ('O', 'H'), ('Ti', 'O'), ('Fe', 'O'), ('Cu', 'Cu')]}
    (out / 'reference_acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
