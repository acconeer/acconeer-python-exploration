# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Generic, Optional, TypeVar

import pyqtgraph as pg

from acconeer.exptool.app.new import (
    AppModel,
    BackendPlugin,
    GeneralMessage,
    PlotPluginBase,
    ViewPluginBase,
)


log = logging.getLogger(__name__)


T = TypeVar("T")


class A121BackendPluginBase(Generic[T], BackendPlugin[T]):
    pass


class A121ViewPluginBase(ViewPluginBase):
    pass


class A121PlotPluginBase(PlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        self._is_setup = False
        self._plot_job: Optional[GeneralMessage] = None

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "setup":
            self.plot_layout.clear()
            self.setup_from_message(message)
            self._is_setup = True
        elif message.name == "plot":
            self._plot_job = message
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.update_from_message(self._plot_job)
        finally:
            self._plot_job = None

    @abc.abstractmethod
    def setup_from_message(self, message: GeneralMessage) -> None:
        pass

    @abc.abstractmethod
    def update_from_message(self, message: GeneralMessage) -> None:
        pass
