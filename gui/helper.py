from PyQt5 import QtCore
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QToolButton, QGridLayout
)


class Label(QLabel):
    def __init__(self, img, img_scale=0.7):
        super(Label, self).__init__()

        self.img_scale = img_scale
        self.pixmap = QPixmap(img)

        self.setMinimumSize(1, 1)
        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignHCenter)
        self.setPixmap(self.pixmap)

    def resizeEvent(self, event):
        w = self.size().width() * self.img_scale
        h = self.size().height() * self.img_scale
        scaled_size = QtCore.QSize(w, h)

        scaled_pixmap = self.pixmap.scaled(
            scaled_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )

        self.setPixmap(scaled_pixmap)


class CollapsibleSection(QFrame):
    def __init__(self, header_text, init_collapsed=False, is_top=False):
        super().__init__()

        if not is_top:
            self.setObjectName("CollapsibleSection")
            self.setStyleSheet("#CollapsibleSection{border-top: 1px solid lightgrey;}")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)
        self._header_widget = QWidget()
        self.body_widget = QWidget()
        self._layout.addWidget(self._header_widget)
        self._layout.addWidget(self.body_widget)

        self.grid = QGridLayout(self.body_widget)
        self.grid.setContentsMargins(9, 0, 9, 9)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

        self._header_widget_layout = QHBoxLayout(self._header_widget)
        self._header_widget_layout.setContentsMargins(7, 7, 7, 7)
        self._header_widget.setLayout(self._header_widget_layout)

        self._button = QToolButton()
        self._button.setText(header_text)
        self._button.setCheckable(True)
        self._button.setStyleSheet("QToolButton { border: none; }")
        self._button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._button.pressed.connect(self.button_event)
        self.button_event(override=init_collapsed)
        self._header_widget_layout.addWidget(self._button)
        self._header_widget_layout.addStretch()

    def button_event(self, override=None):
        if override is None:
            checked = not self._button.isChecked()
        else:
            checked = override
            self._button.setChecked(checked)

        if checked:  # collapsed
            self._button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
            self.body_widget.hide()
        else:
            self._button.setArrowType(QtCore.Qt.ArrowType.DownArrow)
            self.body_widget.show()
