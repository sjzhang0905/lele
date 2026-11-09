"""Private fresh-process Qt probe; run through benchmark_startup.py."""
import os
import sys
import time
import json

start = time.perf_counter()
# cwd is the selected source tree; never import the driver release by accident.
sys.path.insert(0, os.getcwd())
from PySide6.QtCore import QTimer, QObject, QEvent
from PySide6.QtWidgets import QApplication
from lele.app import LELEWindow

marks = {'imports_s': time.perf_counter() - start}
app = QApplication(['Startup benchmark'])
app.setStyle('Fusion')
window = LELEWindow()
marks['constructed_s'] = time.perf_counter() - start


class Probe(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Paint and 'first_paint_s' not in marks:
            marks['first_paint_s'] = time.perf_counter() - start
        return False


probe = Probe(window)
window.welcome_page.title_label.installEventFilter(probe)


def check():
    if window._backend_state == 'failed':
        print(window._backend_loader.error, file=sys.stderr)
        app.exit(1)
    elif window._backend_state == 'ready':
        marks['ready_s'] = time.perf_counter() - start
        print(json.dumps(marks), flush=True)
        window.close()


timer = QTimer()
timer.timeout.connect(check)
timer.start(1)
QTimer.singleShot(20000, lambda: app.exit(2))
window.show()
sys.exit(app.exec())
