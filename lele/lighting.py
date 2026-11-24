"""Camera-relative directional lighting for interactive and exported scenes.

Directions follow VMD's four standard lights. The front and upper-right
lights are enabled by default. VMD light directions:
https://www.ks.uiuc.edu/Research/vmd/doxygen/Scene_8C-source.html
"""
from math import isfinite

LIGHT_NAMES = ('Front', 'Upper right', 'Rear upper left', 'Lower left')
DEFAULT_LIGHT_ENABLED = (True, True, False, False)
DEFAULT_LIGHT_INTENSITIES = (1.15, 1.35, .45, 1.05)
DEFAULT_LIGHT_POSITIONS = ((-.1, .1, 1.), (1., 2., .5), (-1., 2., -1.), (-1., -1., 0.))
DEFAULT_HIGHLIGHT_SIZE = 47.
DEFAULT_HIGHLIGHT_BRIGHTNESS = 47.

_FINISHES = {
    # The middle of each slider retains the original material calibration.
    'Balanced': (.22, .39, .36, 24.),
    'Glossy': (.07, .58, .80, 32.),
    'Matte': (.32, .36, .05, 9.),
}


def apply_surface_finish(prop, options):
    ambient, diffuse, specular, power = _FINISHES.get(options.surface_finish, _FINISHES['Balanced'])
    # Interpolate the Phong exponent logarithmically within VTK's supported
    # range. The middle position uses each material's calibrated exponent.
    adjustment = (options.highlight_size - 50.) / 50.
    if adjustment < 0:
        power *= (128. / power) ** -adjustment
    else:
        power **= 1. - adjustment
    # Both halves of the brightness slider stay active. The upper end allows
    # up to twice the preset strength within VTK's 0..1 material range.
    brightness = options.highlight_brightness / 50.
    if brightness <= 1.:
        specular *= brightness
    else:
        specular += (brightness - 1.) * min(specular, 1. - specular)
    prop.SetAmbient(ambient)
    prop.SetDiffuse(diffuse)
    # vtkProperty.SetColor also sets the specular RGB. A white light must
    # reflect white even from a dark atom or a saturated cyan density layer.
    prop.SetSpecularColor(1., 1., 1.)
    prop.SetSpecular(specular)
    prop.SetSpecularPower(power)


def light_settings(options):
    """Validate persisted settings before updating any live lights."""
    enabled = tuple(getattr(options, 'light_enabled', DEFAULT_LIGHT_ENABLED))
    intensities = tuple(getattr(options, 'light_intensities', DEFAULT_LIGHT_INTENSITIES))
    positions = tuple(getattr(options, 'light_positions', DEFAULT_LIGHT_POSITIONS))
    if not len(enabled) == len(intensities) == len(positions) == 4:
        raise ValueError('Exactly four directional light settings are required.')
    if any(not isinstance(v, bool) for v in enabled):
        raise ValueError('Light switches must be true or false.')
    intensities = tuple(float(v) for v in intensities)
    if any(not isfinite(v) or not 0 <= v <= 4 for v in intensities):
        raise ValueError('Light intensity must lie between 0 and 4.')
    positions = tuple(tuple(float(v) for v in p) for p in positions)
    if any(len(p) != 3 or not all(isfinite(v) for v in p)
           or sum(v*v for v in p) < 1e-12 for p in positions):
        raise ValueError('Each light direction must be a finite, nonzero 3D vector.')
    return enabled, intensities, positions


def upgrade_default_lights(options):
    """Update only the unmodified pre-4.1.1 rig when opening an older project."""
    previous = ((True, True, False, False), (.85, .45, .45, .35), DEFAULT_LIGHT_POSITIONS)
    if light_settings(options) == previous:
        options.light_enabled = DEFAULT_LIGHT_ENABLED
        options.light_intensities = DEFAULT_LIGHT_INTENSITIES


def create_lights(renderer):
    from vtkmodules.vtkRenderingCore import vtkLight
    renderer.AutomaticLightCreationOff()
    renderer.LightFollowCameraOn()
    lights = []
    for _ in LIGHT_NAMES:
        light = vtkLight()
        light.SetLightTypeToCameraLight()
        light.PositionalOff()
        light.SetColor(1., 1., 1.)
        light.SetFocalPoint(0., 0., 0.)
        renderer.AddLight(light)
        lights.append(light)
    return lights


def update_lights(lights, options):
    enabled, intensities, positions = light_settings(options)
    for light, switch, intensity, position in zip(lights, enabled, intensities, positions):
        light.SetSwitch(switch)
        light.SetIntensity(intensity)
        light.SetPosition(*position)
