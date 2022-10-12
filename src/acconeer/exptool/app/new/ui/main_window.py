# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import importlib_metadata
import numpy as np

from PySide6 import QtCore
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new.app_model import AppModel

from .connection_widget import ClientConnectionWidget, GenerationSelection
from .flash_widget import FlashButton
from .misc import ConnectionHint, ExceptionWidget, VerticalSeparator
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
    _FPS: int = 60

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setToolTip("Reported update rate / jitter")

        self.rate = np.nan
        self.rate_warning = False
        self.jitter = np.nan
        self.jitter_warning = False

        self.startTimer(int(1000 / self._FPS))

        app_model.sig_rate_stats.connect(self._on_app_model_rate_stats)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if np.isnan(self.rate) or np.isnan(self.jitter):
            css = "color: #888;"
            text = "- Hz / - ms"
        else:
            css = ""

            WARNING_STYLE = "color: #FD5200;"
            rate_style = WARNING_STYLE if self.rate_warning else ""
            jitter_style = WARNING_STYLE if self.jitter_warning else ""
            text = (
                f'<span style="{rate_style}">{self.rate:>6.1f} Hz</span>'
                " / "
                f'<span style="{jitter_style}">{self.jitter * 1e3:5.1f} ms</span>'
            )

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
        self.jitter = jitter
        self.jitter_warning = jitter_warning


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        app_model.sig_notify.connect(self._on_app_model_update)
        app_model.sig_status_message.connect(self._on_app_model_status_message)

        self.message_timer = QtCore.QTimer(self)
        self.message_timer.setInterval(3000)
        self.message_timer.setSingleShot(True)
        self.message_timer.timeout.connect(self._on_timer)

        self.message_widget = QLabel(self)
        self.addWidget(self.message_widget)

        self.addPermanentWidget(RateStatsLabel(app_model, self))

        self.rss_version_label = QLabel(self)
        self.addPermanentWidget(self.rss_version_label)

        et_version = importlib_metadata.version("acconeer-exptool")
        et_version_text = f"ET: {et_version}"
        self.addPermanentWidget(QLabel(et_version_text, self))

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
