from __future__ import annotations

import abc
from typing import Any

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new import plugin


class DetectorBackendPluginBase(plugin.BackendPlugin):
    pass


class DetectorPlotPluginBase(plugin.PlotPlugin):
    pass


class DetectorViewPluginBase(plugin.ViewPlugin):
    pass


class ProcessorBackendPluginBase(plugin.BackendPlugin):
    pass


class ProcessorPlotPluginBase(plugin.PlotPlugin):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        parent: pg.GraphicsLayout,
    ) -> None:
        pass

    @abc.abstractmethod
    def update(self, processor_result: Any) -> None:
        pass


class ProcessorViewPluginBase(plugin.ViewPlugin):
    pass
