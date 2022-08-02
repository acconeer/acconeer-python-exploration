from __future__ import annotations

import abc
import logging
from typing import Generic, TypeVar

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins._a121 import A121PlotPluginBase
from acconeer.exptool.app.new import AppModel, GeneralMessage


ResultT = TypeVar("ResultT")

log = logging.getLogger(__name__)


class ProcessorPlotPluginBase(Generic[ResultT], A121PlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        self.update(message.data)  # type: ignore[arg-type]

    @abc.abstractmethod
    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        pass

    @abc.abstractmethod
    def update(self, processor_result: ResultT) -> None:
        pass
