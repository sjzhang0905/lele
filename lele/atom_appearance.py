"""Frame-local display overrides; independent of Qt and scientific libraries."""
from dataclasses import dataclass


LABEL_MODES = ('None', 'Element', 'Index (1..N)',
               'Element + index (global)', 'VESTA (POSCAR groups)')


@dataclass(frozen=True)
class AtomAppearance:
    visible: bool = True
    color: str | None = None
    opacity: float = 1.0
    label_mode: str = 'Global'
    label_text: str = ''

    def __post_init__(self):
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError('Atom opacity must be between 0 and 1')
        if self.label_mode not in ('Global', 'Custom', *LABEL_MODES):
            raise ValueError('Unsupported atom label mode')
        if self.color is not None:
            if len(self.color) != 7 or not self.color.startswith('#'):
                raise ValueError('Atom colour must be #RRGGBB')
            int(self.color[1:], 16)


DEFAULT_APPEARANCE = AtomAppearance()


def appearance(frame, index):
    return frame.atom_appearance.get(index, DEFAULT_APPEARANCE)


def atom_is_drawn(frame, index):
    style = appearance(frame, index)
    return style.visible and style.opacity > 0.0
