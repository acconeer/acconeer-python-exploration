# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.icons import BUTTON_ICON_COLOR
from acconeer.exptool.app.new.ui.misc import VerticalSeparator
from acconeer.exptool.app.new.ui.utils import LayoutWrapper

from .connection_widget import ClientConnectionWidget, GenerationSelection
from .hints import HintWidget
from .plugin_widget import PluginControlArea, PluginPlotArea, PluginSelectionArea
from .recording_widget import RecordingWidget


class StreamingMainWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = TopBar(app_model, self)
        layout.addWidget(top_bar)
        layout.setStretchFactor(top_bar, 0)

        working_area = WorkingArea(app_model, self)
        layout.addWidget(working_area)
        layout.setStretchFactor(working_area, 1)

        self.setLayout(layout)


class TopBar(QFrame):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setObjectName("TopBar")
        self.setStyleSheet("QFrame#TopBar {background: #ebebeb;}")

        layout = QHBoxLayout(self)

        layout.addWidget(GenerationSelection(app_model, self))
        layout.addWidget(VerticalSeparator(self))
        layout.addWidget(ClientConnectionWidget(app_model, self))
        layout.addWidget(HintWidget(app_model, self))
        layout.addStretch(1)
        layout.addWidget(RecordingWidget(app_model, self))

        self.setLayout(layout)


class PluginTitleLabel(QLabel):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__("", parent)

        self.setStyleSheet(f"color: {BUTTON_ICON_COLOR}; text-align: center; font-weight: bold;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_model.sig_notify.connect(self.on_app_model_update)

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.setText(app_model.plugin.title if app_model.plugin is not None else "")


class WorkingArea(QSplitter):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        left_area = PluginSelectionArea(app_model, self)
        left_area.setMinimumWidth(250)
        left_area.setMaximumWidth(350)
        layout.addWidget(left_area)
        layout.setStretchFactor(left_area, 0)

        plugin_layout = QVBoxLayout()

        plugin_label = PluginTitleLabel(app_model, self)
        plugin_layout.addWidget(plugin_label)
        plugin_layout.setStretchFactor(plugin_label, 0)

        plot_plugin_area = PluginPlotArea(app_model, self)
        plugin_layout.addWidget(plot_plugin_area)
        plugin_layout.setStretchFactor(plot_plugin_area, 1)

        plot_layout_wrapper = LayoutWrapper(plugin_layout)
        layout.addWidget(plot_layout_wrapper)
        layout.setStretchFactor(plot_layout_wrapper, 1)

        right_area = PluginControlArea(app_model, self)
        right_area.setMinimumWidth(400)
        right_area.setMaximumWidth(450)
        layout.addWidget(right_area)
        layout.setStretchFactor(right_area, 0)

        self.setLayout(layout)
