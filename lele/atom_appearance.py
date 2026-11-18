"""Frame-local display overrides; independent of Qt and scientific libraries."""
from dataclasses import dataclass
from math import isfinite


LABEL_MODES = ('None', 'Element', 'Index (1..N)',
               'Element + index (global)', 'ORCA index (0..N-1)',
               'Element + ORCA index', 'VESTA (POSCAR groups)')
ATOM_REPRESENTATIONS = ('Global', 'Ball and stick', 'Space filling', 'Sticks', 'Wireframe')


@dataclass(frozen=True)
class AtomAppearance:
    visible: bool = True
    color: str | None = None
    opacity: float = 1.0
    label_mode: str = 'Global'
    label_text: str = ''
    representation: str = 'Global'
    size_scale: float = 1.0

    def __post_init__(self):
        if not isfinite(self.size_scale) or self.size_scale <= 0.0:
            raise ValueError('Atom size scale must be finite and greater than zero')
        if self.representation not in ATOM_REPRESENTATIONS:
            raise ValueError('Unsupported atom representation')
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError('Atom opacity must be between 0 and 1')
        if self.label_mode not in ('Global', 'Custom', *LABEL_MODES):
            raise ValueError('Unsupported atom label mode')
        if self.color is not None:
            if len(self.color) != 7 or not self.color.startswith('#'):
                raise ValueError('Atom color must be #RRGGBB')
            int(self.color[1:], 16)


DEFAULT_APPEARANCE = AtomAppearance()


def appearance(frame, index):
    return frame.atom_appearance.get(index, DEFAULT_APPEARANCE)


def atom_is_drawn(frame, index):
    style = appearance(frame, index)
    return style.visible and style.opacity > 0.0
