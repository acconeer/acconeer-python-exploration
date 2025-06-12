# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import abc
import logging
import typing as t

from PySide6.QtWidgets import QVBoxLayout

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.backend import GeneralMessage

from .ui_plugin_base import UiPluginBase


log = logging.getLogger(__name__)


class PlotPluginBase(UiPluginBase):
    """
    A basic widget with the following signals connected:

    AppModel signal -> method
    --------------------------------------
    sig_notify -> on_app_model_update (no-op hook)
    sig_load_plugin -> on_load_plugin
    sig_message_plot_plugin -> handle_message
    sig_backend_state_changed -> on_backend_state_update (no-op hook)
    """

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        self.app_model = app_model

        self.app_model.sig_message_plot_plugin.connect(self.handle_message)
        self.app_model.sig_notify.connect(self.on_app_model_update)
        self.app_model.sig_backend_state_changed.connect(self.on_backend_state_update)
        self.app_model.sig_load_plugin.connect(self.on_load_plugin)

    def on_load_plugin(self, plugin_spec: t.Optional[t.Any]) -> None:
        if plugin_spec is None:
            self.app_model.sig_message_plot_plugin.disconnect(self.handle_message)
            self.app_model.sig_notify.disconnect(self.on_app_model_update)
            self.app_model.sig_backend_state_changed.disconnect(self.on_backend_state_update)
            self.app_model.sig_load_plugin.disconnect(self.on_load_plugin)

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_backend_state_update(self, state: t.Optional[t.Any]) -> None:
        pass

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        """Handles messages with recipient=="plot_plugin" from the BackendPlugin"""
        pass

    @abc.abstractmethod
    def draw(self) -> None:
        """Gets called with a set frequency (see PluginPlotArea)"""
        pass


# def handle_message(self, message: GeneralMessage) -> None:
#     if message.kwargs is None:
#         raise RuntimeError("Plot message needs non-None kwargs")

#     if message.name == "setup":
#         self.setup(**message.kwargs)
#         self._is_setup = True
#     elif message.name == "plot":
#         self._plot_job = message.kwargs
#     else:
#         log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

# def draw(self) -> None:
#     if not self._is_setup or self._plot_job is None:
#         return

#     try:
#         self.draw_plot_job(**self._plot_job)
#     finally:
#         self._plot_job = None


class PgPlotPlugin(PlotPluginBase):
    """
    Expands PlotPluginBase by adding a pyqtgraph GraphicsLayout
    to the widget. The GraphicsLayout is accessible via the
    plot_layout attribute
    """

    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model=app_model)

        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_layout = self.plot_widget.ci

        layout = QVBoxLayout()

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

        self.setLayout(layout)
