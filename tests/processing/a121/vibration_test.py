# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import math
from typing import Any, Optional

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import (
    attrs_ndarray_isclose,
)
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121.algo import vibration
from acconeer.exptool.a121.algo.vibration._example_app import ExampleApp, _load_algo_data


@attrs.frozen
class ResultSlice:
    _REL_TOL = 1e-9

    max_displacement: Optional[float] = attrs.field()
    max_displacement_freq: Optional[float] = attrs.field()
    max_sweep_amplitude: float
    lp_displacements: Optional[npt.NDArray[np.float64]] = attrs.field(eq=attrs_ndarray_isclose)
    lp_displacements_freqs: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    time_series_std: Optional[float] = attrs.field()

    @classmethod
    def from_processor_result(cls, result: vibration.ExampleAppResult) -> te.Self:
        return cls(
            max_displacement=result.max_displacement,
            max_displacement_freq=result.max_displacement_freq,
            max_sweep_amplitude=result.max_sweep_amplitude,
            lp_displacements=result.lp_displacements,
            lp_displacements_freqs=result.lp_displacements_freqs,
            time_series_std=result.time_series_std,
        )

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False

        if other.max_displacement is None:
            # Handle NoneType values
            return math.isclose(
                self.max_sweep_amplitude, other.max_sweep_amplitude, rel_tol=self._REL_TOL
            ) and math.isclose(self.time_series_std, other.time_series_std, rel_tol=self._REL_TOL)

        return (
            math.isclose(
                self.max_sweep_amplitude, other.max_sweep_amplitude, rel_tol=self._REL_TOL
            )
            and math.isclose(self.max_displacement, other.max_displacement, rel_tol=self._REL_TOL)
            and math.isclose(
                self.max_displacement_freq, other.max_displacement_freq, rel_tol=self._REL_TOL
            )
            and math.isclose(self.time_series_std, other.time_series_std, rel_tol=self._REL_TOL)
            and np.allclose(self.lp_displacements, other.lp_displacements, rtol=self._REL_TOL)
            and np.allclose(
                self.lp_displacements_freqs, other.lp_displacements_freqs, rtol=self._REL_TOL
            )
        )


@attrs.mutable
class ProcessorWrapper:
    processor: vibration.Processor

    def __getattr__(self, name: str) -> Any:
        return getattr(self.processor, name)

    def process(self, result: a121.Result) -> ResultSlice:
        return ResultSlice.from_processor_result(self.processor.process(result))


def vibration_controller(record: a121.H5Record) -> ProcessorWrapper:
    algo_group = record.get_algo_group("vibration")
    _, config = _load_algo_data(algo_group)
    processor_config = ExampleApp._get_processor_config(config)
    return ProcessorWrapper(
        vibration.Processor(
            sensor_config=record.session_config.sensor_config,
            metadata=utils.unextend(record.extended_metadata),
            processor_config=processor_config,
        )
    )
