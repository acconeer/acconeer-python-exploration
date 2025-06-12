# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

from importlib.resources import as_file, files
from typing import Optional

from typing_extensions import Literal

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
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

        label_shadow = QGraphicsDropShadowEffect(self)
        label_shadow.setColor(QColor(64, 64, 64))
        label_shadow.setOffset(2, 2)
        label_shadow.setBlurRadius(10)

        label = QLabel(text)
        label.setGraphicsEffect(label_shadow)

        self._layout.addStretch()
        self._layout.addWidget(label, 0, alignment=Qt.AlignmentFlag.AlignCenter)
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
                border-image: url('{image_path}') 0 0 0 0 stretch stretch;
            }}
            """
        )
        self.installEventFilter(self)

    def _do_animation(self, start_value: int, end_value: int, duration: int = 500) -> None:
        self._animator.stop()
        self._animator.setDuration(duration)
        self._animator.setStartValue(start_value)
        self._animator.setEndValue(end_value)
        self._animator.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animator.start()

    def eventFilter(self, _: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.HoverEnter:
            self._do_animation(0, 100, duration=300)

        if event.type() == QEvent.Type.HoverLeave:
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
                border-image: url('{self._image_path}') {zoom_string} stretch stretch;
            }}
            """
        )


class CentralWidget(QWidget):
    sig_new_app_clicked = Signal()
    sig_old_app_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)

        with as_file(files(et_app_resources) / "new_gui.png") as path:
            new_app_button = ImageButton("A121", path.as_posix(), QSize(500, 300))
            new_app_button.clicked.connect(self.sig_new_app_clicked)
            layout.addWidget(new_app_button)

        with as_file(files(et_app_resources) / "old_gui.png") as path:
            old_app_button = ImageButton("A111", path.as_posix(), QSize(500, 300))
            old_app_button.clicked.connect(self.sig_old_app_clicked)
            layout.addWidget(old_app_button)

        self.setLayout(layout)


class ValueHolder:
    def __init__(self) -> None:
        self.selection: Optional[Literal["new", "old"]] = None


class Launcher(QMainWindow):
    def __init__(self, value_holder: ValueHolder) -> None:
        super().__init__()
        self._value_holder = value_holder

        self._central_widget = CentralWidget()
        self._central_widget.sig_new_app_clicked.connect(lambda: self.on_selection("new"))
        self._central_widget.sig_old_app_clicked.connect(lambda: self.on_selection("old"))

        self.setWindowTitle("Acconeer Exptool Launcher")
        self.setCentralWidget(self._central_widget)

    def on_selection(self, selection: Literal["new", "old"]) -> None:
        self._value_holder.selection = selection
        self.close()


def run_launcher() -> Optional[Literal["new", "old"]]:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )

    app = QApplication([])

    vh = ValueHolder()
    launcher = Launcher(vh)
    launcher.show()

    app.exec()

    return vh.selection
