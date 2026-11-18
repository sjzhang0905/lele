"""Small color swatches shared by appearance controls."""
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy


def set_color_swatch(button, color, label='Color'):
    """Show a square instead of a hex label; keep the value separate from text."""
    value = QColor(color) if color else QColor()
    button.setProperty('leleColor', value.name() if value.isValid() else '')
    button.setText('')
    button.setFixedSize(26, 26)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button.setAccessibleName(label)
    button.setToolTip(label if value.isValid() else label + ' (mixed)')
    fill = value.name() if value.isValid() else 'qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #ffffff,stop:0.49 #ffffff,stop:0.5 #64748b,stop:1 #64748b)'
    button.setStyleSheet('QPushButton { background: ' + fill +
                        '; border: 1px solid #64748b; border-radius: 2px; padding: 0px; }'
                        'QPushButton:hover { border: 2px solid #1685b8; }'
                        'QPushButton:focus { border: 2px solid #1685b8; }')


def color_value(button):
    return button.property('leleColor') or ''
