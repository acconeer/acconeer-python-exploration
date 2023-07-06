# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import threading
from typing import Optional

import numpy as np

from PySide6 import QtCore
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QStatusBar,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import acconeer.exptool
from acconeer.exptool.app.new import check_package_outdated, get_latest_changelog
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.utils import get_module_version  # type: ignore[import]

from .icons import BUTTON_ICON_COLOR, REFRESH


class FrameCountLabel(QLabel):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setToolTip("Number of received frames")

        app_model.sig_frame_count.connect(self._on_app_model_frame_count)
        self._on_app_model_frame_count(None)

    def _on_app_model_frame_count(self, frame_count: Optional[int]) -> None:
        if frame_count is None:
            css = "color: #888;"
            text = "Frames: -    "
        else:
            css = ""
            text = f"Frames: {frame_count:5}"

        self.setStyleSheet(f"QWidget{{{css}}}")
        self.setText(text)


class RateStatsLabel(QLabel):
    _FPS: int = 10

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setToolTip("Reported update rate")

        self.rate = np.nan
        self.rate_warning = False

        self.startTimer(int(1000 / self._FPS))

        app_model.sig_rate_stats.connect(self._on_app_model_rate_stats)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if np.isnan(self.rate):
            css = "color: #888;"
            text = "     - Hz"
        else:
            css = "color: #FD5200;" if self.rate_warning else ""
            text = f"{self.rate:>6.1f} Hz"

        self.setStyleSheet(f"QWidget{{{css}}}")
        self.setText(text)

    def _on_app_model_rate_stats(
        self,
        rate: float,
        rate_warning: bool,
        jitter: float,
        jitter_warning: bool,
    ) -> None:
        self.rate = rate
        self.rate_warning = rate_warning


class JitterStatsLabel(QLabel):
    _FPS: int = 10

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setToolTip("Reported jitter")

        self.jitter = np.nan
        self.jitter_warning = False

        self.startTimer(int(1000 / self._FPS))

        app_model.sig_rate_stats.connect(self._on_app_model_rate_stats)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if np.isnan(self.jitter):
            css = "color: #888;"
            text = "    - ms"
        else:
            css = "color: #FD5200;" if self.jitter_warning else ""
            text = f"{self.jitter * 1e3:5.1f} ms"

        self.setStyleSheet(f"QWidget{{{css}}}")
        self.setText(text)

    def _on_app_model_rate_stats(
        self,
        rate: float,
        rate_warning: bool,
        jitter: float,
        jitter_warning: bool,
    ) -> None:
        self.jitter = jitter
        self.jitter_warning = jitter_warning


class BackendCPUPercentLabel(QLabel):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setToolTip("Client process CPU load")

        app_model.sig_backend_cpu_percent.connect(self._on_app_model_backend_cpu_percent)

        self._on_app_model_backend_cpu_percent(0)

    def _on_app_model_backend_cpu_percent(self, cpu_percent: int) -> None:
        self.setText(f"CPU: {cpu_percent:3}%")

        css = "color: #FD5200;" if cpu_percent >= 85 else ""
        self.setStyleSheet(f"QWidget{{{css}}}")


class RSSVersionLabel(QLabel):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        app_model.sig_notify.connect(self._on_app_model_update)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.rss_version is None:
            css = "color: #888;"
            text = "RSS: <not connected>"
            tooltip = ""
        else:
            text = f"RSS: {app_model.rss_version}"

            if app_model.connection_warning:
                css = "background-color: #D78100; color: #e2e2e2;"
                tooltip = app_model.connection_warning
            else:
                css = ""
                tooltip = ""

        self.setToolTip(tooltip)
        self.setStyleSheet(f"QWidget{{{css}}}")
        self.setText(text)


class VersionButton(QPushButton):
    sig_payload = QtCore.Signal(
        tuple
    )  # tuple[changelog (str), latest version (str), outdated? (bool)]

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        et_version = get_module_version(acconeer.exptool)
        self._changelog_text: Optional[str] = None

        self.setFlat(True)
        self.setText(f"ET: {et_version}")

        self.clicked.connect(self._on_click)
        self.sig_payload.connect(self._handle_payload)

        self._version_thread = threading.Thread(target=lambda: self._get_payload(et_version))
        self._version_thread.start()

    def _on_click(self) -> None:
        if self._changelog_text is None:
            return

        ChangelogDialog(markdown_text=self._changelog_text).exec()

    def _handle_payload(self, payload: tuple[str, str, bool]) -> None:
        (changelog_text, latest_version, is_outdated) = payload

        if not is_outdated:
            return

        self._changelog_text = changelog_text

        self.setIcon(REFRESH(color="#e2e2e2"))
        self.setStyleSheet(
            f"QPushButton{{ background-color: {BUTTON_ICON_COLOR}; color: #e2e2e2; }}"
        )
        self.setToolTip(
            "There is a new software version available!\n"
            f"The latest version is: {latest_version}. \n"
            "Click to view changelog."
        )

    def _get_payload(self, et_version: str) -> None:
        is_outdated, latest_version = check_package_outdated("acconeer-exptool", et_version)
        self.sig_payload.emit((get_latest_changelog(), latest_version, is_outdated))


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        app_model.sig_status_message.connect(self._on_app_model_status_message)

        self.message_timer = QtCore.QTimer(self)
        self.message_timer.setInterval(3000)
        self.message_timer.setSingleShot(True)
        self.message_timer.timeout.connect(self._on_timer)

        self.message_widget = QLabel(self)
        self.addWidget(self.message_widget)

        self.addPermanentWidget(FrameCountLabel(app_model, self))
        self.addPermanentWidget(RateStatsLabel(app_model, self))
        self.addPermanentWidget(JitterStatsLabel(app_model, self))
        self.addPermanentWidget(BackendCPUPercentLabel(app_model, self))
        self.addPermanentWidget(RSSVersionLabel(app_model, self))
        self.addPermanentWidget(VersionButton(app_model, self))

        font_families = [
            "Consolas",  # Windows
            "Droid Sans Mono",  # Ubuntu
            "DejaVu Sans Mono",  # Ubuntu, backup
            "SF Mono",  # Mac
        ]
        font_family = ", ".join(f'"{ff}"' for ff in font_families)
        self.setStyleSheet(f"QWidget{{font-family: {font_family};}}")

    def _on_app_model_status_message(self, message: Optional[str]) -> None:
        self.message_timer.stop()

        if message:
            self.message_widget.setText(message)
            self.message_timer.start()
        else:
            self.message_widget.clear()

    def _on_timer(self) -> None:
        self.message_widget.clear()


class ChangelogDialog(QDialog):
    def __init__(self, markdown_text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        document = QTextDocument()
        document.setMarkdown(markdown_text)

        text_browser = QTextBrowser(self)
        text_browser.setDocument(document)
        text_browser.setMinimumWidth(round(document.idealWidth() * 1.1))
        text_browser.setMinimumHeight(500)

        self.setLayout(QVBoxLayout())
        self.layout().addWidget(text_browser)
