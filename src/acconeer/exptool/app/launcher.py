# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import importlib.resources
from typing import Optional, Union

from typing_extensions import Literal

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import acconeer.exptool.app.resources as et_app_resources


class ImageButton(QToolButton):
    def __init__(
        self, text: str, image_path: str, size: QSize, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)
        self._layout = QVBoxLayout(self)
        self.setLayout(self._layout)
        self.setFixedSize(size)
        self.setIconSize(size)

        self._image_path = image_path
        self._animator = QVariantAnimation(self)
        self._animator.valueChanged.connect(self._update_zoom)

        self._layout.addStretch()
        self._layout.addWidget(QLabel(text), 0, alignment=Qt.AlignCenter)
        self.setStyleSheet(
            f"""
            QLabel {{
                font: bold;
                color: #000;
                font-size: 32px;
            }}
            QToolButton {{
                /* The border-image attribute is hack:
                 * https://forum.qt.io/topic/40151/solved-scaled-background-image-using-stylesheet
                 */
                border-image: url({image_path}) 0 0 0 0 stretch stretch;
            }}
            """
        )
        self.installEventFilter(self)

    def _do_animation(self, start_value: int, end_value: int, duration: int = 500) -> None:
        self._animator.stop()
        self._animator.setDuration(duration)
        self._animator.setStartValue(start_value)
        self._animator.setEndValue(end_value)
        self._animator.setEasingCurve(QEasingCurve.InOutSine)
        self._animator.start()

    def eventFilter(self, _: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.HoverEnter:
            self._do_animation(0, 100, duration=300)

        if event.type() == QEvent.HoverLeave:
            self._do_animation(100, 0, duration=100)

        return False

    def _update_zoom(self, current_value: float) -> None:
        zoom_string = str(current_value)
        self.setStyleSheet(
            f"""
            QLabel {{
                font: bold;
                color: #000;
                font-size: 32px;
            }}
            QToolButton {{
                border-image: url({self._image_path}) {zoom_string} stretch stretch;
            }}
            """
        )


class CentralWidget(QWidget):
    sig_a121_clicked = Signal()
    sig_a111_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayout(QHBoxLayout(self))

        with importlib.resources.path(et_app_resources, "a121_gui.png") as path:
            a121_button = ImageButton("A121 (Beta)", path.as_posix(), QSize(500, 300))
            a121_button.clicked.connect(self.sig_a121_clicked)
            self.layout().addWidget(a121_button)

        with importlib.resources.path(et_app_resources, "a111_gui.png") as path:
            a111_button = ImageButton("A111", path.as_posix(), QSize(500, 300))
            a111_button.clicked.connect(self.sig_a111_clicked)
            self.layout().addWidget(a111_button)


class ValueHolder:
    def __init__(self) -> None:
        self.selection: Optional[Union[Literal["a121"], Literal["a111"]]] = None


class Launcher(QMainWindow):
    def __init__(self, value_holder: ValueHolder) -> None:
        super().__init__()
        self._value_holder = value_holder

        self._central_widget = CentralWidget()
        self._central_widget.sig_a111_clicked.connect(lambda: self.on_selection("a111"))
        self._central_widget.sig_a121_clicked.connect(lambda: self.on_selection("a121"))

        self.setWindowTitle("Acconeer Exptool Launcher")
        self.setCentralWidget(self._central_widget)

    def on_selection(self, selection: Union[Literal["a121"], Literal["a111"]]) -> None:
        self._value_holder.selection = selection
        self.close()


def run_launcher() -> Optional[Union[Literal["a121"], Literal["a111"]]]:
    app = QApplication([])

    vh = ValueHolder()
    launcher = Launcher(vh)
    launcher.show()

    app.exec()

    return vh.selection
