# Copyright (c) Acconeer AB, 2024
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

import acconeer.exptool.a121.algo.waste_level as wl
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.waste_level._processor import _load_algo_data


@attrs.frozen
class ResultSlice:
    level_m: t.Optional[float]
    level_percent: t.Optional[int]
    # omits extra_result

    @classmethod
    def from_processor_result(cls, processor_result: wl.ProcessorResult) -> te.Self:
        return cls(
            level_m=processor_result.level_m,
            level_percent=processor_result.level_percent,
        )


@attrs.mutable
class ProcessorWrapper:
    processor: wl.Processor

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


def waste_level_processor(record: a121.H5Record) -> ProcessorWrapper:
    algo_group = record.get_algo_group("waste_level")
    processor_config = _load_algo_data(algo_group)

    processor = wl.Processor(
        sensor_config=record.session_config.sensor_config,
        metadata=record.metadata,
        processor_config=processor_config,
    )
    return ProcessorWrapper(processor)
