# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import abc
import logging
from typing import Dict, Generic, List

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._base import MetadataT, ResultT
from acconeer.exptool.app.new import PgPlotPlugin


log = logging.getLogger(__name__)


class GenericProcessorPlotPluginBase(PgPlotPlugin, Generic[ResultT, MetadataT]):
    @abc.abstractmethod
    def setup(self, metadata: MetadataT, sensor_config: a121.SensorConfig) -> None:
        pass

    @abc.abstractmethod
    def draw_plot_job(self, processor_result: ResultT) -> None:
        pass


ProcessorPlotPluginBase = GenericProcessorPlotPluginBase[ResultT, a121.Metadata]
ExtendedProcessorPlotPluginBase = GenericProcessorPlotPluginBase[
    ResultT, List[Dict[int, a121.Metadata]]
]
