"""Repeatedly widened lower panels must not stretch their action buttons."""
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QPushButton, QStyleFactory, QWidget
from lele.app import LELEWindow
from lele.color_controls import color_value


@pytest.mark.parametrize('style', ['Windows', 'Fusion'])
def test_lower_actions_keep_natural_width_and_colors_remain_swatches(style):
    app = QApplication.instance() or QApplication([])
    app.setStyle(QStyleFactory.create(style))
    with patch.object(LELEWindow, '_start_backend_loading', lambda self: None):
        window = LELEWindow()
    try:
        window.resize(1920, 1000)
        window.show()
        window.structure_page.insertWidget(0, QWidget())
        window.canvas_stack.setCurrentWidget(window.structure_page)
        window.structure_page.setSizes([400, 550])
        for width in (450, 700, 1000):
            window.lower_splitter.setSizes([width, 1500-width, 300])
            for tab in range(window.bottom_control_tabs.count()):
                window.bottom_control_tabs.setCurrentIndex(tab)
                app.processEvents()
                for button in window.bottom_control_tabs.currentWidget().findChildren(QPushButton):
                    if button.isVisible():
                        assert button.width() <= 265
                        assert button.width() <= max(26, button.sizeHint().width())
        window._set_option('background', '#439ea5')
        window._set_option('label_color', '#123456')
        assert color_value(window.bg_btn) == '#439ea5'
        assert color_value(window.label_color_btn) == '#123456'
        for button in (window.bg_btn, window.label_color_btn,
                       window.positive_color, window.negative_color):
            assert not button.text()
            assert button.width() == button.height() == 26
            assert button.accessibleName()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
