"""On-demand orbitals and persistent measurements beside Short contacts."""
from pathlib import Path
import numpy as np
from lele.core import Frame
from lele.formats import load_document
from test_periodic_fragment_ui_v171 import gui

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples/synthetic_orca_full_v190.out'


def test_bottom_measurement_covers_length_angle_dihedral_clear_and_frame_change(gui):
    frame = Frame(['C']*4, [[0,1,0],[0,0,0],[1,0,0],[1,0,1]])
    second = frame.clone();second.positions *= 2
    gui.attach(frame, second_frame=second);w = gui.window
    gui.select([0,1]);assert 'Bond length' in w.measurement_label.text() and '1.0000 Å' in w.measurement_label.text()
    w.change_frame(1);assert '2.0000 Å' in w.measurement_label.text()
    gui.select([0,1,2]);assert 'Bond angle' in w.measurement_label.text() and '90.0000 °' in w.measurement_label.text()
    gui.select([0,1,2,3]);assert 'Dihedral' in w.measurement_label.text() and '90.0000 °' in w.measurement_label.text()
    assert 'Short contacts' in w.short_contacts_button.text()
    w.resize(1600,900);w.show();gui.app.processEvents()
    assert w.measurement_label.isVisible()
    assert w.measurement_label.x() >= w.summary_label.x()+w.summary_label.width()
    w.clear_selection();assert not w.measurement_label.text()
    gui.select([1]);assert not w.measurement_label.text()


def test_orca_button_curve_and_frequency_reference_use_current_document(gui):
    from lele.orbital_dialog import OrbitalDialog
    from matplotlib.backend_bases import MouseEvent
    w = gui.window
    gui.addCleanup(lambda: [dialog.close() for dialog in list(w._analysis_windows)])
    w._open_path_now(EXAMPLE)
    assert not w._analysis_windows and w.orbital_btn.isEnabled()
    w.orbital_btn.click();dialog, = w._analysis_windows
    assert isinstance(dialog, OrbitalDialog) and dialog.summary.rowCount() == 2
    assert dialog.summary.item(0,1).text() == '1'
    curve = w.show_energy_curve();curve.scan_only.setChecked(False);curve.canvas.draw()
    line = curve.energy_axes.lines[0]
    x,y = line.axes.transData.transform((line.get_xdata()[-1], line.get_ydata()[-1]))
    event = MouseEvent('button_press_event', curve.canvas, x, y, button=1)
    curve.canvas.callbacks.process('button_press_event', event)
    assert w.frame_index == 1
    w.select_vibration(w.current_doc,0,0,autoplay=False)
    assert w._active_vibration == (w.current_doc,0,0)
    assert w.doc.vibrations[0].modes[0].number == 6
    np.testing.assert_array_equal(w.frame.positions,w.doc.frames[1].positions)
    gui.select([0,1]);assert '0.9600 Å' in w.measurement_label.text()
