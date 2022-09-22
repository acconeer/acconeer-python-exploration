# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import threading
from typing import Optional

import importlib_metadata
import numpy as np
import qtawesome as qta

from PySide6 import QtCore
from PySide6.QtGui import QPainter, QTextDocument
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyleOption,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new import check_package_outdated, get_latest_changelog
from acconeer.exptool.app.new.app_model import AppModel

from .connection_widget import ClientConnectionWidget, GenerationSelection
from .flash_widget import FlashButton
from .misc import (
    BUTTON_ICON_COLOR,
    ConnectionHint,
    ExceptionWidget,
    UnflashedDeviceHint,
    VerticalSeparator,
)
from .plugin_widget import PluginControlArea, PluginPlotArea, PluginSelection
from .recording_widget import RecordingWidget
from .utils import ScrollAreaDecorator, TopAlignDecorator


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        self.setCentralWidget(MainWindowCentralWidget(app_model, self))
        self.setStatusBar(StatusBar(app_model, self))
        self.setWindowTitle("Acconeer Exploration Tool (Beta)")
        self.moveEvent = lambda _: self.saveGeometry()

        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_error(self, exception: Exception, traceback_str: Optional[str]) -> None:
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()


class MainWindowCentralWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        top_bar = TopBar(app_model, self)
        self.layout().addWidget(top_bar)
        self.layout().setStretchFactor(top_bar, 0)

        working_area = WorkingArea(app_model, self)
        self.layout().addWidget(working_area)
        self.layout().setStretchFactor(working_area, 1)


class TopBar(QFrame):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setObjectName("TopBar")
        self.setStyleSheet("QFrame#TopBar {background: #ebebeb;}")

        self.setLayout(QHBoxLayout(self))

        self.layout().addWidget(GenerationSelection(app_model, self))
        self.layout().addWidget(VerticalSeparator(self))
        self.layout().addWidget(ClientConnectionWidget(app_model, self))
        self.layout().addWidget(VerticalSeparator(self))
        self.layout().addWidget(FlashButton(app_model, self))
        self.layout().addWidget(ConnectionHint(app_model, self))
        self.layout().addWidget(UnflashedDeviceHint(app_model, self))
        self.layout().addStretch(1)
        self.layout().addWidget(RecordingWidget(app_model, self))


class WorkingArea(QSplitter):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        left_area = ScrollAreaDecorator(
            TopAlignDecorator(
                PluginSelection(app_model, self),
            )
        )
        left_area.setMinimumWidth(250)
        left_area.setMaximumWidth(350)
        self.layout().addWidget(left_area)
        self.layout().setStretchFactor(left_area, 0)

        plot_plugin_area = PluginPlotArea(app_model, self)
        self.layout().addWidget(plot_plugin_area)
        self.layout().setStretchFactor(plot_plugin_area, 1)

        right_area = PluginControlArea(app_model, self)
        right_area.setMinimumWidth(400)
        right_area.setMaximumWidth(450)
        self.layout().addWidget(right_area)
        self.layout().setStretchFactor(right_area, 0)


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

        self.setStyleSheet(css)
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

        self.setStyleSheet(css)
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
        self.setStyleSheet(css)


class VersionLabel(QWidget):
    sig_version_outdated = QtCore.Signal()

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.parent = parent
        h_layout = QHBoxLayout()
        self.setLayout(h_layout)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)

        et_version = importlib_metadata.version("acconeer-exptool")
        et_version_text = f"ET: {et_version}"
        et_version_label = QLabel(et_version_text, self)
        h_layout.addWidget(et_version_label)

        def version_check(et_version: str) -> None:
            version_outdated, latest_v = check_package_outdated("acconeer-exptool", et_version)
            self.changelog = None

            if version_outdated:
                self.changelog = get_latest_changelog()
                self.setStyleSheet(
                    "QWidget{background-color: %s ; color: #e2e2e2}"
                    "QToolTip{ background-color: #e2e2e2 ; color: #4d5157}" % BUTTON_ICON_COLOR
                )

                self.setToolTip(
                    "There is a new software version available!\n "
                    f"The latest version is: {latest_v}. \n"
                    "Click to view changelog."
                )
                self.sig_version_outdated.emit()
                self.mousePressEvent = self._toggle_changelog

        self.sig_version_outdated.connect(self._create_changelog_window)
        self.sig_version_outdated.connect(lambda: self._add_icon_to_version_label(self))

        version_thread = threading.Thread(target=lambda: version_check(et_version))
        version_thread.start()

    def _create_changelog_window(self) -> None:
        if self.changelog is not None:
            self.cl_window = ChangelogWindow(self)
            self.cl_window.set_text(self.changelog)

    def _add_icon_to_version_label(self, version_widget: QWidget) -> None:
        layout = version_widget.layout()
        icon_widget = qta.IconWidget()
        icon_widget.setIcon(qta.icon("fa.refresh", color="#e2e2e2"))
        layout.addWidget(icon_widget)

    def _toggle_changelog(self, label: QLabel) -> None:
        if self.changelog is not None:
            self.cl_window.setVisible(not self.cl_window.isVisible())

    def paintEvent(self, pe):
        o = QStyleOption()
        o.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, o, p, self)


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.parent = parent

        app_model.sig_notify.connect(self._on_app_model_update)
        app_model.sig_status_message.connect(self._on_app_model_status_message)

        self.message_timer = QtCore.QTimer(self)
        self.message_timer.setInterval(3000)
        self.message_timer.setSingleShot(True)
        self.message_timer.timeout.connect(self._on_timer)

        self.message_widget = QLabel(self)
        self.addWidget(self.message_widget)

        self.addPermanentWidget(RateStatsLabel(app_model, self))
        self.addPermanentWidget(JitterStatsLabel(app_model, self))
        self.addPermanentWidget(BackendCPUPercentLabel(app_model, self))

        self.rss_version_label = QLabel(self)
        self.addPermanentWidget(self.rss_version_label)

        self.addPermanentWidget(VersionLabel(app_model, self))

        font_families = [
            "Consolas",  # Windows
            "Droid Sans Mono",  # Ubuntu
            "DejaVu Sans Mono",  # Ubuntu, backup
            "SF Mono",  # Mac
        ]
        font_family = ", ".join(f'"{ff}"' for ff in font_families)
        self.setStyleSheet(f"font-family: {font_family};")

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.rss_version is None:
            css = "color: #888;"
            text = "RSS: <not connected>"
        else:
            css = ""
            text = f"RSS: {app_model.rss_version}"

        self.rss_version_label.setStyleSheet(css)
        self.rss_version_label.setText(text)

    def _on_app_model_status_message(self, message: Optional[str]) -> None:
        self.message_timer.stop()

        if message:
            self.message_widget.setText(message)
            self.message_timer.start()
        else:
            self.message_widget.clear()

    def _on_timer(self) -> None:
        self.message_widget.clear()


class ChangelogWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()

        self.setWindowTitle("Changelog")
        self.text_browser = QTextBrowser()
        self.setCentralWidget(self.text_browser)
        self.set_center(parent.parent.parent)
        self.showEvent = lambda _: self.set_center(parent.parent.parent)

    def set_text(self, text: str) -> None:
        document = QTextDocument()
        document.setHtml(text)
        self.text_browser.setDocument(document)

    def set_center(self, main_window):
        fg = self.frameGeometry()
        fg.moveCenter(main_window.geometry().center())
        self.move(fg.topLeft())
        self.resize(500, 400)
