import json

from lele.core import Document, Frame
from lele.settings import read_style_presets, update_style_preset
from lele.style_presets import BUILTIN_PRESETS, CUSTOM_KEY, snapshot
from test_periodic_fragment_ui_v171 import gui


def test_delete_preset_keeps_document_appearance_and_persists(gui, tmp_path, monkeypatch):
    from lele.dialog_policy import QInputDialog
    w = gui.window
    path = tmp_path/'settings'/'style_presets.json'
    monkeypatch.setattr(w, '_style_storage_path', lambda: path)
    name = 'My copper'
    monkeypatch.setattr(QInputDialog, 'getText', lambda *_: (name, True))
    w._set_option('atom_scale', .83)
    w._save_style_preset()
    first = w.doc
    opts = snapshot(w.render_options)
    w._attach_loaded_document(Document(tmp_path/'b.xyz', 'XYZ', [Frame(['H'], [[0,0,0]])]))
    assert w.preset_combo.currentData() == name
    assert w.delete_style_button.isEnabled()
    # Another instance saved a different style after this window opened.
    update_style_preset(path, 'Other window', BUILTIN_PRESETS['Soft pastel'])
    def choose(_parent, _title, _label, names, current, editable):
        assert names == [name] and names[current] == name and not editable
        return name, True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    w.delete_style_button.click()
    assert w.preset_combo.currentData() == CUSTOM_KEY and w.preset_combo.findData(name) == -1
    assert snapshot(w.render_options) == opts and w._custom_style_state == opts
    assert w._document_views[id(first)].preset == CUSTOM_KEY
    w.change_frame(0, switch_doc=0)
    assert w.preset_combo.currentData() == CUSTOM_KEY and snapshot(w.render_options) == opts
    assert list(read_style_presets(path)) == ['Other window']
    assert all(w.preset_combo.findData(k) >= 0 for k in BUILTIN_PRESETS)
    assert not w.delete_style_button.isEnabled()


def test_cancel_or_write_error_keeps_preset_then_last_deletion_persists(gui, tmp_path, monkeypatch):
    from lele.dialog_policy import QInputDialog, QMessageBox
    w = gui.window
    path = tmp_path/'presets.json'
    monkeypatch.setattr(w, '_style_storage_path', lambda: path)
    monkeypatch.setattr(QInputDialog, 'getText', lambda *_: ('Saved', True))
    w._save_style_preset()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *_: ('Saved', False))
    w.delete_style_button.click()
    original = path.read_bytes()
    assert 'Saved' in w._user_style_presets and w.delete_style_button.isEnabled()
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *_: ('Saved', True))
    def fail(*_):
        raise OSError('Disk full')
    with monkeypatch.context() as m:
        m.setattr('lele.app.update_style_preset', fail)
        m.setattr(QMessageBox, 'warning', lambda *_: None)
        w.delete_style_button.click()
    assert path.read_bytes() == original and w.preset_combo.currentData() == 'Saved'
    w.delete_style_button.click()
    assert json.loads(path.read_text()) == {} and not w.delete_style_button.isEnabled()
