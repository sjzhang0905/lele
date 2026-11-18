"""Keep atom identity and its selected display image separate.

Editing and atom tables retain unique source indices. Measurements additionally
retain ordered lattice-image picks, including two images of one source atom.
"""
from dataclasses import dataclass
import numpy as np

from .core import Frame, measure


@dataclass(frozen=True)
class AtomImage:
    index: int
    shift: tuple[int, int, int] = (0, 0, 0)

    def position(self, frame):
        return frame.positions[self.index] + np.asarray(self.shift) @ frame.cell


def selected_images(window):
    """Return picks only while they still describe the current selection."""
    frame = window.frame
    records = getattr(window, '_selected_atom_images', None)
    context = getattr(window, '_selected_atom_image_frame', None)
    bounds = tuple(tuple(pair) for pair in window.render_options.boundary_bounds)
    preserve_origin = bool(window.render_options.boundary_preserve_origin)
    if (frame is None or context is not frame or records is None
            or list(dict.fromkeys(item.index for item in records)) != list(window.selection)
            or getattr(window, '_selected_atom_image_bounds', None) != bounds
            or getattr(window, '_selected_atom_image_preserve_origin', None) != preserve_origin
            or not window.render_options.boundary_enabled or not any(frame.pbc)):
        window._selected_atom_images = None
        window._selected_atom_image_frame = None
        return [AtomImage(i) for i in window.selection]
    return list(records)


def toggle_atom_image(window, index, world_position=None):
    """Toggle the exact displayed copy while preserving source selections."""
    frame = window.frame
    records = selected_images(window)
    shift = (0, 0, 0)
    if (world_position is not None and window.renderer.boundary_display is not None
            and any(frame.pbc)):
        renderer = window.renderer
        point = ((np.asarray(world_position) - renderer.display_translation)
                 @ renderer.display_rotation.T)
        shift = tuple(int(x) for x in np.rint(
            (point - frame.positions[index]) @ np.linalg.inv(frame.cell)))
    item = AtomImage(int(index), shift)
    if item in records:
        records.remove(item)
    else:
        records.append(item)
    window.selection = list(dict.fromkeys(record.index for record in records))
    window._selected_atom_images = records
    window._selected_atom_image_frame = frame
    window._selected_atom_image_bounds = tuple(tuple(pair) for pair in window.render_options.boundary_bounds)
    window._selected_atom_image_preserve_origin = bool(window.render_options.boundary_preserve_origin)
    return item


def image_measurement(frame, records):
    """Use the clicked Cartesian images, never an implicit minimum image."""
    points = [record.position(frame) for record in records]
    temporary = Frame([frame.symbols[record.index] for record in records], points)
    return measure(temporary, list(range(len(records))))


def image_label(frame, record):
    label = f'{frame.symbols[record.index]}{record.index + 1}'
    if any(record.shift):
        label += '[' + ','.join(str(i) for i in record.shift) + ']'
    return label


def image_editable(records):
    """A common translation does not change an internal-coordinate edit."""
    return len({record.shift for record in records}) <= 1
