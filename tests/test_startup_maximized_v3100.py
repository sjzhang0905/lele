"""Exercise the installed entry point's first window state in a fresh Qt app."""
import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_entry_point_opens_maximized_and_can_restore():
    result = subprocess.run(
        [sys.executable, '-c', textwrap.dedent('''
            from unittest.mock import patch
            from PySide6.QtWidgets import QApplication
            from lele.app import LELEWindow, main

            def inspect_event_loop():
                app = QApplication.instance()
                app.processEvents()
                window = next(w for w in app.topLevelWidgets() if isinstance(w, LELEWindow))
                assert window.isMaximized()
                assert window.isVisible()
                window.showNormal()
                app.processEvents()
                assert not window.isMaximized()
                window.close()
                return 0

            with patch.object(LELEWindow, '_start_backend_loading'), \
                 patch.object(LELEWindow, '_read_user_style_presets', return_value={}), \
                 patch.object(QApplication, 'exec', side_effect=inspect_event_loop):
                assert main([]) == 0
        ''')],
        cwd=Path(__file__).resolve().parents[1],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'),
        text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
