from pathlib import Path
import numpy as np
from unittest.mock import patch
from test_binary_wavefunctions_v320 import write_wavecar
from test_periodic_fragment_ui_v171 import gui
from lele.binary_wavefunctions import read_wavecar
from lele.output_text import LoadCancelled


def wave_document(tmp_path, *, coeff_count=1):
    path=write_wavecar(tmp_path/'WAVECAR', spins=2, coeff_count=coeff_count)
    (tmp_path/'POSCAR').write_text('H\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n')
    return read_wavecar(path)


def test_wavecar_selection_generation_and_labels(gui,tmp_path):
    w=gui.window;document=wave_document(tmp_path);w._attach_loaded_document(document)
    assert w.wavecar_generate.isEnabled()
    assert w.wavecar_spin.count()==2 and w.wavecar_kpoint.count()==2
    w.wavecar_spin.setCurrentIndex(1);w.wavecar_kpoint.setCurrentIndex(1);w.wavecar_band.setValue(2)
    assert 'Energy 3 eV' in w.wavecar_state.text()
    for kind in ('density','real','imag'):
        w.wavecar_kind.setCurrentIndex(w.wavecar_kind.findData(kind))
        with patch('lele.field_actions.run_data_task',side_effect=lambda parent,title,callback,**kwargs: callback()) as task:
            w._generate_wavecar_grid()
        assert task.call_args.kwargs['cancellable']
        assert f'band 2' in document.volume.label.lower()
        assert document.volume.unit and document.volume.periodic
        assert len(document.volumes)==('density','real','imag').index(kind)+1
    assert 'PAW' in w.wavecar_warning.text() and 'phase' in w.wavecar_warning.text()


def test_unsupported_or_modified_sources_disabled(gui,tmp_path):
    w=gui.window;document=wave_document(tmp_path,coeff_count=2);w._attach_loaded_document(document)
    assert not w.wavecar_generate.isEnabled()
    assert 'unavailable' in w.wavecar_state.text()
    document=wave_document(tmp_path);w._attach_loaded_document(document)
    document.modified=True;w._refresh_field_controls()
    assert not w.wavecar_generate.isEnabled()
    document.modified=False;document.wavecar.path.unlink();w._refresh_field_controls()
    assert not w.wavecar_generate.isEnabled()


def test_cancelled_wavecar_generation_keeps_state(gui,tmp_path):
    w=gui.window;document=wave_document(tmp_path);w._attach_loaded_document(document)
    with patch('lele.field_actions.run_data_task',side_effect=LoadCancelled()):
        w._generate_wavecar_grid()
    assert document.volume is None and document.volumes==[]
