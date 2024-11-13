# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved
from __future__ import annotations

from typing import Any, Optional

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import touchless_button


@attrs.frozen
class ResultSlice:
    detection_close: Optional[bool] = attrs.field()
    detection_far: Optional[bool] = attrs.field()

    @classmethod
    def from_processor_result(cls, result: touchless_button.ProcessorResult) -> te.Self:
        def is_none_or_detection(
            x: Optional[touchless_button.RangeResult],
        ) -> Optional[bool]:
            return x.detection if x is not None else None

        return cls(
            detection_close=is_none_or_detection(result.close),
            detection_far=is_none_or_detection(result.far),
        )


@attrs.mutable
class ProcessorWrapper:
    processor: touchless_button.Processor

    def __getattr__(self, name: str) -> Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


def touchless_button_processor(record: a121.H5Record) -> ProcessorWrapper:
    algo_group = record.get_algo_group("touchless_button")
    processor_config = touchless_button.ProcessorConfig.from_json(
        algo_group["processor_config"][()]
    )
    return ProcessorWrapper(
        touchless_button.Processor(
            sensor_config=record.session_config.sensor_config,
            processor_config=processor_config,
            metadata=utils.unextend(record.extended_metadata),
        )
    )
