
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyleOptionViewItem

from lele.binary_wavefunctions import read_wavecar
from lele.core import Document, Frame
from lele.orbital_picker import OrbitalPicker, initial_choice
from lele.periodic_geometry import short_contact_details
from test_binary_wavefunctions_v320 import write_wavecar
from test_periodic_fragment_ui_v171 import gui


def test_threshold_updates_sorted_snapshot_footer_and_next_frame(gui):
    w=gui.window
    f=Frame(['H','O','N'],[[.1,1,1],[1.9,1,1],[1.1,1,1]], np.diag([2,10,10]),(True,False,False))
    g=Frame(f.symbols,[[.1,1,1],[.6,1,1],[1.1,1,1]], f.cell,f.pbc)
    gui.attach(f,second_frame=g)
    d=w.show_short_contacts()
    assert len(d.contacts)==1 and d.threshold.value()==.6
    d.threshold.setValue(.9)
    assert d.table.rowCount()==2 and '2' in w.short_contacts_button.text()
    d.table.sortItems(2,Qt.SortOrder.DescendingOrder)
    d.threshold.setValue(1.1)
    assert d.table.item(0,2).data(Qt.ItemDataRole.DisplayRole)==pytest.approx(1)
    w.change_frame(1)
    d.threshold.setValue(.4)
    assert len(d.contacts)==1 and w.short_contacts_button.text()=='Short contacts 0'
    d.close();next_dialog=w.show_short_contacts()
    assert next_dialog.threshold.value()==.4 and not next_dialog.contacts
    next_dialog.close()
    rows=short_contact_details(f,50.)
    assert len(rows)==3 and rows[0].image_shift==(-1,0,0)


def test_flat_tree_paints_only_requested_rows_and_remains_navigable(gui, tmp_path, monkeypatch):
    import lele.workflow_ui as ui
    w=gui.window
    source=ui.frame_tree_label
    indices=[]
    def tracked(frame, index, *args, **kwargs):
        indices.append(index)
        return source(frame,index,*args,**kwargs)
    monkeypatch.setattr(ui,'frame_tree_label',tracked)
    doc=Document(tmp_path/'test.xyz','XYZ',[Frame(['H'],[[1,1,1+i*.01]]) for i in range(10000)])
    w.files_tree.clear();w.documents=[];w.current_doc=-1;w._attach_loaded_document(doc)
    parent=w.files_tree.topLevelItem(0)
    assert parent.childCount()==10000
    for k in (0,255,256,499,500,9999):
        leaf=parent.child(k)
        opt=QStyleOptionViewItem();w.files_tree.itemDelegate().initStyleOption(opt,leaf.index())
        assert opt.text==f'Frame {k+1}' and leaf.childCount()==0
        w.files_tree.setCurrentItem(leaf)
        assert w.frame_index==k
    assert len(set(indices))<256


@pytest.mark.parametrize('spins,ncoeff,factor,label',[(1,1,2,'Spin-degenerate'),(2,1,1,'Spin 1'),(1,2,None,'Stored channel 1')])
def test_wavecar_band_and_raw_weight_columns(gui,tmp_path,spins,ncoeff,factor,label):
    doc=read_wavecar(write_wavecar(tmp_path/'WAVECAR',spins=spins,coeff_count=ncoeff))
    wave=doc.wavecar;wave.occupations[0,0,0]=.375
    assert wave.occupation_factor==factor
    dlg=OrbitalPicker(doc,initial_choice(None,wave),gui.window)
    assert dlg.spins.tabText(0)==label
    assert dlg.model.index(0,3).data()=='0.375'
    assert dlg.model.index(0,1).data()==('—' if factor is None else str(.375*factor))
    dlg.close()
