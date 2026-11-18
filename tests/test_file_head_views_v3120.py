"""A file heading recalls its saved frame, while geometry children stay explicit."""
from pathlib import Path

from lele.core import Document, Frame
from test_periodic_fragment_ui_v171 import gui


def test_file_heading_recalls_last_frame_and_explicit_children_override(gui):
    window = gui.window
    frames = [Frame(['C', 'H'], [[0, 0, 0], [1 + i * .1, 0, 0]]) for i in range(3)]
    docs = [Document(Path(gui.temp.name) / f'{name}.xyz', 'XYZ', [f.clone() for f in frames])
            for name in ('first', 'second')]
    window.documents = []; window.current_doc = -1; window.files_tree.clear()
    for doc in docs:
        window._attach_loaded_document(doc)
    window.change_frame(1, switch_doc=0)
    window.scene.GetActiveCamera().SetPosition(10, 2, 8)
    saved = window.scene.GetActiveCamera().GetPosition()
    window.change_frame(0, switch_doc=1)
    window.files_tree.setCurrentItem(window.files_tree.topLevelItem(0))
    assert window.current_doc == 0 and window.frame_index == 1
    assert window.scene.GetActiveCamera().GetPosition() == saved
    window.files_tree.setCurrentItem(window.files_tree.topLevelItem(1))
    assert window.current_doc == 1 and window.frame_index == 0
    item = window._frame_tree_items[(0, 2)]
    window.files_tree.setCurrentItem(item)
    assert window.current_doc == 0 and window.frame_index == 2
