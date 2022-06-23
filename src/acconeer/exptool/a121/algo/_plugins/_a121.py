from __future__ import annotations

import abc
import logging
from typing import Generic, Optional, TypeVar

import pyqtgraph as pg

from acconeer.exptool.app.new import AppModel, BackendPlugin, Message, PlotPlugin, ViewPlugin


log = logging.getLogger(__name__)


T = TypeVar("T")


class A121BackendPluginBase(Generic[T], BackendPlugin[T]):
    pass


class A121ViewPluginBase(ViewPlugin):
    pass


class A121PlotPluginBase(PlotPlugin):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        self._is_setup = False
        self._plot_job: Optional[Message] = None

    def handle_message(self, message: Message) -> None:
        if message.command_name == "setup":
            self.plot_layout.clear()
            self.setup_from_message(message)
            self._is_setup = True
        elif message.command_name == "plot":
            self._plot_job = message
        else:
            log.warn(
                f"{self.__class__.__name__} got an unsupported command: {message.command_name!r}."
            )

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        self.update_from_message(self._plot_job)
        self._plot_job = None

    @abc.abstractmethod
    def setup_from_message(self, message: Message) -> None:
        pass

    @abc.abstractmethod
    def update_from_message(self, message: Message) -> None:
        pass
