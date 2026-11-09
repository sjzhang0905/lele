"""Renamed charge grids survive the actual background import and field UI."""
from pathlib import Path
from unittest.mock import patch
import hashlib
import os
import shutil

import numpy as np
import pytest

from test_periodic_fragment_ui_v171 import gui
from test_large_files_v250 import wait_until


@pytest.mark.parametrize('name',['renamed_density.dat','renamed_density.vasp'])
def test_renamed_grid_background_import_populates_field_controls(gui,tmp_path,name):
    from test_volumetric_readers_v320 import vasp_text
    path=tmp_path/name
    path.write_text(vasp_text([24]*8,
        'augmentation occupancies 1 3\n2 2 2\n2 2 2\n'+' '.join(['12']*8)+'\n'))
    window=gui.window
    window._closing=False
    window._backend_state='ready'
    before=len(window.documents)
    errors=[]
    with patch('lele.file_loading.ASYNC_THRESHOLD',0), patch(
        'lele.file_loading.QMessageBox.warning',side_effect=lambda *args:errors.append(args)
    ):
        window.open_path(path)
        wait_until(gui,lambda:window._file_load_active is None)
        wait_until(gui,lambda:not gui.app._lele_file_loaders)
    assert not errors
    assert len(window.documents)==before+1
    assert window.doc.path==path.resolve()
    assert window.atom_table.rowCount()==2
    assert window.field_combo.count()==2
    assert window.field_combo.isEnabled()
    np.testing.assert_array_equal(window.doc.volumes[0].data,1)
    np.testing.assert_array_equal(window.doc.volumes[1].data,.5)
    window.field_combo.setCurrentIndex(1)
    assert window.doc.volume is window.doc.volumes[1]


def test_supplied_chgcar_renamed_exact_original_grid(tmp_path):
    """The user's 6-atom 48x48x192 example is external, never redistributed."""
    source=os.environ.get('LELE_CHGCAR_EXAMPLE')
    if not source:
        pytest.skip('Set LELE_CHGCAR_EXAMPLE to the supplied CHGCAR; not redistributed.')
    from lele.formats import load_document
    hashes=set()
    for name in ('CHGCAR','CHGCAR(1)','charge_difference','charge.vasp','charge.txt','charge.cube'):
        path=tmp_path/name
        shutil.copyfile(source,path)
        doc=load_document(path)
        assert len(doc.frames)==1 and len(doc.frames[0].symbols)==6
        assert doc.frames[0].symbols==['Mo','Mo','S','S','S','S']
        assert len(doc.volumes)==1 and doc.volume.unit=='e/Å³'
        assert doc.volume.data.shape==(48,48,192)
        assert doc.volume.data.dtype==np.float32
        hashes.add(hashlib.sha256(doc.volume.data.tobytes()).hexdigest())
    # Measured with v3.5.1 under the canonical CHGCAR name before the fix.
    assert hashes=={'52ef3ef764df5a11fbb020a7c3e033152d3ea3ad251c2b8621cd394d077030b0'}
