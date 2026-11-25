from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialogButtonBox

from lele.formats import load_document
from lele.orbital_picker import OrbitalPicker
from test_periodic_fragment_ui_v171 import gui
from test_wavefunction_inputs import fchk_text, molden_text


@pytest.mark.parametrize('suffix', ['fchk', 'molden'])
def test_molecular_picker_select_cancel_switch_and_evaluate(gui, tmp_path, suffix):
    path = tmp_path / ('spin.' + suffix)
    # Opposite phase for beta makes an accidental alpha evaluation detectable.
    source = fchk_text(True) if suffix == 'fchk' else molden_text()
    prefix = source.rstrip().rsplit('\n', 1)[0]
    path.write_text(prefix + '\n' + ('-1' if suffix == 'fchk' else '1 -1.0') + '\n')
    doc = load_document(path)
    win = gui.window
    win._attach_loaded_document(doc)
    assert win.mo_select.isEnabled() and 'Alpha' in win.mo_selected.text()

    def select_beta(dialog):
        assert [dialog.spins.tabData(i) for i in range(dialog.spins.count())] == ['alpha', 'beta']
        assert not dialog.kpoints.isEnabled() and dialog.kpoints.currentData() is None
        dialog.spins.setCurrentIndex(1)
        assert float(dialog.model.data(dialog.model.index(0, 1))) == 0.
        assert float(dialog.model.data(dialog.model.index(0, 2))) > 0.
        return dialog.DialogCode.Accepted

    with patch.object(OrbitalPicker, 'exec', select_beta):
        win.mo_select.click()
    assert 'Beta' in win.mo_selected.text() and doc.volume is None

    def cancel(dialog):
        assert dialog.spins.tabData(dialog.spins.currentIndex()) == 'beta'
        dialog.spins.setCurrentIndex(0)
        return dialog.DialogCode.Rejected

    with patch.object(OrbitalPicker, 'exec', cancel):
        win.mo_select.click()
    other = tmp_path / 'restricted.fchk'
    other.write_text(fchk_text())
    win._attach_loaded_document(load_document(other))
    assert win.mo_selected.text() == 'Restricted · MO 1'
    win.change_frame(0, switch_doc=win.documents.index(doc))
    assert 'Beta' in win.mo_selected.text()
    win.mo_generate.click()
    assert doc.volume.label == 'beta MO 1'
    expected = doc.wavefunction.evaluate_orbital('beta', 1, spacing=win.mo_spacing.value())
    np.testing.assert_array_equal(doc.volume.data, expected.data)
    assert doc.volume.data.min() < 0 and doc.volume.data.max() <= 0


def test_real_picker_buttons_accept_and_cancel(gui, tmp_path):
    path = tmp_path / 'spin.molden'
    path.write_text(molden_text())
    window = gui.window
    window._attach_loaded_document(load_document(path))
    for tab, button in [(1, QDialogButtonBox.StandardButton.Ok), (0, QDialogButtonBox.StandardButton.Cancel)]:
        def click_button():
            dialog = next(d for d in window.findChildren(OrbitalPicker) if d.isVisible())
            dialog.spins.setCurrentIndex(tab)
            dialog.buttons.button(button).click()
        QTimer.singleShot(0, click_button)
        window.mo_select.click()
        assert 'Beta' in window.mo_selected.text()
