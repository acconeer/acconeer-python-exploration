# Copyright (c) Acconeer AB, 2023
# All rights reserved


import math
from typing import Any

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import surface_velocity
from acconeer.exptool.a121.algo.surface_velocity._example_app import ExampleApp, _load_algo_data


@attrs.frozen
class ResultSlice:
    estimated_v: float = attrs.field()
    distance_m: float = attrs.field()

    @classmethod
    def from_processor_result(cls, result: surface_velocity.ProcessorResult) -> te.Self:
        return cls(
            estimated_v=result.estimated_v,
            distance_m=result.distance_m,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return math.isclose(
                self.estimated_v, other.estimated_v, rel_tol=1e-9
            ) and math.isclose(self.distance_m, other.distance_m, rel_tol=1e-9)
        else:
            return False


@attrs.mutable
class ProcessorWrapper:
    processor: surface_velocity.Processor

    def __getattr__(self, name: str) -> Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


def surface_velocity_controller(record: a121.H5Record) -> ProcessorWrapper:
    algo_group = record.get_algo_group("surface_velocity")
    _, config = _load_algo_data(algo_group)
    processor_config = ExampleApp._get_processor_config(config)
    return ProcessorWrapper(
        surface_velocity.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=processor_config,
            metadata=utils.unextend(record.extended_metadata),
        )
    )
