# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QSplitter, QVBoxLayout, QWidget

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.flash_tab import FlashButton
from acconeer.exptool.app.new.ui.misc import VerticalSeparator

from .connection_widget import ClientConnectionWidget, GenerationSelection
from .hints import HintWidget
from .plugin_widget import PluginControlArea, PluginPlotArea, PluginSelectionArea
from .recording_widget import RecordingWidget


class StreamingMainWidget(QWidget):
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
        self.layout().addWidget(HintWidget(app_model, self))
        self.layout().addStretch(1)
        self.layout().addWidget(RecordingWidget(app_model, self))


class WorkingArea(QSplitter):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        left_area = PluginSelectionArea(app_model, self)
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
