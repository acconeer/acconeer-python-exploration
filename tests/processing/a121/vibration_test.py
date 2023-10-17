# Copyright (c) Acconeer AB, 2023
# All rights reserved


import math
from typing import Any, Optional

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import vibration
from acconeer.exptool.a121.algo.vibration._processor import _load_algo_data


@attrs.frozen
class ResultSlice:
    max_psd_ampl: Optional[float] = attrs.field()
    max_psd_ampl_freq: Optional[float] = attrs.field()

    @classmethod
    def from_processor_result(cls, result: vibration.ProcessorResult) -> te.Self:
        return cls(
            max_psd_ampl=result.max_psd_ampl,
            max_psd_ampl_freq=result.max_psd_ampl_freq,
        )

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            # Handle NoneType values
            equality = (
                self.max_psd_ampl == other.max_psd_ampl
                and self.max_psd_ampl_freq == other.max_psd_ampl_freq
            )

            if not equality:
                # Handle real values
                equality = math.isclose(
                    self.max_psd_ampl, other.max_psd_ampl, rel_tol=1e-9
                ) and math.isclose(self.max_psd_ampl_freq, other.max_psd_ampl_freq, rel_tol=1e-9)

            return equality
        else:
            return False


@attrs.mutable
class ProcessorWrapper:
    processor: vibration.Processor

    def __getattr__(self, name: str) -> Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


def vibration_controller(record: a121.H5Record) -> ProcessorWrapper:
    algo_group = record.get_algo_group("vibration")
    processor_config = _load_algo_data(algo_group)
    return ProcessorWrapper(
        vibration.Processor(
            sensor_config=record.session_config.sensor_config,
            metadata=utils.unextend(record.extended_metadata),
            processor_config=processor_config,
        )
    )
