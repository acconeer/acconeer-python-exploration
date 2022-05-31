from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool import a121
from acconeer.exptool.a121 import algo


class DistanceProcessorConfig:
    pass


@attrs.frozen(kw_only=True)
class DistanceProcessorContext:
    pass  # e.g. calibration, background measurement


@attrs.frozen(kw_only=True)
class DistanceProcessorResult:
    distance: Optional[float] = attrs.field()


class DistanceProcessor(algo.Processor[DistanceProcessorConfig, DistanceProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: DistanceProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[DistanceProcessorContext] = None,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_indexes = subsweep_indexes
        self.context = context

    def process(self, result: a121.Result) -> DistanceProcessorResult:
        ...

    def update_config(self, config: DistanceProcessorConfig) -> None:
        ...
