# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.ui.icons import BUTTON_ICON_COLOR, FULLSCREEN, FULLSCREEN_EXIT
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

        self.working_area = WorkingArea(app_model, self)
        layout.addWidget(self.working_area)
        layout.setStretchFactor(self.working_area, 1)

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

        self._is_fullscreen = False

        layout = QHBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._left_area = PluginSelectionArea(app_model, self)
        self._left_area.setMinimumWidth(250)
        self._left_area.setMaximumWidth(350)
        layout.addWidget(self._left_area)
        layout.setStretchFactor(self._left_area, 0)

        plugin_layout = QVBoxLayout()

        self._fullscreen_btn = QPushButton()
        self._fullscreen_btn.setIcon(FULLSCREEN())
        self._fullscreen_btn.setFixedSize(30, 30)
        self._fullscreen_btn.setIconSize(QSize(20, 20))
        self._fullscreen_btn.setFlat(True)
        self._fullscreen_btn.setToolTip("Toggle fullscreen")
        self._fullscreen_btn.clicked.connect(self._toggle_fullscreen)

        left_spacer = QWidget()
        left_spacer.setFixedSize(30, 30)

        plugin_label = PluginTitleLabel(app_model, self)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.addWidget(left_spacer)
        title_row.addWidget(plugin_label, stretch=1)
        title_row.addWidget(self._fullscreen_btn)
        plugin_layout.addLayout(title_row)

        self._plot_plugin_area = PluginPlotArea(app_model, self)
        plugin_layout.addWidget(self._plot_plugin_area)
        plugin_layout.setStretchFactor(self._plot_plugin_area, 1)

        plot_layout_wrapper = LayoutWrapper(plugin_layout)
        layout.addWidget(plot_layout_wrapper)
        layout.setStretchFactor(plot_layout_wrapper, 1)

        self._right_area = PluginControlArea(app_model, self)
        self._right_area.setMinimumWidth(400)
        self._right_area.setMaximumWidth(450)
        layout.addWidget(self._right_area)
        layout.setStretchFactor(self._right_area, 0)

        self.setLayout(layout)

    def _toggle_fullscreen(self) -> None:
        self._is_fullscreen = not self._is_fullscreen
        self._left_area.setVisible(not self._is_fullscreen)
        self._right_area.setVisible(not self._is_fullscreen)
        self._fullscreen_btn.setIcon(FULLSCREEN_EXIT() if self._is_fullscreen else FULLSCREEN())
        if self._is_fullscreen:
            self.window().showFullScreen()
        else:
            self.window().showNormal()

    def exit_fullscreen(self) -> None:
        if self._is_fullscreen:
            self._toggle_fullscreen()
