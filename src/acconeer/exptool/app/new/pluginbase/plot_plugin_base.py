# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel, PlotPluginInterface
from acconeer.exptool.app.new.backend import GeneralMessage

from .ui_plugin_base import UiPluginBase


class PlotPluginBase(UiPluginBase, abc.ABC, PlotPluginInterface):
    def __init__(self, app_model: AppModel, plot_layout: pg.GraphicsLayout) -> None:
        super().__init__(app_model)

        self.__app_model = app_model
        self.__app_model.sig_message_plot_plugin.connect(self.handle_message)

        self.plot_layout = plot_layout

    def stop_listening(self) -> None:
        super().stop_listening()
        self.__app_model.sig_message_plot_plugin.disconnect(self.handle_message)

    @abc.abstractmethod
    def handle_message(self, message: GeneralMessage) -> None:
        pass

    @abc.abstractmethod
    def draw(self) -> None:
        pass
