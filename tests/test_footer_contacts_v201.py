"""Compact footer, inspectable periodic contacts and source-cell volumes."""
import numpy as np
import pytest

from lele.core import Frame
from lele.periodic_geometry import short_contact_details, short_contacts
from test_periodic_fragment_ui_v171 import gui


def test_contact_details_and_summary_count_share_unique_pairs_and_distances():
    frame = Frame(['H']*3, [[0,0,0],[.2,0,0],[.5,0,0]])
    rows = short_contact_details(frame)
    assert len(rows) == short_contacts(frame)[0] == 3
    np.testing.assert_allclose([r.distance for r in rows], [.2,.3,.5])
    assert len({(r.first,r.second) for r in rows}) == 3
    assert all(r.image_shift == (0,0,0) for r in rows)


def test_contact_cutoff_is_strict_and_empty_geometry_is_supported():
    assert short_contact_details(Frame(['H','H'], [[0,0,0],[.6,0,0]])) == []
    assert short_contacts(Frame(['H'], [[0,0,0]])) == (0,None)
    assert short_contact_details(Frame([], [])) == []


@pytest.mark.parametrize('second,expected', [(9.8,(-1,0,0)), (19.8,(-2,0,0)), (-.2,(0,0,0))])
def test_periodic_image_shifts_reconstruct_the_contact_in_original_coordinates(second, expected):
    frame = Frame(['O','H'], [[.1,0,0],[second,0,0]], np.eye(3)*10, (True,True,True))
    row, = short_contact_details(frame)
    assert row.image_shift == expected
    displacement = frame.positions[row.second] + np.asarray(row.image_shift) @ frame.cell - frame.positions[row.first]
    assert np.linalg.norm(displacement) == pytest.approx(row.distance)
    assert row.distance == pytest.approx(.3)
    assert short_contacts(frame)[0] == 1


def test_skew_cell_contact_has_a_consistent_minimum_image():
    cell = np.array([[4.,0,0],[1.,3,0],[0,0,2.]])
    frame = Frame(['C','O'], np.array([[.02,.02,.2],[.98,.98,.2]]) @ cell, cell, (True,True,True))
    row, = short_contact_details(frame)
    assert row.image_shift == (-1,-1,0)
    assert row.distance == pytest.approx(np.linalg.norm([-.2,-.12,0]))


def test_footer_is_compact_and_button_opens_contact_details(gui):
    frame = Frame(['H']*3, [[0,0,0],[.2,0,0],[.5,0,0]])
    gui.attach(frame); w = gui.window
    gui.addCleanup(lambda: [d.close() for d in list(w._analysis_windows)])
    assert w.summary_label.text() == 'Atoms 3  |  Formula H3  |  electrons odd  |'
    assert w.short_contacts_button.text() == 'Short contacts 3'
    assert ':' not in w.summary_label.text()
    assert '0.6' not in w.short_contacts_button.text()
    assert 'assumed charge 0' in w.summary_label.toolTip()
    w.resize(1380,850); w.show(); gui.app.processEvents()
    margins = w.summary_label.contentsMargins()
    assert w.summary_label.height() <= w.summary_label.fontMetrics().height() + margins.top() + margins.bottom() + 4
    w.short_contacts_button.click(); dialog, = w._analysis_windows
    assert dialog.table.rowCount() == 3 and dialog.table.columnCount() == 3
    assert float(dialog.table.item(0,2).text()) == pytest.approx(.2)
    assert dialog.table.item(0,0).text() == 'H1'
    gui.select([0,1]); assert ':' not in w.measurement_label.text()


def test_periodic_popup_reports_image_and_snapshot_context(gui):
    frame = Frame(['O','H'], [[.1,0,0],[9.8,0,0]], np.eye(3)*10, (True,True,True))
    other = frame.clone(); other.positions[1,0] = 5
    gui.attach(frame, second_frame=other); w = gui.window
    gui.addCleanup(lambda: [d.close() for d in list(w._analysis_windows)])
    assert 'Composition H1O1' in w.summary_label.text()
    w.short_contacts_button.click(); dialog, = w._analysis_windows
    assert dialog.table.columnCount() == 4 and dialog.table.item(0,3).text() == '-1 0 0'
    assert 'Frame 1' in dialog.context_label.text()
    w.change_frame(1)
    assert w.short_contacts_button.text() == 'Short contacts 0'
    assert len(dialog.contacts) == 1 and 'Frame 1' in dialog.context_label.text()
    empty = w.show_short_contacts()
    assert empty.table.rowCount() == 0 and 'No short contacts' in empty.note.text()


@pytest.mark.parametrize('cell', [np.diag([2.,3,4]), np.array([[-2.,0,0],[1.,3,0],[.5,.2,4.]])])
def test_results_info_uses_absolute_determinant_for_periodic_volume_and_updates_by_frame(gui, cell):
    frame = Frame(['He'], [[0,0,0]], cell, (True,True,True))
    other = frame.clone(); other.cell *= 2
    gui.attach(frame, second_frame=other); w = gui.window
    assert 'Cell volume: 24.000000 Å³' in w.info_view.toPlainText()
    w.change_frame(1)
    assert 'Cell volume: 192.000000 Å³' in w.info_view.toPlainText()
    other.pbc = (False,False,False); w._refresh_info()
    assert 'Cell volume' not in w.info_view.toPlainText()


def test_frequency_reference_uses_its_own_contacts(gui):
    doc = gui.attach_vibrations(); w = gui.window
    gui.addCleanup(lambda: [d.close() for d in list(w._analysis_windows)])
    w.select_vibration(0,0,0,autoplay=False)
    dialog = w.show_short_contacts()
    assert 'Frequency reference 1' in dialog.context_label.text()
    np.testing.assert_array_equal(dialog.frame.positions, doc.vibrations[0].reference.positions)
