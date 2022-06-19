from __future__ import annotations

import abc
import logging
from typing import Callable, Generic, TypeVar

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    AppModel,
    BackendPlugin,
    KwargMessage,
    Message,
    PlotPlugin,
    ViewPlugin,
)


ResultT = TypeVar("ResultT")

log = logging.getLogger(__name__)


class NullAppModel(AppModel):
    class _NullSignal:
        def connect(self, slot: Callable) -> None:
            pass

    sig_notify: _NullSignal
    sig_error: _NullSignal
    sig_message_plot_plugin: _NullSignal

    def __init__(self) -> None:
        self.sig_notify = self._NullSignal()
        self.sig_error = self._NullSignal()
        self.sig_message_plot_plugin = self._NullSignal()


class DetectorBackendPluginBase(BackendPlugin):
    pass


class DetectorPlotPluginBase(PlotPlugin):
    pass


class DetectorViewPluginBase(ViewPlugin):
    pass


class ProcessorBackendPluginBase(BackendPlugin):
    pass


class ProcessorPlotPluginBase(Generic[ResultT], PlotPlugin):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        self._is_setup = False
        self._plot_job = None

    def handle_message(self, message: Message) -> None:
        if message.command_name == "setup":
            assert isinstance(message, KwargMessage)
            self.plot_layout.clear()
            self.setup(**message.kwargs)
            self._is_setup = True
        elif message.command_name == "plot":
            self._plot_job = message.data
        else:
            log.warn(
                f"{self.__class__.__name__} got an unsupported command: {message.command_name!r}."
            )

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        self.update(self._plot_job)
        self._plot_job = None

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_app_model_error(self, exception: Exception) -> None:
        pass

    @abc.abstractmethod
    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        pass

    @abc.abstractmethod
    def update(self, processor_result: ResultT) -> None:
        pass


class ProcessorViewPluginBase(ViewPlugin):
    pass
