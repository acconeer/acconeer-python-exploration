# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import typing as t

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel, PlotPluginInterface
from acconeer.exptool.app.new.backend import GeneralMessage


class PlotPluginBase(abc.ABC, PlotPluginInterface):
    def __init__(self, app_model: AppModel, plot_layout: pg.GraphicsLayout) -> None:
        self.plot_layout = plot_layout
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
        pass

    @abc.abstractmethod
    def draw(self) -> None:
        pass
