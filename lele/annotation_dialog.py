"""Content and appearance of a world-space text annotation."""
from copy import deepcopy
from PySide6.QtWidgets import QVBoxLayout, QFormLayout, QPlainTextEdit, QDoubleSpinBox, QPushButton, QCheckBox, QDialogButtonBox, QLabel
from .dialog_policy import QDialog, QFileDialog, QColorDialog
from PySide6.QtGui import QColor


class AnnotationDialog(QDialog):
    def __init__(self, annotation, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Canvas text')
        self.resize(430, 310)
        self.annotation = deepcopy(annotation)
        root = QVBoxLayout(self)
        form = QFormLayout();root.addLayout(form)
        self.content = QPlainTextEdit(annotation.text)
        self.content.setMaximumHeight(110)
        form.addRow('Text', self.content)
        self.height = QDoubleSpinBox();self.height.setRange(.001, 1000.)
        self.height.setDecimals(3);self.height.setSingleStep(.05)
        self.height.setSuffix(' Å');self.height.setValue(annotation.height)
        form.addRow('Character size', self.height)
        self.color = QPushButton(annotation.color);self.color.clicked.connect(self._color)
        form.addRow('Color', self.color)
        self.bold = QCheckBox('Bold');self.bold.setChecked(annotation.bold);form.addRow('', self.bold)
        self.font = QPushButton('Choose font file…');self.font.clicked.connect(self._font)
        self.font.setToolTip(annotation.font_file or 'Optional TTF/OTF font, for example a CJK font.')
        form.addRow('Font', self.font)
        root.addWidget(QLabel('Click text to select it. Alt + middle drag moves it.\n'
                             'Alt + left drag rotates it; Alt + right drag rolls it.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        root.addWidget(buttons);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.content.textChanged.connect(self._validate);self._validate()

    def _validate(self):
        self.ok.setEnabled(bool(self.content.toPlainText().strip()) and len(self.content.toPlainText()) <= 10000)

    def _color(self):
        color = QColorDialog.getColor(QColor(self.annotation.color), self, 'Text color')
        if color.isValid():
            self.annotation.color = color.name();self.color.setText(color.name())

    def _font(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Text font', self.annotation.font_file, 'Font files (*.ttf *.otf)')
        if filename:
            self.annotation.font_file = filename;self.font.setToolTip(filename)

    def result_annotation(self):
        result = deepcopy(self.annotation)
        result.text = self.content.toPlainText();result.height = self.height.value();result.bold = self.bold.isChecked()
        result.__post_init__()
        return result
