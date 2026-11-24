"""Horizontal scalar bars shared by mapped surfaces and field slices."""
from vtkmodules.vtkRenderingAnnotation import vtkScalarBarActor

from .field_mapping import is_esp_field


def field_legend(volume, lookup, title, row, background):
    from .renderer import rgb

    bar = vtkScalarBarActor()
    bar.SetLookupTable(lookup)
    bar.SetOrientationToHorizontal()
    width = .38 if is_esp_field(volume) else .76
    bar.SetPosition((1. - width) / 2., .02 + row * .09)
    bar.SetWidth(width)
    bar.SetHeight(.08)
    bar.SetTitle(title)
    bar.SetNumberOfLabels(5)
    bar.SetLabelFormat('%.3g')
    bar.SetUnconstrainedFontSize(True)
    shade = .1 if sum(rgb(background)) / 3. > .5 else .95
    for text in (bar.GetTitleTextProperty(), bar.GetLabelTextProperty()):
        text.SetColor(shade, shade, shade)
        text.SetFontSize(12)
        text.BoldOff()
        text.ItalicOff()
        text.ShadowOff()
    bar.PickableOff()
    bar.UseBoundsOff()
    return bar
