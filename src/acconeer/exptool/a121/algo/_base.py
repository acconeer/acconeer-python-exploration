from __future__ import annotations

import abc
from typing import Generic, TypeVar

from acconeer.exptool import a121


ConfigT = TypeVar("ConfigT")
ResultT = TypeVar("ResultT")


# TODO: Here we assume that the processor handles a single config entry, but that assumption
# cannot be made in general. Maybe we need different variants?


class ProcessorBase(abc.ABC, Generic[ConfigT, ResultT]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ConfigT,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config

    @abc.abstractmethod
    def process(self, result: a121.Result) -> ResultT:
        ...

    @abc.abstractmethod
    def update_config(self, config: ConfigT) -> None:
        ...
